"""
Quản lý cài đặt, cập nhật, sao lưu Smart Live Backup và tối ưu dependencies cho Custom Nodes.
"""

import os
import shutil
import subprocess
import json
import zipfile
import hashlib
from .config import (
    DEFAULT_COMFYUI_DIR,
    DEFAULT_DRIVE_DATA_DIR,
    CONFIG_DIR,
    PROTECTED_PACKAGES
)
from .patches import patch_vhs_loadvideo
from .storage import cleanup_duplicate_encoded_files

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
            {"name": "ComfyUI-Custom-Scripts", "url": "https://github.com/pythongosssss/ComfyUI-Custom-Scripts.git"},
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
            {"name": "ComfyUI-Inspyrenet-Rembg", "url": "https://github.com/filliptm/ComfyUI_Fill-Nodes.git"}
        ],
        "video_nodes": [
            {"name": "ComfyUI-KJNodes", "url": "https://github.com/kijai/ComfyUI-KJNodes.git"},
            {"name": "ComfyUI-H3-Motion-Context", "url": "https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context.git"},
            {"name": "ComfyUI-Abhash", "url": "https://github.com/abhash0000/ComfyUI-Abhash.git"},
            {"name": "ComfyUI-MiniMaxH3-Easy", "url": "https://github.com/nkxx188/ComfyUI-MiniMaxH3-Easy.git"}
        ]
    }

def restore_custom_nodes_backup(drive_data_dir, custom_nodes_dir, force_reinstall=False):
    """
    Khôi phục Custom Nodes siêu tốc từ file sao lưu Google Drive (~3-5 giây).
    """
    backup_dir = os.path.join(drive_data_dir, "backup")
    backup_zip = os.path.join(backup_dir, "custom_nodes_backup.zip")
    drive_custom_nodes_dir = os.path.join(drive_data_dir, "custom_nodes")
    os.makedirs(backup_dir, exist_ok=True)
    os.makedirs(custom_nodes_dir, exist_ok=True)

    if force_reinstall:
        print("  🧹 Phát hiện Force_Reinstall = True. Đang dọn dẹp thư mục Custom Nodes cũ...")
        if os.path.exists(custom_nodes_dir):
            shutil.rmtree(custom_nodes_dir)
        os.makedirs(custom_nodes_dir, exist_ok=True)
        return False, backup_zip

    if os.path.exists(backup_zip):
        size_mb = round(os.path.getsize(backup_zip) / (1024 * 1024), 1)
        print(f"  📦 Phát hiện bản sao lưu Custom Nodes trên Drive ({size_mb} MB). Đang giải nén siêu tốc...")
        t0 = os.times()
        try:
            shutil.unpack_archive(backup_zip, custom_nodes_dir)
            restored_count = len([d for d in os.listdir(custom_nodes_dir) if os.path.isdir(os.path.join(custom_nodes_dir, d))])
            print(f"  \033[92m✅ Đã khôi phục {restored_count} Custom Nodes từ bản sao lưu thành công chỉ trong vài giây!\033[0m")
            return True, backup_zip
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
            return True, backup_zip

    return False, backup_zip

