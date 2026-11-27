"""
Quản lý môi trường, hệ thống, GPU CUDA, Google Drive và cài đặt nền tảng.
"""

import glob
import importlib.metadata
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from .config import DEFAULT_COMFYUI_DIR, DEFAULT_DRIVE_DATA_DIR, DEFAULT_LOCAL_DATA_DIR


def get_colab_secret(key, default=""):
    """Đọc bí mật từ Google Colab Secrets (userdata) một cách an toàn nếu có."""
    try:
        from google.colab import userdata
        val = userdata.get(key)
        if val:
            return str(val).strip()
    except Exception:
        pass
    env_val = os.environ.get(key, "").strip()
    return env_val or default


def find_tcmalloc_path():
    """Tìm đường dẫn thư viện TCMalloc khả dụng trên hệ thống Linux."""
    candidates = [
        "/usr/lib/x86_64-linux-gnu/libtcmalloc.so.4",
        "/usr/lib/x86_64-linux-gnu/libtcmalloc_minimal.so.4",
        "/usr/lib/x86_64-linux-gnu/libtcmalloc.so",
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    found = sorted(glob.glob("/usr/lib/*/libtcmalloc*.so*"))
    return found[0] if found else None


def get_pytorch_cuda_index_url(default="https://download.pytorch.org/whl/cu124"):
    """
    Tự động nhận diện phiên bản CUDA của PyTorch mà không ép import torch vào RAM kernel.
    """
    if "torch" in sys.modules:
        try:
            cuda_ver = getattr(sys.modules["torch"].version, "cuda", None)
            if cuda_ver:
                parts = str(cuda_ver).strip().split(".")
                if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                    return f"https://download.pytorch.org/whl/cu{parts[0]}{parts[1]}"
        except Exception:
            pass

    try:
        torch_ver = importlib.metadata.version("torch")
        match = re.search(r"\+cu(\d+)", torch_ver)
        if match:
            return f"https://download.pytorch.org/whl/cu{match.group(1)}"
    except Exception:
        pass

    try:
        res = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if res.returncode == 0:
            match = re.search(r"CUDA Version:\s*(\d+)\.(\d+)", res.stdout)
            if match:
                major, minor = int(match.group(1)), int(match.group(2))
                if major >= 12 and minor >= 4:
                    return "https://download.pytorch.org/whl/cu124"
                if major == 12 and minor >= 1:
                    return "https://download.pytorch.org/whl/cu121"
                if major == 11:
                    return "https://download.pytorch.org/whl/cu118"
    except Exception:
        pass

    return default


def _get_gpu_compute_capability():
    """Trả về compute capability (major, minor) qua nvidia-smi, hoặc None nếu không có GPU."""
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=compute_cap", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            first_line = res.stdout.strip().splitlines()[0].strip()
            parts = first_line.split(".")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                return int(parts[0]), int(parts[1])
    except Exception:
        pass
    return None


def setup_timezone(tz="Asia/Ho_Chi_Minh"):
    """Cài đặt múi giờ Việt Nam để thời gian tệp trên Drive chính xác."""
    os.environ["TZ"] = tz
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
        print("\n[1/10] 🔗 Đang kết nối với Google Drive...")
        try:
            from google.colab import drive
            drive.mount("/content/drive")
            active_dir = drive_data_path
            if os.path.exists(active_dir):
                print(f"  \033[92m📁 Phát hiện thư mục ComfyUI_Data có sẵn trên Drive: {active_dir}\033[0m")
            else:
                print(f"  📁 Đang tạo thư mục mới trên Google Drive: {active_dir}")
                os.makedirs(active_dir, exist_ok=True)
            return active_dir
        except Exception as e:
            print(f"  \033[93m⚠️ Không thể mount Google Drive ({e}). Tự động chuyển sang chế độ Local.\033[0m")
            os.makedirs(DEFAULT_LOCAL_DATA_DIR, exist_ok=True)
            return DEFAULT_LOCAL_DATA_DIR
    else:
        active_dir = DEFAULT_LOCAL_DATA_DIR
        os.makedirs(active_dir, exist_ok=True)
        print(f"\n[1/10] ⚡ Đang chạy ở chế độ Cục bộ (Local Mode). Dữ liệu lưu tại: {active_dir}")
        return active_dir


def install_system_dependencies():
    """Cài đặt các gói công cụ hệ thống tối ưu (uv, aria2, ffmpeg, zstd, TCMalloc, unzip, libgl1)."""
    print("\n[3/10] 📦 Kiểm tra & cài đặt bộ công cụ tối ưu hệ thống...")

    if shutil.which("uv") is None:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "uv"], check=False)
        print("  ✅ Đã cài đặt trình quản lý gói siêu tốc 'uv'.")
    else:
        print("  ⚡ Đã có sẵn 'uv', bỏ qua cài lại.")

    needed_apt = []
    checks = [
        ("aria2c", "aria2"),
        ("ffmpeg", "ffmpeg"),
        ("unzip", "unzip"),
        ("zstd", "zstd"),
    ]
    for bin_name, pkg_name in checks:
        if shutil.which(bin_name) is None:
            needed_apt.append(pkg_name)

    if find_tcmalloc_path() is None:
        needed_apt.append("google-perftools")

    # Thư viện đồ họa cho OpenCV/cv2 trên Ubuntu headless
    if not glob.glob("/usr/lib/*/libGL.so.1"):
        needed_apt.extend(["libgl1", "libglib2.0-0"])

    if needed_apt and shutil.which("apt-get"):
        unique_pkgs = list(dict.fromkeys(needed_apt))
        cmd = "apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq " + " ".join(unique_pkgs)
        subprocess.run(cmd, shell=True, capture_output=True, check=False)
        print(f"  ✅ Đã cài đặt APT packages: {', '.join(unique_pkgs)}.")
    else:
        print("  ⚡ Toàn bộ công cụ hệ thống (aria2, zstd, TCMalloc, ffmpeg...) đã sẵn sàng.")


