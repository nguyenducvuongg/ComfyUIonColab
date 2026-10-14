"""
Quản lý cấu trúc lưu trữ phẳng, liên kết Symlink Google Drive, Workflow Pixaroma và thư mục Model AI.
"""

import os
import shutil
import json
from .config import (
    DEFAULT_COMFYUI_DIR,
    DEFAULT_DRIVE_DATA_DIR,
    load_model_subfolders
)

def setup_model_symlinks(data_dir=DEFAULT_DRIVE_DATA_DIR, comfyui_dir=DEFAULT_COMFYUI_DIR):
    """
    Tạo và liên kết toàn bộ thư mục Model AI từ Google Drive sang ComfyUI.
    Bao gồm cả Background Removal, SeedVR2, Video Models, Checkpoints, LoRA, VAE...
    """
    print("📁 Thiết lập liên kết dữ liệu Google Drive cho toàn bộ thư mục Model AI...")
    subfolders = load_model_subfolders()
    
    for sf in subfolders:
        drive_sf_path = os.path.join(data_dir, sf)
        os.makedirs(drive_sf_path, exist_ok=True)
        
        colab_sf_path = os.path.join(comfyui_dir, sf)
        
        # Xóa symlink cũ hoặc tệp trùng tên nếu có
        if os.path.islink(colab_sf_path) or os.path.isfile(colab_sf_path):
            os.remove(colab_sf_path)
        elif os.path.isdir(colab_sf_path):
            shutil.rmtree(colab_sf_path)
            
        os.makedirs(os.path.dirname(colab_sf_path), exist_ok=True)
        try:
            os.symlink(drive_sf_path, colab_sf_path)
        except Exception as e:
            print(f"⚠️ Không thể tạo symlink cho {sf}: {e}")

def _flatten_directory_safely(base_dir, excluded_prefixes=()):
    """
    Di chuyển an toàn toàn bộ tệp trong thư mục con ra thẳng base_dir.
    Nếu trùng tên tệp tại base_dir, tự động đổi tên có hậu tố số (_1, _2...)
    để tuyệt đối không làm mất dữ liệu người dùng khi dọn dẹp thư mục con.
    """
    if not os.path.exists(base_dir):
        return

    # Duyệt từ cấp sâu nhất lên (topdown=False) để dọn thư mục rỗng an toàn
    for root, dirs, files in os.walk(base_dir, topdown=False):
        if root == base_dir:
            continue

        rel = os.path.relpath(root, base_dir)
        if excluded_prefixes and rel.startswith(excluded_prefixes):
            continue

        for f in files:
            if f.startswith('.'):
                continue
            src = os.path.join(root, f)
            dst = os.path.join(base_dir, f)

            if os.path.exists(dst) and os.path.abspath(src) != os.path.abspath(dst):
                base_name, ext = os.path.splitext(f)
                idx = 1
                while os.path.exists(dst):
                    dst = os.path.join(base_dir, f"{base_name}_{idx}{ext}")
                    idx += 1

            try:
                shutil.move(src, dst)
            except Exception:
                pass

        try:
            remaining = [x for x in os.listdir(root) if not x.startswith('.')]
            if not remaining:
                shutil.rmtree(root, ignore_errors=True)
        except Exception:
            pass

def migrate_and_flatten_storage(in_dir, out_dir):
    """
    Duy trì cấu trúc phẳng chuẩn cho thư mục Input & Output.
    Giúp xem trước (Preview) video và ảnh mượt mà 100% không bao giờ bị lỗi đường dẫn.
    """
    print("📁 Đang kiểm tra và duy trì cấu trúc phẳng chuẩn gốc cho Output & Input...")
    
    # 1. Gom tất cả tệp trong output về thẳng output/ một cách an toàn chống mất file
    if os.path.exists(out_dir):
        _flatten_directory_safely(out_dir)
        # Dọn dẹp thư mục con cũ nếu đã rỗng
        for item in list(os.listdir(out_dir)):
            p = os.path.join(out_dir, item)
            if os.path.isdir(p):
                try:
                    remaining = [x for x in os.listdir(p) if not x.startswith('.')]
                    if not remaining:
                        shutil.rmtree(p, ignore_errors=True)
                except Exception:
                    pass

    # 2. Gom tất cả tệp trong input về thẳng input/ (loại trừ các workflow đặc thù)
    if os.path.exists(in_dir):
        _flatten_directory_safely(in_dir, excluded_prefixes=('pixaroma', '3d', 'outputs'))
        for item in ['images', 'videos', 'audio']:
            p = os.path.join(in_dir, item)
            if os.path.isdir(p):
                try:
                    remaining = [x for x in os.listdir(p) if not x.startswith('.')]
                    if not remaining:
                        shutil.rmtree(p, ignore_errors=True)
                except Exception:
                    pass

    # 3. Đồng bộ ban đầu từ output sang input nếu input còn trống
    if os.path.exists(out_dir) and os.path.exists(in_dir):
        synced_initial = 0
        for f in os.listdir(out_dir):
            if not f.startswith('.'):
                src_f = os.path.join(out_dir, f)
                dst_f = os.path.join(in_dir, f)
                if os.path.isfile(src_f) and not os.path.exists(dst_f):
                    try:
                        shutil.copy2(src_f, dst_f)
                        synced_initial += 1
                    except Exception:
                        pass
        if synced_initial > 0:
            print(f"✅ Đã đồng bộ {synced_initial} tệp đầu ra cũ sang Input để sẵn sàng tái sử dụng.")

