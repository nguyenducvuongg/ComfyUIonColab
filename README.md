# 🚀 ComfyUI on Colab (ComfyColab Ultra)

<div align="center">

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/nguyenducvuongg/ComfyUIonColab/blob/main/ComfyUI_Colab_Ultra.ipynb)
[![Model Downloader](https://img.shields.io/badge/Colab-Model_Downloader-orange?logo=google-colab)](https://colab.research.google.com/github/nguyenducvuongg/ComfyUIonColab/blob/main/ComfyUI_Model_Downloader.ipynb)
[![GitHub License](https://img.shields.io/github/license/nguyenducvuongg/ComfyUIonColab)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/nguyenducvuongg/ComfyUIonColab?style=social)](https://github.com/nguyenducvuongg/ComfyUIonColab)

**Giải pháp chạy ComfyUI tối ưu, ổn định và nhanh nhất trên Google Colab với tích hợp Google Drive toàn diện và cổng SSH-Tailscale chạy thẳng về máy cá nhân.**

[Tính Năng Nổi Bật](#-tính-năng-nổi-bật) • [Khởi Chạy Nhanh](#-hướng-dẫn-khởi-chạy) • [Kết Nối SSH-Tailscale](#-kết-nối-ssh-tailscale-chạy-thẳng-về-máy-cá-nhân) • [Cấu Trúc Thư Mục](#-cấu-trúc-thư-mục-lưu-trữ-trên-google-drive) • [English Guide](#-english-guide)

</div>

---

## 🌟 Tính Năng Nổi Bật

- ⚡ **Khởi Động Siêu Tốc với `uv`, `aria2` & `zstd`**: Tăng tốc cài đặt thư viện Python 10-50 lần, bỏ qua bước cài lại khi công cụ đã sẵn sàng, nén/giải nén backup bằng `.tar.zst` đa luồng.
- 🧠 **Tối Ưu Hóa VRAM & RAM Kernel (Chống OOM & Tràn Bộ Nhớ)**: Cấu hình `PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"`, kích hoạt **TCMalloc** (`google-perftools`), kiểm tra CUDA/Transformers qua subprocess để tiết kiệm ~1.5 GB RAM cho kernel Colab.
- 🔐 **Đa Đường Truyền Bảo Mật: Colab-Proxy / SSH-Tailscale / Cloudflare**:
  - **Colab-Proxy** *(Mặc định)*: Kết nối trực tiếp qua tài khoản Google.
  - **SSH-Tailscale** *(Mới)*: Mở cổng SSH mã hóa qua mạng riêng Tailscale WireGuard, chuyển tiếp thẳng ComfyUI về `http://127.0.0.1:8188` trên máy cá nhân (hỗ trợ cả Terminal, SFTP/rsync, VS Code / Antigravity Remote-SSH), mọi Models/Input/Output/Workflow vẫn lưu trực tiếp trên Google Drive.
  - **Cloudflare Quick Tunnel**: Tạo link công khai dự phòng qua `cloudflared` (tích hợp drain pipe chống treo).
- 📜 **Live Log Streaming Thời Gian Thực**: Stream log theo chunk hỗ trợ thanh tiến trình `tqdm` (`it/s`), kết nối WebSocket và quá trình nạp mô hình.
- 💾 **Smart Live Backup (.tar.zst + Manifest)**: Tự động khôi phục Custom Nodes từ Google Drive; phát hiện node mới cài từ ComfyUI-Manager, lưu kèm `custom_nodes_manifest.json` và tự động bỏ qua `.venv`/`node_modules`/file nặng >50 MB.
- 📁 **Lưu Trữ Phẳng An Toàn Tuyệt Đối (Collision-Safe Storage)**: Gom tệp chuẩn phẳng cho `input/` và `output/`, giữ nguyên mọi tệp trên Google Drive `MyDrive/ComfyUI_Data/`.
- 🔄 **Động Cơ Đồng Bộ 1 Chiều Output ➔ Input**: Tự động chuyển ảnh/video kết xuất từ `output/` sang `input/` thời gian thực.
- 🎨 **Tự Động Cập Nhật Pixaroma Mới Nhất & Thư Viện Workflow Mẫu Chống Trùng Lặp (`Alt + W`)**: Đồng bộ 26+ workflow mẫu chính hãng vào `workflows/Pixaroma/` bằng SHA256 deduplication.
- 📥 **ComfyUI Model Downloader Chuyên Dụng**: Tải mô hình đa luồng từ Civitai (hỗ trợ API Key & Colab Secrets, che token khỏi log) và HuggingFace (hỗ trợ Token & Resume).

---

## 🚀 Hướng Dẫn Khởi Chạy

### 1. Khởi Chạy ComfyUI Chính
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/nguyenducvuongg/ComfyUIonColab/blob/main/ComfyUI_Colab_Ultra.ipynb)

1. Chọn môi trường GPU: **Runtime** ➔ **Change runtime type** ➔ **T4 GPU** (hoặc L4 / A100).
2. Chạy **Bước 1**: Kết nối Google Drive, cài đặt môi trường và khôi phục Custom Nodes.
3. Chạy **Bước 2**: Chọn `Tunnel_Method` (`Colab-Proxy`, `SSH-Tailscale`, hoặc `Cloudflare`) và khởi động ComfyUI.

### 2. Tải Mô Hình AI Tốc Độ Cao
[![Open Model Downloader](https://img.shields.io/badge/Colab-Model_Downloader-orange?logo=google-colab)](https://colab.research.google.com/github/nguyenducvuongg/ComfyUIonColab/blob/main/ComfyUI_Model_Downloader.ipynb)

---

## 🔐 Kết Nối SSH-Tailscale (Chạy Thẳng Về Máy Cá Nhân)

Chế độ **SSH-Tailscale** chạy ComfyUI trên GPU của Google Colab nhưng forward cổng thẳng về **`http://127.0.0.1:8188`** trên máy cá nhân (macOS / Windows / Linux) qua mạng riêng WireGuard:
- **0đ, không cần mở port router, không cần tên miền riêng**.
- **Toàn bộ Models, Input, Output, Workflows vẫn đọc/ghi trực tiếp trên Google Drive** (`MyDrive/ComfyUI_Data/`).
- **Bảo mật tuyệt đối**: Mặc định `Local_Only_Bind = True` khiến ComfyUI chỉ lắng nghe `127.0.0.1:8188` trên Colab và `sshd` chỉ chấp nhận SSH Key trên `127.0.0.1:2222`.

### Thiết lập 1 lần duy nhất
1. Cài app **Tailscale** trên máy cá nhân và đăng nhập tài khoản Tailscale.
2. Vào [Tailscale Admin Console ➔ Settings ➔ Keys](https://login.tailscale.com/admin/settings/keys) tạo 1 **Auth Key** (bật **Reusable** + **Ephemeral**).
3. Dán key đó vào **Colab Secrets** với tên `TAILSCALE_AUTHKEY` (khuyên dùng) hoặc nhập trực tiếp vào ô `Tailscale_Auth_Key` ở Bước 2 (hệ thống tự lưu lại vào Drive).
4. *(Tùy chọn)* Dán nội dung file `~/.ssh/id_ed25519.pub` của máy bạn vào `SSH_Public_Key` hoặc Colab Secret `SSH_PUBLIC_KEY`. Nếu bỏ trống, hệ thống sẽ tự tạo cặp key `colab_ssh_key` trên Drive (`MyDrive/ComfyUI_Data/config/`).

### Kết nối từ máy cá nhân
Sau khi Bước 2 trên Colab báo **`CỔNG SSH-TAILSCALE ĐÃ SẴN SÀNG`**:

- **Cách 1 (Khuyên dùng — 1-click auto-reconnect + tự mở trình duyệt)**:
  ```bash
  python3 scripts/local_connect.py
  ```
  *Nếu muốn tự động kéo luôn ảnh/video vừa render từ Google Drive `output/` trên Colab về thư mục máy cá nhân:*
  ```bash
  python3 scripts/local_connect.py --sync-output ~/ComfyUI_Outputs
  ```
- **Cách 2 (Chạy lệnh SSH trực tiếp hiển thị trên cell Colab)**:
  ```bash
  ssh -N -L 127.0.0.1:8188:127.0.0.1:8188 -p 2222 root@<TAILSCALE_IP_OR_HOST>
  ```
- Sau đó mở trình duyệt trên máy cá nhân tại **`http://127.0.0.1:8188`**.
- Để lấy cấu hình cho **VS Code / Antigravity / Cursor Remote-SSH**, chạy:
  ```bash
  python3 scripts/local_connect.py --print-ssh-config
  ```

---

## 📁 Cấu Trúc Thư Mục Lưu Trữ Trên Google Drive

Dữ liệu của bạn được lưu trữ vĩnh viễn tại `MyDrive/ComfyUI_Data/`:

```text
ComfyUI_Data/
├── backup/
│   ├── custom_nodes_backup.tar.zst # Bản sao lưu Zstandard đa luồng (tương thích ngược .zip)
│   └── custom_nodes_manifest.json  # Lưu remote URL & commit hash của các node đã cài
├── config/
│   ├── tokens.json                 # Civitai Key, HF Token & Tailscale Auth Key
│   ├── authorized_keys             # SSH Public Keys được phép kết nối
│   ├── ssh_endpoint.json           # Thông tin Tailscale IP / Host / Port cho local_connect.py
│   └── batch_links.txt             # Danh sách tải mô hình hàng loạt
├── input/                          # Thư mục đầu vào (ảnh, video, audio)
├── output/                         # Thư mục kết xuất hình ảnh & video (lưu trực tiếp lên Drive)
├── user/
│   └── default/
│       ├── comfy.settings.json     # Cấu hình giao diện (Locale: en)
│       └── workflows/              # Toàn bộ file workflow JSON lưu trữ tại đây
└── models/                         # 37 danh mục thư mục model AI chuẩn hóa
```

---

## 🌐 English Guide

### Quick Start
1. Open `ComfyUI_Colab_Ultra.ipynb` in Google Colab and select a GPU runtime (`T4`, `L4`, or `A100`).
2. Run **Step 1** to mount Google Drive, install dependencies with `uv`, and restore custom nodes (`.tar.zst` / `.zip`).
3. Run **Step 2** and choose:
   - **`Colab-Proxy`** for instant browser access inside your Google session.
   - **`SSH-Tailscale`** to tunnel ComfyUI directly to `http://127.0.0.1:8188` on your personal machine (`python3 scripts/local_connect.py`), with persistent Google Drive storage for models, inputs, outputs, and workflows.
   - **`Cloudflare`** for a temporary public tunnel URL.

---

## 📄 License

Dự án được phát hành dưới giấy phép [MIT License](LICENSE).
Mọi đóng góp (Pull Request, Issue) đều được hoan nghênh tại [GitHub Repository](https://github.com/nguyenducvuongg/ComfyUIonColab.git).