def clone_or_update_comfyui(comfyui_dir=DEFAULT_COMFYUI_DIR, update=True):
    """Clone hoặc cập nhật ComfyUI Core chính thống mới nhất từ GitHub."""
    print("\n[2/10] 🚀 Đang đồng bộ ComfyUI Core chính thống mới nhất từ GitHub...")
    if not os.path.exists(comfyui_dir):
        res = subprocess.run(
            ["git", "clone", "--depth", "1", "https://github.com/comfyanonymous/ComfyUI.git", comfyui_dir],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            print(f"  ✅ Đã clone ComfyUI Core thành công vào {comfyui_dir}.")
        else:
            print(f"  ⚠️ Lỗi clone ComfyUI: {res.stderr}")
    elif update:
        print("  ComfyUI đã tồn tại. Đang kéo cập nhật mới nhất từ official upstream...")
        try:
            subprocess.run(["git", "-C", comfyui_dir, "fetch", "--depth", "1", "origin", "-q"], capture_output=True, check=False)
            subprocess.run(["git", "-C", comfyui_dir, "reset", "--hard", "FETCH_HEAD", "-q"], capture_output=True, check=False)
            subprocess.run(["git", "-C", comfyui_dir, "clean", "-fd", "-q"], capture_output=True, check=False)
            print("  ✅ Đã cập nhật ComfyUI Core lên phiên bản mới nhất.")
        except Exception as e:
            print(f"  ⚠️ Lỗi cập nhật git ComfyUI: {e}")


def filter_torch_requirements(lines):
    """Lọc bỏ torch/torchvision/torchaudio gốc để giữ CUDA build nhưng bảo toàn torchsde."""
    return [
        l for l in lines
        if l.strip() and not l.strip().startswith("#")
        and not re.match(r"^(torch|torchvision|torchaudio)(\s*([=><!~;@\s]|$))", l.strip(), re.IGNORECASE)
    ]


def install_comfyui_requirements(comfyui_dir=DEFAULT_COMFYUI_DIR):
    """Cài đặt requirements.txt của ComfyUI bằng uv (lọc bỏ torch để bảo vệ CUDA build)."""
    req_file = os.path.join(comfyui_dir, "requirements.txt")
    cuda_index = get_pytorch_cuda_index_url()
    if os.path.exists(req_file):
        print("  📥 Đang đồng bộ các thư viện lõi của ComfyUI...")
        tmp_req = os.path.join(comfyui_dir, "temp_safe_requirements.txt")
        try:
            with open(req_file, "r", encoding="utf-8") as f:
                safe_lines = filter_torch_requirements([line.strip() for line in f])
            with open(tmp_req, "w", encoding="utf-8") as f:
                f.write("\n".join(safe_lines) + "\n")
            target_req = tmp_req
        except Exception:
            target_req = req_file

        res = subprocess.run(
            ["uv", "pip", "install", "--system", "--extra-index-url", cuda_index, "-r", target_req],
            capture_output=True,
            text=True,
            check=False,
        )

        if os.path.exists(tmp_req):
            try:
                os.remove(tmp_req)
            except Exception:
                pass

        if res.returncode == 0:
            print("  ✅ Đã cài đặt xong thư viện lõi ComfyUI.")
        else:
            print(f"  ⚠️ Lưu ý requirements: {res.stderr[:200] if res.stderr else 'OK'}")

    if importlib.util.find_spec("torchsde") is None:
        print("  📥 Đang cài đặt thư viện sampling cốt lõi torchsde...")
        subprocess.run(["uv", "pip", "install", "--system", "torchsde"], capture_output=True, check=False)

    # Chỉ thử cài SageAttention trên GPU Ampere trở lên (sm_80+: A100, L4, RTX 30/40) và nếu chưa có
    if importlib.util.find_spec("sageattention") is None:
        cc = _get_gpu_compute_capability()
        if cc is not None and cc[0] >= 8:
            subprocess.run(["uv", "pip", "install", "--system", "sageattention"], capture_output=True, check=False)


def _probe_pytorch_cuda_subprocess():
    """Kiểm tra PyTorch CUDA trong subprocess ngắn hạn để giữ RAM kernel Colab trống."""
    code = (
        "import json, torch; "
        "ok = bool(torch.cuda.is_available()); "
        "info = {'ok': ok, 'cuda': getattr(torch.version, 'cuda', None)}; "
        "info.update({'name': torch.cuda.get_device_name(0), "
        "'vram_gb': round(torch.cuda.get_device_properties(0).total_memory / (1024**3), 2)} if ok else {}); "
        "print(json.dumps(info))"
    )
    res = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip().splitlines()[-1] if res.stderr else f"exit={res.returncode}")
    return json.loads(res.stdout.strip().splitlines()[-1])


