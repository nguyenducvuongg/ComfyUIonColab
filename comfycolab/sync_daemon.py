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

_SYNC_STOP_EVENT = None
_BACKUP_STOP_EVENT = None
_BACKUP_WRITE_LOCK = threading.Lock()

def _stop_existing_event(ev):
    if ev is not None:
        ev.set()

def start_output_to_input_sync_daemon(out_dir, in_dir):
    """
    Kích hoạt tiến trình đồng bộ 1 chiều hướng sự kiện từ Output sang Input thời gian thực.
    Tiết kiệm dung lượng và CPU bằng cách dùng os.scandir và kiểm tra kích thước ổn định trước khi copy.
    """
    global _SYNC_STOP_EVENT
    _stop_existing_event(_SYNC_STOP_EVENT)
    stop_event = threading.Event()
    _SYNC_STOP_EVENT = stop_event

    def _sync_worker():
        try:
            synced_files = {
                entry.name for entry in os.scandir(out_dir)
                if not entry.name.startswith('.') and entry.is_file()
            } if os.path.exists(out_dir) else set()
        except OSError:
            synced_files = set()

        pending_sizes = {}
        while not stop_event.is_set():
            try:
                if os.path.exists(out_dir):
                    with os.scandir(out_dir) as it:
                        for entry in it:
                            f = entry.name
                            if f.startswith('.') or f in synced_files:
                                continue
                            try:
                                if not entry.is_file():
                                    continue
                                size_now = entry.stat().st_size
                                if size_now <= 0:
                                    continue
                                prev_size = pending_sizes.get(f)
                                if prev_size is None or prev_size != size_now:
                                    pending_sizes[f] = size_now
                                    continue
                                # Kích thước ổn định qua 2 chu kỳ -> copy an toàn
                                pending_sizes.pop(f, None)
                                dst_file = os.path.join(in_dir, f)
                                if not os.path.exists(dst_file):
                                    shutil.copy2(entry.path, dst_file)
                                    print(f"\n\033[96m⚡️ [Live Sync] Đã tự động đồng bộ kết quả sang Input: {f}\033[0m")
                                synced_files.add(f)
                            except OSError:
                                pass
            except Exception:
                pass
            stop_event.wait(1.0)

    t = threading.Thread(target=_sync_worker, daemon=True)
    t.start()
    print("⚡️ Đã kích hoạt Động cơ Đồng bộ 1 Chiều Output -> Input Thời Gian Thực!")

def _wait_until_node_install_stable(local_nodes_dir, new_nodes, stop_event, max_wait_s=60):
    """Đợi git clone/install hoàn tất (không còn index.lock và số file ổn định) trước khi nén backup."""
    deadline = time.monotonic() + max_wait_s
    last_count = -1
    stable_ticks = 0
    excluded = {".git", "__pycache__", ".venv", "venv", "node_modules"}
    while time.monotonic() < deadline and not stop_event.is_set():
        locked = False
        file_count = 0
        for node in new_nodes:
            node_path = os.path.join(local_nodes_dir, node)
            if os.path.exists(os.path.join(node_path, ".git", "index.lock")):
                locked = True
                break
            for _, dirs, files in os.walk(node_path):
                dirs[:] = [d for d in dirs if d not in excluded]
                file_count += len(files)
        if not locked and file_count == last_count and file_count > 0:
            stable_ticks += 1
            if stable_ticks >= 2:
                return
        else:
            stable_ticks = 0
        last_count = file_count
        stop_event.wait(3.0)

def start_custom_nodes_backup_daemon(local_nodes_dir, backup_zip_path):
    """
    Tiến trình chạy ngầm phát hiện Custom Node mới cài đặt từ UI (ComfyUI-Manager)
    và tự động nén sao lưu lên Google Drive vĩnh viễn.
    """
    global _BACKUP_STOP_EVENT
    _stop_existing_event(_BACKUP_STOP_EVENT)
    stop_event = threading.Event()
    _BACKUP_STOP_EVENT = stop_event

    def _sync_worker():
        known_nodes = set(os.listdir(local_nodes_dir)) if os.path.exists(local_nodes_dir) else set()
        while not stop_event.is_set():
            try:
                if os.path.exists(local_nodes_dir):
                    current_local = {
                        d for d in os.listdir(local_nodes_dir)
                        if os.path.isdir(os.path.join(local_nodes_dir, d))
                        and not d.startswith(('.', '__'))
                        and not d.endswith(('.tmp', '.cache', '__pycache__'))
                    }
                    new_nodes = current_local - known_nodes
                    if new_nodes:
                        _wait_until_node_install_stable(local_nodes_dir, new_nodes, stop_event)
                        if stop_event.is_set():
                            break
                        with _BACKUP_WRITE_LOCK:
                            create_compact_nodes_backup(local_nodes_dir, backup_zip_path)
                        known_nodes = current_local
                        print(f"\n\033[92m[Smart Live Backup] Đã tự động lưu {len(new_nodes)} Custom Node mới ({', '.join(sorted(new_nodes))}) lên Google Drive vĩnh viễn!\033[0m")
            except Exception:
                pass
            stop_event.wait(15.0)

    t = threading.Thread(target=_sync_worker, daemon=True)
    t.start()
    print("⚡️ Đã kích hoạt Smart Live Backup Daemon (Tự động sao lưu mọi node mới lên Drive)!")
