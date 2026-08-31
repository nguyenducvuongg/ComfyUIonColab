"""
ComfyColab Core Engine Package
Tối ưu và nâng cấp toàn diện cho việc chạy ComfyUI và tải mô hình trên Google Colab.
"""

import os
import sys
from .config import (
    DEFAULT_COMFYUI_DIR,
    DEFAULT_DRIVE_DATA_DIR,
    DEFAULT_LOCAL_DATA_DIR
)
from .environment import (
    setup_timezone,
    mount_google_drive,
    install_system_dependencies,
    clone_or_update_comfyui,
    install_comfyui_requirements,
    verify_pytorch_cuda,
    ensure_transformers_compatibility,
    enable_tcmalloc
)
from .storage import (
    setup_model_symlinks,
    setup_io_directories,
    setup_user_and_workflows
)
from .patches import apply_all_patches
from .custom_nodes import (
    restore_custom_nodes_backup,
    setup_all_custom_nodes,
    create_compact_nodes_backup,
    install_custom_nodes_requirements
)
from .sync_daemon import (
    start_output_to_input_sync_daemon,
    start_custom_nodes_backup_daemon
)
from .tunnel import run_comfyui
from .downloader import (
    scan_model_folders,
    load_or_save_tokens,
    download_model_file,
    process_batch_text,
    normalize_folder_name
)

# Biến lưu trạng thái thư mục dữ liệu hiện tại
ACTIVE_DATA_DIR = DEFAULT_DRIVE_DATA_DIR

def launch_setup(
    connect_drive=True,
    drive_path=DEFAULT_DRIVE_DATA_DIR,
    use_backup=True,
    update_nodes=True,
    install_video_nodes=True,
    force_reinstall=False,
    comfyui_dir=DEFAULT_COMFYUI_DIR
):
    """
    Hàm khởi chạy toàn bộ quy trình thiết lập môi trường, Google Drive,
    cập nhật ComfyUI, khôi phục Custom Nodes và kích hoạt Live Sync Daemons.
    """
    global ACTIVE_DATA_DIR
    print("=" * 60)
    print("🚀 BẮT ĐẦU THIẾT LẬP COMFYUI TRÊN GOOGLE COLAB (COMFYCOLAB ULTRA)")
    print("=" * 60)

    # 1. Mount Google Drive
    ACTIVE_DATA_DIR = mount_google_drive(connect_drive, drive_path)

    # 2. Clone / Cập nhật ComfyUI Core
    clone_or_update_comfyui(comfyui_dir)

    # 3. Cài đặt các công cụ hệ thống và requirements
    install_system_dependencies()
    install_comfyui_requirements(comfyui_dir)

    # 4. Thiết lập Symlink thư mục Models trên Drive
    setup_model_symlinks(ACTIVE_DATA_DIR, comfyui_dir)

    # 5. Cấu hình cấu trúc phẳng cho Input/Output và Workflows
    drive_in, drive_out = setup_io_directories(ACTIVE_DATA_DIR, comfyui_dir)
    drive_wf = setup_user_and_workflows(ACTIVE_DATA_DIR, comfyui_dir)

    # 6. Kích hoạt daemon đồng bộ 1 chiều Output -> Input
    start_output_to_input_sync_daemon(drive_out, drive_in)

    # 7. Áp dụng bản vá hệ thống lõi
    apply_all_patches(comfyui_dir)

    # 8. Khôi phục / Cài đặt Custom Nodes
    custom_nodes_dir = os.path.join(comfyui_dir, "custom_nodes")
    restored, backup_zip = restore_custom_nodes_backup(ACTIVE_DATA_DIR, custom_nodes_dir, force_reinstall)

    has_new_nodes = setup_all_custom_nodes(
        custom_nodes_dir,
        update_nodes=update_nodes,
        install_video_nodes=install_video_nodes,
        drive_default_workflows=drive_wf
    )

    # Tạo file backup nhanh nếu có node mới
    if use_backup and (not restored or has_new_nodes or force_reinstall):
        print("💾 Đang nén và cập nhật bản sao lưu Custom Nodes siêu tốc lên Drive...")
        create_compact_nodes_backup(custom_nodes_dir, backup_zip)

    # Kích hoạt daemon Smart Live Backup cho Custom Nodes
    if use_backup:
        start_custom_nodes_backup_daemon(custom_nodes_dir, backup_zip)

    # 9. Cài đặt dependencies cho Custom Nodes & SeedVR2
    install_custom_nodes_requirements(custom_nodes_dir)

    # 10. Kiểm tra PyTorch CUDA & Transformers
    verify_pytorch_cuda()
    ensure_transformers_compatibility()

    print("\n" + "=" * 60)
    print("🎉 HOÀN TẤT THIẾT LẬP! HÃY CHẠY BƯỚC 2 ĐỂ MỞ COMFYUI.")
    print("=" * 60 + "\n")

