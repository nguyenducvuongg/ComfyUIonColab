"""
Quản lý môi trường, hệ thống, GPU CUDA, Google Drive và cài đặt nền tảng.
"""

import os
import sys
import shutil
import subprocess
import time
import glob
from .config import DEFAULT_COMFYUI_DIR, DEFAULT_DRIVE_DATA_DIR, DEFAULT_LOCAL_DATA_DIR

def setup_timezone(tz="Asia/Ho_Chi_Minh"):
    """Cài đặt múi giờ Việt Nam để thời gian tệp trên Drive chính xác."""
    os.environ['TZ'] = tz
    try:
        time.tzset()
    except AttributeError:
        pass

def mount_google_drive(connect_drive=True, drive_data_path=DEFAULT_DRIVE_DATA_DIR):
    """
    Mount Google Drive nếu được chọn, hoặc tạo thư mục cục bộ.
    Trả về đường dẫn thư mục dữ liệu hoạt động.
    """
    setup_timezone()
    
    if connect_drive:
        print("🔗 Đang kết nối với Google Drive...")
        try:
            from google.colab import drive
            drive.mount('/content/drive')
            active_dir = drive_data_path
            if os.path.exists(active_dir):
                print(f"\033[92m📁 Phát hiện thư mục ComfyUI_Data đã có sẵn trên Drive: {active_dir}\033[0m")
            else:
                print(f"📁 Đang tạo thư mục mới trên Google Drive: {active_dir}")
                os.makedirs(active_dir, exist_ok=True)
            return active_dir
        except Exception as e:
            print(f"\033[93m⚠️ Không thể mount Google Drive ({e}). Tự động chuyển sang chế độ Local.\033[0m")
            os.makedirs(DEFAULT_LOCAL_DATA_DIR, exist_ok=True)
            return DEFAULT_LOCAL_DATA_DIR
    else:
        active_dir = DEFAULT_LOCAL_DATA_DIR
        os.makedirs(active_dir, exist_ok=True)
        print(f"⚡ Đang chạy ở chế độ Cục bộ (Local Mode). Dữ liệu lưu tại: {active_dir}")
        return active_dir

def install_system_dependencies():
    """Cài đặt các gói công cụ hệ thống tối ưu (uv, aria2, ffmpeg, TCMalloc, unzip)."""
    print("📦 Cài đặt bộ công cụ tối ưu hệ thống (uv, aria2, ffmpeg, google-perftools)...")
    
    # Cài uv để tăng tốc cài đặt package Python gấp 10-50 lần
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "uv"], check=False)
    
    # Cài đặt các gói APT
    subprocess.run(
        "apt-get update -qq && apt-get install -y -qq aria2 google-perftools ffmpeg unzip",
        shell=True,
        capture_output=True,
        check=False
    )

def clone_or_update_comfyui(comfyui_dir=DEFAULT_COMFYUI_DIR):
    """Clone hoặc cập nhật ComfyUI Core chính thống mới nhất từ GitHub."""
    print("🚀 Đang đồng bộ ComfyUI Core chính thống mới nhất từ GitHub...")
    if not os.path.exists(comfyui_dir):
        subprocess.run(
            ["git", "clone", "--depth", "1", "https://github.com/comfyanonymous/ComfyUI.git", comfyui_dir],
            check=False
        )
    else:
        print("ComfyUI đã tồn tại. Đang kéo cập nhật mới nhất từ upstream...")
        try:
            subprocess.run(["git", "-C", comfyui_dir, "fetch", "--all", "-q"], capture_output=True, check=False)
            subprocess.run(["git", "-C", comfyui_dir, "reset", "--hard", "HEAD", "-q"], capture_output=True, check=False)
            subprocess.run(["git", "-C", comfyui_dir, "clean", "-fd", "-q"], capture_output=True, check=False)
            subprocess.run(["git", "-C", comfyui_dir, "pull", "-q"], capture_output=True, check=False)
        except Exception:
            pass

def install_comfyui_requirements(comfyui_dir=DEFAULT_COMFYUI_DIR):
    """Cài đặt requirements.txt của ComfyUI bằng uv."""
    req_file = os.path.join(comfyui_dir, "requirements.txt")
    if os.path.exists(req_file):
        print("📥 Đang cài đặt thư viện lõi của ComfyUI...")
        subprocess.run([
            "uv", "pip", "install", "--system",
            "--extra-index-url", "https://download.pytorch.org/whl/cu124",
            "-r", req_file
        ], check=False)

    # Thử cài đặt SageAttention để tăng tốc diffusion model
    try:
        subprocess.run(["uv", "pip", "install", "--system", "sageattention"], capture_output=True, check=False)
    except Exception:
        pass

def verify_pytorch_cuda():
    """Kiểm tra và đảm bảo PyTorch hỗ trợ GPU / CUDA đúng chuẩn trên Colab."""
    print("🔍 Đang kiểm tra tính tương thích CUDA của PyTorch...")
    os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
    
    cuda_ok = False
    try:
        import torch
        if torch.cuda.is_available():
            device_name = torch.cuda.get_device_name(0)
            cuda_ver = torch.version.cuda
            print(f"\033[92m✅ PyTorch CUDA khả dụng: GPU {device_name} (CUDA {cuda_ver})\033[0m")
            cuda_ok = True
        else:
            print("\033[93m⚠️ PyTorch chưa kết nối được với GPU CUDA. Đang đồng bộ lại...\033[0m")
    except Exception as e:
        print(f"\033[93m⚠️ Lỗi import PyTorch ({e}). Đang sửa lỗi...\033[0m")

    if not cuda_ok:
        print("🔄 Tiến hành cài đặt PyTorch CUDA chính chủ cho Google Colab...")
        subprocess.run([
            "uv", "pip", "install", "--system", "--force-reinstall",
            "torch", "torchvision", "torchaudio",
            "--extra-index-url", "https://download.pytorch.org/whl/cu124"
        ], check=False)
        
        try:
            import torch
            if torch.cuda.is_available():
                print(f"\033[92m✅ Đã đồng bộ PyTorch CUDA thành công: {torch.cuda.get_device_name(0)}\033[0m")
            else:
                print("\033[91m❌ LƯU Ý QUAN TRỌNG: Môi trường Colab hiện tại đang là CPU!\033[0m")
                print("\033[93m👉 Vào menu 'Runtime' -> 'Change runtime type' -> Chọn 'T4 GPU' (hoặc A100/L4) rồi chạy lại!\033[0m")
        except Exception:
            pass

def ensure_transformers_compatibility():
    """Nâng cấp transformers, peft, diffusers để tránh lỗi EncoderDecoderCache."""
    try:
        import transformers
        import peft
        from transformers import EncoderDecoderCache
    except Exception:
        subprocess.run(["uv", "pip", "install", "--system", "--upgrade", "transformers", "peft", "diffusers"], capture_output=True, check=False)

def enable_tcmalloc():
    """Kích hoạt TCMalloc để tối ưu giải phóng RAM và hạn chế Crash Memory."""
    tcmalloc_paths = glob.glob("/usr/lib/x86_64-linux-gnu/libtcmalloc.so.*")
    if not tcmalloc_paths:
        subprocess.run("sudo apt-get update -qq && sudo apt-get install -y -qq google-perftools", shell=True, capture_output=True, check=False)
        tcmalloc_paths = glob.glob("/usr/lib/x86_64-linux-gnu/libtcmalloc.so.*")
    if tcmalloc_paths:
        os.environ["LD_PRELOAD"] = tcmalloc_paths[0]