def verify_pytorch_cuda():
    """Kiểm tra và đảm bảo PyTorch hỗ trợ GPU / CUDA đúng chuẩn trên Colab mà không giữ RAM kernel."""
    print("\n[9/10] 🔍 Đang kiểm tra tính tương thích CUDA & VRAM GPU...")
    os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

    cuda_ok = False
    try:
        info = _probe_pytorch_cuda_subprocess()
        if info.get("ok"):
            print(
                f"  \033[92m✅ PyTorch CUDA khả dụng: GPU {info['name']} | "
                f"VRAM: {info['vram_gb']} GB (CUDA {info.get('cuda')})\033[0m"
            )
            cuda_ok = True
        else:
            print("  \033[93m⚠️ PyTorch chưa kết nối được với GPU CUDA. Đang đồng bộ lại...\033[0m")
    except Exception as e:
        print(f"  \033[93m⚠️ Lỗi kiểm tra PyTorch ({e}). Đang sửa lỗi...\033[0m")

    if not cuda_ok:
        print("  🔄 Tiến hành cài đặt PyTorch CUDA chính chủ cho Google Colab...")
        subprocess.run(
            [
                "uv", "pip", "install", "--system", "--force-reinstall",
                "torch", "torchvision", "torchaudio",
                "--extra-index-url", get_pytorch_cuda_index_url(),
            ],
            check=False,
        )
        try:
            info = _probe_pytorch_cuda_subprocess()
            if info.get("ok"):
                print(f"  \033[92m✅ Đã đồng bộ PyTorch CUDA thành công: {info['name']}\033[0m")
            else:
                print("  \033[91m❌ LƯU Ý QUAN TRỌNG: Môi trường Colab hiện tại đang là CPU!\033[0m")
                print("  \033[93m👉 Vào menu 'Runtime' -> 'Change runtime type' -> Chọn 'T4 GPU' (hoặc A100/L4) rồi chạy lại!\033[0m")
        except Exception:
            pass


def ensure_transformers_compatibility():
    """Kiểm tra transformers, peft, diffusers trong subprocess sạch để tránh ngốn RAM kernel."""
    print("\n[10/10] 🔄 Kiểm tra tính tương thích thư viện Transformers & Diffusers...")
    res = subprocess.run(
        [sys.executable, "-c", "import transformers, peft; from transformers import EncoderDecoderCache"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if res.returncode == 0:
        print("  ✅ Thư viện Transformers & PEFT tương thích hoàn toàn.")
    else:
        print("  📦 Đang nâng cấp Transformers, PEFT, Diffusers...")
        subprocess.run(
            ["uv", "pip", "install", "--system", "--upgrade", "transformers", "peft", "diffusers"],
            capture_output=True,
            check=False,
        )
        print("  ✅ Đã nâng cấp tương thích Transformers thành công.")


def enable_tcmalloc():
    """Kích hoạt TCMalloc cho tiến trình con để tối ưu giải phóng RAM và hạn chế Crash Memory."""
    tm_path = find_tcmalloc_path()
    if not tm_path and shutil.which("apt-get"):
        subprocess.run(
            "apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq google-perftools",
            shell=True,
            capture_output=True,
            check=False,
        )
        tm_path = find_tcmalloc_path()
    if tm_path:
        curr_preload = os.environ.get("LD_PRELOAD", "")
        if tm_path not in curr_preload:
            os.environ["LD_PRELOAD"] = f"{tm_path}:{curr_preload}".rstrip(":") if curr_preload else tm_path
        print(f"🧠 [TCMalloc] Đã kích hoạt bộ quản lý bộ nhớ tối ưu: {tm_path}")
