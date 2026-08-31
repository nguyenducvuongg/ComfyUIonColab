"""
Động cơ đồng bộ nền (Background Sync Daemons):
1. Đồng bộ 1 chiều tức thì Output -> Input để tái sử dụng hình ảnh/video làm đầu vào mà không tốn công upload.
2. Smart Live Backup Daemon cho Custom Nodes cài mới qua ComfyUI-Manager.
"""

import os
import time
import shutil
import threading
from .custom_nodes import create_compact_nodes_backup

def start_output_to_input_sync_daemon(out_dir, in_dir):
    """
    Kích hoạt tiến trình đồng bộ 1 chiều hướng sự kiện từ Output sang Input thời gian thực.
    Tiết kiệm dung lượng và CPU bằng cách kiểm tra kích thước ổn định trước khi copy.
    """
    def _sync_worker():
        synced_files = set(os.listdir(out_dir)) if os.path.exists(out_dir) else set()
        while True:
            try:
                if os.path.exists(out_dir):
                    current_files = list(os.listdir(out_dir))
                    for f in current_files:
                        src_file = os.path.join(out_dir, f)
                        if os.path.isfile(src_file) and not f.startswith('.') and f not in synced_files:
                            try:
                                s1 = os.path.getsize(src_file)
                                time.sleep(0.3)
                                s2 = os.path.getsize(src_file)
                                if s1 == s2 and s1 > 0:
                                    dst_file = os.path.join(in_dir, f)
                                    if not os.path.exists(dst_file):
                                        shutil.copy2(src_file, dst_file)
                                        print(f"\n\033[96m⚡️ [Live Sync] Đã tự động đồng bộ kết quả sang Input: {f}\033[0m")
                                    synced_files.add(f)
                            except Exception:
                                pass
            except Exception:
                pass
            time.sleep(1.0)

    t = threading.Thread(target=_sync_worker, daemon=True)
    t.start()
    print("⚡️ Đã kích hoạt Động cơ Đồng bộ 1 Chiều Output -> Input Thời Gian Thực!")

def start_custom_nodes_backup_daemon(local_nodes_dir, backup_zip_path):
    """
    Tiến trình chạy ngầm phát hiện Custom Node mới cài đặt từ UI (ComfyUI-Manager)
    và tự động nén sao lưu lên Google Drive vĩnh viễn.
    """
    def _sync_worker():
        known_nodes = set(os.listdir(local_nodes_dir)) if os.path.exists(local_nodes_dir) else set()
        while True:
            try:
                if os.path.exists(local_nodes_dir):
                    current_local = set([d for d in os.listdir(local_nodes_dir) if os.path.isdir(os.path.join(local_nodes_dir, d))])
                    new_nodes = current_local - known_nodes
                    if new_nodes:
                        # Đợi 5 giây để git clone hoặc cài đặt node hoàn tất
                        time.sleep(5.0)
                        create_compact_nodes_backup(local_nodes_dir, backup_zip_path)
                        known_nodes = current_local
                        print(f"\n\033[92m[Smart Live Backup] Đã tự động lưu {len(new_nodes)} Custom Node mới ({', '.join(new_nodes)}) lên Google Drive vĩnh viễn!\033[0m")
            except Exception:
                pass
            time.sleep(15.0)

    t = threading.Thread(target=_sync_worker, daemon=True)
    t.start()
    print("⚡️ Đã kích hoạt Smart Live Backup Daemon (Tự động sao lưu mọi node mới lên Drive)!")
