"""
Quản lý các đường truyền bảo mật (Tunnel) cho ComfyUI:
- Colab-Proxy: Đường truyền trực tiếp nội bộ Google Colab
- SSH-Tailscale: Đường hầm SSH mã hóa qua Tailscale Mesh nối thẳng về localhost máy cá nhân
- Cloudflare Quick Tunnel: Đường truyền public tạm thời qua cloudflared
"""

import importlib.util
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

try:
    from IPython.display import HTML, display
    HAS_IPYTHON = True
except ImportError:
    HAS_IPYTHON = False
    display = None
    HTML = None

from .config import DEFAULT_COMFYUI_DIR, DEFAULT_DRIVE_DATA_DIR, DEFAULT_SSH_PORT, DEFAULT_TAILSCALE_HOSTNAME
from .custom_nodes import ensure_pixaroma_latest
from .environment import find_tcmalloc_path, get_pytorch_cuda_index_url
from .ssh_tunnel import start_tailscale_ssh_tunnel, stop_ssh_tunnel_processes
from .storage import validate_and_heal_symlinks

_MANAGED_PROCESSES = []
_PROCESS_LOCK = threading.Lock()


def check_port_open(port):
    """Kiểm tra xem dịch vụ đã lắng nghe trên port hay chưa."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        return sock.connect_ex(("127.0.0.1", int(port))) == 0
    finally:
        sock.close()


def wait_for_port(port, timeout=600):
    """Đợi cổng ComfyUI mở hoàn toàn trước khi tạo đường truyền."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if check_port_open(port):
            return True
        time.sleep(1.0)
    return False


def show_success_card(method, url):
    """Hiển thị card giao diện đồ họa đẹp mắt và link truy cập ComfyUI."""
    print(f"\n\033[92m🔗 Link truy cập ComfyUI ({method}):\033[0m \033[94m\033[4m{url}\033[0m")

    html_content = f"""
    <div style='background: linear-gradient(135deg, #181828, #232342); border: 1px solid #3b3b6d; padding: 22px; border-radius: 14px; margin-top: 15px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; box-shadow: 0 8px 24px rgba(0,0,0,0.5); max-width: 560px;'>
      <div style='display: flex; align-items: center; margin-bottom: 14px;'>
        <div style='background-color: #00ff87; width: 14px; height: 14px; border-radius: 50%; margin-right: 12px; box-shadow: 0 0 12px #00ff87; animation: comfy_pulse 1.6s infinite;'></div>
        <h3 style='color: #00ff87; margin: 0; font-size: 16px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;'>ComfyUI Đã Sẵn Sàng!</h3>
      </div>
      <p style='color: #d1d5db; font-size: 13.5px; margin: 0 0 16px 0; line-height: 1.5;'>
        Đường truyền kết nối <b>{method}</b> đã được thiết lập ổn định. Click nút bên dưới để mở giao diện làm việc.
      </p>
      <div style='display: flex; gap: 10px; align-items: center;'>
        <a href='{url}' target='_blank' style='display: inline-block; background: linear-gradient(90deg, #2563eb, #06b6d4); color: white; padding: 11px 24px; border-radius: 8px; text-decoration: none; font-weight: 700; font-size: 13.5px; box-shadow: 0 4px 14px rgba(37, 99, 235, 0.4);'>🚀 MỞ COMFYUI</a>
      </div>
    </div>
    <style>
    @keyframes comfy_pulse {{
      0% {{ transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 255, 135, 0.7); }}
      70% {{ transform: scale(1.05); box-shadow: 0 0 0 10px rgba(0, 255, 135, 0); }}
      100% {{ transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 255, 135, 0.7); }}
    }}
    </style>
    """
    if HAS_IPYTHON and display and HTML:
        display(HTML(html_content))


