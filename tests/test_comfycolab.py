import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from comfycolab.config import CONFIG_DIR, load_model_subfolders
from comfycolab.custom_nodes import (
    ensure_pixaroma_latest,
    filter_safe_requirements,
    load_default_nodes,
)
from comfycolab.downloader import normalize_folder_name
from comfycolab.environment import filter_torch_requirements, get_pytorch_cuda_index_url
from comfycolab.storage import (
    _flatten_directory_safely,
    cleanup_duplicate_encoded_files,
    validate_and_heal_symlinks,
)


REPO_ROOT = os.path.dirname(CONFIG_DIR)


class TestConfigAndNotebooks(unittest.TestCase):
    def test_custom_nodes_json_valid(self):
        data = load_default_nodes()
        self.assertIn("core_nodes", data)
        self.assertIn("video_nodes", data)
        self.assertEqual(len(data["core_nodes"]), 18)
        self.assertEqual(len(data["video_nodes"]), 4)
        node_map = {n["name"]: n["url"] for n in data["core_nodes"]}
        self.assertEqual(
            node_map["ComfyUI-Inspyrenet-Rembg"],
            "https://github.com/john-mnz/ComfyUI-Inspyrenet-Rembg.git",
        )
        self.assertEqual(
            node_map["ComfyUI-Pixaroma"],
            "https://github.com/pixaroma/comfyui-pixaroma.git",
        )

    def test_model_folders_json_count(self):
        folders = load_model_subfolders()
        self.assertEqual(len(folders), 38)
        self.assertIn("models/checkpoints", folders)
        self.assertIn("models/SEEDVR2", folders)

    def test_notebooks_valid_json(self):
        for nb_name in ("ComfyUI_Colab_Ultra.ipynb", "ComfyUI_Model_Downloader.ipynb"):
            nb_path = os.path.join(REPO_ROOT, nb_name)
            with open(nb_path, "r", encoding="utf-8") as f:
                nb = json.load(f)
            self.assertEqual(len(nb.get("cells", [])), 3)


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
        # Tạo sẵn một broken symlink và một thư mục thường cản trở
        models_dir = os.path.join(self.comfy_dir, "models")
        os.makedirs(models_dir, exist_ok=True)
        os.symlink("/nonexistent/broken/target", os.path.join(models_dir, "checkpoints"))
        os.makedirs(os.path.join(self.comfy_dir, "input"), exist_ok=True)

        healed = validate_and_heal_symlinks(self.data_dir, self.comfy_dir)
        self.assertGreaterEqual(healed, 42)
        # Chạy lần 2 phải không còn symlink lỗi nào cần phục hồi
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


class TestRequirementFiltersAndPixaroma(unittest.TestCase):
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

            # Workflow trùng nội dung đã có sẵn của người dùng
            with open(os.path.join(drive_wf, "UserCustom.json"), "w", encoding="utf-8") as f:
                f.write('{"id": 1}')
            with open(os.path.join(src_wf, "DuplicateByHash.json"), "w", encoding="utf-8") as f:
                f.write('{"id": 1}')
            with open(os.path.join(src_wf, "DuplicateByHash.jpg"), "wb") as f:
                f.write(b"orphan-thumb")

            # Workflow mới hợp lệ kèm thumbnail
            with open(os.path.join(src_wf, "Inpaint.json"), "w", encoding="utf-8") as f:
                f.write('{"id": 2}')
            with open(os.path.join(src_wf, "Inpaint.jpg"), "wb") as f:
                f.write(b"valid-thumb")

            with patch("comfycolab.custom_nodes.subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                ensure_pixaroma_latest(custom_nodes, drive_default_workflows=drive_wf)

            target_pix = os.path.join(drive_wf, "Pixaroma")
            pix_files = set(os.listdir(target_pix))
            self.assertEqual(pix_files, {"Inpaint.json", "Inpaint.jpg"})
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


if __name__ == "__main__":
    unittest.main()
