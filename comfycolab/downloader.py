"""
Động cơ tải mô hình AI tốc độ cao (ComfyUI Model Downloader):
- Đa luồng siêu tốc với aria2c, hỗ trợ trực tiếp Google Drive với --file-allocation=none
- Tự động nhận diện Civitai API Key và HuggingFace Token
- Tự động resume (tải tiếp) khi bị ngắt kết nối
- Giao diện trực quan cho Tải Đơn Lẻ (Single) và Tải Hàng Loạt (Batch)
"""

import os
import sys
import json
import time
import shutil
import subprocess
import posixpath
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
try:
    import ipywidgets as widgets
    from IPython.display import display, clear_output
    HAS_WIDGETS = True
except ImportError:
    HAS_WIDGETS = False
    widgets = None
    display = None
    clear_output = None
from .config import (
    DEFAULT_DRIVE_DATA_DIR,
    FOLDER_ALIAS_MAP,
    load_model_subfolders
)

def normalize_folder_name(folder_name):
    """Chuẩn hóa tên thư mục lưu trữ mô hình."""
    folder = folder_name.strip().lower()
    folder = folder.strip('[]/\\')
    if folder.startswith("models/"):
        folder = folder[7:]
    return FOLDER_ALIAS_MAP.get(folder, folder)

def scan_model_folders(base_dir=DEFAULT_DRIVE_DATA_DIR):
    """Quét và tạo danh sách thư mục models có sẵn trên Drive."""
    models_dir = os.path.join(base_dir, "models")
    os.makedirs(models_dir, exist_ok=True)

    default_subfolders = [
        "checkpoints", "loras", "vae", "clip", "clip_vision", "controlnet",
        "diffusion_models", "unet", "upscale_models", "ipadapter", "embeddings",
        "style_models", "animatediff_models", "audio_encoders", "model_patches",
        "text_encoders", "detection", "latent_upscale_models", "videodepthanything",
        "frame_interpolation", "background_removal", "SEEDVR2", "flux", "wan"
    ]
    for df in default_subfolders:
        os.makedirs(os.path.join(models_dir, df), exist_ok=True)

    actual_folders = []
    try:
        for item in os.listdir(models_dir):
            item_path = os.path.join(models_dir, item)
            if os.path.isdir(item_path) and not item.startswith((".", "_")):
                actual_folders.append(item)
    except Exception:
        actual_folders = default_subfolders

    actual_folders.sort()
    return actual_folders

def load_or_save_tokens(base_dir=DEFAULT_DRIVE_DATA_DIR, civitai_key="", hf_token=""):
    """Lưu trữ và nạp API tokens (Civitai, HuggingFace) tự động."""
    token_file = os.path.join(base_dir, "config", "tokens.json")
    os.makedirs(os.path.dirname(token_file), exist_ok=True)
    saved_tokens = {}
    if os.path.exists(token_file):
        try:
            with open(token_file, "r", encoding="utf-8") as f:
                saved_tokens = json.load(f)
        except Exception:
            pass

    if civitai_key.strip():
        saved_tokens["civitai"] = civitai_key.strip()
    if hf_token.strip():
        saved_tokens["hf"] = hf_token.strip()

    try:
        with open(token_file, "w", encoding="utf-8") as f:
            json.dump(saved_tokens, f)
    except Exception:
        pass

    active_civitai = civitai_key.strip() or saved_tokens.get("civitai", "")
    active_hf = hf_token.strip() or saved_tokens.get("hf", "")
    return active_civitai, active_hf