def show_ssh_tailscale_card(endpoint):
    """Hiển thị link mở thẳng ComfyUI qua Tailscale (0 lệnh ở máy cá nhân) kèm tùy chọn SSH."""
    host = endpoint.get("tailscale_ip") or endpoint.get("magic_dns") or endpoint.get("hostname")
    ssh_port = endpoint.get("ssh_port", DEFAULT_SSH_PORT)
    comfy_port = endpoint.get("comfy_port", 8188)
    ssh_user = endpoint.get("ssh_user", "root")
    magic_dns = endpoint.get("magic_dns", "")
    tailscale_ip = endpoint.get("tailscale_ip", "")
    direct_url = endpoint.get("direct_url") or (f"https://{magic_dns}" if magic_dns else f"http://{host}:{comfy_port}")
    serve_mode = endpoint.get("serve_mode", "https")
    ssh_cmd = endpoint.get("ssh_forward_cmd", "")
    local_url = endpoint.get("local_url", f"http://127.0.0.1:{comfy_port}")

    print("\n" + "=" * 68)
    print("\033[92m🔐 TAILSCALE ĐÃ SẴN SÀNG — MỞ THẲNG TỪ MÁY CÁ NHÂN!\033[0m")
    print(f"  • Mở thẳng trình duyệt (chỉ cần bật app Tailscale): \033[94m\033[4m{direct_url}\033[0m")
    if tailscale_ip:
        print(f"  • Tailscale IP  : {tailscale_ip}")
    if magic_dns:
        print(f"  • MagicDNS      : {magic_dns}")
    if serve_mode == "tcp":
        print("  💡 Mẹo: Bật 'Enable HTTPS' trong Tailscale Admin -> DNS để có link https:// không cần số cổng.")
    print(f"  • (Tùy chọn SSH nếu muốn mở qua {local_url}): {ssh_cmd}")
    print("=" * 68 + "\n")

    html_content = f"""
    <div style='background: linear-gradient(135deg, #0f172a, #1e293b); border: 1px solid #22c55e; padding: 22px; border-radius: 14px; margin-top: 12px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 660px; color: #e2e8f0;'>
      <div style='display:flex;align-items:center;margin-bottom:12px;'>
        <div style='background:#22c55e;width:12px;height:12px;border-radius:50%;margin-right:10px;box-shadow:0 0 10px #22c55e;'></div>
        <h3 style='margin:0;color:#22c55e;font-size:16px;text-transform:uppercase;'>Tailscale Direct Ready (Colab ➔ Máy Cá Nhân)</h3>
      </div>
      <p style='margin:0 0 14px 0;font-size:13.5px;color:#cbd5e1;line-height:1.5;'>
        Chỉ cần bật app <b>Tailscale</b> trên máy cá nhân (không cần gõ lệnh hay chạy script) rồi bấm mở trực tiếp bên dưới:
      </p>
      <div style='margin-bottom:14px;'>
        <a href='{direct_url}' target='_blank' style='display:inline-block;background:linear-gradient(90deg,#16a34a,#0ea5e9);color:white;padding:11px 22px;border-radius:8px;text-decoration:none;font-weight:700;font-size:13.5px;box-shadow:0 4px 14px rgba(22,163,74,0.35);'>🚀 MỞ COMFYUI QUA TAILSCALE ({serve_mode.upper()})</a>
      </div>
      <p style='margin:6px 0;font-size:12.5px;color:#94a3b8;'>
        <b>URL:</b> <code>{direct_url}</code> &nbsp;|&nbsp;
        <b>IP:</b> <code>{tailscale_ip or 'N/A'}</code> &nbsp;|&nbsp;
        <b>SSH:</b> <code>{ssh_user}@{tailscale_ip or magic_dns or host}:{ssh_port}</code>
      </p>
      <details style='margin-top:10px;font-size:12px;color:#94a3b8;'>
        <summary style='cursor:pointer;color:#38bdf8;'>Tùy chọn nâng cao: Forward về {local_url} hoặc VS Code Remote-SSH</summary>
        <div style='background:#020617;border:1px solid #334155;border-radius:8px;padding:9px 11px;margin-top:8px;font-family:monospace;font-size:12px;color:#38bdf8;word-break:break-all;'>
          {ssh_cmd}
        </div>
      </details>
    </div>
    """
    if HAS_IPYTHON and display and HTML:
        display(HTML(html_content))


def _drain_stream(stream, callback=None):
    """Đọc liên tục stdout/stderr để tránh đầy OS pipe buffer (64KB deadlock)."""
    try:
        for raw_line in iter(stream.readline, b""):
            if callback:
                text = raw_line.decode("utf-8", errors="ignore")
                callback(text)
    except Exception:
        pass
    finally:
        try:
            stream.close()
        except Exception:
            pass