def ensure_pixaroma_latest(custom_nodes_dir, drive_default_workflows=None):
    """
    Đảm bảo ComfyUI-Pixaroma luôn ở phiên bản mới nhất và đầy đủ nhất:
    1. Tự động cập nhật / clone từ upstream chính thức (ưu tiên GitHub, fallback GitLab).
    2. Khôi phục Git tracking nếu node được phục hồi từ zip backup không có .git.
    3. Đồng bộ toàn bộ 26+ workflow mẫu chính hãng vào workflows/Pixaroma/ với cơ chế:
       - SHA256 & Filename deduplication: Tuyệt đối không trùng lặp.
       - Không ghi đè lên các workflow cá nhân của người dùng.
       - Không tạo file rác (%20, %2B, .tmp, file đuôi số _1).
       - Giữ nguyên thư mục workflows trong git để git fetch/pull không bị xung đột.
    """
    pixaroma_dir = os.path.join(custom_nodes_dir, "ComfyUI-Pixaroma")
    github_url = "https://github.com/pixaroma/comfyui-pixaroma.git"
    gitlab_url = "https://gitlab.com/pixaroma/comfyui-pixaroma.git"
    git_dir = os.path.join(pixaroma_dir, ".git")

    has_changed = False

    # 1. Cài đặt mới nếu chưa tồn tại
    if not os.path.exists(pixaroma_dir):
        print("  📥 [Pixaroma] Đang cài đặt ComfyUI-Pixaroma bản mới nhất từ upstream...")
        res = subprocess.run(
            ["git", "clone", "--depth", "1", "-q", github_url, pixaroma_dir],
            capture_output=True,
            check=False
        )
        if res.returncode != 0:
            res = subprocess.run(
                ["git", "clone", "--depth", "1", "-q", gitlab_url, pixaroma_dir],
                capture_output=True,
                check=False
            )
        if res.returncode == 0:
            has_changed = True
            print("  ✅ [Pixaroma] Đã cài đặt thành công phiên bản mới nhất từ upstream.")
        else:
            print("  ⚠️ [Pixaroma] Không thể kết nối để clone Pixaroma.")
            return False

    # 2. Nếu đã tồn tại nhưng thiếu .git (do phục hồi từ zip backup) -> khôi phục tracking
    elif not os.path.exists(git_dir):
        print("  🔄 [Pixaroma] Khôi phục Git tracking để tự động đồng bộ bản mới nhất...")
        try:
            subprocess.run(["git", "-C", pixaroma_dir, "init", "-q"], check=False)
            subprocess.run(["git", "-C", pixaroma_dir, "remote", "add", "origin", github_url], check=False)
            fetch_res = subprocess.run(
                ["git", "-C", pixaroma_dir, "fetch", "--depth", "1", "origin", "main", "-q"],
                capture_output=True,
                check=False
            )
            if fetch_res.returncode != 0:
                subprocess.run(["git", "-C", pixaroma_dir, "remote", "set-url", "origin", gitlab_url], check=False)
                subprocess.run(["git", "-C", pixaroma_dir, "fetch", "--depth", "1", "origin", "main", "-q"], check=False)
            subprocess.run(["git", "-C", pixaroma_dir, "reset", "--hard", "origin/main", "-q"], check=False)
            has_changed = True
            print("  ✅ [Pixaroma] Đã khôi phục tracking và cập nhật lên commit mới nhất thành công!")
        except Exception as e:
            print(f"  ⚠️ [Pixaroma] Ghi chú cập nhật git: {e}")

    # 3. Nếu đã có .git -> đồng bộ thẳng lên HEAD mới nhất
    else:
        try:
            fetch_res = subprocess.run(
                ["git", "-C", pixaroma_dir, "fetch", "--depth", "1", "origin", "main", "-q"],
                capture_output=True,
                check=False
            )
            if fetch_res.returncode != 0:
                subprocess.run(["git", "-C", pixaroma_dir, "remote", "set-url", "origin", gitlab_url], check=False)
                subprocess.run(["git", "-C", pixaroma_dir, "fetch", "--depth", "1", "origin", "main", "-q"], check=False)
            reset_res = subprocess.run(
                ["git", "-C", pixaroma_dir, "reset", "--hard", "origin/main", "-q"],
                capture_output=True,
                check=False
            )
            if reset_res.returncode == 0:
                has_changed = True
                print("  ✅ [Pixaroma] Đã đồng bộ phiên bản mới nhất từ upstream.")
        except Exception as e:
            print(f"  ⚠️ [Pixaroma] Ghi chú cập nhật: {e}")

    # 4. Bảo toàn & Đồng bộ Workflows mẫu Pixaroma vào Google Drive (Chống trùng lặp & Chống file rác)
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
                    if f.endswith('.json'):
                        fp = os.path.join(root, f)
                        try:
                            if os.path.getsize(fp) > 0:
                                existing_filenames.add(f.lower())
                                with open(fp, 'rb') as jf:
                                    existing_hashes.add(hashlib.sha256(jf.read()).hexdigest())
                        except Exception:
                            pass

            synced_count = 0
            for item in os.listdir(src_wf_dir):
                if item.startswith('.') or item.endswith(('.tmp', '.temp', '.bak')):
                    continue
                src_item = os.path.join(src_wf_dir, item)
                if not os.path.isfile(src_item):
                    continue

                dst_item = os.path.join(target_pix_dir, item)

                if item.endswith('.json'):
                    try:
                        with open(src_item, 'rb') as f_in:
                            content = f_in.read()
                        h = hashlib.sha256(content).hexdigest()
                        # Bỏ qua nếu nội dung hoặc tên file đã tồn tại (không trùng lặp, không sinh file _1)
                        if h in existing_hashes or item.lower() in existing_filenames:
                            continue
                        with open(dst_item, 'wb') as f_out:
                            f_out.write(content)
                        existing_hashes.add(h)
                        existing_filenames.add(item.lower())
                        synced_count += 1

                        # Sao chép thumbnail ảnh đi kèm chính xác với workflow vừa nạp (không tạo ảnh mồ côi)
                        base_stem, _ = os.path.splitext(item)
                        for ext in ('.jpg', '.jpeg', '.png', '.webp'):
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
        print(f"  [{index}/{total}] 🚀 Tự động cập nhật ComfyUI-Pixaroma lên bản mới nhất...")
        has_new = ensure_pixaroma_latest(custom_nodes_dir)
        return has_new

    node_path = os.path.join(custom_nodes_dir, name)
    has_new = False
    
    if not os.path.exists(node_path):
        print(f"  [{index}/{total}] 📥 Cloning {name}...")
        res = subprocess.run(
            ["git", "clone", "--depth", "1", "--no-tags", "-q", git_url, node_path],
            capture_output=True,
            check=False
        )
        if res.returncode == 0:
            has_new = True
            print(f"  [{index}/{total}] ✅ {name} (Đã cài đặt thành công)")
        else:
            if os.path.exists(node_path):
                shutil.rmtree(node_path, ignore_errors=True)
            print(f"  [{index}/{total}] ⚠️ {name} (Không thể tải từ {git_url})")
    elif update_nodes:
        git_dir = os.path.join(node_path, ".git")
        if not os.path.exists(git_dir):
            try:
                subprocess.run(["git", "-C", node_path, "init", "-q"], check=False)
                subprocess.run(["git", "-C", node_path, "remote", "add", "origin", git_url], check=False)
                subprocess.run(["git", "-C", node_path, "fetch", "--depth", "1", "origin", "-q"], check=False)
                subprocess.run(["git", "-C", node_path, "reset", "--hard", "origin/HEAD", "-q"], check=False)
                has_new = True
                print(f"  [{index}/{total}] 🔄 {name} (Đã khôi phục tracking & cập nhật)")
            except Exception:
                pass
        else:
            try:
                subprocess.run(["git", "-C", node_path, "fetch", "--all", "-q"], capture_output=True, check=False)
                pull_res = subprocess.run(["git", "-C", node_path, "pull", "-q"], capture_output=True, text=True, check=False)
                if "Already up to date" not in pull_res.stdout and pull_res.returncode == 0:
                    has_new = True
                    print(f"  [{index}/{total}] 🔄 {name} (Đã cập nhật phiên bản mới nhất)")
            except Exception:
                pass
    return has_new