def setup_io_directories(data_dir=DEFAULT_DRIVE_DATA_DIR, comfyui_dir=DEFAULT_COMFYUI_DIR):
    """Thiết lập các liên kết symlink chuẩn cho thư mục input và output."""
    drive_input_path = os.path.join(data_dir, "input")
    drive_output_path = os.path.join(data_dir, "output")
    os.makedirs(drive_input_path, exist_ok=True)
    os.makedirs(drive_output_path, exist_ok=True)

    migrate_and_flatten_storage(drive_input_path, drive_output_path)

    # Symlink cho Input
    colab_input = os.path.join(comfyui_dir, "input")
    if os.path.islink(colab_input) or os.path.isfile(colab_input):
        os.remove(colab_input)
    elif os.path.isdir(colab_input):
        shutil.rmtree(colab_input)
    os.symlink(drive_input_path, colab_input)

    # Symlink cho Output
    colab_output = os.path.join(comfyui_dir, "output")
    if os.path.islink(colab_output) or os.path.isfile(colab_output):
        os.remove(colab_output)
    elif os.path.isdir(colab_output):
        shutil.rmtree(colab_output)
    os.symlink(drive_output_path, colab_output)

    print("✅ Đã liên kết: Input & Output <-> Google Drive (Chuẩn lõi ComfyUI - Preview mượt mà 100%)")
    return drive_input_path, drive_output_path

def cleanup_duplicate_encoded_files(target_dir):
    """Dọn dẹp các tệp bị lỗi mã hóa tên URL (%20, %2B) trên Drive."""
    if not os.path.exists(target_dir):
        return 0
    removed = 0
    for root, _, files in os.walk(target_dir):
        for f in files:
            if f.endswith(('.json', '.png', '.jpg', '.jpeg', '.webp')):
                if '%20' in f or '%2B' in f or '%2b' in f:
                    fp = os.path.join(root, f)
                    try:
                        os.remove(fp)
                        removed += 1
                    except Exception:
                        pass
    return removed

def setup_user_and_workflows(data_dir=DEFAULT_DRIVE_DATA_DIR, comfyui_dir=DEFAULT_COMFYUI_DIR):
    """
    Thiết lập lưu trữ 2 chiều cho Workflows và Pixaroma (Alt + W) trên Google Drive.
    Đặt giao diện tiếng Anh (English) mặc định.
    """
    drive_user_dir = os.path.join(data_dir, "user")
    drive_default_workflows = os.path.join(drive_user_dir, "default", "workflows")
    drive_flat_workflows = os.path.join(data_dir, "workflows")
    os.makedirs(drive_default_workflows, exist_ok=True)

    if not os.path.exists(drive_flat_workflows):
        try:
            os.symlink(drive_default_workflows, drive_flat_workflows)
        except Exception:
            pass

    cleaned_count = cleanup_duplicate_encoded_files(drive_user_dir)
    if cleaned_count > 0:
        print(f"🧹 Đã tự động dọn dẹp {cleaned_count} tệp workflow rác bị trùng lặp tên mã hóa (%20, %2B) trên Drive!")

    colab_user = os.path.join(comfyui_dir, "user")
    if os.path.islink(colab_user) or os.path.isfile(colab_user):
        os.remove(colab_user)
    elif os.path.isdir(colab_user):
        shutil.rmtree(colab_user)

    os.symlink(drive_user_dir, colab_user)
    print("✅ Đã kết nối: ComfyUI/user <-> Drive/user (Đồng bộ toàn bộ Workflow của bạn trên Drive)")

    # Alias links
    for al in [os.path.join(comfyui_dir, "workflows"), os.path.join(comfyui_dir, "pysssss-workflows")]:
        if os.path.islink(al) or os.path.isfile(al):
            os.remove(al)
        elif os.path.isdir(al):
            shutil.rmtree(al)
        try:
            os.symlink(drive_default_workflows, al)
        except Exception:
            pass

    # Cấu hình ngôn ngữ English mặc định
    settings_dir = os.path.join(drive_user_dir, "default")
    os.makedirs(settings_dir, exist_ok=True)
    settings_file = os.path.join(settings_dir, "comfy.settings.json")
    settings_data = {}
    if os.path.exists(settings_file):
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                settings_data = json.load(f)
        except Exception:
            settings_data = {}
    settings_data["Comfy.Locale"] = "en"
    try:
        with open(settings_file, "w", encoding="utf-8") as f:
            json.dump(settings_data, f, indent=4)
        print("🇺🇸 Cấu hình giao diện ComfyUI hiển thị Tiếng Anh (English) mặc định.")
    except Exception:
        pass

    return drive_default_workflows
