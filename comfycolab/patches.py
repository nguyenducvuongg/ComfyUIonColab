"""
Bản vá (monkey patches) an toàn và tối ưu cho các tệp lõi của ComfyUI & Custom Nodes.
Đảm bảo tính tương thích cao, hỗ trợ URL decode, nạp dynamic media thời gian thực.
"""

import os
from .config import DEFAULT_COMFYUI_DIR

def patch_user_manager(comfyui_dir=DEFAULT_COMFYUI_DIR):
    """Vá an toàn cho UserDataServer ComfyUI để hỗ trợ URL decode và thư mục con cho Pixaroma."""
    um_path = os.path.join(comfyui_dir, "app", "user_manager.py")
    if not os.path.exists(um_path):
        return

    try:
        with open(um_path, "r", encoding="utf-8") as f:
            orig_content = f.read()

        content = orig_content
        if "_patched_smart_resolver" not in content:
            if "import urllib.parse" not in content:
                content = "import urllib.parse\n" + content

            patch_code = '''
    def _resolve_smart_user_file(self, full_user_dir, rel_file):
        base_real = os.path.realpath(full_user_dir)
        candidates = [
            rel_file,
            urllib.parse.unquote(rel_file),
            urllib.parse.unquote_plus(rel_file),
            rel_file.replace("%2B", "+"),
            rel_file.replace("%2B", " "),
            rel_file.replace("%2B", "_").replace("+", "_").replace("%20", "_").replace(" ", "_"),
        ]
        for c in candidates:
            p = os.path.realpath(os.path.join(base_real, c))
            try:
                if os.path.commonpath([base_real, p]) == base_real and os.path.exists(p):
                    return p
            except ValueError:
                continue
        fallback = os.path.realpath(os.path.join(base_real, urllib.parse.unquote(rel_file)))
        try:
            if os.path.commonpath([base_real, fallback]) == base_real:
                return fallback
        except ValueError:
            pass
        return os.path.join(base_real, os.path.basename(rel_file))
'''
            if "class UserManager:" in content:
                content = content.replace("class UserManager:", "class UserManager:\n" + patch_code)
            elif "class UserManager" in content:
                idx = content.find("class UserManager")
                idx_colon = content.find(":", idx)
                if idx_colon != -1:
                    content = content[:idx_colon+1] + "\n" + patch_code + content[idx_colon+1:]

            replaced_return = "return self._resolve_smart_user_file(user_dir, file) # _patched_smart_resolver"
            updated_content = content.replace("return os.path.join(user_dir, file)", replaced_return)
            if updated_content == content:
                print("⚠️ Cảnh báo: Cấu trúc user_manager.py đã thay đổi ở bản ComfyUI mới, bỏ qua hook resolver.")
            content = updated_content

        content = content.replace('@routes.get("/userdata/{file}")', '@routes.get("/userdata/{file:.*}")')
        content = content.replace('@routes.get("/api/userdata/{file}")', '@routes.get("/api/userdata/{file:.*}")')

        if content != orig_content:
            with open(um_path, "w", encoding="utf-8") as f:
                f.write(content)
            print("✅ Đã kích hoạt bản vá thông minh cho UserDataServer (Pixaroma & UI)!")
    except Exception as e:
        print(f"⚠️ Ghi chú user_manager patch: {e}")

