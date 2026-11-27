"""
Quản lý SSH Server (OpenSSH) & Tailscale Mesh Tunnel trên Google Colab:
- Chạy tailscaled ở chế độ userspace-networking (tương thích container không có /dev/net/tun).
- Bật sshd độc lập trên 127.0.0.1:2222 (chỉ dùng SSH Key, tắt password, UsePAM no).
- Lưu giữ SSH Host Key & Client Key bền vững trên Google Drive để không bị lỗi đổi fingerprint giữa các phiên.
- Xuất endpoint JSON lên Drive để máy cá nhân kết nối 1-click về http://127.0.0.1:8188.
"""

from datetime import datetime, timezone
import getpass
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time

from .config import DEFAULT_COMFYUI_DIR, DEFAULT_DRIVE_DATA_DIR, DEFAULT_SSH_PORT, DEFAULT_TAILSCALE_HOSTNAME
from .environment import get_colab_secret

_SSH_PROCESSES = []
_SSH_WATCHDOG_STOP = None
_SSH_LOCK = threading.Lock()


def _get_tokens_path(data_dir):
    return os.path.join(data_dir, "config", "tokens.json")


def resolve_tailscale_auth_key(data_dir, explicit_key=""):
    """
    Lấy Tailscale Auth Key theo thứ tự ưu tiên:
    1. Tham số truyền trực tiếp (và lưu vào Drive tokens.json cho lần sau).
    2. Google Colab Secret (TAILSCALE_AUTHKEY / TS_AUTHKEY).
    3. Drive tokens.json.
    """
    tokens_file = _get_tokens_path(data_dir)
    saved = {}
    if os.path.exists(tokens_file):
        try:
            with open(tokens_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
        except Exception:
            saved = {}

    clean_explicit = (explicit_key or "").strip()
    if clean_explicit:
        saved["tailscale_authkey"] = clean_explicit
        try:
            os.makedirs(os.path.dirname(tokens_file), exist_ok=True)
            tmp_file = tokens_file + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(saved, f, indent=2)
            os.replace(tmp_file, tokens_file)
        except Exception:
            pass
        return clean_explicit

    secret_key = get_colab_secret("TAILSCALE_AUTHKEY") or get_colab_secret("TS_AUTHKEY")
    if secret_key:
        return secret_key

    return str(saved.get("tailscale_authkey", "")).strip()


def resolve_ssh_keys(data_dir, explicit_public_key="", ssh_dir=None):
    """
    Thu thập SSH Public Keys hợp lệ và đồng bộ vào authorized_keys.
    Nếu người dùng chưa từng tạo key, tự sinh cặp ed25519 lưu trên Drive để dùng ngay.
    Trả về (danh_sach_public_keys, duong_dan_private_key_tu_sinh_hoac_None).
    """
    config_dir = os.path.join(data_dir, "config")
    os.makedirs(config_dir, exist_ok=True)
    drive_auth_file = os.path.join(config_dir, "authorized_keys")
    generated_priv_key = os.path.join(config_dir, "colab_ssh_key")
    generated_pub_key = generated_priv_key + ".pub"

    keys = []
    for raw in ((explicit_public_key or "").strip(), get_colab_secret("SSH_PUBLIC_KEY")):
        if raw:
            for line in raw.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and line not in keys:
                    keys.append(line)

    if os.path.exists(drive_auth_file):
        try:
            with open(drive_auth_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and line not in keys:
                        keys.append(line)
        except Exception:
            pass

    auto_generated_path = None
    if not keys:
        if not (os.path.exists(generated_priv_key) and os.path.exists(generated_pub_key)):
            if shutil.which("ssh-keygen"):
                subprocess.run(
                    [
                        "ssh-keygen", "-t", "ed25519", "-N", "",
                        "-C", "comfycolab-tailscale", "-f", generated_priv_key,
                    ],
                    capture_output=True,
                    check=False,
                )
        if os.path.exists(generated_pub_key):
            try:
                os.chmod(generated_priv_key, 0o600)
            except OSError:
                pass
            with open(generated_pub_key, "r", encoding="utf-8") as f:
                pub_line = f.read().strip()
            if pub_line:
                keys.append(pub_line)
                auto_generated_path = generated_priv_key

    # Lưu lại Drive authorized_keys để đồng bộ xuyên suốt các phiên
    if keys:
        try:
            tmp_drive_auth = drive_auth_file + ".tmp"
            with open(tmp_drive_auth, "w", encoding="utf-8") as f:
                f.write("\n".join(keys) + "\n")
            os.replace(tmp_drive_auth, drive_auth_file)
        except Exception:
            pass

    target_ssh_dir = ssh_dir or os.path.expanduser("~/.ssh")
    os.makedirs(target_ssh_dir, mode=0o700, exist_ok=True)
    try:
        os.chmod(target_ssh_dir, 0o700)
    except OSError:
        pass

    local_auth_file = os.path.join(target_ssh_dir, "authorized_keys")
    with open(local_auth_file, "w", encoding="utf-8") as f:
        f.write("\n".join(keys) + ("\n" if keys else ""))
    try:
        os.chmod(local_auth_file, 0o600)
    except OSError:
        pass

    return keys, auto_generated_path


def ensure_persistent_host_keys(data_dir, ssh_runtime_dir="/tmp/comfycolab_ssh"):
    """
    Sinh và lưu trữ SSH host keys trên Drive để không đổi fingerprint mỗi lần bật lại Colab.
    Bản runtime được đặt trong /tmp với quyền 0600 (vì Google Drive FUSE không giữ chuẩn POSIX chmod).
    """
    drive_host_dir = os.path.join(data_dir, "config", "ssh_host_keys")
    os.makedirs(drive_host_dir, exist_ok=True)
    os.makedirs(ssh_runtime_dir, mode=0o700, exist_ok=True)

    runtime_keys = []
    for key_type in ("ed25519", "rsa"):
        key_name = f"ssh_host_{key_type}_key"
        drive_priv = os.path.join(drive_host_dir, key_name)
        drive_pub = drive_priv + ".pub"
        rt_priv = os.path.join(ssh_runtime_dir, key_name)
        rt_pub = rt_priv + ".pub"

        if not os.path.exists(drive_priv) and shutil.which("ssh-keygen"):
            subprocess.run(
                ["ssh-keygen", "-t", key_type, "-N", "", "-f", rt_priv],
                capture_output=True,
                check=False,
            )
            if os.path.exists(rt_priv):
                try:
                    shutil.copy2(rt_priv, drive_priv)
                    if os.path.exists(rt_pub):
                        shutil.copy2(rt_pub, drive_pub)
                except Exception:
                    pass
        elif os.path.exists(drive_priv):
            try:
                shutil.copy2(drive_priv, rt_priv)
                if os.path.exists(drive_pub):
                    shutil.copy2(drive_pub, rt_pub)
            except Exception:
                pass

        if os.path.exists(rt_priv):
            try:
                os.chmod(rt_priv, 0o600)
            except OSError:
                pass
            runtime_keys.append(rt_priv)

    return runtime_keys


def write_ssh_environment(ssh_dir=None, data_dir=DEFAULT_DRIVE_DATA_DIR, comfyui_dir=DEFAULT_COMFYUI_DIR):
    """Ghi các biến môi trường CUDA/Python/ComfyUI vào ~/.ssh/environment để phiên SSH nhận đủ GPU."""
    target_ssh_dir = ssh_dir or os.path.expanduser("~/.ssh")
    os.makedirs(target_ssh_dir, mode=0o700, exist_ok=True)
    env_file = os.path.join(target_ssh_dir, "environment")

    keys_to_export = [
        "PATH", "LD_LIBRARY_PATH", "PYTHONPATH", "CUDA_HOME",
        "PYTORCH_CUDA_ALLOC_CONF", "TZ", "HF_HOME", "TORCH_HOME",
    ]
    lines = []
    for k in keys_to_export:
        val = os.environ.get(k)
        if val:
            clean_val = str(val).replace("\n", " ")
            lines.append(f"{k}={clean_val}")
    lines.append(f"COMFYUI_DIR={comfyui_dir}")
    lines.append(f"COMFYUI_DATA_DIR={data_dir}")

    with open(env_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    try:
        os.chmod(env_file, 0o600)
    except OSError:
        pass
    return env_file


def build_sshd_config(
    ssh_port=DEFAULT_SSH_PORT,
    authorized_keys_file="/root/.ssh/authorized_keys",
    host_keys=None,
    pid_file="/tmp/comfycolab_sshd.pid",
    listen_address="127.0.0.1",
):
    """Tạo nội dung cấu hình sshd tách biệt, bảo mật cao (key-only, UsePAM no)."""
    lines = [
        f"Port {int(ssh_port)}",
        f"ListenAddress {listen_address}",
        f"PidFile {pid_file}",
        f"AuthorizedKeysFile {authorized_keys_file}",
    ]
    for hk in (host_keys or []):
        lines.append(f"HostKey {hk}")
    lines.extend([
        "PasswordAuthentication no",
        "KbdInteractiveAuthentication no",
        "PubkeyAuthentication yes",
        "PermitRootLogin prohibit-password",
        "AllowTcpForwarding yes",
        "GatewayPorts no",
        "PermitUserEnvironment yes",
        "Subsystem sftp internal-sftp",
        "ClientAliveInterval 30",
        "ClientAliveCountMax 3",
        "UsePAM no",
    ])
    return "\n".join(lines) + "\n"


def _find_sshd_binary():
    for cand in (shutil.which("sshd"), "/usr/sbin/sshd", "/usr/bin/sshd"):
        if cand and os.path.exists(cand):
            return cand
    return None


def ensure_openssh_server():
    """Đảm bảo OpenSSH Server đã được cài đặt trên Colab."""
    sshd_bin = _find_sshd_binary()
    if sshd_bin:
        return sshd_bin
    if shutil.which("apt-get"):
        print("  📦 [SSH] Đang cài đặt openssh-server...")
        subprocess.run(
            "apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server",
            shell=True,
            capture_output=True,
            check=False,
        )
    return _find_sshd_binary()


def ensure_tailscale_installed():
    """Đảm bảo tailscale và tailscaled đã được cài đặt."""
    if shutil.which("tailscale") and shutil.which("tailscaled"):
        return True
    print("  📦 [Tailscale] Đang cài đặt Tailscale...")
    res = subprocess.run(
        "curl -fsSL https://tailscale.com/install.sh | DEBIAN_FRONTEND=noninteractive sh",
        shell=True,
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode == 0 and shutil.which("tailscale") and shutil.which("tailscaled"):
        print("  ✅ [Tailscale] Đã cài đặt thành công.")
        return True
    print(f"  ⚠️ [Tailscale] Lỗi cài đặt tự động: {(res.stderr or '')[:200]}")
    return False


def _wait_local_port(port, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        try:
            if sock.connect_ex(("127.0.0.1", int(port))) == 0:
                return True
        finally:
            sock.close()
        time.sleep(0.25)
    return False


def _wait_file(path, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if os.path.exists(path):
            return True
        time.sleep(0.25)
    return False


def stop_ssh_tunnel_processes():
    """Dừng gọn các tiến trình sshd / tailscaled do module quản lý."""
    global _SSH_WATCHDOG_STOP
    if _SSH_WATCHDOG_STOP is not None:
        _SSH_WATCHDOG_STOP.set()
        _SSH_WATCHDOG_STOP = None

    with _SSH_LOCK:
        procs = list(_SSH_PROCESSES)
        _SSH_PROCESSES.clear()

    for proc in procs:
        try:
            if proc.poll() is None:
                proc.terminate()
        except Exception:
            pass
    for proc in procs:
        try:
            if proc.poll() is None:
                proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def build_tailscaled_command(state_dir, socket_path, socks5_port=1055):
    """Tạo lệnh khởi chạy tailscaled với chế độ userspace-networking an toàn cho Colab."""
    return [
        "tailscaled",
        "--tun=userspace-networking",
        f"--statedir={state_dir}",
        f"--socket={socket_path}",
        f"--socks5-server=127.0.0.1:{socks5_port}",
    ]


def build_tailscale_up_command(socket_path, auth_key, hostname=DEFAULT_TAILSCALE_HOSTNAME, enable_ts_ssh=True):
    """Tạo lệnh tailscale up cho Colab."""
    cmd = [
        "tailscale",
        f"--socket={socket_path}",
        "up",
        f"--auth-key={auth_key}",
        f"--hostname={hostname}",
        "--accept-dns=false",
    ]
    if enable_ts_ssh:
        cmd.append("--ssh")
    return cmd


def _start_sshd_process(sshd_bin, config_path):
    os.makedirs("/run/sshd", mode=0o755, exist_ok=True)
    log_path = os.path.join(tempfile.gettempdir(), "comfycolab_sshd.log")
    log_f = open(log_path, "ab")
    proc = subprocess.Popen(
        [sshd_bin, "-D", "-e", "-f", config_path],
        stdout=log_f,
        stderr=subprocess.STDOUT,
    )
    log_f.close()
    with _SSH_LOCK:
        _SSH_PROCESSES.append(proc)
    return proc


def _start_tailscaled_process(state_dir, socket_path):
    os.makedirs(state_dir, mode=0o700, exist_ok=True)
    log_path = os.path.join(tempfile.gettempdir(), "comfycolab_tailscaled.log")
    log_f = open(log_path, "ab")
    proc = subprocess.Popen(
        build_tailscaled_command(state_dir, socket_path),
        stdout=log_f,
        stderr=subprocess.STDOUT,
    )
    log_f.close()
    with _SSH_LOCK:
        _SSH_PROCESSES.append(proc)
    return proc


def write_ssh_endpoint_info(
    data_dir,
    tailscale_ip="",
    magic_dns="",
    hostname=DEFAULT_TAILSCALE_HOSTNAME,
    ssh_port=DEFAULT_SSH_PORT,
    comfy_port=8188,
    ssh_user="root",
    key_hint="",
):
    """Ghi thông tin kết nối SSH-Tailscale mới nhất vào Drive để client local tự đọc."""
    target_host = tailscale_ip or magic_dns or hostname
    forward_cmd = f"ssh -N -L 127.0.0.1:{comfy_port}:127.0.0.1:{comfy_port} -p {ssh_port} {ssh_user}@{target_host}"
    if key_hint:
        forward_cmd = f"ssh -i \"{key_hint}\" -N -L 127.0.0.1:{comfy_port}:127.0.0.1:{comfy_port} -p {ssh_port} {ssh_user}@{target_host}"

    payload = {
        "method": "SSH-Tailscale",
        "hostname": hostname,
        "magic_dns": magic_dns,
        "tailscale_ip": tailscale_ip,
        "ssh_user": ssh_user,
        "ssh_port": int(ssh_port),
        "comfy_port": int(comfy_port),
        "local_url": f"http://127.0.0.1:{comfy_port}",
        "remote_output_dir": os.path.join(data_dir, "output"),
        "ssh_forward_cmd": forward_cmd,
        "key_hint": key_hint,
        "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }
    endpoint_path = os.path.join(data_dir, "config", "ssh_endpoint.json")
    os.makedirs(os.path.dirname(endpoint_path), exist_ok=True)
    tmp_path = endpoint_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, endpoint_path)
    return endpoint_path, payload


def start_tailscale_ssh_tunnel(
    data_dir=DEFAULT_DRIVE_DATA_DIR,
    comfyui_dir=DEFAULT_COMFYUI_DIR,
    comfy_port=8188,
    ssh_port=DEFAULT_SSH_PORT,
    tailscale_auth_key="",
    tailscale_hostname=DEFAULT_TAILSCALE_HOSTNAME,
    ssh_public_key="",
):
    """
    Khởi động đầy đủ OpenSSH Server + Tailscale Userspace Daemon cho kết nối Local PC:
    Trả về dict thông tin endpoint nếu thành công, hoặc raise RuntimeError khi thiếu cấu hình.
    """
    global _SSH_WATCHDOG_STOP
    stop_ssh_tunnel_processes()

    auth_key = resolve_tailscale_auth_key(data_dir, tailscale_auth_key)
    if not auth_key:
        raise ValueError(
            "Thiếu Tailscale Auth Key! Hãy nhập vào ô 'Tailscale_Auth_Key' hoặc tạo Colab Secret 'TAILSCALE_AUTHKEY'."
        )

    print("\n[SSH-Tailscale] 🔐 Đang thiết lập cổng SSH bảo mật kết nối Colab -> Máy cá nhân...")

    sshd_bin = ensure_openssh_server()
    if not sshd_bin:
        raise RuntimeError("Không tìm thấy hoặc không thể cài đặt OpenSSH Server (sshd).")

    if not ensure_tailscale_installed():
        raise RuntimeError("Không thể cài đặt Tailscale trên Colab runtime.")

    ssh_runtime_dir = os.path.join(tempfile.gettempdir(), "comfycolab_ssh")
    os.makedirs(ssh_runtime_dir, mode=0o700, exist_ok=True)

    keys, auto_priv_key = resolve_ssh_keys(data_dir, explicit_public_key=ssh_public_key)
    if not keys:
        raise RuntimeError("Không thể tạo hoặc nạp SSH Public Key vào authorized_keys.")

    host_keys = ensure_persistent_host_keys(data_dir, ssh_runtime_dir=ssh_runtime_dir)
    if not host_keys and shutil.which("ssh-keygen"):
        subprocess.run(["ssh-keygen", "-A"], capture_output=True, check=False)

    write_ssh_environment(data_dir=data_dir, comfyui_dir=comfyui_dir)

    local_auth_file = os.path.expanduser("~/.ssh/authorized_keys")
    sshd_pid = os.path.join(ssh_runtime_dir, "sshd.pid")
    sshd_cfg_path = os.path.join(ssh_runtime_dir, "sshd_config")
    with open(sshd_cfg_path, "w", encoding="utf-8") as f:
        f.write(
            build_sshd_config(
                ssh_port=ssh_port,
                authorized_keys_file=local_auth_file,
                host_keys=host_keys,
                pid_file=sshd_pid,
                listen_address="127.0.0.1",
            )
        )

    sshd_proc = _start_sshd_process(sshd_bin, sshd_cfg_path)
    if not _wait_local_port(ssh_port, timeout=10.0):
        raise RuntimeError(f"OpenSSH Server không thể lắng nghe trên cổng nội bộ {ssh_port}.")
    print(f"  ✅ [SSH] OpenSSH Server đã sẵn sàng trên 127.0.0.1:{ssh_port} (Key-only).")

    ts_dir = os.path.join(tempfile.gettempdir(), "comfycolab_tailscale")
    ts_state = os.path.join(ts_dir, "state")
    ts_sock = os.path.join(ts_dir, "tailscaled.sock")
    ts_proc = _start_tailscaled_process(ts_state, ts_sock)
    if not _wait_file(ts_sock, timeout=15.0):
        raise RuntimeError("tailscaled không khởi tạo được Unix socket.")

    up_res = subprocess.run(
        build_tailscale_up_command(ts_sock, auth_key, hostname=tailscale_hostname, enable_ts_ssh=True),
        capture_output=True,
        text=True,
        timeout=35,
        check=False,
    )
    if up_res.returncode != 0:
        # Fallback nếu Tailnet Policy chưa bật Tailscale SSH: vẫn dùng được sshd qua cổng 2222
        up_res = subprocess.run(
            build_tailscale_up_command(ts_sock, auth_key, hostname=tailscale_hostname, enable_ts_ssh=False),
            capture_output=True,
            text=True,
            timeout=35,
            check=False,
        )
        if up_res.returncode != 0:
            err_msg = (up_res.stderr or up_res.stdout or "tailscale up failed").strip()
            raise RuntimeError(f"Kết nối Tailscale thất bại: {err_msg[:240]}")

    ip_res = subprocess.run(
        ["tailscale", f"--socket={ts_sock}", "ip", "-4"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    tailscale_ip = ip_res.stdout.strip().splitlines()[0].strip() if ip_res.returncode == 0 and ip_res.stdout.strip() else ""

    magic_dns = ""
    st_res = subprocess.run(
        ["tailscale", f"--socket={ts_sock}", "status", "--json"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if st_res.returncode == 0 and st_res.stdout.strip():
        try:
            st_data = json.loads(st_res.stdout)
            dns_raw = (st_data.get("Self") or {}).get("DNSName", "")
            magic_dns = dns_raw.rstrip(".")
        except Exception:
            pass

    ssh_user = getpass.getuser() or "root"
    key_hint = auto_priv_key or ""
    endpoint_path, payload = write_ssh_endpoint_info(
        data_dir=data_dir,
        tailscale_ip=tailscale_ip,
        magic_dns=magic_dns,
        hostname=tailscale_hostname,
        ssh_port=ssh_port,
        comfy_port=comfy_port,
        ssh_user=ssh_user,
        key_hint=key_hint,
    )

    # Watchdog giữ sshd & tailscaled luôn sống suốt phiên Colab
    stop_ev = threading.Event()
    _SSH_WATCHDOG_STOP = stop_ev

    def _watchdog():
        nonlocal sshd_proc, ts_proc
        while not stop_ev.is_set():
            if sshd_proc.poll() is not None:
                try:
                    sshd_proc = _start_sshd_process(sshd_bin, sshd_cfg_path)
                except Exception:
                    pass
            if ts_proc.poll() is not None:
                try:
                    ts_proc = _start_tailscaled_process(ts_state, ts_sock)
                    if _wait_file(ts_sock, timeout=10.0):
                        subprocess.run(
                            build_tailscale_up_command(ts_sock, auth_key, hostname=tailscale_hostname, enable_ts_ssh=False),
                            capture_output=True,
                            timeout=25,
                            check=False,
                        )
                except Exception:
                    pass
            stop_ev.wait(10.0)

    threading.Thread(target=_watchdog, daemon=True).start()
    print(f"  💾 Đã ghi cấu hình kết nối vào Drive: {endpoint_path}")
    return payload