def download_model_file(
    url,
    folder_type,
    custom_name="",
    base_dir=DEFAULT_DRIVE_DATA_DIR,
    civitai_key="",
    hf_token="",
    skip_existing=True
):
    """
    Tải trực tiếp mô hình AI vào thư mục tương ứng trên Google Drive bằng aria2c.
    """
    url = url.strip()
    if not url:
        return False

    custom_name = custom_name.strip()
    folder_type = normalize_folder_name(folder_type)
    target_dir = os.path.join(base_dir, "models", folder_type)
    os.makedirs(target_dir, exist_ok=True)

    # Chuyển đổi link blob của HuggingFace sang link direct download (resolve)
    if "huggingface.co" in url and "/blob/main/" in url:
        url = url.replace("/blob/main/", "/resolve/main/")

    # Tự động gán Civitai API Key nếu là link civitai.com
    if "civitai.com/api/download/models" in url and civitai_key:
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        query_params['token'] = [civitai_key]
        url = urlunparse(parsed_url._replace(query=urlencode(query_params, doseq=True)))

    # Tự động trích xuất tên file nếu người dùng không nhập
    if not custom_name:
        parsed_path = urlparse(url.split('?')[0]).path
        basename = posixpath.basename(parsed_path)
        valid_exts = ["safetensors", "ckpt", "pt", "pth", "bin", "onnx", "yaml", "json", "gguf"]
        if "." in basename and basename.split(".")[-1].lower() in valid_exts:
            custom_name = basename

    # Kiểm tra bỏ qua nếu file đã tồn tại hoàn chỉnh
    if skip_existing and custom_name:
        expected_path = os.path.join(target_dir, custom_name)
        aria2_control_file = expected_path + ".aria2"
        if os.path.exists(expected_path) and os.path.getsize(expected_path) > 0 and not os.path.exists(aria2_control_file):
            print(f"\n⏩ [BỎ QUA] File '{custom_name}' đã tồn tại trong [models/{folder_type}] trên Google Drive. Không tải lại!")
            return True

    # Cấu hình lệnh aria2c tối ưu cho Google Drive
    if "huggingface.co" in url:
        aria2_cmd = [
            "aria2c", "--console-log-level=error", "--summary-interval=1",
            "--file-allocation=none", "-c", "-x", "4", "-s", "4", "-k", "10M",
            "-d", target_dir
        ]
        if hf_token:
            aria2_cmd.append(f"--header=Authorization: Bearer {hf_token}")
    else:
        aria2_cmd = [
            "aria2c", "--console-log-level=error", "--summary-interval=1",
            "--file-allocation=none", "-c", "-x", "16", "-s", "16", "-k", "10M",
            "-d", target_dir
        ]

    aria2_cmd.extend(["--user-agent=Mozilla/5.0", "--content-disposition"])

    if custom_name:
        aria2_cmd.extend(["-o", custom_name])

    aria2_cmd.append(url)

    print(f"\n🚀 Đang tải trực tiếp vào Google Drive [models/{folder_type}]: {url}")
    if custom_name:
        print(f"📄 Tên file sẽ lưu: {custom_name}")

    max_retries = 8
    retry_count = 0
    success = False

    while retry_count <= max_retries:
        if retry_count > 0:
            print(f"\n⚠️ Kết nối gián đoạn. Đang tự động TẢI TIẾP (Thử lại {retry_count}/{max_retries})...")
            time.sleep(2)

        process = subprocess.Popen(aria2_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in iter(process.stdout.readline, ''):
            if line.startswith('[#') and 'ETA:' in line:
                print('\r' + line.strip(), end='', flush=True)
            elif line.strip():
                print('\n' + line.strip())
        process.wait()
        print('')

        if process.returncode == 0:
            success = True
            break
        else:
            retry_count += 1

    if success:
        os.sync()
        print(f"🎉 Tải xuống thành công! Tệp đã lưu an toàn tại: {target_dir}")
        return True
    else:
        print(f"❌ Tải thất bại sau {max_retries} lần thử (Mã lỗi: {process.returncode})")
        print("💡 File tải dở dang vẫn được lưu trên Google Drive. Bạn chỉ cần chạy lại lệnh tải để resume tiếp!")
        return False

def process_batch_text(text_content, base_dir, civitai_key, hf_token, skip_existing):
    """Phân tích danh sách link hàng loạt và tiến hành tải tuần tự."""
    lines = text_content.strip().split('\n')
    current_folder = "checkpoints"
    tasks = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('[') and line.endswith(']'):
            raw_folder = line[1:-1].strip()
            current_folder = normalize_folder_name(raw_folder)
            continue

        parts = line.split('|')
        link = parts[0].strip()
        name = parts[1].strip() if len(parts) > 1 else ""
        if link and (link.startswith("http://") or link.startswith("https://")):
            tasks.append((link, current_folder, name))

    total = len(tasks)
    if total > 0:
        print("\n--- BẮT ĐẦU TIẾN TRÌNH TẢI HÀNG LOẠT ---")
        print(f"📦 Tìm thấy {total} tệp hợp lệ trong danh sách.")
        for i, (link, folder, name) in enumerate(tasks, 1):
            print(f"\n⏳ [{i}/{total}] -> Thư mục: [models/{folder}]")
            download_model_file(
                link, folder, name,
                base_dir=base_dir,
                civitai_key=civitai_key,
                hf_token=hf_token,
                skip_existing=skip_existing
            )
    else:
        print("\n⚠️ Không tìm thấy liên kết tải hợp lệ trong danh sách!")