def cloudflare_tunnel(port):
    """Khởi chạy Cloudflare Quick Tunnel với cơ chế drain pipe liên tục chống treo."""
    if not wait_for_port(port):
        print("Timeout: Không tìm thấy ComfyUI hoạt động trên port", port)
        return

    print("\n[Cloudflare] Đang tạo đường truyền public...")
    cf_bin = shutil.which("cloudflared") or "/content/cloudflared"
    if cf_bin == "/content/cloudflared" and not os.path.exists(cf_bin):
        print("[Cloudflare] Đang tải cloudflared...")
        dl_url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
        if shutil.which("aria2c"):
            subprocess.run(
                ["aria2c", "-c", "-x", "16", "-s", "16", "-k", "1M", "--console-log-level=error", "-d", "/content", "-o", "cloudflared", dl_url],
                check=False,
            )
        else:
            subprocess.run(["wget", "-q", dl_url, "-O", cf_bin], check=False)
        if os.path.exists(cf_bin):
            os.chmod(cf_bin, 0o755)

    if not shutil.which(cf_bin) and not os.path.exists(cf_bin):
        print("❌ [Cloudflare] Không thể tải hoặc tìm thấy cloudflared.")
        return

    proc = subprocess.Popen(
        [cf_bin, "tunnel", "--url", f"http://127.0.0.1:{port}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    with _PROCESS_LOCK:
        _MANAGED_PROCESSES.append(proc)

    announced = {"done": False}

    def _on_line(line_str):
        if not announced["done"] and "trycloudflare.com" in line_str:
            match = re.search(r"(https?://[^\s]+\.trycloudflare\.com)", line_str)
            if match:
                announced["done"] = True
                show_success_card("Cloudflare", match.group(1))

    # Tiếp tục drain stderr cho đến khi cloudflared thoát hoàn toàn (không break bỏ lửng)
    _drain_stream(proc.stderr, callback=_on_line)


def start_tunnel_service(method="Colab-Proxy", port=8188):
    """Bắt đầu dịch vụ tunnel chạy ngầm (Cloudflare)."""
    if method == "Cloudflare":
        t = threading.Thread(target=cloudflare_tunnel, args=(port,), daemon=True)
        t.start()


def _terminate_process_gracefully(proc, timeout=5.0):
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=timeout)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def kill_existing_processes(comfyui_dir=DEFAULT_COMFYUI_DIR):
    """Tắt sạch và an toàn các tiến trình ComfyUI / tunnel cũ (SIGTERM trước, SIGKILL sau)."""
    stop_ssh_tunnel_processes()

    with _PROCESS_LOCK:
        procs = list(_MANAGED_PROCESSES)
        _MANAGED_PROCESSES.clear()

    for proc in procs:
        _terminate_process_gracefully(proc, timeout=4.0)

    main_py_pattern = os.path.join(comfyui_dir, "main.py")
    for pattern in (main_py_pattern, "cloudflared tunnel"):
        res = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True, check=False)
        if res.returncode == 0 and res.stdout.strip():
            my_pid = os.getpid()
            for pid_str in res.stdout.strip().splitlines():
                try:
                    pid = int(pid_str.strip())
                    if pid != my_pid:
                        os.kill(pid, 15)  # SIGTERM
                except Exception:
                    pass
            time.sleep(1.0)
            for pid_str in res.stdout.strip().splitlines():
                try:
                    pid = int(pid_str.strip())
                    if pid != my_pid:
                        os.kill(pid, 9)  # SIGKILL nếu chưa thoát
                except Exception:
                    pass