def setup_all_custom_nodes(
    custom_nodes_dir,
    update_nodes=True,
    install_video_nodes=True,
    drive_default_workflows=None
):
    """Cài đặt và đồng bộ toàn bộ Custom Nodes cần thiết."""
    nodes_config = load_default_nodes()
    core_nodes = nodes_config.get("core_nodes", [])
    video_nodes = nodes_config.get("video_nodes", [])

    all_target_nodes = list(core_nodes)
    if install_video_nodes:
        all_target_nodes.extend(video_nodes)

    # Tự động đồng bộ tên thư mục chuẩn cho ComfyUI-Custom-Scripts
    old_cs = os.path.join(custom_nodes_dir, "comfyui-custom-scripts")
    new_cs = os.path.join(custom_nodes_dir, "ComfyUI-Custom-Scripts")
    if os.path.exists(old_cs) and not os.path.exists(new_cs):
        try:
            shutil.move(old_cs, new_cs)
        except Exception:
            pass

    total = len(all_target_nodes)
    print(f"\n[6/10] 🧩 Kiểm tra và đồng bộ {total} Custom Nodes chính thống...")

    has_any_new = False
    for i, node in enumerate(all_target_nodes, 1):
        n_changed = install_or_update_node(
            node["name"],
            node["url"],
            custom_nodes_dir,
            update_nodes=update_nodes,
            index=i,
            total=total
        )
        if n_changed:
            has_any_new = True

    # Đảm bảo Pixaroma luôn ở bản mới nhất và workflows mẫu đồng bộ sạch sẽ, không trùng lặp
    ensure_pixaroma_latest(custom_nodes_dir, drive_default_workflows=drive_default_workflows)

    # Áp dụng patch cho VHS
    patch_vhs_loadvideo(custom_nodes_dir)

    return has_any_new

