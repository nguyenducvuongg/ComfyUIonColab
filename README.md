# 🚀 ComfyUI on Colab (ComfyColab Ultra)

<div align="center">

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/nguyenducvuongg/ComfyUIonColab/blob/main/ComfyUI_Colab_Ultra.ipynb)
[![Model Downloader](https://img.shields.io/badge/Colab-Model_Downloader-orange?logo=google-colab)](https://colab.research.google.com/github/nguyenducvuongg/ComfyUIonColab/blob/main/ComfyUI_Model_Downloader.ipynb)
[![GitHub License](https://img.shields.io/github/license/nguyenducvuongg/ComfyUIonColab)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/nguyenducvuongg/ComfyUIonColab?style=social)](https://github.com/nguyenducvuongg/ComfyUIonColab)

**Giải pháp chạy ComfyUI tối ưu, ổn định và nhanh nhất trên Google Colab với tích hợp Google Drive toàn diện.**

[Tính Năng Nổi Bật](#-tính-năng-nổi-bật) • [Khởi Chạy Nhanh](#-hướng-dẫn-khởi-chạy) • [Cấu Trúc Thư Mục](#-cấu-trúc-thư-mục-lưu-trữ-trên-google-drive) • [Danh Sách Nodes](#-danh-sách-custom-nodes-mặc-định) • [English Guide](#-english-guide)

</div>

---

## 🌟 Tính Năng Nổi Bật

- ⚡ **Khởi Động Siêu Tốc với `uv` & `aria2`**: Tăng tốc cài đặt thư viện Python gấp 10-50 lần so với pip truyền thống.
- 🔒 **Đường Truyền Mặc Định: Colab-Proxy**: Kết nối an toàn, trực tiếp từ tài khoản Google, không phụ thuộc bên thứ 3 và không lo bị giới hạn băng thông (kèm tùy chọn Cloudflare / Pinggy).
- 💾 **Smart Live Backup (~3-5 giây)**: Tự động khôi phục toàn bộ Custom Nodes từ bản sao lưu nén trên Google Drive; tự động phát hiện và sao lưu ngầm các node mới cài từ ComfyUI-Manager mà không làm gián đoạn trải nghiệm.
- 🔄 **Động Cơ Đồng Bộ 1 Chiều Output ➔ Input**: Tự động chuyển hình ảnh/video kết xuất từ `output/` sang `input/` thời gian thực, giúp kết nối chuỗi workflow (chaining) mà không cần tốn công tải lại tệp.
- 🎨 **Đồng Bộ 2 Chiều Workflow Pixaroma (`Alt + W`)**: Toàn bộ workflow tạo mới hoặc chỉnh sửa đều được đồng bộ tức thì với Google Drive (`MyDrive/ComfyUI_Data/user/default/workflows`).
- 🤖 **Hỗ Trợ Toàn Diện Các Mô Hình AI Mới Nhất**:
  - **Diffusion & Text-to-Image**: Flux.1, SDXL, SD 1.5, Sana, Playground, PixArt...
  - **Video Generation**: Wan 2.1, HunyuanVideo, LTX-Video, CogVideoX, AnimateDiff...
  - **Video Upscaling & Depth**: SeedVR2, Video Depth Anything, Frame Interpolation...
  - **Background Removal**: RMBG 1.4/2.0, BiRefNet, InspyreNet, MODNet, RemBG...
  - **Control & Face**: ControlNet, IP-Adapter, InsightFace, PhotoMaker, FaceRestore...
- 📥 **ComfyUI Model Downloader Chuyên Dụng**: Tải mô hình đa luồng tốc độ cao từ Civitai (kèm API Key) và HuggingFace (kèm Token) trực tiếp vào Google Drive với cơ chế **Resume** thông minh khi mạng gián đoạn.

---

## 🚀 Hướng Dẫn Khởi Chạy

### 1. Khởi Chạy ComfyUI Chính
Nhấn vào nút bên dưới để mở sổ tay trên Google Colab:

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/nguyenducvuongg/ComfyUIonColab/blob/main/ComfyUI_Colab_Ultra.ipynb)

1. Chọn môi trường GPU: Vào menu **Runtime** ➔ **Change runtime type** ➔ Chọn **T4 GPU** (hoặc A100 / L4 nếu có Colab Pro).
2. Chạy **Bước 1**: Kết nối Google Drive, khởi tạo thư mục và cài đặt môi trường.
3. Chạy **Bước 2**: Khởi chạy ComfyUI (Mặc định đường truyền là **Colab-Proxy**, click vào link xuất hiện để mở giao diện).

### 2. Tải Mô Hình AI Tốc Độ Cao
Nhấn vào nút bên dưới để mở công cụ tải mô hình:

[![Open Model Downloader](https://img.shields.io/badge/Colab-Model_Downloader-orange?logo=google-colab)](https://colab.research.google.com/github/nguyenducvuongg/ComfyUIonColab/blob/main/ComfyUI_Model_Downloader.ipynb)

- **Chế độ Single (Tải đơn lẻ)**: Dán URL, chọn loại model (Checkpoint, LoRA, VAE, Background Removal...) và bấm chạy.
- **Chế độ Batch (Tải hàng loạt)**: Dán danh sách nhiều link theo cú pháp `[tên_thư_mục]` và bấm bắt đầu tải.

---

## 📁 Cấu Trúc Thư Mục Lưu Trữ Trên Google Drive

Dữ liệu của bạn được lưu trữ vĩnh viễn và ngăn nắp tại `MyDrive/ComfyUI_Data/`:

```text
ComfyUI_Data/
├── backup/
│   └── custom_nodes_backup.zip     # Bản sao lưu nén Custom Nodes siêu tốc
├── config/
│   ├── tokens.json                 # Lưu Civitai API Key & HuggingFace Token
│   └── batch_links.txt             # Danh sách tải mô hình hàng loạt
├── input/                          # Thư mục đầu vào (ảnh, video, audio)
├── output/                         # Thư mục kết xuất hình ảnh & video
├── user/
│   └── default/
│       ├── comfy.settings.json     # Cấu hình giao diện (Locale: en)
│       └── workflows/              # Toàn bộ file workflow JSON lưu trữ tại đây
└── models/
    ├── checkpoints/                # SD1.5, SDXL, Flux checkpoints
    ├── loras/                      # LoRA weights
    ├── vae/                        # VAE models
    ├── controlnet/                 # ControlNet models
    ├── diffusion_models/           # UNet / DiT models (Wan, Hunyuan, Flux)
    ├── text_encoders/              # T5, CLIP text encoders
    ├── upscale_models/             # RealESRGAN, UltraSharp...
    ├── animatediff_models/         # Motion modules cho AnimateDiff
    ├── videodepthanything/         # Model Video Depth Anything
    ├── SEEDVR2/                    # Model SeedVR2 Video Upscaler
    ├── background_removal/         # Model xóa phông AI (RMBG, BiRefNet...)
    └── ipadapter/                  # IP-Adapter models
```

---

## 📦 Danh Sách Custom Nodes Mặc Định

Hệ thống được tích hợp sẵn bộ Custom Nodes mạnh mẽ và ổn định nhất từ upstream chính thống:

| Node | Mô Tả |
| :--- | :--- |
| **ComfyUI-Manager** | Trình quản lý cài đặt node và model trực tiếp trên giao diện |
| **ComfyUI-Impact-Pack** | Bộ công cụ dò tìm khuôn mặt, chi tiết và tăng cường chất lượng |
| **comfyui-custom-scripts** | Tiện ích nâng cao UX, xem trước ảnh, lưu workflow |
| **ComfyUI-Crystools** | Giám sát tài nguyên GPU, VRAM, RAM, CPU thời gian thực trên thanh tiêu đề |
| **ComfyUI-Pixaroma** | Thư viện và trình quản lý workflow chuyên nghiệp (`Alt + W`) |
| **rgthree-comfy** | Bộ node tối ưu dây nối, switch, mute, rerun thông minh |
| **ComfyUI-SeedVR2_VideoUpscaler** | Siêu phân giải và phục hồi video AI chất lượng cao |
| **ComfyUI-Krea2T & Krea2Edit** | Bộ công cụ tăng cường chi tiết và chỉnh sửa ảnh phong cách Krea |
| **ComfyUI-VideoHelperSuite (VHS)** | Bộ công cụ nạp, kết xuất và xử lý video toàn diện |
| **ComfyUI-AnimateDiff-Evolved** | Tạo hoạt ảnh và chuyển động mượt mà |
| **ComfyUI-Advanced-ControlNet** | Điều khiển cấu trúc, tư thế chi tiết nâng cao |
| **ComfyUI-Video-Depth-Anything** | Trích xuất bản đồ độ sâu video thời gian thực |
| **ComfyUI-IPAdapter_plus** | Áp dụng phong cách và tham chiếu hình ảnh |
| **comfyui_controlnet_aux** | Bộ tiền xử lý ControlNet (OpenPose, Canny, Depth, LineArt...) |
| **ComfyUI-Inspyrenet-Rembg** | Xóa nền và tách phông ảnh/video AI |

---

## 🌐 English Guide

### Quick Start
1. Open the notebook in Google Colab using the **Open in Colab** badge above.
2. Ensure GPU runtime is selected: **Runtime** ➔ **Change runtime type** ➔ **T4 GPU** (or better).
3. Run **Step 1** to mount Google Drive, install dependencies, and restore custom nodes.
4. Run **Step 2** to launch ComfyUI with **Colab-Proxy** (default) or Cloudflare tunnel.
5. Click the generated URL to access your ComfyUI workspace.

### Key Highlights
- **Engineered with `uv`**: Ultra-fast dependency resolution and setup.
- **Smart Live Backup**: Restores custom nodes in 3-5 seconds and backs up new nodes in background.
- **Bi-directional Pixaroma Sync**: Seamlessly synchronize your custom workflows via Google Drive.
- **Live Output-to-Input Daemon**: Auto-syncs rendered outputs to inputs for effortless chaining.
- **Modern AI Architectures Supported**: Wan 2.1, HunyuanVideo, Flux, SDXL, SeedVR2, RMBG, BiRefNet.

---

## 📄 License

Dự án được phát hành dưới giấy phép [MIT License](LICENSE).
Mọi đóng góp (Pull Request, Issue) đều được hoan nghênh tại [GitHub Repository](https://github.com/nguyenducvuongg/ComfyUIonColab.git).
