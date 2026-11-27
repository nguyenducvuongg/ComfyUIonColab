#!/usr/bin/env python3
"""
Client kết nối 1-click từ Máy Cá Nhân (macOS / Windows / Linux) tới Google Colab qua SSH-Tailscale:
- Tự động đọc thông tin ssh_endpoint.json từ Google Drive Desktop (hoặc truyền --host trực tiếp).
- Forward cổng ComfyUI trên Colab về http://127.0.0.1:8188 và tự mở trình duyệt.
- Tự động giữ kết nối (auto-reconnect) và tùy chọn đồng bộ thư mục output về máy cá nhân (--sync-output).
"""

import argparse
import glob
import json
import os
import shutil
import socket
import string
import subprocess
import sys
import threading
import time
import webbrowser


def discover_endpoint_paths():
    """Tìm các vị trí có thể chứa ssh_endpoint.json từ Google Drive Desktop."""
    candidates = []
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        candidates.extend(
            sorted(
                glob.glob(
                    os.path.join(
                        home,
                        "Library",
                        "CloudStorage",
                        "GoogleDrive-*",
                        "My Drive",
                        "ComfyUI_Data",
                        "config",
                        "ssh_endpoint.json",
                    )
                )
            )
        )
        candidates.append(os.path.join(home, "Google Drive", "My Drive", "ComfyUI_Data", "config", "ssh_endpoint.json"))
    elif os.name == "nt":
        for drive in string.ascii_uppercase:
            p = f"{drive}:\\My Drive\\ComfyUI_Data\\config\\ssh_endpoint.json"
            if os.path.exists(p):
                candidates.append(p)
    else:
        candidates.append(os.path.join(home, "ComfyUI_Data", "config", "ssh_endpoint.json"))
    return [p for p in candidates if os.path.isfile(p)]


def load_endpoint_config(endpoint_path=None):
    """Đọc ssh_endpoint.json nếu tìm thấy."""
    paths = [endpoint_path] if endpoint_path else discover_endpoint_paths()
    for p in paths:
        if p and os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data["_endpoint_file"] = p
                return data
            except Exception:
                continue
    return {}


def prepare_private_key(explicit_identity="", endpoint_data=None):
    """
    Chuẩn bị private key an toàn: nếu key nằm trên Google Drive Desktop có permission lỏng,
    sao chép sang ~/.ssh/comfycolab_key với chmod 0600 để OpenSSH chấp nhận.
    """
    if explicit_identity:
        src = os.path.expanduser(explicit_identity)
        if not os.path.isfile(src):
            raise FileNotFoundError(f"Không tìm thấy SSH private key: {src}")
    else:
        src = ""
        if endpoint_data and endpoint_data.get("_endpoint_file"):
            drive_key = os.path.join(os.path.dirname(endpoint_data["_endpoint_file"]), "colab_ssh_key")
            if os.path.isfile(drive_key):
                src = drive_key
        if not src:
            return ""

    if os.name == "nt":
        return src

    ssh_dir = os.path.expanduser("~/.ssh")
    os.makedirs(ssh_dir, mode=0o700, exist_ok=True)
    local_copy = os.path.join(ssh_dir, "comfycolab_key")
    try:
        src_real = os.path.realpath(src)
        dst_real = os.path.realpath(local_copy)
        if src_real != dst_real:
            shutil.copy2(src, local_copy)
        os.chmod(local_copy, 0o600)
        return local_copy
    except Exception:
        return src


def build_ssh_forward_command(
    host,
    ssh_port=2222,
    user="root",
    local_port=8188,
    remote_port=8188,
    identity_file="",
):
    """Tạo lệnh ssh -N -L forward cổng từ Colab về 127.0.0.1 máy cá nhân."""
    cmd = [
        "ssh",
        "-N",
        "-L", f"127.0.0.1:{int(local_port)}:127.0.0.1:{int(remote_port)}",
        "-p", str(int(ssh_port)),
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=3",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "StrictHostKeyChecking=accept-new",
    ]
    if identity_file:
        cmd.extend(["-i", identity_file])
    cmd.append(f"{user}@{host}")
    return cmd


