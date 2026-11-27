import ast
import io
import json
import os
import shutil
import stat
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from comfycolab import cli, launch_and_run
from comfycolab.config import CONFIG_DIR, load_model_subfolders
from comfycolab.custom_nodes import (
    _iter_backup_files,
    create_compact_nodes_backup,
    ensure_pixaroma_latest,
    filter_safe_requirements,
    load_default_nodes,
)
from comfycolab.downloader import normalize_folder_name, redact_url_tokens
from comfycolab.environment import filter_torch_requirements, get_pytorch_cuda_index_url
from comfycolab.patches import patch_universal_multimedia_hook, patch_user_manager
from comfycolab.ssh_tunnel import (
    build_sshd_config,
    build_tailscale_serve_command,
    build_tailscale_up_command,
    build_tailscaled_command,
    configure_tailscale_serve,
    resolve_ssh_keys,
    resolve_tailscale_auth_key,
    write_ssh_endpoint_info,
)
from comfycolab.storage import (
    _flatten_directory_safely,
    cleanup_duplicate_encoded_files,
    validate_and_heal_symlinks,
)
from comfycolab.tunnel import build_comfyui_launch_args
from scripts.local_connect import build_ssh_forward_command, format_ssh_config_block


REPO_ROOT = os.path.dirname(CONFIG_DIR)


class TestConfigAndNotebooks(unittest.TestCase):
    def test_custom_nodes_json_valid(self):
        data = load_default_nodes()
        self.assertIn("core_nodes", data)
        self.assertIn("video_nodes", data)
        self.assertEqual(len(data["core_nodes"]), 17)
        self.assertEqual(len(data["video_nodes"]), 4)
        node_map = {n["name"]: n["url"] for n in data["core_nodes"]}
        self.assertNotIn("ComfyUI-Custom-Scripts", node_map)
        self.assertEqual(
            node_map["ComfyUI-Inspyrenet-Rembg"],
            "https://github.com/john-mnz/ComfyUI-Inspyrenet-Rembg.git",
        )
        self.assertEqual(
            node_map["ComfyUI-Pixaroma"],
            "https://github.com/pixaroma/comfyui-pixaroma.git",
        )

    def test_deprecated_custom_scripts_cleaned_up_on_setup(self):
        from comfycolab.custom_nodes import setup_all_custom_nodes
        tmp_dir = tempfile.mkdtemp(prefix="comfycolab_rm_cs_")
        try:
            old_node = os.path.join(tmp_dir, "ComfyUI-Custom-Scripts")
            os.makedirs(old_node, exist_ok=True)
            with open(os.path.join(old_node, "__init__.py"), "w", encoding="utf-8") as f:
                f.write("# legacy\n")
            with patch("comfycolab.custom_nodes.load_default_nodes", return_value={"core_nodes": [], "video_nodes": []}), \
                 patch("comfycolab.custom_nodes.ensure_pixaroma_latest", return_value=False), \
                 patch("comfycolab.custom_nodes.patch_vhs_loadvideo"):
                changed = setup_all_custom_nodes(tmp_dir, update_nodes=False, install_video_nodes=False)
            self.assertTrue(changed)
            self.assertFalse(os.path.exists(old_node))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_model_folders_json_count_and_no_case_duplicates(self):
        folders = load_model_subfolders()
        self.assertEqual(len(folders), 37)
        self.assertIn("models/checkpoints", folders)
        self.assertIn("models/SEEDVR2", folders)
        lowered = [f.lower() for f in folders]
        self.assertEqual(len(lowered), len(set(lowered)))

    def test_notebooks_valid_json_python_and_no_pinggy(self):
        expected_cells = {
            "ComfyUI_Colab_Ultra.ipynb": 2,
            "ComfyUI_Model_Downloader.ipynb": 3,
        }
        for nb_name, count in expected_cells.items():
            nb_path = os.path.join(REPO_ROOT, nb_name)
            with open(nb_path, "r", encoding="utf-8") as f:
                raw_text = f.read()
                nb = json.loads(raw_text)
            self.assertEqual(len(nb.get("cells", [])), count)
            self.assertNotIn("pinggy", raw_text.lower())
            for cell in nb["cells"]:
                if cell.get("cell_type") == "code":
                    src = "".join(cell.get("source", []))
                    ast.parse(src, filename=nb_name)
                    if cell.get("metadata", {}).get("id") == "download-cell":
                        self.assertIn("sys.path.insert", src)
        with open(os.path.join(REPO_ROOT, "ComfyUI_Colab_Ultra.ipynb"), "r", encoding="utf-8") as f:
            ultra_raw = f.read()
            self.assertIn("launch_and_run", ultra_raw)
            self.assertIn("Tunnel_Method = \\\"Tailscale\\\"", ultra_raw)

    def test_no_pinggy_in_tunnel_modules(self):
        import comfycolab.tunnel as tunnel_mod
        self.assertFalse(hasattr(tunnel_mod, "pinggy_tunnel"))
        for fname in ("tunnel.py", "__init__.py"):
            with open(os.path.join(REPO_ROOT, "comfycolab", fname), "r", encoding="utf-8") as f:
                self.assertNotIn("pinggy", f.read().lower())