def patch_universal_multimedia_hook(comfyui_dir=DEFAULT_COMFYUI_DIR):
    """Kích hoạt Universal Dynamic Model & Multi-media Master Hook trong folder_paths.py và nodes.py."""
    fp_path = os.path.join(comfyui_dir, "folder_paths.py")
    if os.path.exists(fp_path):
        try:
            with open(fp_path, "r", encoding="utf-8") as f:
                content = f.read()
            if "_universal_multimedia_master_hook" not in content:
                master_patch = '''
# --- UNIVERSAL DYNAMIC MODEL & MULTI-MEDIA MASTER HOOK ---
import time as _universal_time
_universal_media_cache = {"ts": 0.0, "files": []}
_orig_get_filename_list = get_filename_list
def _universal_get_filename_list(folder_name):
    file_list = _orig_get_filename_list(folder_name)
    if folder_name in ["input", "video", "image", "audio"]:
        now = _universal_time.monotonic()
        if now - _universal_media_cache["ts"] < 2.0 and _universal_media_cache["files"]:
            merged = set(file_list)
            merged.update(_universal_media_cache["files"])
            return sorted(merged)
        in_d = get_input_directory()
        media_exts = {
            '.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff',
            '.mp4', '.mkv', '.mov', '.avi', '.webm', '.gif',
            '.wav', '.mp3', '.flac', '.ogg', '.m4a', '.aac'
        }
        discovered = []
        if in_d and os.path.exists(in_d):
            scan_dirs = [(in_d, "")]
            for sub in ("pixaroma", "3d", "outputs"):
                sp = os.path.join(in_d, sub)
                if os.path.isdir(sp):
                    scan_dirs.append((sp, sub))
            for sd, prefix in scan_dirs:
                try:
                    with os.scandir(sd) as it:
                        for entry in it:
                            if not entry.name.startswith('.') and entry.is_file():
                                ext = os.path.splitext(entry.name)[1].lower()
                                if ext in media_exts:
                                    rel = f"{prefix}/{entry.name}" if prefix else entry.name
                                    discovered.append(rel)
                except OSError:
                    pass
        _universal_media_cache["ts"] = now
        _universal_media_cache["files"] = discovered
        file_list = list(set(file_list) | set(discovered))
    return sorted(file_list)
get_filename_list = _universal_get_filename_list

_orig_get_annotated_filepath = get_annotated_filepath
def _universal_get_annotated_filepath(name, default_dir=None):
    if not name:
        return ""
    res = _orig_get_annotated_filepath(name, default_dir)
    if os.path.isfile(res):
        return res
    clean_name = name
    for suffix in (" [input]", " [output]", " [temp]"):
        if clean_name.endswith(suffix):
            clean_name = clean_name[:-len(suffix)].strip()
            break
    base_name = os.path.basename(clean_name)
    in_d = get_input_directory()
    out_d = get_output_directory()
    for bdir in [in_d, out_d, default_dir]:
        if bdir and os.path.exists(bdir):
            cand = os.path.join(bdir, clean_name)
            if os.path.isfile(cand):
                return cand
            for root, _, files in os.walk(bdir, followlinks=True):
                if base_name in files:
                    return os.path.join(root, base_name)
    return res
get_annotated_filepath = _universal_get_annotated_filepath
# _universal_multimedia_master_hook
'''
                with open(fp_path, "a", encoding="utf-8") as f:
                    f.write("\n" + master_patch)
                print("✅ Đã kích hoạt Universal Dynamic Model & Multi-Media Master Hook trong folder_paths.py!")
        except Exception as e:
            print(f"⚠️ Ghi chú folder_paths patch: {e}")

    nodes_path = os.path.join(comfyui_dir, "nodes.py")
    if os.path.exists(nodes_path):
        try:
            with open(nodes_path, "r", encoding="utf-8") as f:
                ncontent = f.read()
            if "_universal_nodes_load_media_patch" not in ncontent:
                nodes_patch = '''
# --- UNIVERSAL NODES LOAD MEDIA PATCH ---
_orig_load_image_input_types = LoadImage.INPUT_TYPES
@classmethod
def _universal_load_image_input_types(cls):
    try:
        import folder_paths
        files = folder_paths.get_filename_list("input")
        img_exts = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff')
        img_files = [f for f in files if f.lower().endswith(img_exts)]
        if img_files:
            return {"required": {"image": (sorted(list(set(img_files))), {"image_upload": True})}}
    except Exception:
        pass
    return _orig_load_image_input_types()
LoadImage.INPUT_TYPES = _universal_load_image_input_types
# _universal_nodes_load_media_patch
'''
                with open(nodes_path, "a", encoding="utf-8") as f:
                    f.write("\n" + nodes_patch)
                print("✅ Đã kích hoạt nạp tệp thời gian thực cho LoadImage trong nodes.py!")
        except Exception as e:
            print(f"⚠️ Ghi chú nodes.py patch: {e}")

def patch_vhs_loadvideo(custom_nodes_dir):
    """Hỗ trợ node VHS_LoadVideo nhận diện tức thì toàn bộ Video mới trong input/."""
    vhs_dir = os.path.join(custom_nodes_dir, "ComfyUI-VideoHelperSuite")
    if os.path.exists(vhs_dir):
        try:
            vhs_nodes = os.path.join(vhs_dir, "videohelpersuite", "nodes.py")
            if os.path.exists(vhs_nodes):
                with open(vhs_nodes, "r", encoding="utf-8") as f:
                    vcontent = f.read()
                if "_vhs_dynamic_patch" not in vcontent:
                    target = 'files = [f for f in os.listdir(folder_paths.get_input_directory()) if os.path.isfile(os.path.join(folder_paths.get_input_directory(), f))]'
                    if target in vcontent:
                        vcontent = vcontent.replace(
                            target,
                            '''import folder_paths\n        files = folder_paths.get_filename_list("input") # _vhs_dynamic_patch'''
                        )
                        with open(vhs_nodes, "w", encoding="utf-8") as f:
                            f.write(vcontent)
                        print("✅ Đã kích hoạt bộ nhận diện Video tức thì cho VHS_LoadVideo!")
                    else:
                        print("ℹ️ VHS_LoadVideo upstream đã thay đổi cấu trúc liệt kê tệp, bỏ qua patch tự động.")
        except Exception as e:
            print(f"⚠️ Ghi chú VHS_LoadVideo patch: {e}")

def apply_all_patches(comfyui_dir=DEFAULT_COMFYUI_DIR, custom_nodes_dir=None):
    """Áp dụng toàn bộ các bản vá tối ưu."""
    patch_user_manager(comfyui_dir)
    patch_universal_multimedia_hook(comfyui_dir)
    if custom_nodes_dir:
        patch_vhs_loadvideo(custom_nodes_dir)
