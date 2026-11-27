"""
Quản lý cài đặt, cập nhật, sao lưu Smart Live Backup (.tar.zst / .zip) và tối ưu dependencies cho Custom Nodes.
"""

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from .config import (
    CONFIG_DIR,
    DEFAULT_COMFYUI_DIR,
    DEFAULT_DRIVE_DATA_DIR,
    PROTECTED_PACKAGES,
)
from .environment import get_pytorch_cuda_index_url
from .patches import patch_vhs_loadvideo
from .storage import cleanup_duplicate_encoded_files

_PRINT_LOCK = threading.Lock()
_EXCLUDED_BACKUP_DIRS = {
    ".git", "__pycache__", ".pytest_cache", ".venv", "venv",
    "node_modules", ".mypy_cache", ".ruff_cache",
}
_MAX_BACKUP_FILE_BYTES = 50 * 1024 * 1024  # 50 MB: tránh nhầm model weights vào backup code


def load_default_nodes():
    """Nạp danh sách Custom Nodes từ tệp json config."""
    config_file = os.path.join(CONFIG_DIR, "custom_nodes.json")
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "core_nodes": [
            {"name": "ComfyUI-Manager", "url": "https://github.com/ltdrdata/ComfyUI-Manager.git"},
            {"name": "ComfyUI-Impact-Pack", "url": "https://github.com/ltdrdata/ComfyUI-Impact-Pack.git"},
            {"name": "ComfyUI-Crystools", "url": "https://github.com/crystian/ComfyUI-Crystools.git"},
            {"name": "ComfyUI-Pixaroma", "url": "https://github.com/pixaroma/comfyui-pixaroma.git"},
            {"name": "rgthree-comfy", "url": "https://github.com/rgthree/rgthree-comfy.git"},
            {"name": "ComfyUI-SeedVR2_VideoUpscaler", "url": "https://github.com/numz/ComfyUI-SeedVR2_VideoUpscaler.git"},
            {"name": "ComfyUI-Krea2T-Enhancer", "url": "https://github.com/capitan01R/ComfyUI-Krea2T-Enhancer.git"},
            {"name": "comfyui-krea2edit", "url": "https://github.com/lbouaraba/comfyui-krea2edit.git"},
            {"name": "ComfyUI-Apt_Preset", "url": "https://github.com/cardenluo/ComfyUI-Apt_Preset.git"},
            {"name": "ComfyUI_Swwan", "url": "https://github.com/aining2022/ComfyUI_Swwan.git"},
            {"name": "ComfyUI-VideoHelperSuite", "url": "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git"},
            {"name": "ComfyUI-AnimateDiff-Evolved", "url": "https://github.com/Kosinkadink/ComfyUI-AnimateDiff-Evolved.git"},
            {"name": "ComfyUI-Advanced-ControlNet", "url": "https://github.com/Kosinkadink/ComfyUI-Advanced-ControlNet.git"},
            {"name": "ComfyUI-Video-Depth-Anything", "url": "https://github.com/yuvraj108c/ComfyUI-Video-Depth-Anything.git"},
            {"name": "ComfyUI-IPAdapter_plus", "url": "https://github.com/cubiq/ComfyUI_IPAdapter_plus.git"},
            {"name": "comfyui_controlnet_aux", "url": "https://github.com/Fannovel16/comfyui_controlnet_aux.git"},
            {"name": "ComfyUI-Inspyrenet-Rembg", "url": "https://github.com/john-mnz/ComfyUI-Inspyrenet-Rembg.git"},
        ],
        "video_nodes": [
            {"name": "ComfyUI-KJNodes", "url": "https://github.com/kijai/ComfyUI-KJNodes.git"},
            {"name": "ComfyUI-H3-Motion-Context", "url": "https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context.git"},
            {"name": "ComfyUI-Abhash", "url": "https://github.com/abhash0000/ComfyUI-Abhash.git"},
            {"name": "ComfyUI-MiniMaxH3-Easy", "url": "https://github.com/nkxx188/ComfyUI-MiniMaxH3-Easy.git"},
        ],
    }