class TestStorageAndSymlinks(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="comfycolab_test_")
        self.data_dir = os.path.join(self.tmp_dir, "drive_data")
        self.comfy_dir = os.path.join(self.tmp_dir, "ComfyUI")
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.comfy_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_validate_and_heal_symlinks(self):
        models_dir = os.path.join(self.comfy_dir, "models")
        os.makedirs(models_dir, exist_ok=True)
        os.symlink("/nonexistent/broken/target", os.path.join(models_dir, "checkpoints"))
        os.makedirs(os.path.join(self.comfy_dir, "input"), exist_ok=True)

        healed = validate_and_heal_symlinks(self.data_dir, self.comfy_dir)
        self.assertGreaterEqual(healed, len(load_model_subfolders()) + 4)
        self.assertTrue(os.path.islink(os.path.join(models_dir, "seedvr2")))
        healed_second = validate_and_heal_symlinks(self.data_dir, self.comfy_dir)
        self.assertEqual(healed_second, 0)

    def test_flatten_collision_and_broken_symlink_safe(self):
        base_dir = os.path.join(self.tmp_dir, "flat_io")
        sub_dir = os.path.join(base_dir, "nested")
        kept_dir = os.path.join(base_dir, "pixaroma")
        os.makedirs(sub_dir, exist_ok=True)
        os.makedirs(kept_dir, exist_ok=True)

        with open(os.path.join(base_dir, "img.png"), "w", encoding="utf-8") as f:
            f.write("root")
        with open(os.path.join(sub_dir, "img.png"), "w", encoding="utf-8") as f:
            f.write("nested")
        with open(os.path.join(kept_dir, "keep.png"), "w", encoding="utf-8") as f:
            f.write("keep")

        _flatten_directory_safely(base_dir, excluded_prefixes=("pixaroma",))
        self.assertTrue(os.path.isfile(os.path.join(base_dir, "img.png")))
        self.assertTrue(os.path.isfile(os.path.join(base_dir, "img_1.png")))
        self.assertTrue(os.path.isfile(os.path.join(kept_dir, "keep.png")))

    def test_cleanup_duplicate_encoded_files(self):
        wf_dir = os.path.join(self.tmp_dir, "workflows")
        os.makedirs(wf_dir, exist_ok=True)
        for junk in ("flow%20copy.json", "a%2Bb.json", "temp.tmp", "zero.json"):
            with open(os.path.join(wf_dir, junk), "w", encoding="utf-8") as f:
                if junk != "zero.json":
                    f.write("{}")
        valid_path = os.path.join(wf_dir, "valid.json")
        with open(valid_path, "w", encoding="utf-8") as f:
            f.write('{"nodes": []}')

        removed = cleanup_duplicate_encoded_files(wf_dir)
        self.assertEqual(removed, 4)
        self.assertTrue(os.path.exists(valid_path))


