"""
CLI tiện ích cho ComfyColab:
- doctor: Kiểm tra nhanh môi trường hệ thống, GPU, công cụ nén/mạng, Drive.
- connect: Khởi chạy client kết nối local PC (nếu chạy trên máy cá nhân).
"""

import argparse
import json
import os
import shutil
import sys

from .config import DEFAULT_DRIVE_DATA_DIR
from .environment import find_tcmalloc_path, get_pytorch_cuda_index_url


def run_doctor(data_dir=DEFAULT_DRIVE_DATA_DIR):
    """Kiểm tra nhanh trạng thái môi trường và công cụ."""
    tools = ["git", "uv", "aria2c", "ffmpeg", "unzip", "zstd", "tar", "sshd", "tailscale", "tailscaled"]
    tool_status = {t: bool(shutil.which(t) or (t == "sshd" and os.path.exists("/usr/sbin/sshd"))) for t in tools}

    report = {
        "python": sys.version.split()[0],
        "cuda_index_url": get_pytorch_cuda_index_url(),
        "tcmalloc": find_tcmalloc_path() or "",
        "data_dir_exists": os.path.exists(data_dir),
        "tools": tool_status,
    }
    try:
        usage = shutil.disk_usage("/content" if os.path.exists("/content") else os.getcwd())
        report["local_disk_free_gb"] = round(usage.free / (1024 ** 3), 2)
    except Exception:
        pass
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="comfycolab", description="ComfyColab Ultra CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    doc_p = sub.add_parser("doctor", help="Kiểm tra trạng thái hệ thống & công cụ")
    doc_p.add_argument("--data-dir", default=DEFAULT_DRIVE_DATA_DIR)

    conn_p = sub.add_parser("connect", help="Kết nối từ máy cá nhân tới Colab qua SSH-Tailscale")
    conn_p.add_argument("args", nargs=argparse.REMAINDER)

    parsed = parser.parse_args(argv)
    if parsed.command == "doctor":
        return run_doctor(parsed.data_dir)
    if parsed.command == "connect":
        from scripts.local_connect import main as connect_main
        return connect_main(parsed.args)
    return 0