def _supports_zstd():
    """Kiểm tra hệ thống có sẵn zstd để nén/giải nén đa luồng qua tarfile stream hay không."""
    return bool(shutil.which("zstd"))


def _safe_extract_tar_stream(fileobj, dest_dir):
    """Giải nén tar stream an toàn chống path traversal (tar-slip)."""
    dest_real = os.path.realpath(dest_dir)
    extract_kwargs = {"path": dest_real}
    if sys.version_info >= (3, 12):
        extract_kwargs["filter"] = "data"
    with tarfile.open(fileobj=fileobj, mode="r|") as tf:
        for member in tf:
            target = os.path.realpath(os.path.join(dest_real, member.name))
            if os.path.commonpath([dest_real, target]) != dest_real:
                continue
            tf.extract(member, **extract_kwargs)


def _get_preferred_backup_path(backup_dir):
    if _supports_zstd():
        return os.path.join(backup_dir, "custom_nodes_backup.tar.zst")
    return os.path.join(backup_dir, "custom_nodes_backup.zip")


def restore_custom_nodes_backup(drive_data_dir, custom_nodes_dir, force_reinstall=False):
    """
    Khôi phục Custom Nodes siêu tốc từ file sao lưu Google Drive (.tar.zst hoặc .zip).
    """
    backup_dir = os.path.join(drive_data_dir, "backup")
    backup_zst = os.path.join(backup_dir, "custom_nodes_backup.tar.zst")
    backup_zip = os.path.join(backup_dir, "custom_nodes_backup.zip")
    preferred_backup = _get_preferred_backup_path(backup_dir)
    drive_custom_nodes_dir = os.path.join(drive_data_dir, "custom_nodes")
    os.makedirs(backup_dir, exist_ok=True)
    os.makedirs(custom_nodes_dir, exist_ok=True)

    if force_reinstall:
        print("  🧹 Phát hiện Force_Reinstall = True. Đang dọn dẹp thư mục Custom Nodes cũ...")
        if os.path.exists(custom_nodes_dir):
            shutil.rmtree(custom_nodes_dir)
        os.makedirs(custom_nodes_dir, exist_ok=True)
        return False, preferred_backup

    if os.path.exists(backup_zst) and _supports_zstd():
        size_mb = round(os.path.getsize(backup_zst) / (1024 * 1024), 1)
        print(f"  📦 Phát hiện bản sao lưu Zstandard trên Drive ({size_mb} MB). Đang giải nén siêu tốc...")
        try:
            proc = subprocess.Popen(
                ["zstd", "-dc", backup_zst],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            _safe_extract_tar_stream(proc.stdout, custom_nodes_dir)
            proc.stdout.close()
            stderr_bytes = proc.stderr.read()
            proc.stderr.close()
            if proc.wait() == 0:
                restored_count = len([d for d in os.listdir(custom_nodes_dir) if os.path.isdir(os.path.join(custom_nodes_dir, d))])
                print(f"  \033[92m✅ Đã khôi phục {restored_count} Custom Nodes từ .tar.zst chỉ trong vài giây!\033[0m")
                return True, preferred_backup
            raise RuntimeError(stderr_bytes.decode("utf-8", errors="ignore"))
        except Exception as e:
            print(f"  ⚠️ Lỗi giải nén .tar.zst ({e}), thử fallback sang .zip nếu có...")

    if os.path.exists(backup_zip):
        size_mb = round(os.path.getsize(backup_zip) / (1024 * 1024), 1)
        print(f"  📦 Phát hiện bản sao lưu Custom Nodes trên Drive ({size_mb} MB). Đang giải nén siêu tốc...")
        try:
            unzip_bin = shutil.which("unzip")
            if unzip_bin:
                res = subprocess.run(
                    [unzip_bin, "-q", "-o", backup_zip, "-d", custom_nodes_dir],
                    capture_output=True,
                    check=False,
                )
                if res.returncode != 0:
                    shutil.unpack_archive(backup_zip, custom_nodes_dir)
            else:
                shutil.unpack_archive(backup_zip, custom_nodes_dir)
            restored_count = len([d for d in os.listdir(custom_nodes_dir) if os.path.isdir(os.path.join(custom_nodes_dir, d))])
            print(f"  \033[92m✅ Đã khôi phục {restored_count} Custom Nodes từ bản sao lưu thành công chỉ trong vài giây!\033[0m")
            return True, preferred_backup
        except Exception as e:
            print(f"  ⚠️ Lỗi giải nén bản sao lưu: {e}")

    elif os.path.exists(drive_custom_nodes_dir):
        saved_nodes = [d for d in os.listdir(drive_custom_nodes_dir) if os.path.isdir(os.path.join(drive_custom_nodes_dir, d))]
        if saved_nodes:
            print(f"  📦 Phát hiện {len(saved_nodes)} Custom Nodes từ thư mục Drive cũ. Đang chuyển sang gói nén siêu tốc...")
            for sn in saved_nodes:
                src_node = os.path.join(drive_custom_nodes_dir, sn)
                dst_node = os.path.join(custom_nodes_dir, sn)
                if not os.path.exists(dst_node):
                    try:
                        shutil.copytree(src_node, dst_node, dirs_exist_ok=True)
                    except Exception:
                        pass
            return True, preferred_backup

    return False, preferred_backup


def _safe_print(msg):
    """In log an toàn khi chạy đa luồng."""
    with _PRINT_LOCK:
        print(msg)


def _get_git_head(repo_path):
    """Trả về commit hash hiện tại của repo git, hoặc chuỗi rỗng nếu chưa có."""
    res = subprocess.run(
        ["git", "-C", repo_path, "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return res.stdout.strip() if res.returncode == 0 else ""


def _get_git_remote_url(repo_path):
    res = subprocess.run(
        ["git", "-C", repo_path, "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
    )
    return res.stdout.strip() if res.returncode == 0 else ""


def _fetch_default_head(repo_path, fallback_url=None):
    """Fetch HEAD mặc định của upstream mà không hardcode nhánh main."""
    res = subprocess.run(
        ["git", "-C", repo_path, "fetch", "--depth", "1", "origin", "HEAD", "-q"],
        capture_output=True,
        check=False,
    )
    if res.returncode == 0:
        return True
    res = subprocess.run(
        ["git", "-C", repo_path, "fetch", "--depth", "1", "origin", "-q"],
        capture_output=True,
        check=False,
    )
    if res.returncode == 0:
        return True
    if fallback_url:
        subprocess.run(["git", "-C", repo_path, "remote", "set-url", "origin", fallback_url], capture_output=True, check=False)
        res = subprocess.run(
            ["git", "-C", repo_path, "fetch", "--depth", "1", "origin", "HEAD", "-q"],
            capture_output=True,
            check=False,
        )
        return res.returncode == 0
    return False


def ensure_pixaroma_latest(custom_nodes_dir, drive_default_workflows=None):
    """
    Đảm bảo ComfyUI-Pixaroma luôn ở phiên bản mới nhất và đầy đủ nhất:
    1. Tự động cập nhật / clone từ upstream chính thức (ưu tiên GitHub, fallback GitLab).
    2. Khôi phục Git tracking nếu node được phục hồi từ backup không có .git.
    3. Chỉ báo has_changed=True khi cài mới hoặc HEAD thay đổi thực sự.
    4. Đồng bộ an toàn workflow mẫu vào workflows/Pixaroma/ với SHA256 deduplication.
    """
    pixaroma_dir = os.path.join(custom_nodes_dir, "ComfyUI-Pixaroma")
    github_url = "https://github.com/pixaroma/comfyui-pixaroma.git"
    gitlab_url = "https://gitlab.com/pixaroma/comfyui-pixaroma.git"
    git_dir = os.path.join(pixaroma_dir, ".git")

    has_changed = False

    if not os.path.exists(pixaroma_dir):
        print("  📥 [Pixaroma] Đang cài đặt ComfyUI-Pixaroma bản mới nhất từ upstream...")
        res = subprocess.run(
            ["git", "clone", "--depth", "1", "-q", github_url, pixaroma_dir],
            capture_output=True,
            check=False,
        )
        if res.returncode != 0:
            res = subprocess.run(
                ["git", "clone", "--depth", "1", "-q", gitlab_url, pixaroma_dir],
                capture_output=True,
                check=False,
            )
        if res.returncode == 0:
            has_changed = True
            print("  ✅ [Pixaroma] Đã cài đặt thành công phiên bản mới nhất từ upstream.")
        else:
            print("  ⚠️ [Pixaroma] Không thể kết nối để clone Pixaroma.")
            return False

    elif not os.path.exists(git_dir):
        print("  🔄 [Pixaroma] Khôi phục Git tracking để tự động đồng bộ bản mới nhất...")
        try:
            subprocess.run(["git", "-C", pixaroma_dir, "init", "-q"], capture_output=True, check=False)
            subprocess.run(["git", "-C", pixaroma_dir, "remote", "add", "origin", github_url], capture_output=True, check=False)
            if _fetch_default_head(pixaroma_dir, fallback_url=gitlab_url):
                reset_res = subprocess.run(
                    ["git", "-C", pixaroma_dir, "reset", "--hard", "FETCH_HEAD", "-q"],
                    capture_output=True,
                    check=False,
                )
                if reset_res.returncode == 0:
                    has_changed = True
                    print("  ✅ [Pixaroma] Đã khôi phục tracking và cập nhật lên commit mới nhất thành công!")
        except Exception as e:
            print(f"  ⚠️ [Pixaroma] Ghi chú cập nhật git: {e}")

    else:
        try:
            old_head = _get_git_head(pixaroma_dir)
            if _fetch_default_head(pixaroma_dir, fallback_url=gitlab_url):
                reset_res = subprocess.run(
                    ["git", "-C", pixaroma_dir, "reset", "--hard", "FETCH_HEAD", "-q"],
                    capture_output=True,
                    check=False,
                )
                if reset_res.returncode == 0:
                    new_head = _get_git_head(pixaroma_dir)
                    if not old_head or (new_head and new_head != old_head):
                        has_changed = True
                        print("  ✅ [Pixaroma] Đã đồng bộ phiên bản mới nhất từ upstream.")
        except Exception as e:
            print(f"  ⚠️ [Pixaroma] Ghi chú cập nhật: {e}")

    if drive_default_workflows:
        os.makedirs(drive_default_workflows, exist_ok=True)
        target_pix_dir = os.path.join(drive_default_workflows, "Pixaroma")
        os.makedirs(target_pix_dir, exist_ok=True)

        src_wf_dir = os.path.join(pixaroma_dir, "workflows")
        if os.path.exists(src_wf_dir) and os.path.isdir(src_wf_dir):
            existing_hashes = set()
            existing_filenames = set()

            for root, _, files in os.walk(drive_default_workflows):
                for f in files:
                    if f.endswith(".json"):
                        fp = os.path.join(root, f)
                        try:
                            if os.path.getsize(fp) > 0:
                                existing_filenames.add(f.lower())
                                with open(fp, "rb") as jf:
                                    existing_hashes.add(hashlib.sha256(jf.read()).hexdigest())
                        except Exception:
                            pass

            synced_count = 0
            for item in os.listdir(src_wf_dir):
                if item.startswith(".") or item.endswith((".tmp", ".temp", ".bak")):
                    continue
                src_item = os.path.join(src_wf_dir, item)
                if not os.path.isfile(src_item):
                    continue

                dst_item = os.path.join(target_pix_dir, item)

                if item.endswith(".json"):
                    try:
                        with open(src_item, "rb") as f_in:
                            content = f_in.read()
                        h = hashlib.sha256(content).hexdigest()
                        if h in existing_hashes or item.lower() in existing_filenames:
                            continue
                        with open(dst_item, "wb") as f_out:
                            f_out.write(content)
                        existing_hashes.add(h)
                        existing_filenames.add(item.lower())
                        synced_count += 1

                        base_stem, _ = os.path.splitext(item)
                        for ext in (".jpg", ".jpeg", ".png", ".webp"):
                            thumb_src = os.path.join(src_wf_dir, f"{base_stem}{ext}")
                            thumb_dst = os.path.join(target_pix_dir, f"{base_stem}{ext}")
                            if os.path.exists(thumb_src) and not os.path.exists(thumb_dst):
                                try:
                                    shutil.copy2(thumb_src, thumb_dst)
                                except Exception:
                                    pass
                    except Exception:
                        pass

            if synced_count > 0:
                print(f"  🎨 [Pixaroma] Đã đồng bộ an toàn {synced_count} workflow mẫu mới nhất vào 'workflows/Pixaroma/' (Không trùng lặp)!")
            else:
                print("  🎨 [Pixaroma] Thư viện workflow mẫu đã đầy đủ và đồng bộ hoàn hảo (Không có file trùng lặp).")

        cleaned = cleanup_duplicate_encoded_files(drive_default_workflows)
        if cleaned > 0:
            print(f"  🧹 [Pixaroma] Đã dọn sạch {cleaned} tệp rác (%20, %2B, 0-byte) trong thư mục workflows.")

    return has_changed


def install_or_update_node(name, git_url, custom_nodes_dir, update_nodes=True, index=1, total=1):
    """Cài đặt hoặc cập nhật một Custom Node từ upstream chính thống."""
    if name == "ComfyUI-Pixaroma":
        _safe_print(f"  [{index}/{total}] 🚀 Tự động cập nhật ComfyUI-Pixaroma lên bản mới nhất...")
        return ensure_pixaroma_latest(custom_nodes_dir)

    node_path = os.path.join(custom_nodes_dir, name)
    has_new = False

    if not os.path.exists(node_path):
        _safe_print(f"  [{index}/{total}] 📥 Cloning {name}...")
        res = subprocess.run(
            ["git", "clone", "--depth", "1", "--no-tags", "-q", git_url, node_path],
            capture_output=True,
            check=False,
        )
        if res.returncode == 0:
            has_new = True
            _safe_print(f"  [{index}/{total}] ✅ {name} (Đã cài đặt thành công)")
        else:
            if os.path.exists(node_path):
                shutil.rmtree(node_path, ignore_errors=True)
            _safe_print(f"  [{index}/{total}] ⚠️ {name} (Không thể tải từ {git_url})")
    elif update_nodes:
        git_dir = os.path.join(node_path, ".git")
        if not os.path.exists(git_dir):
            try:
                subprocess.run(["git", "-C", node_path, "init", "-q"], capture_output=True, check=False)
                subprocess.run(["git", "-C", node_path, "remote", "add", "origin", git_url], capture_output=True, check=False)
                if _fetch_default_head(node_path):
                    subprocess.run(["git", "-C", node_path, "reset", "--hard", "FETCH_HEAD", "-q"], capture_output=True, check=False)
                    has_new = True
                    _safe_print(f"  [{index}/{total}] 🔄 {name} (Đã khôi phục tracking & cập nhật)")
            except Exception:
                pass
        else:
            try:
                old_head = _get_git_head(node_path)
                subprocess.run(["git", "-C", node_path, "remote", "set-url", "origin", git_url], capture_output=True, check=False)
                if _fetch_default_head(node_path):
                    subprocess.run(["git", "-C", node_path, "reset", "--hard", "FETCH_HEAD", "-q"], capture_output=True, check=False)
                    new_head = _get_git_head(node_path)
                    if new_head and new_head != old_head:
                        has_new = True
                        _safe_print(f"  [{index}/{total}] 🔄 {name} (Đã cập nhật phiên bản mới nhất)")
            except Exception:
                pass
    return has_new


def setup_all_custom_nodes(
    custom_nodes_dir,
    update_nodes=True,
    install_video_nodes=True,
    drive_default_workflows=None,
):
    """Cài đặt và đồng bộ song song toàn bộ Custom Nodes cần thiết."""
    nodes_config = load_default_nodes()
    core_nodes = nodes_config.get("core_nodes", [])
    video_nodes = nodes_config.get("video_nodes", [])

    all_target_nodes = list(core_nodes)
    if install_video_nodes:
        all_target_nodes.extend(video_nodes)

    has_any_new = False
    for deprecated_cs in ("ComfyUI-Custom-Scripts", "comfyui-custom-scripts"):
        cs_path = os.path.join(custom_nodes_dir, deprecated_cs)
        if os.path.exists(cs_path):
            try:
                shutil.rmtree(cs_path)
                has_any_new = True
                print(f"  🧹 Đã gỡ bỏ node cũ '{deprecated_cs}' (khỏi khôi phục từ backup).")
            except Exception:
                pass

    total = len(all_target_nodes)
    print(f"\n[6/10] 🧩 Kiểm tra và đồng bộ song song {total} Custom Nodes chính thống...")

    other_nodes = [(i, node) for i, node in enumerate(all_target_nodes, 1) if node["name"] != "ComfyUI-Pixaroma"]
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [
            executor.submit(
                install_or_update_node,
                node["name"],
                node["url"],
                custom_nodes_dir,
                update_nodes,
                i,
                total,
            )
            for i, node in other_nodes
        ]
        for fut in as_completed(futures):
            try:
                if fut.result():
                    has_any_new = True
            except Exception:
                pass

    if ensure_pixaroma_latest(custom_nodes_dir, drive_default_workflows=drive_default_workflows):
        has_any_new = True

    patch_vhs_loadvideo(custom_nodes_dir)
    return has_any_new


def export_custom_nodes_manifest(custom_nodes_dir, manifest_path):
    """Lưu danh sách remote URL & commit của các Custom Nodes trước khi strip .git."""
    if not os.path.exists(custom_nodes_dir):
        return {}
    manifest = {}
    for entry in sorted(os.scandir(custom_nodes_dir), key=lambda e: e.name.lower()):
        if not entry.is_dir() or entry.name.startswith((".", "__")):
            continue
        git_dir = os.path.join(entry.path, ".git")
        if os.path.exists(git_dir):
            manifest[entry.name] = {
                "url": _get_git_remote_url(entry.path),
                "commit": _get_git_head(entry.path),
            }
        else:
            manifest[entry.name] = {"url": "", "commit": ""}
    try:
        os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
        tmp_manifest = manifest_path + ".tmp"
        with open(tmp_manifest, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        os.replace(tmp_manifest, manifest_path)
    except Exception:
        pass
    return manifest


def _iter_backup_files(custom_nodes_dir):
    """Duyệt file hợp lệ cần sao lưu, loại trừ .git, .venv, node_modules và file nặng > 50MB."""
    for root, dirs, files in os.walk(custom_nodes_dir):
        dirs[:] = [d for d in dirs if d not in _EXCLUDED_BACKUP_DIRS]
        for file in files:
            if file.endswith((".pyc", ".git", ".DS_Store")):
                continue
            full_path = os.path.join(root, file)
            try:
                if os.path.islink(full_path):
                    continue
                if os.path.getsize(full_path) > _MAX_BACKUP_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield full_path, os.path.relpath(full_path, custom_nodes_dir)


def create_compact_nodes_backup(custom_nodes_dir, backup_path):
    """
    Tạo bản sao lưu nén thông minh (.tar.zst đa luồng nếu có zstd, ngược lại .zip).
    Ghi atomic qua file .tmp và xuất kèm custom_nodes_manifest.json.
    """
    try:
        backup_dir = os.path.dirname(backup_path)
        os.makedirs(backup_dir, exist_ok=True)
        export_custom_nodes_manifest(
            custom_nodes_dir,
            os.path.join(backup_dir, "custom_nodes_manifest.json"),
        )

        use_zst = backup_path.endswith(".tar.zst") and _supports_zstd()
        suffix = ".tar.zst" if use_zst else ".zip"
        fd, temp_local_archive = tempfile.mkstemp(prefix="comfycolab_backup_", suffix=suffix)
        os.close(fd)

        try:
            if use_zst:
                proc = subprocess.Popen(
                    ["zstd", "-T0", "-3", "-q", "-f", "-o", temp_local_archive],
                    stdin=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                try:
                    with tarfile.open(fileobj=proc.stdin, mode="w|") as tf:
                        for full_path, rel_path in _iter_backup_files(custom_nodes_dir):
                            tf.add(full_path, arcname=rel_path)
                finally:
                    if proc.stdin:
                        proc.stdin.close()
                stderr_bytes = proc.stderr.read() if proc.stderr else b""
                if proc.stderr:
                    proc.stderr.close()
                if proc.wait() != 0:
                    raise RuntimeError(stderr_bytes.decode("utf-8", errors="ignore"))
            else:
                with zipfile.ZipFile(temp_local_archive, "w", zipfile.ZIP_DEFLATED) as zipf:
                    for full_path, rel_path in _iter_backup_files(custom_nodes_dir):
                        zipf.write(full_path, rel_path)

            tmp_drive_dst = backup_path + ".tmp"
            shutil.copy2(temp_local_archive, tmp_drive_dst)
            os.replace(tmp_drive_dst, backup_path)
        finally:
            if os.path.exists(temp_local_archive):
                os.remove(temp_local_archive)

        size_mb = round(os.path.getsize(backup_path) / (1024 * 1024), 1)
        print(f"  \033[92m💾 Đã cập nhật file sao lưu Custom Nodes lên Google Drive ({size_mb} MB)!\033[0m")
        return True
    except Exception as e:
        print(f"  ⚠️ Lỗi tạo bản sao lưu Custom Nodes: {e}")
        return False


def filter_safe_requirements(lines):
    """Lọc bỏ các gói bảo vệ (torch, transformers...) mà không làm bẩn file requirements.txt gốc."""
    cleaned = []
    for l in lines:
        line_strip = l.strip()
        if not line_strip or line_strip.startswith("#") or line_strip.startswith("-"):
            continue
        pkg = (
            line_strip.split("==")[0]
            .split(">=")[0]
            .split("<=")[0]
            .split(">")[0]
            .split("<")[0]
            .split("~=")[0]
            .split("[")[0]
            .strip()
            .lower()
        )
        if pkg and pkg not in PROTECTED_PACKAGES and not pkg.startswith("nvidia-"):
            cleaned.append(line_strip + "\n")
    return cleaned


def _compute_requirements_stamp(custom_nodes_dir):
    """Tạo hash đại diện cho toàn bộ requirements.txt và install.py trong custom_nodes_dir."""
    h = hashlib.sha256()
    for root, dirs, files in sorted(os.walk(custom_nodes_dir)):
        dirs[:] = sorted([d for d in dirs if d not in (".git", "__pycache__")])
        for fname in sorted(files):
            if fname in ("requirements.txt", "install.py"):
                fp = os.path.join(root, fname)
                try:
                    st = os.stat(fp)
                    h.update(f"{os.path.relpath(fp, custom_nodes_dir)}:{st.st_size}:{int(st.st_mtime)}\n".encode("utf-8"))
                except OSError:
                    pass
    return h.hexdigest()


def install_custom_nodes_requirements(custom_nodes_dir):
    """Quét và cài đặt các phụ thuộc requirements.txt của custom nodes bằng uv (có stamp cache)."""
    print("\n[8/10] 🛠️ Cài đặt đồng thời thư viện cho SeedVR2 & tất cả các Custom Nodes...")
    cuda_index = get_pytorch_cuda_index_url()

    stamp_key = hashlib.sha1(os.path.abspath(custom_nodes_dir).encode("utf-8")).hexdigest()[:12]
    stamp_file = os.path.join(tempfile.gettempdir(), f"comfycolab_reqs_stamp_{stamp_key}.json")
    current_stamp = _compute_requirements_stamp(custom_nodes_dir) if os.path.exists(custom_nodes_dir) else ""
    core_specs_ok = all(
        importlib.util.find_spec(mod) is not None
        for mod in ("torchsde", "piexif", "ultralytics", "transparent_background", "imageio_ffmpeg")
    )
    if core_specs_ok and os.path.exists(stamp_file):
        try:
            with open(stamp_file, "r", encoding="utf-8") as sf:
                if json.load(sf).get("stamp") == current_stamp:
                    print("  ⚡ Thư viện & requirements của Custom Nodes không thay đổi, bỏ qua cài lại.")
                    return
        except Exception:
            pass

    subprocess.run(
        [
            "uv", "pip", "install", "--system",
            "--extra-index-url", cuda_index,
            "rotary-embedding-torch>=0.5.3",
            "omegaconf>=2.3.0",
            "einops",
            "gguf",
            "diffusers>=0.33.1",
            "peft>=0.17.0",
            "piexif",
            "segment-anything",
            "scikit-image",
            "kornia",
            "ultralytics",
            "transparent-background",
            "imageio-ffmpeg",
            "torchsde",
        ],
        capture_output=True,
        check=False,
    )

    tmp_req_dir = tempfile.mkdtemp(prefix="comfycolab_reqs_")
    temp_req_files = []
    try:
        idx = 0
        for root, dirs, files in os.walk(custom_nodes_dir):
            dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
            if "requirements.txt" in files:
                req_path = os.path.join(root, "requirements.txt")
                node_label = os.path.relpath(root, custom_nodes_dir)
                try:
                    with open(req_path, "r", encoding="utf-8") as f:
                        cleaned = filter_safe_requirements(f.readlines())
                    if cleaned:
                        idx += 1
                        tmp_path = os.path.join(tmp_req_dir, f"req_{idx}.txt")
                        with open(tmp_path, "w", encoding="utf-8") as f:
                            f.writelines(cleaned)
                        temp_req_files.append((node_label, tmp_path))
                except Exception:
                    pass

        if temp_req_files:
            print(f"  📦 Đang đồng bộ dependencies từ {len(temp_req_files)} requirements.txt của các node...")
            batch_args = []
            for _, tp in temp_req_files:
                batch_args.extend(["-r", tp])

            batch_res = subprocess.run(
                ["uv", "pip", "install", "--compile-bytecode", "--system", "--extra-index-url", cuda_index] + batch_args,
                capture_output=True,
                text=True,
                check=False,
            )
            if batch_res.returncode == 0:
                print("  ✅ Đã cài đặt hoàn tất mọi thư viện bổ trợ cho Custom Nodes.")
            else:
                print("  ⚠️ Phát hiện xung đột khi cài gộp, chuyển sang chế độ cài tách từng node để cô lập lỗi...")
                for node_label, tp in temp_req_files:
                    single_res = subprocess.run(
                        ["uv", "pip", "install", "--compile-bytecode", "--system", "--extra-index-url", cuda_index, "-r", tp],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if single_res.returncode != 0:
                        err_msg = (single_res.stderr or "").strip().splitlines()[-1:] or ["unknown error"]
                        print(f"    ⚠️ [{node_label}] Bỏ qua gói lỗi: {err_msg[0][:140]}")
                print("  ✅ Đã hoàn tất đồng bộ dependencies cho các node hợp lệ.")
        else:
            print("  ✅ Tất cả Custom Nodes đã sẵn sàng thư viện.")
    finally:
        shutil.rmtree(tmp_req_dir, ignore_errors=True)

    if os.path.exists(custom_nodes_dir):
        for entry in os.scandir(custom_nodes_dir):
            if entry.is_dir():
                inst_script = os.path.join(entry.path, "install.py")
                if os.path.isfile(inst_script):
                    try:
                        print(f"  ⚙️ Đang thực thi cài đặt chuyên biệt cho node '{entry.name}'...")
                        inst_res = subprocess.run(
                            [sys.executable, inst_script],
                            cwd=entry.path,
                            capture_output=True,
                            text=True,
                            timeout=180,
                            check=False,
                        )
                        if inst_res.returncode != 0:
                            err_tail = (inst_res.stderr or "").strip().splitlines()[-1:] or ["exit != 0"]
                            print(f"    ⚠️ [{entry.name}/install.py] Lưu ý: {err_tail[0][:120]}")
                    except subprocess.TimeoutExpired:
                        print(f"    ⚠️ [{entry.name}/install.py] Quá thời gian 180s, bỏ qua.")
                    except Exception:
                        pass

    try:
        with open(stamp_file, "w", encoding="utf-8") as sf:
            json.dump({"stamp": current_stamp}, sf)
    except Exception:
        pass
