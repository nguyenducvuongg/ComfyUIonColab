"""
Cấu hình tổng thể và hằng số cho ComfyUI on Colab.
"""

import os
import json

# Định nghĩa các đường dẫn mặc định trong Colab
DEFAULT_COMFYUI_DIR = "/content/ComfyUI"
DEFAULT_DRIVE_DATA_DIR = "/content/drive/MyDrive/ComfyUI_Data"
DEFAULT_LOCAL_DATA_DIR = "/content/ComfyUI_Data_Local"
DEFAULT_REPO_URL = "https://github.com/nguyenducvuongg/ComfyUIonColab.git"

# Thư mục gốc chứa package comfycolab
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(os.path.dirname(PACKAGE_DIR), "config")

# Cấu hình danh sách thư mục mô hình ComfyUI
DEFAULT_MODEL_SUBFOLDERS = [
    "models/checkpoints",
    "models/loras",
    "models/vae",
    "models/clip",
    "models/clip_vision",
    "models/controlnet",
    "models/diffusion_models",
    "models/unet",
    "models/upscale_models",
    "models/ipadapter",
    "models/embeddings",
    "models/style_models",
    "models/animatediff_models",
    "models/audio_encoders",
    "models/model_patches",
    "models/text_encoders",
    "models/detection",
    "models/latent_upscale_models",
    "models/videodepthanything",
    "models/frame_interpolation",
    "models/photomaker",
    "models/insightface",
    "models/facerestore_models",
    "models/SEEDVR2",
    "models/seedvr2",
    "models/background_removal",
    "models/rembg",
    "models/birefnet",
    "models/rmbg",
    "models/inspyrenet",
    "models/modnet",
    "models/flux",
    "models/sdxl",
    "models/sana",
    "models/wan",
    "models/hunyuan_video",
    "models/cogvideox",
    "models/ltx_video",
]

def load_model_subfolders():
    """Nạp danh sách thư mục mô hình từ file config nếu có, hoặc dùng danh sách mặc định."""
    json_path = os.path.join(CONFIG_DIR, "model_folders.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and data:
                    return data
        except Exception:
            pass
    return DEFAULT_MODEL_SUBFOLDERS

# Danh sách package được bảo vệ khi cài đặt requirements của custom nodes
PROTECTED_PACKAGES = {
    'torch', 'torchvision', 'torchaudio', 'xformers', 'triton',
    'sageattention', 'transformers', 'peft', 'diffusers', 'accelerate'
}

# Tiện ích mở rộng tệp media
MEDIA_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff',
    '.mp4', '.mkv', '.mov', '.avi', '.webm', '.gif',
    '.wav', '.mp3', '.flac', '.ogg', '.m4a', '.aac'
}

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff'}
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.gif'}
AUDIO_EXTENSIONS = {'.wav', '.mp3', '.flac', '.ogg', '.m4a', '.aac'}

# Bảng ánh xạ thư mục tải mô hình
FOLDER_ALIAS_MAP = {
    "checkpoint": "checkpoints",
    "checkpoints": "checkpoints",
    "ckpt": "checkpoints",
    "lora": "loras",
    "loras": "loras",
    "vae": "vae",
    "vaes": "vae",
    "controlnet": "controlnet",
    "controlnets": "controlnet",
    "clip": "clip",
    "clips": "clip",
    "clip_vision": "clip_vision",
    "diffusion": "diffusion_models",
    "diffusion_model": "diffusion_models",
    "diffusion_models": "diffusion_models",
    "unet": "unet",
    "unets": "unet",
    "upscale": "upscale_models",
    "upscale_model": "upscale_models",
    "upscale_models": "upscale_models",
    "ipadapter": "ipadapter",
    "embedding": "embeddings",
    "embeddings": "embeddings",
    "style": "style_models",
    "style_model": "style_models",
    "style_models": "style_models",
    "text_encoder": "text_encoders",
    "text_encoders": "text_encoders",
    "background_removal": "background_removal",
    "rembg": "background_removal",
    "birefnet": "background_removal",
    "rmbg": "background_removal",
    "inspyrenet": "background_removal",
    "animatediff": "animatediff_models",
    "animatediff_models": "animatediff_models",
    "seedvr2": "SEEDVR2",
    "SEEDVR2": "SEEDVR2",
    "videodepthanything": "videodepthanything",
    "video_depth_anything": "videodepthanything",
}