def build_comfyui_launch_args(
    port=8188,
    extra_args="--preview-method auto --enable-cors-header",
    user_dir="",
    input_dir="",
    output_dir="",
    temp_dir="",
    local_only=False,
):
    """Tạo danh sách đối số an toàn cho ComfyUI main.py (hỗ trợ bind 127.0.0.1 khi qua SSH)."""
    cmd_args = [sys.executable, "-u", "main.py", "--port", str(port)]
    if user_dir and os.path.exists(user_dir):
        cmd_args.extend(["--user-directory", user_dir])
    if input_dir and os.path.exists(input_dir):
        cmd_args.extend(["--input-directory", input_dir])
    if output_dir and os.path.exists(output_dir):
        cmd_args.extend(["--output-directory", output_dir])
    if temp_dir:
        os.makedirs(temp_dir, exist_ok=True)
        cmd_args.extend(["--temp-directory", temp_dir])

    tokens = shlex.split(extra_args) if extra_args else []
    cleaned_tokens = []
    skip_next = False
    for idx, tok in enumerate(tokens):
        if skip_next:
            skip_next = False
            continue
        if tok == "--listen":
            if idx + 1 < len(tokens) and not tokens[idx + 1].startswith("-"):
                skip_next = True
            continue
        if tok.startswith("--listen="):
            continue
        cleaned_tokens.append(tok)

    if local_only:
        cleaned_tokens.extend(["--listen", "127.0.0.1"])
    else:
        cleaned_tokens.extend(["--listen", "0.0.0.0"])

    cmd_args.extend(cleaned_tokens)
    return cmd_args


def _stream_live_output(process, on_line=None):
    """Stream log thời gian thực, hỗ trợ cả \\r (tqdm sampling) lẫn \\n."""
    fd = process.stdout.fileno()
    buf = ""
    while True:
        chunk = os.read(fd, 4096)
        if not chunk:
            break
        text = chunk.decode("utf-8", errors="replace")
        sys.stdout.write(text)
        sys.stdout.flush()
        buf += text
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            if on_line:
                on_line(line)
    if buf and on_line:
        on_line(buf)