def format_ssh_config_block(host, ssh_port=2222, user="root", local_port=8188, remote_port=8188, identity_file=""):
    """Sinh cấu hình ~/.ssh/config dùng cho terminal và VS Code / Antigravity Remote-SSH."""
    lines = [
        "Host colab-comfy",
        f"    HostName {host}",
        f"    User {user}",
        f"    Port {int(ssh_port)}",
        f"    LocalForward 127.0.0.1:{int(local_port)} 127.0.0.1:{int(remote_port)}",
        "    ServerAliveInterval 30",
        "    ServerAliveCountMax 3",
        "    StrictHostKeyChecking accept-new",
    ]
    if identity_file:
        lines.append(f"    IdentityFile {identity_file}")
    return "\n".join(lines) + "\n"


def _is_local_port_open(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        return sock.connect_ex(("127.0.0.1", int(port))) == 0
    finally:
        sock.close()


def _sync_remote_outputs_loop(
    host,
    ssh_port,
    user,
    remote_output_dir,
    local_output_dir,
    identity_file,
    stop_event,
    interval=8.0,
):
    """Tùy chọn đồng bộ file mới từ output/ trên Colab về ổ cứng máy cá nhân qua rsync/sftp."""
    os.makedirs(local_output_dir, exist_ok=True)
    rsync_bin = shutil.which("rsync")
    ssh_opts = f"ssh -p {int(ssh_port)} -o StrictHostKeyChecking=accept-new -o BatchMode=yes"
    if identity_file:
        ssh_opts += f" -i \"{identity_file}\""

    seen = set(os.listdir(local_output_dir))
    while not stop_event.is_set():
        try:
            if rsync_bin:
                src = f"{user}@{host}:{remote_output_dir.rstrip('/')}/"
                subprocess.run(
                    [rsync_bin, "-az", "--ignore-existing", "-e", ssh_opts, src, local_output_dir],
                    capture_output=True,
                    timeout=120,
                    check=False,
                )
            else:
                # Fallback dùng sftp batch nếu Windows chưa cài rsync
                sftp_cmd = [
                    "sftp",
                    "-P", str(int(ssh_port)),
                    "-o", "StrictHostKeyChecking=accept-new",
                    "-o", "BatchMode=yes",
                ]
                if identity_file:
                    sftp_cmd.extend(["-i", identity_file])
                sftp_cmd.append(f"{user}@{host}")
                ls_res = subprocess.run(
                    sftp_cmd,
                    input=f"ls -1 {remote_output_dir}\n",
                    text=True,
                    capture_output=True,
                    timeout=30,
                    check=False,
                )
                if ls_res.returncode == 0:
                    to_fetch = []
                    for line in ls_res.stdout.splitlines():
                        name = os.path.basename(line.strip())
                        if name and not name.startswith((".", "sftp>")) and name not in seen:
                            to_fetch.append(name)
                    if to_fetch:
                        batch = "\n".join(
                            f'get "{remote_output_dir.rstrip("/")}/{n}" "{os.path.join(local_output_dir, n)}"'
                            for n in to_fetch
                        ) + "\n"
                        subprocess.run(sftp_cmd, input=batch, text=True, capture_output=True, timeout=120, check=False)
                        seen.update(to_fetch)
        except Exception:
            pass
        stop_event.wait(interval)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Kết nối cổng SSH-Tailscale từ Google Colab về http://127.0.0.1:8188 trên máy cá nhân."
    )
    parser.add_argument("--endpoint", default="", help="Đường dẫn tới ssh_endpoint.json (mặc định tự tìm trong Google Drive Desktop)")
    parser.add_argument("--host", default="", help="Tailscale IP (100.x.y.z) hoặc hostname (VD: colab-comfy)")
    parser.add_argument("--ssh-port", type=int, default=0, help="Cổng SSH trên Colab (mặc định: 2222)")
    parser.add_argument("--local-port", type=int, default=8188, help="Cổng local trên máy cá nhân (mặc định: 8188)")
    parser.add_argument("--remote-port", type=int, default=0, help="Cổng ComfyUI trên Colab (mặc định: 8188)")
    parser.add_argument("--user", default="", help="SSH user (mặc định: root)")
    parser.add_argument("--identity", default="", help="Đường dẫn SSH private key (tùy chọn)")
    parser.add_argument("--no-browser", action="store_true", help="Không tự động mở trình duyệt")
    parser.add_argument("--print-ssh-config", action="store_true", help="In block ~/.ssh/config cho VS Code / Antigravity Remote-SSH rồi thoát")
    parser.add_argument("--sync-output", default="", help="Thư mục local để tự động kéo file mới từ output/ trên Colab về máy")
    args = parser.parse_args(argv)

    endpoint_data = load_endpoint_config(args.endpoint or None)
    host = args.host or endpoint_data.get("tailscale_ip") or endpoint_data.get("magic_dns") or endpoint_data.get("hostname") or "colab-comfy"
    ssh_port = args.ssh_port or int(endpoint_data.get("ssh_port") or 2222)
    remote_port = args.remote_port or int(endpoint_data.get("comfy_port") or 8188)
    user = args.user or endpoint_data.get("ssh_user") or "root"
    remote_output_dir = endpoint_data.get("remote_output_dir") or "/content/drive/MyDrive/ComfyUI_Data/output"

    identity_file = prepare_private_key(args.identity, endpoint_data)

    if args.print_ssh_config:
        print(
            format_ssh_config_block(
                host=host,
                ssh_port=ssh_port,
                user=user,
                local_port=args.local_port,
                remote_port=remote_port,
                identity_file=identity_file,
            )
        )
        return 0

    if shutil.which("ssh") is None:
        print("❌ Không tìm thấy lệnh 'ssh'. Hãy cài đặt OpenSSH Client trên máy.")
        return 1

    local_url = f"http://127.0.0.1:{args.local_port}"
    print("=" * 64)
    print(f"🔐 Đang kết nối SSH-Tailscale tới {user}@{host}:{ssh_port}")
    print(f"🌐 ComfyUI Local URL: {local_url}")
    if endpoint_data.get("_endpoint_file"):
        print(f"📄 Nguồn cấu hình: {endpoint_data['_endpoint_file']}")
    if identity_file:
        print(f"🔑 SSH Key: {identity_file}")
    print("💡 Nhấn Ctrl+C để ngắt kết nối.")
    print("=" * 64)

    stop_event = threading.Event()
    if args.sync_output:
        print(f"📥 Đang bật tự động đồng bộ output -> {os.path.abspath(args.sync_output)}")
        threading.Thread(
            target=_sync_remote_outputs_loop,
            args=(host, ssh_port, user, remote_output_dir, args.sync_output, identity_file, stop_event),
            daemon=True,
        ).start()

    browser_opened = False
    cmd = build_ssh_forward_command(
        host=host,
        ssh_port=ssh_port,
        user=user,
        local_port=args.local_port,
        remote_port=remote_port,
        identity_file=identity_file,
    )

    try:
        while not stop_event.is_set():
            proc = subprocess.Popen(cmd)
            # Đợi cổng local thông rồi mở trình duyệt lần đầu
            if not args.no_browser and not browser_opened:
                for _ in range(30):
                    if proc.poll() is not None:
                        break
                    if _is_local_port_open(args.local_port):
                        print(f"✅ Đường hầm đã thông! Đang mở {local_url}...")
                        webbrowser.open(local_url)
                        browser_opened = True
                        break
                    time.sleep(0.5)

            exit_code = proc.wait()
            if stop_event.is_set():
                break
            print(f"⚠️ Kết nối SSH vừa ngắt (code={exit_code}). Thử nối lại sau 3 giây...")
            time.sleep(3.0)
    except KeyboardInterrupt:
        print("\n👋 Đã đóng kết nối SSH-Tailscale.")
    finally:
        stop_event.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