class TestRequirementFiltersPixaromaAndBackup(unittest.TestCase):
    def test_filter_torch_requirements_keeps_torchsde(self):
        lines = [
            "# comment",
            "torch>=2.4.0",
            "torchvision==0.19.0",
            "torchaudio",
            "torchsde",
            "numpy>=1.26.0",
        ]
        filtered = filter_torch_requirements(lines)
        self.assertEqual(filtered, ["torchsde", "numpy>=1.26.0"])

    def test_filter_safe_requirements_protects_packages(self):
        lines = [
            "torch==2.5.1\n",
            "transformers>=4.40\n",
            "nvidia-cublas-cu12\n",
            "transparent-background>=1.3.0\n",
            "ultralytics\n",
        ]
        filtered = filter_safe_requirements(lines)
        self.assertEqual(filtered, ["transparent-background>=1.3.0\n", "ultralytics\n"])

    def test_pixaroma_unchanged_commit_returns_false(self):
        tmp_dir = tempfile.mkdtemp(prefix="comfycolab_pix_unchanged_")
        try:
            custom_nodes = os.path.join(tmp_dir, "custom_nodes")
            pix_dir = os.path.join(custom_nodes, "ComfyUI-Pixaroma")
            os.makedirs(os.path.join(pix_dir, ".git"), exist_ok=True)

            def fake_run(cmd, **kwargs):
                class Res:
                    returncode = 0
                    stdout = "deadbeef12345678\n"
                    stderr = ""
                return Res()

            with patch("comfycolab.custom_nodes.subprocess.run", side_effect=fake_run):
                changed = ensure_pixaroma_latest(custom_nodes)
            self.assertFalse(changed)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_pixaroma_workflow_dedup_and_paired_thumbnails(self):
        tmp_dir = tempfile.mkdtemp(prefix="comfycolab_pix_")
        try:
            custom_nodes = os.path.join(tmp_dir, "custom_nodes")
            pix_dir = os.path.join(custom_nodes, "ComfyUI-Pixaroma")
            src_wf = os.path.join(pix_dir, "workflows")
            drive_wf = os.path.join(tmp_dir, "drive_wf")
            os.makedirs(os.path.join(pix_dir, ".git"), exist_ok=True)
            os.makedirs(src_wf, exist_ok=True)
            os.makedirs(drive_wf, exist_ok=True)

            with open(os.path.join(drive_wf, "UserCustom.json"), "w", encoding="utf-8") as f:
                f.write('{"id": 1}')
            with open(os.path.join(src_wf, "DuplicateByHash.json"), "w", encoding="utf-8") as f:
                f.write('{"id": 1}')
            with open(os.path.join(src_wf, "DuplicateByHash.jpg"), "wb") as f:
                f.write(b"orphan-thumb")

            with open(os.path.join(src_wf, "Inpaint.json"), "w", encoding="utf-8") as f:
                f.write('{"id": 2}')
            with open(os.path.join(src_wf, "Inpaint.jpg"), "wb") as f:
                f.write(b"valid-thumb")

            with patch("comfycolab.custom_nodes.subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                mock_run.return_value.stdout = "abc123\n"
                ensure_pixaroma_latest(custom_nodes, drive_default_workflows=drive_wf)

            target_pix = os.path.join(drive_wf, "Pixaroma")
            pix_files = set(os.listdir(target_pix))
            self.assertEqual(pix_files, {"Inpaint.json", "Inpaint.jpg"})
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_backup_excludes_venv_node_modules_and_writes_manifest(self):
        tmp_dir = tempfile.mkdtemp(prefix="comfycolab_bkp_")
        try:
            nodes_dir = os.path.join(tmp_dir, "custom_nodes")
            backup_dir = os.path.join(tmp_dir, "drive", "backup")
            os.makedirs(os.path.join(nodes_dir, "MyNode", ".venv"), exist_ok=True)
            os.makedirs(os.path.join(nodes_dir, "MyNode", "node_modules"), exist_ok=True)
            with open(os.path.join(nodes_dir, "MyNode", "__init__.py"), "w", encoding="utf-8") as f:
                f.write("# ok\n")
            with open(os.path.join(nodes_dir, "MyNode", ".venv", "junk.py"), "w", encoding="utf-8") as f:
                f.write("# skip\n")
            with open(os.path.join(nodes_dir, "MyNode", "node_modules", "junk.js"), "w", encoding="utf-8") as f:
                f.write("// skip\n")

            rels = [rel for _, rel in _iter_backup_files(nodes_dir)]
            self.assertEqual(rels, [os.path.join("MyNode", "__init__.py")])

            backup_zip = os.path.join(backup_dir, "custom_nodes_backup.zip")
            ok = create_compact_nodes_backup(nodes_dir, backup_zip)
            self.assertTrue(ok)
            self.assertTrue(os.path.exists(backup_zip))
            self.assertFalse(os.path.exists(backup_zip + ".tmp"))
            manifest_path = os.path.join(backup_dir, "custom_nodes_manifest.json")
            self.assertTrue(os.path.exists(manifest_path))
            with open(manifest_path, "r", encoding="utf-8") as mf:
                self.assertIn("MyNode", json.load(mf))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestPatchesSecurityAndIdempotency(unittest.TestCase):
    def test_patch_user_manager_idempotent_and_blocks_traversal(self):
        tmp_dir = tempfile.mkdtemp(prefix="comfycolab_patch_")
        try:
            app_dir = os.path.join(tmp_dir, "app")
            os.makedirs(app_dir, exist_ok=True)
            um_path = os.path.join(app_dir, "user_manager.py")
            with open(um_path, "w", encoding="utf-8") as f:
                f.write(
                    "import os\n"
                    "class UserManager:\n"
                    "    def get_path(self, user_dir, file):\n"
                    "        return os.path.join(user_dir, file)\n"
                )

            patch_user_manager(tmp_dir)
            with open(um_path, "r", encoding="utf-8") as f:
                patched_once = f.read()
            self.assertIn("_patched_smart_resolver", patched_once)
            self.assertIn("commonpath", patched_once)

            mtime_before = os.path.getmtime(um_path)
            patch_user_manager(tmp_dir)
            self.assertEqual(os.path.getmtime(um_path), mtime_before)

            ns = {}
            exec(compile(patched_once, um_path, "exec"), ns)
            mgr = ns["UserManager"]()
            user_root = os.path.join(tmp_dir, "user_root")
            os.makedirs(user_root, exist_ok=True)
            resolved = mgr._resolve_smart_user_file(user_root, "../../etc/passwd")
            self.assertTrue(os.path.realpath(resolved).startswith(os.path.realpath(user_root)))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_universal_multimedia_hook_compiles_and_strips_annotation(self):
        tmp_dir = tempfile.mkdtemp(prefix="comfycolab_hook_")
        try:
            in_dir = os.path.join(tmp_dir, "input")
            out_dir = os.path.join(tmp_dir, "output")
            os.makedirs(in_dir, exist_ok=True)
            os.makedirs(out_dir, exist_ok=True)
            target_img = os.path.join(out_dir, "render.png")
            with open(target_img, "wb") as f:
                f.write(b"png")

            fp_path = os.path.join(tmp_dir, "folder_paths.py")
            with open(fp_path, "w", encoding="utf-8") as f:
                f.write(
                    "import os\n"
                    f"def get_input_directory(): return {in_dir!r}\n"
                    f"def get_output_directory(): return {out_dir!r}\n"
                    "def get_filename_list(folder_name): return []\n"
                    "def get_annotated_filepath(name, default_dir=None): return os.path.join(get_input_directory(), name)\n"
                )
            nodes_path = os.path.join(tmp_dir, "nodes.py")
            with open(nodes_path, "w", encoding="utf-8") as f:
                f.write(
                    "class LoadImage:\n"
                    "    @classmethod\n"
                    "    def INPUT_TYPES(cls): return {'required': {}}\n"
                )

            patch_universal_multimedia_hook(tmp_dir)
            ns = {}
            with open(fp_path, "r", encoding="utf-8") as f:
                exec(compile(f.read(), fp_path, "exec"), ns)
            self.assertEqual(ns["get_annotated_filepath"]("render.png [output]"), target_img)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestDownloaderAndCuda(unittest.TestCase):
    def test_normalize_folder_name(self):
        self.assertEqual(normalize_folder_name("[Lora]"), "loras")
        self.assertEqual(normalize_folder_name("models/seedvr2"), "SEEDVR2")
        self.assertEqual(normalize_folder_name("rembg"), "background_removal")

    def test_cuda_index_detection_fallback(self):
        url = get_pytorch_cuda_index_url()
        self.assertTrue(url.startswith("https://download.pytorch.org/whl/cu"))

    def test_redact_url_tokens(self):
        raw = "https://civitai.com/api/download/models/128713?token=secret_abc_123&type=Model"
        safe = redact_url_tokens(raw)
        self.assertNotIn("secret_abc_123", safe)
        self.assertIn("token=%2A%2A%2A", safe)
        self.assertIn("type=Model", safe)


class TestSSHTailscaleAndLocalConnect(unittest.TestCase):
    def test_build_sshd_config_and_tailscale_commands(self):
        cfg = build_sshd_config(
            ssh_port=2222,
            authorized_keys_file="/root/.ssh/authorized_keys",
            host_keys=["/tmp/ssh_host_ed25519_key"],
            pid_file="/tmp/sshd.pid",
            listen_address="127.0.0.1",
        )
        self.assertIn("Port 2222", cfg)
        self.assertIn("ListenAddress 127.0.0.1", cfg)
        self.assertIn("PasswordAuthentication no", cfg)
        self.assertIn("UsePAM no", cfg)
        self.assertIn("AllowTcpForwarding yes", cfg)

        tsd_cmd = build_tailscaled_command("/tmp/ts_state", "/tmp/ts.sock", socks5_port=1055)
        self.assertIn("--tun=userspace-networking", tsd_cmd)
        self.assertIn("--statedir=/tmp/ts_state", tsd_cmd)
        self.assertIn("--socket=/tmp/ts.sock", tsd_cmd)

        up_cmd = build_tailscale_up_command("/tmp/ts.sock", "tskey-auth-123", hostname="colab-comfy", enable_ts_ssh=True)
        self.assertEqual(
            up_cmd,
            [
                "tailscale", "--socket=/tmp/ts.sock", "up",
                "--auth-key=tskey-auth-123", "--hostname=colab-comfy",
                "--accept-dns=false", "--ssh",
            ],
        )

        serve_https = build_tailscale_serve_command("/tmp/ts.sock", comfy_port=8188, https=True)
        self.assertEqual(serve_https, ["tailscale", "--socket=/tmp/ts.sock", "serve", "--bg", "8188"])
        serve_http = build_tailscale_serve_command("/tmp/ts.sock", comfy_port=8188, https=False)
        self.assertEqual(serve_http, ["tailscale", "--socket=/tmp/ts.sock", "serve", "--http=80", "--bg", "8188"])

    def test_configure_tailscale_serve_https_and_fallback(self):
        class Res:
            def __init__(self, rc):
                self.returncode = rc
                self.stdout = ""
                self.stderr = ""

        # Case 1: HTTPS serve thành công
        with patch("comfycolab.ssh_tunnel.subprocess.run", side_effect=[Res(0), Res(0)]):
            url, mode = configure_tailscale_serve("/tmp/ts.sock", 8188, magic_dns="colab-comfy.tailnet.ts.net", tailscale_ip="100.64.0.10")
        self.assertEqual((url, mode), ("https://colab-comfy.tailnet.ts.net", "https"))

        # Case 2: HTTPS thất bại -> fallback HTTP port 80
        with patch("comfycolab.ssh_tunnel.subprocess.run", side_effect=[Res(0), Res(1), Res(0)]):
            url, mode = configure_tailscale_serve("/tmp/ts.sock", 8188, magic_dns="colab-comfy.tailnet.ts.net", tailscale_ip="100.64.0.10")
        self.assertEqual((url, mode), ("http://colab-comfy.tailnet.ts.net", "http"))

        # Case 3: Cả HTTPS & HTTP đều lỗi -> fallback TCP :8188
        with patch("comfycolab.ssh_tunnel.subprocess.run", side_effect=[Res(0), Res(1), Res(1)]):
            url, mode = configure_tailscale_serve("/tmp/ts.sock", 8188, magic_dns="colab-comfy.tailnet.ts.net", tailscale_ip="100.64.0.10")
        self.assertEqual((url, mode), ("http://100.64.0.10:8188", "tcp"))

    def test_resolve_tailscale_auth_key_and_ssh_keys(self):
        tmp_dir = tempfile.mkdtemp(prefix="comfycolab_ssh_")
        try:
            data_dir = os.path.join(tmp_dir, "drive_data")
            ssh_dir = os.path.join(tmp_dir, "dot_ssh")

            key = resolve_tailscale_auth_key(data_dir, explicit_key="tskey-auth-xyz")
            self.assertEqual(key, "tskey-auth-xyz")
            # Lần sau không truyền vẫn lấy được từ Drive tokens.json
            with patch("comfycolab.ssh_tunnel.get_colab_secret", return_value=""):
                self.assertEqual(resolve_tailscale_auth_key(data_dir, explicit_key=""), "tskey-auth-xyz")

            keys, auto_priv = resolve_ssh_keys(
                data_dir,
                explicit_public_key="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest user@local",
                ssh_dir=ssh_dir,
            )
            self.assertEqual(len(keys), 1)
            self.assertIsNone(auto_priv)
            auth_file = os.path.join(ssh_dir, "authorized_keys")
            self.assertTrue(os.path.isfile(auth_file))
            mode = stat.S_IMODE(os.stat(auth_file).st_mode)
            self.assertEqual(mode, 0o600)

            ep_path, payload = write_ssh_endpoint_info(
                data_dir,
                tailscale_ip="100.64.0.10",
                magic_dns="colab-comfy.tailnet.ts.net",
                ssh_port=2222,
                comfy_port=8188,
                direct_url="https://colab-comfy.tailnet.ts.net",
                serve_mode="https",
            )
            self.assertTrue(os.path.isfile(ep_path))
            self.assertEqual(payload["direct_url"], "https://colab-comfy.tailnet.ts.net")
            self.assertEqual(payload["serve_mode"], "https")
            self.assertEqual(payload["local_url"], "http://127.0.0.1:8188")
            self.assertIn("-L 127.0.0.1:8188:127.0.0.1:8188", payload["ssh_forward_cmd"])
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_build_comfyui_launch_args_local_only_and_dirs(self):
        tmp_dir = tempfile.mkdtemp(prefix="comfycolab_args_")
        try:
            in_d = os.path.join(tmp_dir, "input")
            out_d = os.path.join(tmp_dir, "output")
            usr_d = os.path.join(tmp_dir, "user")
            tmp_d = os.path.join(tmp_dir, "temp")
            for d in (in_d, out_d, usr_d):
                os.makedirs(d, exist_ok=True)

            args_local = build_comfyui_launch_args(
                port=8188,
                extra_args="--preview-method auto --listen 0.0.0.0 --enable-cors-header",
                user_dir=usr_d,
                input_dir=in_d,
                output_dir=out_d,
                temp_dir=tmp_d,
                local_only=True,
            )
            self.assertIn("--output-directory", args_local)
            self.assertIn("--temp-directory", args_local)
            idx = args_local.index("--listen")
            self.assertEqual(args_local[idx + 1], "127.0.0.1")

            args_pub = build_comfyui_launch_args(port=8188, extra_args="--preview-method auto", local_only=False)
            idx_pub = args_pub.index("--listen")
            self.assertEqual(args_pub[idx_pub + 1], "0.0.0.0")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_local_connect_builders_and_cli_doctor(self):
        cmd = build_ssh_forward_command(
            host="100.64.0.10",
            ssh_port=2222,
            user="root",
            local_port=8188,
            remote_port=8188,
            identity_file="/tmp/mykey",
        )
        self.assertIn("-L", cmd)
        self.assertIn("127.0.0.1:8188:127.0.0.1:8188", cmd)
        self.assertIn("root@100.64.0.10", cmd)

        cfg_block = format_ssh_config_block("100.64.0.10", ssh_port=2222, identity_file="/tmp/mykey")
        self.assertIn("Host colab-comfy", cfg_block)
        self.assertIn("LocalForward 127.0.0.1:8188 127.0.0.1:8188", cfg_block)

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.main(["doctor", "--data-dir", "/nonexistent_dir_xyz"])
        self.assertEqual(rc, 0)
        doctor_data = json.loads(buf.getvalue())
        self.assertIn("tools", doctor_data)
        self.assertIn("cuda_index_url", doctor_data)

    def test_launch_and_run_calls_setup_then_start(self):
        calls = []
        with patch("comfycolab.launch_setup", side_effect=lambda **kw: calls.append(("setup", kw))), \
             patch("comfycolab.start_comfyui_and_tunnel", side_effect=lambda **kw: calls.append(("start", kw))):
            launch_and_run(drive_path="/tmp/d", method="Tailscale", port=8188, tailscale_auth_key="tskey-123")
        self.assertEqual([c[0] for c in calls], ["setup", "start"])
        self.assertEqual(calls[0][1]["drive_path"], "/tmp/d")
        self.assertEqual(calls[1][1]["method"], "Tailscale")
        self.assertEqual(calls[1][1]["tailscale_auth_key"], "tskey-123")


if __name__ == "__main__":
    unittest.main()