def run_comfyui(
    method="Colab-Proxy",
    port=8188,
    tailscale_auth_key="",
    tailscale_hostname=DEFAULT_TAILSCALE_HOSTNAME,
    ssh_public_key="",
    ssh_port=DEFAULT_SSH_PORT,
    local_only_bind=True,
    extra_args="--preview-method auto --enable-cors-header",
    data_dir=DEFAULT_DRIVE_DATA_DIR,
    comfyui_dir=DEFAULT_COMFYUI_DIR,
):
    """
    Khởi chạy đường truyền (Colab-Proxy, SSH-Tailscale, Cloudflare) và ComfyUI Server.
    """
    kill_existing_processes(comfyui_dir)

    validate_and_heal_symlinks(data_dir=data_dir, comfyui_dir=comfyui_dir)

    drive_wf_dir = os.path.join(data_dir, "user", "default", "workflows")
    custom_nodes_dir = os.path.join(comfyui_dir, "custom_nodes")
    ensure_pixaroma_latest(custom_nodes_dir, drive_default_workflows=drive_wf_dir)

    proxy_url = None
    ssh_endpoint = None
    use_local_only = False

    if method in ("Tailscale", "SSH-Tailscale"):
        try:
            ssh_endpoint = start_tailscale_ssh_tunnel(
                data_dir=data_dir,
                comfyui_dir=comfyui_dir,
                comfy_port=port,
                ssh_port=ssh_port,
                tailscale_auth_key=tailscale_auth_key,
                tailscale_hostname=tailscale_hostname,
                ssh_public_key=ssh_public_key,
            )
            show_ssh_tailscale_card(ssh_endpoint)
            use_local_only = bool(local_only_bind)
        except Exception as e:
            print(f"\033[93m⚠️ Không thể khởi tạo Tailscale ({e}). Tự động thử Colab-Proxy / Cloudflare...\033[0m")
            try:
                from google.colab.output import eval_js
                proxy_url = eval_js(f"google.colab.kernel.proxyPort({port})")
                if proxy_url and isinstance(proxy_url, str) and proxy_url.startswith("http"):
                    method = "Colab-Proxy"
                    show_success_card("Colab-Proxy", proxy_url)
                else:
                    raise ValueError("URL proxy không hợp lệ")
            except Exception:
                method = "Cloudflare"
                start_tunnel_service("Cloudflare", port)
    elif method == "Colab-Proxy":
        print("\n[Colab-Proxy] Đang kết nối trực tiếp qua Google Colab Proxy...")
        try:
            from google.colab.output import eval_js
            proxy_url = eval_js(f"google.colab.kernel.proxyPort({port})")
            if proxy_url and isinstance(proxy_url, str) and proxy_url.startswith("http"):
                show_success_card("Colab-Proxy", proxy_url)
                print("\033[93m💡 Lưu ý: Chỉ tài khoản Google đang chạy notebook này mới có quyền mở link trên (bảo mật tuyệt đối).\033[0m\n")
            else:
                raise ValueError("Không nhận được URL hợp lệ từ Colab Proxy")
        except Exception as e:
            print(f"\033[93m⚠️ Không thể tạo Colab Proxy trực tiếp ({e}). Tự động kích hoạt Cloudflare Tunnel...\033[0m")
            method = "Cloudflare"
            start_tunnel_service("Cloudflare", port)
    else:
        start_tunnel_service(method, port)

    user_dir = os.path.join(data_dir, "user")
    input_dir = os.path.join(data_dir, "input")
    output_dir = os.path.join(data_dir, "output")
    temp_dir = os.path.join(tempfile.gettempdir(), "ComfyUI_temp")

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

    tm_path = find_tcmalloc_path()
    if tm_path:
        curr_preload = env.get("LD_PRELOAD", "")
        if tm_path not in curr_preload:
            env["LD_PRELOAD"] = f"{tm_path}:{curr_preload}".rstrip(":") if curr_preload else tm_path

    healing_targets = [
        ("torchsde", "torchsde", "thư viện sampling cốt lõi ComfyUI"),
        ("piexif", "piexif", "thư viện metadata Impact-Pack"),
        ("segment_anything", "segment-anything", "thư viện SAM cho Impact-Pack"),
        ("ultralytics", "ultralytics", "thư viện YOLO cho Impact-Pack"),
        ("kornia", "kornia", "thư viện thị giác máy tính Kornia"),
        ("skimage", "scikit-image", "thư viện xử lý ảnh Scikit-Image"),
        ("transparent_background", "transparent-background", "thư viện bóc tách phông InSPyReNet"),
        ("imageio_ffmpeg", "imageio-ffmpeg", "thư viện video codec Pixaroma/VHS"),
    ]
    missing_pkgs = []
    for mod_name, pkg_name, desc in healing_targets:
        if importlib.util.find_spec(mod_name) is None:
            print(f"  📥 [Tự sửa lỗi] Đang bổ sung {desc} ('{pkg_name}')...")
            missing_pkgs.append(pkg_name)
    if missing_pkgs:
        subprocess.run(
            ["uv", "pip", "install", "--system", "--extra-index-url", get_pytorch_cuda_index_url()] + missing_pkgs,
            check=False,
        )

    cmd_args = build_comfyui_launch_args(
        port=port,
        extra_args=extra_args,
        user_dir=user_dir,
        input_dir=input_dir,
        output_dir=output_dir,
        temp_dir=temp_dir,
        local_only=use_local_only,
    )

    print(f"\n🚀 Đang khởi động ComfyUI Server trên cổng {port}...")
    print(f"📋 Lệnh thực thi: {' '.join(cmd_args)}")
    print("-" * 60)
    print("📜 COMFYUI LIVE LOG STREAM (Theo dõi tiến trình tải model, render và websocket bên dưới):")
    print("-" * 60)

    try:
        process = subprocess.Popen(
            cmd_args,
            cwd=comfyui_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
        )
        with _PROCESS_LOCK:
            _MANAGED_PROCESSES.append(process)

        url_announced = {"done": False}

        def _on_comfy_line(line):
            if not url_announced["done"] and ("To see the GUI go to" in line or "Starting server" in line):
                if proxy_url:
                    print(f"\n\033[92m🎉 ComfyUI ĐÃ KHỞI ĐỘNG XONG! Bấm vào đây để mở giao diện:\033[0m \033[94m\033[4m{proxy_url}\033[0m\n")
                elif ssh_endpoint:
                    direct_url = ssh_endpoint.get("direct_url", ssh_endpoint.get("local_url", ""))
                    print(
                        f"\n\033[92m🎉 ComfyUI ĐÃ KHỞI ĐỘNG XONG! Mở thẳng trên máy cá nhân qua Tailscale:\033[0m "
                        f"\033[94m\033[4m{direct_url}\033[0m\n"
                    )
                url_announced["done"] = True

        _stream_live_output(process, on_line=_on_comfy_line)
        process.wait()
    except KeyboardInterrupt:
        print("\n\n⏹️ Đã dừng ComfyUI Server theo yêu cầu người dùng.")
        kill_existing_processes(comfyui_dir)
    except Exception as e:
        print(f"\n❌ Lỗi tiến trình ComfyUI: {e}")
