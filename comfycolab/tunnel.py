"""
Quản lý các đường truyền bảo mật (Tunnel) cho ComfyUI:
- Mặc định: Colab-Proxy (Được khuyên dùng cho Google Colab, nhanh và an toàn nhất)
- Cloudflare Quick Tunnel (Đường truyền công khai tốc độ cao)
- Pinggy SSH Tunnel (Tùy chọn đa máy chủ toàn cầu)
"""

import os
import re
import time
import socket
import shutil
import subprocess
import threading
try:
    from IPython.display import display, HTML
    HAS_IPYTHON = True
except ImportError:
    HAS_IPYTHON = False
    display = None
    HTML = None
from .config import DEFAULT_COMFYUI_DIR

def check_port_open(port):
    """Kiểm tra xem ComfyUI đã lắng nghe trên port hay chưa."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', port))
    sock.close()
    return result == 0

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
    <div style='background: linear-gradient(135deg, #181828, #232342); border: 1px solid #3b3b6d; padding: 22px; border-radius: 14px; margin-top: 15px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; box-shadow: 0 8px 24px rgba(0,0,0,0.5); max-width: 520px;'>
      <div style='display: flex; align-items: center; margin-bottom: 14px;'>
        <div style='background-color: #00ff87; width: 14px; height: 14px; border-radius: 50%; margin-right: 12px; box-shadow: 0 0 12px #00ff87; animation: comfy_pulse 1.6s infinite;'></div>
        <h3 style='color: #00ff87; margin: 0; font-size: 16px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;'>ComfyUI Đã Sẵn Sàng!</h3>
      </div>
      <p style='color: #d1d5db; font-size: 13.5px; margin: 0 0 16px 0; line-height: 1.5;'>
        Đường truyền kết nối <b>{method}</b> đã được thiết lập ổn định. Click nút bên dưới để mở giao diện làm việc.
      </p>
      <div style='display: flex; gap: 10px; align-items: center;'>
        <a href='{url}' target='_blank' style='display: inline-block; background: linear-gradient(90deg, #2563eb, #06b6d4); color: white; padding: 11px 24px; border-radius: 8px; text-decoration: none; font-weight: 700; font-size: 13.5px; box-shadow: 0 4px 14px rgba(37, 99, 235, 0.4); transition: transform 0.2s;'>🚀 MỞ COMFYUI</a>
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

def cloudflare_tunnel(port):
    """Khởi chạy Cloudflare Quick Tunnel."""
    if not wait_for_port(port):
        print("Timeout: Không tìm thấy ComfyUI hoạt động trên port", port)
        return

    print("\n[Cloudflare] Đang tạo đường truyền public...")
    cf_bin = "cloudflared" if shutil.which("cloudflared") else "/content/cloudflared"
    if cf_bin == "/content/cloudflared" and not os.path.exists("/content/cloudflared"):
        print("[Cloudflare] Đang tải cloudflared...")
        if shutil.which("aria2c"):
            subprocess.run(
                "aria2c -c -x 16 -s 16 -k 1M --console-log-level=error -d /content -o cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 && chmod +x /content/cloudflared",
                shell=True, check=False
            )
        else:
            subprocess.run(
                "wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O /content/cloudflared && chmod +x /content/cloudflared",
                shell=True, check=False
            )

    p = subprocess.Popen([cf_bin, "tunnel", "--url", f"http://127.0.0.1:{port}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    for line in p.stderr:
        line_str = line.decode('utf-8', errors='ignore')
        if "trycloudflare.com" in line_str:
            match = re.search(r'(https?://[^\s]+\.trycloudflare\.com)', line_str)
            if match:
                url = match.group(1)
                show_success_card("Cloudflare", url)
                break

def pinggy_tunnel(port, token="", server="Auto"):
    """Khởi chạy Pinggy SSH Tunnel."""
    if not wait_for_port(port):
        print("Timeout: Không tìm thấy ComfyUI hoạt động trên port", port)
        return

    print("\n[Pinggy] Đang tạo đường truyền...")
    server_map = {
        "Auto": "",
        "USA": "us.",
        "Europe": "eu.",
        "Asia": "ap.",
        "South America": "br.",
        "Australia": "au."
    }
    sv = server_map.get(server, "")

    if token:
        if ":" in token:
            pinggy_user, ac, ps = token.split(":")
            cmd = ["ssh", "-p", "443", f"-R0:localhost:{port}", "-o", "StrictHostKeyChecking=no", "-o", "ServerAliveInterval=30", f"{pinggy_user}@{sv}pro.pinggy.io", f'\"b:{ac}:{ps}\"']
        else:
            cmd = ["ssh", "-p", "443", f"-R0:localhost:{port}", "-o", "StrictHostKeyChecking=no", "-o", "ServerAliveInterval=30", f"{token}@{sv}pro.pinggy.io"]
    else:
        cmd = ["ssh", "-p", "443", "-L4300:localhost:4300", "-o", "StrictHostKeyChecking=no", "-o", "ServerAliveInterval=30", f"-R0:localhost:{port}", f"{sv}free.pinggy.io"]

    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for line in iter(p.stdout.readline, ''):
        match = re.search(r'(https?://[^\s]+)', line)
        if match:
            url = match.group(1)
            if "dashboard.pinggy.io" in url:
                continue
            show_success_card("Pinggy", url)
            break

def colab_proxy_tunnel(port):
    """Khởi chạy đường truyền qua Colab Proxy (Mặc định được khuyến nghị)."""
    print("\n[Colab-Proxy] Đang kết nối trực tiếp qua Google Colab Proxy...")
    try:
        from google.colab.output import eval_js
        url = eval_js(f"google.colab.kernel.proxyPort({port})")
        show_success_card("Colab-Proxy", url)
        print("\033[93m💡 Lưu ý: Chỉ tài khoản Google đang chạy notebook này mới có quyền mở link trên.\033[0m")
    except Exception as e:
        print(f"\033[91m❌ Lỗi tạo Colab Proxy: {str(e)}. Bạn có thể đổi sang Cloudflare trong form.\033[0m")

def start_tunnel_service(method="Colab-Proxy", port=8188, pinggy_token="", pinggy_server="Auto"):
    """Bắt đầu dịch vụ tunnel tương ứng."""
    if method == "Cloudflare":
        threading.Thread(target=cloudflare_tunnel, args=(port,), daemon=True).start()
    elif method == "Pinggy":
        threading.Thread(target=pinggy_tunnel, args=(port, pinggy_token, pinggy_server), daemon=True).start()
    elif method == "Colab-Proxy":
        colab_proxy_tunnel(port)
    else:
        colab_proxy_tunnel(port)

def kill_existing_processes():
    """Tắt sạch các phiên bản ComfyUI hoặc tunnel cũ đang chạy ngầm."""
    subprocess.run("pkill -9 -f 'main.py'", shell=True, check=False)
    subprocess.run("pkill -9 -f cloudflared", shell=True, check=False)
    subprocess.run("pkill -9 -f pinggy.io", shell=True, check=False)

def run_comfyui(
    method="Colab-Proxy",
    port=8188,
    pinggy_token="",
    pinggy_server="Auto",
    extra_args="--preview-method auto --listen --enable-cors-header",
    data_dir="/content/drive/MyDrive/ComfyUI_Data",
    comfyui_dir=DEFAULT_COMFYUI_DIR
):
    """Khởi chạy đường truyền và ComfyUI Server."""
    kill_existing_processes()
    
    # Bắt đầu dịch vụ Tunnel
    start_tunnel_service(method, port, pinggy_token, pinggy_server)

    user_dir = os.path.join(data_dir, "user")
    input_dir = os.path.join(data_dir, "input")

    user_arg = f"--user-directory {user_dir}" if os.path.exists(user_dir) else ""
    input_arg = f"--input-directory {input_dir}" if os.path.exists(input_dir) else ""

    cmd = f"cd {comfyui_dir} && python main.py --port {port} {user_arg} {input_arg} {extra_args}"
    print(f"\n🚀 Đang khởi động ComfyUI Server trên cổng {port}...")
    subprocess.run(cmd, shell=True)