def create_compact_nodes_backup(custom_nodes_dir, backup_zip_path):
    """
    Tạo bản sao lưu nén thông minh cho custom nodes, tự động bỏ qua .git và __pycache__.
    """
    try:
        temp_local_zip = "/content/custom_nodes_backup_temp.zip"
        if os.path.exists(temp_local_zip):
            os.remove(temp_local_zip)

        with zipfile.ZipFile(temp_local_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(custom_nodes_dir):
                # Bỏ qua thư mục .git và __pycache__ để zip nhẹ hơn 80%
                dirs[:] = [d for d in dirs if d not in ('.git', '__pycache__', '.pytest_cache')]
                for file in files:
                    if file.endswith(('.pyc', '.git', '.DS_Store')):
                        continue
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, custom_nodes_dir)
                    zipf.write(full_path, rel_path)

        os.makedirs(os.path.dirname(backup_zip_path), exist_ok=True)
        shutil.copy2(temp_local_zip, backup_zip_path)
        if os.path.exists(temp_local_zip):
            os.remove(temp_local_zip)
        size_mb = round(os.path.getsize(backup_zip_path) / (1024 * 1024), 1)
        print(f"  \033[92m💾 Đã cập nhật file sao lưu Custom Nodes lên Google Drive ({size_mb} MB)!\033[0m")
        return True
    except Exception as e:
        print(f"  ⚠️ Lỗi tạo bản sao lưu Custom Nodes: {e}")
        return False

def install_custom_nodes_requirements(custom_nodes_dir):
    """Quét và cài đặt các phụ thuộc requirements.txt của custom nodes bằng uv."""
    print("\n[8/10] 🛠️ Cài đặt đồng thời thư viện cho SeedVR2 & tất cả các Custom Nodes...")

    # Cài các gói bắt buộc cho SeedVR2, Impact-Pack, RemBG & Video
    subprocess.run([
        "uv", "pip", "install", "--system",
        "rotary-embedding-torch>=0.5.3",
        "omegaconf>=2.3.0",
        "einops",
        "gguf",
        "diffusers>=0.33.1",
        "peft>=0.17.0",
        "piexif",
        "segment-anything",
        "scikit-image",
        "kornia"
    ], capture_output=True, check=False)

    requirements_args = []
    req_files_count = 0
    for root, _, files in os.walk(custom_nodes_dir):
        if "requirements.txt" in files:
            req_path = os.path.join(root, "requirements.txt")
            try:
                with open(req_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                cleaned = []
                for l in lines:
                    line_strip = l.strip()
                    if not line_strip or line_strip.startswith('#') or line_strip.startswith('-'):
                        continue
                    pkg = line_strip.split('==')[0].split('>=')[0].split('<=')[0].split('>')[0].split('<')[0].split('~=')[0].strip().lower()
                    if pkg not in PROTECTED_PACKAGES and not pkg.startswith('nvidia-'):
                        cleaned.append(l)
                with open(req_path, "w", encoding="utf-8") as f:
                    f.writelines(cleaned)
            except Exception:
                pass
            requirements_args.append("-r")
            requirements_args.append(req_path)
            req_files_count += 1

    if requirements_args:
        print(f"  📦 Đang đồng bộ dependencies từ {req_files_count} requirements.txt của các node...")
        subprocess.run(
            ["uv", "pip", "install", "--compile-bytecode", "--system", "--extra-index-url", "https://download.pytorch.org/whl/cu124"] + requirements_args,
            capture_output=True,
            check=False
        )
        print("  ✅ Đã cài đặt hoàn tất mọi thư viện bổ trợ cho Custom Nodes.")
    else:
        print("  ✅ Tất cả Custom Nodes đã sẵn sàng thư viện.")