def start_comfyui_and_tunnel(
    method="Colab-Proxy",
    port=8188,
    pinggy_token="",
    pinggy_server="Auto",
    extra_args="--preview-method auto --listen --enable-cors-header",
    comfyui_dir=DEFAULT_COMFYUI_DIR
):
    """
    Kích hoạt TCMalloc, khởi chạy đường truyền Tunnel và ComfyUI Server.
    """
    global ACTIVE_DATA_DIR
    enable_tcmalloc()

    active_dir = ACTIVE_DATA_DIR
    if not active_dir or not os.path.exists(active_dir):
        if os.path.exists("/content/drive/MyDrive/ComfyUI_Data"):
            active_dir = "/content/drive/MyDrive/ComfyUI_Data"
        else:
            active_dir = DEFAULT_LOCAL_DATA_DIR

    run_comfyui(
        method=method,
        port=port,
        pinggy_token=pinggy_token,
        pinggy_server=pinggy_server,
        extra_args=extra_args,
        data_dir=active_dir,
        comfyui_dir=comfyui_dir
    )

def setup_downloader_env(drive_path=DEFAULT_DRIVE_DATA_DIR):
    """Thiết lập môi trường cho ComfyUI Model Downloader."""
    setup_timezone()
    print("🔗 Đang kết nối Google Drive...")
    from google.colab import drive
    drive.mount('/content/drive')

    os.makedirs(drive_path, exist_ok=True)
    print("📦 Cài đặt công cụ tải đa luồng aria2...")
    import subprocess
    subprocess.run("apt-get update -qq && apt-get install -y -qq aria2", shell=True, check=False)
    print("✅ Hoàn tất thiết lập môi trường tải mô hình!")

def run_downloader_ui(
    download_mode="Single (Tải Đơn Lẻ)",
    skip_existing=True,
    model_url="",
    model_type="checkpoints",
    custom_folder_name="",
    custom_file_name="",
    civitai_api_key="",
    hf_token="",
    drive_path=DEFAULT_DRIVE_DATA_DIR
):
    """Khởi chạy giao diện và tiến trình tải mô hình AI."""
    active_civitai, active_hf = load_or_save_tokens(drive_path, civitai_api_key, hf_token)
    print(f"🔑 Civitai Token: {'Đã kích hoạt' if active_civitai else 'Không có'} | HuggingFace Token: {'Đã kích hoạt' if active_hf else 'Không có'}")

    folders = scan_model_folders(drive_path)
    print(f"🔍 [Quét thư mục Models]: Phát hiện {len(folders)} thư mục khả dụng:")
    print("   " + ", ".join([f"[{f}]" for f in folders]))

    if download_mode == "Single (Tải Đơn Lẻ)":
        target_folder = custom_folder_name.strip() if custom_folder_name.strip() else model_type
        if model_url.strip():
            print(f"\n--- BẮT ĐẦU TẢI ĐƠN LẺ -> [models/{normalize_folder_name(target_folder)}] ---")
            download_model_file(
                model_url,
                target_folder,
                custom_name=custom_file_name,
                base_dir=drive_path,
                civitai_key=active_civitai,
                hf_token=active_hf,
                skip_existing=skip_existing
            )
        else:
            print("\n⚠️ Bạn chưa nhập Model_URL để tải đơn lẻ!")
    else:
        # Batch Mode UI
        try:
            import ipywidgets as widgets
            from IPython.display import display, clear_output
            has_widgets = True
        except ImportError:
            has_widgets = False

        batch_file_path = os.path.join(drive_path, "config", "batch_links.txt")
        os.makedirs(os.path.dirname(batch_file_path), exist_ok=True)

        initial_text = """[checkpoints]\n# https://civitai.com/api/download/models/128713 | DreamShaper_8.safetensors\n\n[loras]\n# dán link lora vào đây\n\n[background_removal]\n# https://huggingface.co/briaai/RMBG-1.4/resolve/main/model.pth | RMBG-1.4.pth\n"""
        if os.path.exists(batch_file_path):
            try:
                with open(batch_file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    if content.strip():
                        initial_text = content
            except Exception:
                pass
        else:
            with open(batch_file_path, "w", encoding="utf-8") as f:
                f.write(initial_text)

        print(f"📁 Tệp danh sách Hàng Loạt trên Drive: {batch_file_path}")
        print("💡 Bạn có thể chỉnh sửa trực tiếp bên dưới rồi bấm BẮT ĐẦU TẢI.\n")

        if has_widgets:
            textarea = widgets.Textarea(
                value=initial_text,
                placeholder="Dán danh sách link theo cú pháp [tên_thư_mục]",
                description="Danh sách:",
                disabled=False,
                layout=widgets.Layout(width='98%', height='250px')
            )

            btn_save_run = widgets.Button(
                description="🚀 BẮT ĐẦU TẢI HÀNG LOẠT",
                button_style="success",
                icon="download",
                layout=widgets.Layout(width='280px', height='42px')
            )
            out = widgets.Output()

            def on_button_click(b):
                with out:
                    clear_output()
                    with open(batch_file_path, "w", encoding="utf-8") as f:
                        f.write(textarea.value)
                    print("💾 Đã lưu danh sách vào Drive. Bắt đầu tải...")
                    process_batch_text(
                        textarea.value,
                        base_dir=drive_path,
                        civitai_key=active_civitai,
                        hf_token=active_hf,
                        skip_existing=skip_existing
                    )

            btn_save_run.on_click(on_button_click)
            display(textarea)
            display(btn_save_run)
            display(out)
        else:
            with open(batch_file_path, "r", encoding="utf-8") as f:
                content = f.read()
            process_batch_text(
                content,
                base_dir=drive_path,
                civitai_key=active_civitai,
                hf_token=active_hf,
                skip_existing=skip_existing
            )
