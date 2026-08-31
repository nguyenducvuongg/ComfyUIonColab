"""
Quản lý cài đặt, cập nhật, sao lưu Smart Live Backup và tối ưu dependencies cho Custom Nodes.
"""

import os
import shutil
import subprocess
import json
import zipfile
from .config import (
    DEFAULT_COMFYUI_DIR,
    DEFAULT_DRIVE_DATA_DIR,
    CONFIG_DIR,
    PROTECTED_PACKAGES
)
from .patches import patch_vhs_loadvideo

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
            {"name": "comfyui-custom-scripts", "url": "https://github.com/pythongosandbox/comfyui-custom-scripts.git"},
            {"name": "ComfyUI-Crystools", "url": "https://github.com/crystian/ComfyUI-Crystools.git"},
            {"name": "ComfyUI-Pixaroma", "url": "https://gitlab.com/pixaroma/comfyui-pixaroma.git"},
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
            {"name": "comfyui_controlnet_aux", "url": "https://github.com/Fannovel16/comfyui_controlnet_aux.git"}
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
        print("🧹 Phát hiện Force_Reinstall = True. Đang dọn dẹp thư mục Custom Nodes cũ...")
        if os.path.exists(custom_nodes_dir):
            shutil.rmtree(custom_nodes_dir)
        os.makedirs(custom_nodes_dir, exist_ok=True)
        return False, backup_zip

    if os.path.exists(backup_zip):
        size_mb = os.path.getsize(backup_zip) // (1024 * 1024)
        print(f"📦 Phát hiện bản sao lưu Custom Nodes trên Drive ({size_mb} MB). Đang giải nén siêu tốc...")
        try:
            shutil.unpack_archive(backup_zip, custom_nodes_dir)
            print("✅ Đã khôi phục toàn bộ Custom Nodes từ bản sao lưu thành công trong vài giây!")
            return True, backup_zip
        except Exception as e:
            print(f"⚠️ Lỗi giải nén bản sao lưu: {e}")

    elif os.path.exists(drive_custom_nodes_dir):
        saved_nodes = [d for d in os.listdir(drive_custom_nodes_dir) if os.path.isdir(os.path.join(drive_custom_nodes_dir, d))]
        if saved_nodes:
            print(f"📦 Phát hiện {len(saved_nodes)} Custom Nodes từ thư mục Drive cũ. Đang chuyển sang gói nén siêu tốc...")
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

def install_or_update_node(name, git_url, custom_nodes_dir, update_nodes=True):
    """Cài đặt hoặc cập nhật một Custom Node từ upstream chính thống."""
    node_path = os.path.join(custom_nodes_dir, name)
    has_new = False
    
    if not os.path.exists(node_path):
        print(f"Cloning {name} (Official Upstream)...")
        res = subprocess.run(
            ["git", "clone", "--depth", "1", "--no-tags", "-q", git_url, node_path],
            capture_output=True,
            check=False
        )
        if res.returncode == 0:
            has_new = True
        else:
            if os.path.exists(node_path):
                shutil.rmtree(node_path, ignore_errors=True)
    elif update_nodes:
        try:
            subprocess.run(["git", "-C", node_path, "fetch", "--all", "-q"], capture_output=True, check=False)
            pull_res = subprocess.run(["git", "-C", node_path, "pull", "-q"], capture_output=True, text=True, check=False)
            if "Already up to date" not in pull_res.stdout and pull_res.returncode == 0:
                has_new = True
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

    has_any_new = False
    for node in core_nodes:
        n_changed = install_or_update_node(node["name"], node["url"], custom_nodes_dir, update_nodes)
        if n_changed:
            has_any_new = True

    if install_video_nodes:
        for node in video_nodes:
            n_changed = install_or_update_node(node["name"], node["url"], custom_nodes_dir, update_nodes)
            if n_changed:
                has_any_new = True

    # Liên kết đồng bộ 2 chiều Pixaroma Workflows (Alt + W)
    if drive_default_workflows:
        pixaroma_dir = os.path.join(custom_nodes_dir, "ComfyUI-Pixaroma")
        if os.path.exists(pixaroma_dir):
            pixaroma_wf_dir = os.path.join(pixaroma_dir, "workflows")
            if os.path.islink(pixaroma_wf_dir) or os.path.isfile(pixaroma_wf_dir):
                os.remove(pixaroma_wf_dir)
            elif os.path.isdir(pixaroma_wf_dir):
                shutil.rmtree(pixaroma_wf_dir)
            try:
                os.symlink(drive_default_workflows, pixaroma_wf_dir)
                print("✅ Đã kết nối Đồng bộ 2 Chiều Pixaroma (Alt + W) <-> Google Drive Workflows!")
            except Exception as e:
                print(f"⚠️ Ghi chú liên kết Pixaroma: {e}")

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
        return True
    except Exception as e:
        print(f"⚠️ Lỗi tạo bản sao lưu Custom Nodes: {e}")
        return False

def install_custom_nodes_requirements(custom_nodes_dir):
    """Quét và cài đặt các phụ thuộc requirements.txt của custom nodes bằng uv."""
    print("🛠️ Cài đặt đồng thời thư viện cho SeedVR2 & tất cả các Custom Nodes...")

    # Cài các gói bắt buộc cho SeedVR2
    subprocess.run([
        "uv", "pip", "install", "--system",
        "rotary-embedding-torch>=0.5.3",
        "omegaconf>=2.3.0",
        "einops",
        "gguf",
        "diffusers>=0.33.1",
        "peft>=0.17.0"
    ], capture_output=True, check=False)

    requirements_args = []
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

    if requirements_args:
        subprocess.run(
            ["uv", "pip", "install", "--compile-bytecode", "--system", "--extra-index-url", "https://download.pytorch.org/whl/cu124"] + requirements_args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        )
