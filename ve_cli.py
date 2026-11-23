import ctypes
import ctypes.wintypes
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from fractions import Fraction
from pathlib import Path
from typing import Any, Optional

import sys
import numpy as np
import torch
from PIL import Image

import folder_paths


def _get_comfy_video_api():
    try:
        from comfy_api.latest import Input, InputImpl, Types
        return Input, InputImpl, Types
    except Exception:
        return None, None, None

logger = logging.getLogger("ComfyUI-Visual-Enhancer")

PACKAGE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = PACKAGE_DIR / "ve_config.json"

DEFAULT_INSTALL_DIR = Path(os.path.expandvars(r"%LOCALAPPDATA%\Programs\Visual Enhancer"))
DEFAULT_CLI_PATH = DEFAULT_INSTALL_DIR / "VE_CLI.exe"

_STATE_LOCK = threading.Lock()
_CONNECTION_CACHE: dict[str, Any] = {
    "cli_path": "",
    "connected": False,
    "mtime": 0.0,
    "version": "",
    "devices": [],
    "fsr_adapters": [],
    "supported_commands": set(),
    "supported_options": {},
    "schema_version": 47,
    "message": "Not checked",
}


def _load_saved_cli_path() -> str:
    if CONFIG_PATH.is_file():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            saved = data.get("ve_cli_path", "").strip()
            if saved:
                return saved
        except Exception:
            pass
    return ""


def _save_cli_path(cli_path: str, schema_version: Optional[int] = None) -> None:
    try:
        data = {}
        if CONFIG_PATH.is_file():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        data["ve_cli_path"] = cli_path
        if schema_version is not None:
            data["schema_version"] = schema_version
        CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not persist Visual Enhancer CLI config: %s", exc)


def resolve_candidate_cli_path(custom_path: Optional[str] = None) -> str:
    candidates = []
    if custom_path and custom_path.strip():
        expanded = os.path.expandvars(os.path.expanduser(custom_path.strip().strip('"')))
        p = Path(expanded)
        if p.is_dir():
            p = p / "VE_CLI.exe"
        candidates.append(p)

    if DEFAULT_CLI_PATH.is_file():
        candidates.append(DEFAULT_CLI_PATH)

    saved = _load_saved_cli_path()
    if saved:
        p = Path(os.path.expandvars(os.path.expanduser(saved)))
        if p.is_dir():
            p = p / "VE_CLI.exe"
        candidates.append(p)

    candidates.append(DEFAULT_CLI_PATH)

    for candidate in candidates:
        try:
            if candidate.is_file():
                return str(candidate.resolve())
        except Exception:
            continue

    return str(candidates[0]) if candidates else str(DEFAULT_CLI_PATH)


def _extract_json_from_stdout(stdout_text: str) -> Optional[dict[str, Any]]:
    if not stdout_text:
        return None
    for line in reversed(stdout_text.splitlines()):
        stripped = line.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                return json.loads(stripped)
            except Exception:
                continue
    try:
        return json.loads(stdout_text.strip())
    except Exception:
        return None


def _probe_cli_capabilities(cli_path: str) -> tuple[set[str], dict[str, set[str]], str]:
    commands: set[str] = set()
    options_by_cmd: dict[str, set[str]] = {}
    version_str = ""

    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        ver_proc = subprocess.run(
            [cli_path, "--version"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            creationflags=creation_flags,
        )
        if ver_proc.returncode == 0 and ver_proc.stdout.strip():
            version_str = ver_proc.stdout.strip().splitlines()[-1].strip()
    except Exception:
        pass

    help_proc = subprocess.run(
        [cli_path, "--help"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        creationflags=creation_flags,
    )
    if help_proc.returncode != 0 or "Usage:" not in help_proc.stdout:
        raise RuntimeError(help_proc.stderr.strip() or "Invalid VE_CLI.exe executable.")

    for line in help_proc.stdout.splitlines():
        if line.strip().startswith("Commands:"):
            raw_cmds = line.split(":", 1)[1]
            for c in raw_cmds.split(","):
                cmd_name = c.strip()
                if cmd_name:
                    commands.add(cmd_name)

    if not commands:
        commands = {"render", "reconstruct", "upscale", "interpolate", "devices"}

    for cmd in commands:
        cmd_opts: set[str] = set()
        try:
            c_proc = subprocess.run(
                [cli_path, cmd, "--help"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                creationflags=creation_flags,
            )
            for match in re.finditer(r"(--[a-zA-Z0-9_-]+)", c_proc.stdout):
                cmd_opts.add(match.group(1))
        except Exception:
            pass
        options_by_cmd[cmd] = cmd_opts

    return commands, options_by_cmd, version_str


def check_connection(custom_path: Optional[str] = None, force: bool = False) -> dict[str, Any]:
    resolved = resolve_candidate_cli_path(custom_path)
    p = Path(resolved)

    with _STATE_LOCK:
        if not p.is_file():
            _CONNECTION_CACHE.update({
                "cli_path": resolved,
                "connected": False,
                "mtime": 0.0,
                "devices": [],
                "fsr_adapters": [],
                "message": f"VE_CLI.exe not found at: {resolved}",
            })
            return dict(_CONNECTION_CACHE, supported_commands=list(_CONNECTION_CACHE["supported_commands"]))

        mtime = p.stat().st_mtime
        if (
            not force
            and _CONNECTION_CACHE["connected"]
            and os.path.normcase(_CONNECTION_CACHE["cli_path"]) == os.path.normcase(resolved)
            and _CONNECTION_CACHE["mtime"] == mtime
        ):
            return {
                "cli_path": _CONNECTION_CACHE["cli_path"],
                "connected": _CONNECTION_CACHE["connected"],
                "version": _CONNECTION_CACHE["version"],
                "devices": _CONNECTION_CACHE["devices"],
                "fsr_adapters": _CONNECTION_CACHE["fsr_adapters"],
                "supported_commands": list(_CONNECTION_CACHE["supported_commands"]),
                "schema_version": _CONNECTION_CACHE["schema_version"],
                "message": _CONNECTION_CACHE["message"],
            }

    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        commands, options_by_cmd, version_str = _probe_cli_capabilities(resolved)
        devices = []
        fsr_adapters = []
        if "devices" in commands:
            dev_proc = subprocess.run(
                [resolved, "devices", "--json"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                creationflags=creation_flags,
            )
            dev_json = _extract_json_from_stdout(dev_proc.stdout)
            if dev_json and dev_json.get("ok"):
                devices = dev_json.get("devices", [])
                fsr_adapters = dev_json.get("fsr_adapters", [])

        gpu_names = [d.get("name", "GPU") for d in devices if d.get("name")]
        if not gpu_names:
            gpu_names = [a.get("name", "GPU") for a in fsr_adapters if a.get("name")]
        gpu_summary = ", ".join(gpu_names) if gpu_names else "Ready"
        msg = f"Connected ({gpu_summary})"

        with _STATE_LOCK:
            _CONNECTION_CACHE.update({
                "cli_path": resolved,
                "connected": True,
                "mtime": mtime,
                "version": version_str or "Visual Enhancer CLI",
                "devices": devices,
                "fsr_adapters": fsr_adapters,
                "supported_commands": commands,
                "supported_options": options_by_cmd,
                "message": msg,
            })
            _save_cli_path(resolved, _CONNECTION_CACHE["schema_version"])
            return {
                "cli_path": _CONNECTION_CACHE["cli_path"],
                "connected": True,
                "version": _CONNECTION_CACHE["version"],
                "devices": devices,
                "fsr_adapters": fsr_adapters,
                "supported_commands": list(commands),
                "schema_version": _CONNECTION_CACHE["schema_version"],
                "message": msg,
            }
    except Exception as exc:
        err_msg = f"Failed to verify VE_CLI.exe: {exc}"
        with _STATE_LOCK:
            _CONNECTION_CACHE.update({
                "cli_path": resolved,
                "connected": False,
                "mtime": 0.0,
                "devices": [],
                "fsr_adapters": [],
                "message": err_msg,
            })
        return {
            "cli_path": resolved,
            "connected": False,
            "version": "",
            "devices": [],
            "fsr_adapters": [],
            "supported_commands": [],
            "schema_version": 47,
            "message": err_msg,
        }


def browse_for_ve_cli() -> Optional[str]:
    """Open the native Windows file dialog to choose VE_CLI.exe."""
    if os.name != "nt":
        return None

    class OPENFILENAMEW(ctypes.Structure):
        _fields_ = [
            ("lStructSize", ctypes.wintypes.DWORD),
            ("hwndOwner", ctypes.wintypes.HWND),
            ("hInstance", ctypes.wintypes.HINSTANCE),
            ("lpstrFilter", ctypes.wintypes.LPCWSTR),
            ("lpstrCustomFilter", ctypes.wintypes.LPWSTR),
            ("nMaxCustFilter", ctypes.wintypes.DWORD),
            ("nFilterIndex", ctypes.wintypes.DWORD),
            ("lpstrFile", ctypes.wintypes.LPWSTR),
            ("nMaxFile", ctypes.wintypes.DWORD),
            ("lpstrFileTitle", ctypes.wintypes.LPWSTR),
            ("nMaxFileTitle", ctypes.wintypes.DWORD),
            ("lpstrInitialDir", ctypes.wintypes.LPCWSTR),
            ("lpstrTitle", ctypes.wintypes.LPCWSTR),
            ("Flags", ctypes.wintypes.DWORD),
            ("nFileOffset", ctypes.wintypes.WORD),
            ("nFileExtension", ctypes.wintypes.WORD),
            ("lpstrDefExt", ctypes.wintypes.LPCWSTR),
            ("lCustData", ctypes.wintypes.LPARAM),
            ("lpfnHook", ctypes.c_void_p),
            ("lpTemplateName", ctypes.wintypes.LPCWSTR),
            ("pvReserved", ctypes.c_void_p),
            ("dwReserved", ctypes.wintypes.DWORD),
            ("FlagsEx", ctypes.wintypes.DWORD),
        ]

    OFN_FILEMUSTEXIST = 0x00001000
    OFN_PATHMUSTEXIST = 0x00000800
    OFN_NOCHANGEDIR = 0x00000008
    OFN_EXPLORER = 0x00080000

    file_buffer = ctypes.create_unicode_buffer(4096)
    if DEFAULT_CLI_PATH.is_file():
        file_buffer.value = str(DEFAULT_CLI_PATH)
    else:
        file_buffer.value = "VE_CLI.exe"

    if DEFAULT_CLI_PATH.is_file():
        initial_dir = str(DEFAULT_INSTALL_DIR)
    else:
        prog_dir = Path(os.path.expandvars(r"%LOCALAPPDATA%\Programs"))
        initial_dir = str(prog_dir) if prog_dir.is_dir() else os.path.expandvars("%LOCALAPPDATA%")

    # Create a temporary topmost owner window so the file dialog always opens in front of the browser
    WS_EX_TOPMOST = 0x00000008
    WS_POPUP = 0x80000000
    SW_SHOWNOACTIVATE = 4
    user32 = ctypes.windll.user32
    hwnd_owner = user32.CreateWindowExW(
        WS_EX_TOPMOST,
        "Static",
        "Select VE_CLI.exe",
        WS_POPUP,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    )
    if hwnd_owner:
        user32.ShowWindow(hwnd_owner, SW_SHOWNOACTIVATE)
        user32.SetForegroundWindow(hwnd_owner)
    else:
        hwnd_owner = user32.GetForegroundWindow()

    try:
        ofn = OPENFILENAMEW()
        ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
        ofn.hwndOwner = hwnd_owner
        ofn.lpstrFilter = "Visual Enhancer CLI (VE_CLI.exe)\0VE_CLI.exe;*.exe\0Executable Files (*.exe)\0*.exe\0All Files (*.*)\0*.*\0\0"
        ofn.nFilterIndex = 1
        ofn.lpstrFile = ctypes.cast(file_buffer, ctypes.wintypes.LPWSTR)
        ofn.nMaxFile = len(file_buffer)
        ofn.lpstrInitialDir = initial_dir
        ofn.lpstrTitle = "Select VE_CLI.exe"
        ofn.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR | OFN_EXPLORER
        ofn.lpstrDefExt = "exe"

        if ctypes.windll.comdlg32.GetOpenFileNameW(ctypes.byref(ofn)):
            return file_buffer.value
        return None
    finally:
        if hwnd_owner and hwnd_owner != user32.GetForegroundWindow():
            try:
                user32.DestroyWindow(hwnd_owner)
            except Exception:
                pass
        elif hwnd_owner:
            try:
                user32.DestroyWindow(hwnd_owner)
            except Exception:
                pass


def get_active_connection(connection: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    if connection and isinstance(connection, dict) and connection.get("cli_path"):
        status = check_connection(connection["cli_path"])
        if status.get("connected"):
            return {
                "cli_path": status["cli_path"],
                "gpu": str(connection.get("gpu", "auto") or "auto"),
                "schema_version": status.get("schema_version", 47),
                "supported_commands": set(status.get("supported_commands", [])),
                "supported_options": _CONNECTION_CACHE.get("supported_options", {}),
            }
        raise RuntimeError(status.get("message") or f"VE_CLI.exe is not available at {connection['cli_path']}")

    status = check_connection()
    if not status.get("connected"):
        raise RuntimeError(
            "Visual Enhancer CLI (VE_CLI.exe) is not connected. "
            "Open the Connection node and verify %LOCALAPPDATA%\\Programs\\Visual Enhancer\\VE_CLI.exe, "
            "input the path manually, or click 'Select VE_CLI.exe'."
        )
    return {
        "cli_path": status["cli_path"],
        "gpu": "auto",
        "schema_version": status.get("schema_version", 47),
        "supported_commands": set(status.get("supported_commands", [])),
        "supported_options": _CONNECTION_CACHE.get("supported_options", {}),
    }


def _write_preset_file(path: Path, name: str, settings: dict[str, Any], schema_version: int) -> None:
    payload = {
        "format": "dlss5-visual-enhancer-settings-preset",
        "schema_version": int(schema_version),
        "name": name[:120],
        "settings": settings,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _negotiate_schema_version(
    cli_path: str,
    probe_input: str,
    preset_path: Path,
    name: str,
    settings: dict[str, Any],
    initial_version: int,
) -> int:
    """Discover a compatible preset schema_version for older or newer Visual Enhancer releases."""
    candidates = [initial_version]
    for v in range(47, 0, -1):
        if v not in candidates:
            candidates.append(v)
    for v in range(48, 80):
        if v not in candidates:
            candidates.append(v)

    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    for ver in candidates:
        _write_preset_file(preset_path, name, settings, ver)
        proc = subprocess.run(
            [cli_path, "render", probe_input, "--preset", str(preset_path), "--dry-run", "--json"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            creationflags=creation_flags,
        )
        combined_err = (proc.stderr or "") + "\n" + (proc.stdout or "")
        if "Unsupported preset schema version" not in combined_err:
            with _STATE_LOCK:
                _CONNECTION_CACHE["schema_version"] = ver
                _save_cli_path(cli_path, ver)
            return ver
    return initial_version


def _run_ve_cli_command(
    cli_path: str,
    args: list[str],
    work_dir: Path,
) -> dict[str, Any]:
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    cmd = [cli_path] + args
    comfy_utils = sys.modules.get("comfy.utils")
    comfy_mm = sys.modules.get("comfy.model_management")
    pbar = comfy_utils.ProgressBar(100) if (comfy_utils and hasattr(comfy_utils, "ProgressBar")) else None

    proc = subprocess.Popen(
        cmd,
        cwd=str(Path(cli_path).resolve().parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        creationflags=creation_flags,
    )

    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    def _read_stdout():
        assert proc.stdout is not None
        stdout_chunks.append(proc.stdout.read())

    def _read_stderr():
        assert proc.stderr is not None
        buf = ""
        while True:
            ch = proc.stderr.read(1)
            if not ch:
                break
            stderr_chunks.append(ch)
            if ch in ("\r", "\n"):
                if pbar is not None:
                    match = re.search(r"(\d+(?:\.\d+)?)%", buf)
                    if match:
                        try:
                            pct = max(0, min(100, int(float(match.group(1)))))
                            pbar.update_absolute(pct, 100)
                        except Exception:
                            pass
                buf = ""
            else:
                buf += ch

    t_out = threading.Thread(target=_read_stdout, daemon=True)
    t_err = threading.Thread(target=_read_stderr, daemon=True)
    t_out.start()
    t_err.start()

    try:
        while proc.poll() is None:
            if comfy_mm is not None and hasattr(comfy_mm, "processing_interrupted") and comfy_mm.processing_interrupted():
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                comfy_mm.throw_exception_if_processing_interrupted()
            try:
                proc.wait(timeout=0.15)
            except subprocess.TimeoutExpired:
                pass
    finally:
        t_out.join(timeout=2)
        t_err.join(timeout=2)

    if pbar is not None:
        pbar.update_absolute(100, 100)
    stdout_text = "".join(stdout_chunks)
    stderr_text = "".join(stderr_chunks)
    parsed = _extract_json_from_stdout(stdout_text)

    if proc.returncode != 0 or (parsed is not None and not parsed.get("ok", False)):
        err_detail = ""
        if parsed:
            err_detail = parsed.get("error", "")
            if not err_detail and parsed.get("items"):
                for item in parsed["items"]:
                    if item.get("error"):
                        err_detail = item["error"]
                        break
        if not err_detail:
            err_lines = [ln.strip() for ln in stderr_text.splitlines() if ln.strip() and not ln.strip().startswith("[")]
            err_detail = err_lines[-1] if err_lines else (stderr_text.strip() or stdout_text.strip() or f"Exit code {proc.returncode}")
        raise RuntimeError(f"Visual Enhancer CLI error: {err_detail}")

    return parsed or {"ok": True}


def _tensor_to_png(frame: torch.Tensor, path: Path) -> None:
    arr = frame.detach().cpu().numpy()
    arr = np.clip(arr * 255.0, 0.0, 255.0).round().astype(np.uint8)
    if arr.ndim == 3 and arr.shape[2] == 4:
        img = Image.fromarray(arr, mode="RGBA")
    elif arr.ndim == 3 and arr.shape[2] == 3:
        img = Image.fromarray(arr, mode="RGB")
    elif arr.ndim == 2:
        img = Image.fromarray(arr, mode="L").convert("RGB")
    else:
        img = Image.fromarray(arr[..., :3], mode="RGB")
    img.save(str(path), format="PNG", compress_level=1)


def _png_to_tensor(path: Path, preserve_alpha: bool = False) -> torch.Tensor:
    with Image.open(str(path)) as img:
        converted = img.convert("RGBA" if (preserve_alpha and "A" in img.getbands()) else "RGB")
        arr = np.asarray(converted, dtype=np.float32) / 255.0
    return torch.from_numpy(arr).unsqueeze(0)


def _extract_first_frame_tensor(video_path: str) -> torch.Tensor:
    try:
        import av
        with av.open(video_path, mode="r") as container:
            for frame in container.decode(video=0):
                arr = frame.to_ndarray(format="rgb24").astype(np.float32) / 255.0
                return torch.from_numpy(arr).unsqueeze(0)
    except Exception:
        pass
    return torch.zeros((1, 64, 64, 3), dtype=torch.float32)


def execute_ve_feature(
    *,
    feature_name: str,
    mode: str,
    stage_id: str,
    preset_settings: dict[str, Any],
    cli_command: str = "render",
    cli_extra_args: Optional[list[str]] = None,
    use_preset: bool = True,
    connection: Optional[dict[str, Any]] = None,
    image: Optional[torch.Tensor] = None,
    video: Optional[Any] = None,
    video_only: bool = False,
    force_hdr_video: bool = False,
) -> tuple[torch.Tensor, Any]:
    """Execute a Visual Enhancer feature through VE_CLI.exe for Image or Video mode."""
    conn = get_active_connection(connection)
    cli_path = conn["cli_path"]
    gpu = conn["gpu"]
    supported_commands = conn["supported_commands"]
    supported_options = conn["supported_options"]
    schema_version = conn["schema_version"]

    effective_mode = "Video" if video_only else mode
    if effective_mode not in ("Image", "Video"):
        effective_mode = "Video" if video_only else "Image"

    cmd = cli_command if cli_command in supported_commands else "render"
    cmd_opts = supported_options.get(cmd, set())

    filtered_extra_args: list[str] = []
    if cli_extra_args:
        i = 0
        while i < len(cli_extra_args):
            token = cli_extra_args[i]
            if token.startswith("--"):
                if not cmd_opts or token in cmd_opts:
                    filtered_extra_args.append(token)
                    if i + 1 < len(cli_extra_args) and not cli_extra_args[i + 1].startswith("--"):
                        filtered_extra_args.append(cli_extra_args[i + 1])
                        i += 2
                        continue
                else:
                    if i + 1 < len(cli_extra_args) and not cli_extra_args[i + 1].startswith("--"):
                        i += 2
                        continue
            else:
                filtered_extra_args.append(token)
            i += 1

    if effective_mode == "Image":
        if image is None:
            if video is not None:
                raise ValueError(
                    f"[{feature_name}] Node mode is set to 'Image', but a VIDEO was connected. "
                    "Switch 'mode' to 'Video' or connect an IMAGE input."
                )
            raise ValueError(f"[{feature_name}] Please connect an IMAGE input when mode is 'Image'.")

        batch_size = image.shape[0]
        preserve_alpha = image.shape[-1] == 4

        with tempfile.TemporaryDirectory(prefix="comfy_ve_img_", ignore_cleanup_errors=True) as tmp_dir:
            work_dir = Path(tmp_dir)
            input_paths: list[str] = []
            for idx in range(batch_size):
                in_path = work_dir / f"in_{idx:05d}.png"
                _tensor_to_png(image[idx], in_path)
                input_paths.append(str(in_path))

            settings = dict(preset_settings)
            settings["image_enabled_stages"] = [stage_id]
            settings["video_enabled_stages"] = []
            settings["image_format"] = "PNG"
            settings["image_bit_depth"] = 8

            preset_path = work_dir / "preset.json"
            if use_preset and (not cmd_opts or "--preset" in cmd_opts):
                _write_preset_file(preset_path, feature_name, settings, schema_version)

            output_tensors: list[torch.Tensor] = []
            for idx, in_path in enumerate(input_paths):
                out_path = work_dir / f"out_{idx:05d}.png"
                args = [cmd, in_path]
                if use_preset and (not cmd_opts or "--preset" in cmd_opts):
                    args.extend(["--preset", str(preset_path)])
                args.extend(filtered_extra_args)
                if gpu and gpu != "auto" and (not cmd_opts or "--gpu" in cmd_opts):
                    args.extend(["--gpu", gpu])
                if not cmd_opts or "--format" in cmd_opts:
                    args.extend(["--format", "png"])
                args.extend(["--output", str(out_path), "--json"])

                try:
                    _run_ve_cli_command(cli_path, args, work_dir)
                except RuntimeError as err:
                    if use_preset and "Unsupported preset schema version" in str(err):
                        schema_version = _negotiate_schema_version(
                            cli_path, in_path, preset_path, feature_name, settings, schema_version
                        )
                        _write_preset_file(preset_path, feature_name, settings, schema_version)
                        _run_ve_cli_command(cli_path, args, work_dir)
                    else:
                        raise

                if not out_path.is_file():
                    raise RuntimeError(f"[{feature_name}] VE_CLI.exe did not produce expected output image: {out_path}")
                output_tensors.append(_png_to_tensor(out_path, preserve_alpha=preserve_alpha))

            result_image = torch.cat(output_tensors, dim=0)
            return (result_image, None)

    # Video Mode
    if video is None and image is None:
        raise ValueError(f"[{feature_name}] Please connect a VIDEO input (or IMAGE frame batch) when mode is 'Video'.")

    comfy_temp_dir = Path(folder_paths.get_temp_directory())
    comfy_temp_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="comfy_ve_vid_", ignore_cleanup_errors=True) as tmp_dir:
        work_dir = Path(tmp_dir)
        created_from_images = False

        Input, InputImpl, Types = _get_comfy_video_api()

        if video is not None:
            input_video_path: Optional[str] = None
            if Input is not None and isinstance(video, Input.Video):
                trim_start, trim_dur = video.get_active_trim_window()
                crop_rect = video.get_active_crop_rect()
                stream_src = video.get_stream_source()
                if (
                    trim_start == 0.0
                    and trim_dur == 0.0
                    and crop_rect is None
                    and isinstance(stream_src, str)
                    and os.path.isfile(stream_src)
                ):
                    input_video_path = stream_src
                else:
                    temp_in = work_dir / "input_source.mp4"
                    video.save_to(
                        str(temp_in),
                        format=Types.VideoContainer.MP4,
                        codec=Types.VideoCodec.H264,
                    )
                    input_video_path = str(temp_in)
            elif hasattr(video, "get_stream_source"):
                stream_src = video.get_stream_source()
                if isinstance(stream_src, str) and os.path.isfile(stream_src):
                    input_video_path = stream_src
                else:
                    temp_in = work_dir / "input_source.mp4"
                    video.save_to(str(temp_in))
                    input_video_path = str(temp_in)
            elif isinstance(video, str) and os.path.isfile(video):
                input_video_path = video
            else:
                raise ValueError(f"[{feature_name}] Unsupported VIDEO input object: {type(video)}")
        else:
            # Build a temporary video from the IMAGE batch tensor
            assert image is not None
            created_from_images = True
            if image.shape[0] < 2:
                raise ValueError(
                    f"[{feature_name}] Video mode requires a VIDEO input or an IMAGE batch with at least 2 frames."
                )
            temp_in = work_dir / "input_frames.mp4"
            if InputImpl is not None and Types is not None:
                comp_video = InputImpl.VideoFromComponents(
                    Types.VideoComponents(images=image, frame_rate=Fraction(24))
                )
                comp_video.save_to(
                    str(temp_in),
                    format=Types.VideoContainer.MP4,
                    codec=Types.VideoCodec.H264,
                )
                input_video_path = str(temp_in)
            else:
                import av
                container = av.open(str(temp_in), mode="w")
                stream = container.add_stream("h264", rate=24)
                stream.width = image.shape[2]
                stream.height = image.shape[1]
                stream.pix_fmt = "yuv420p"
                for frame_t in image:
                    arr = np.clip(frame_t.detach().cpu().numpy()[..., :3] * 255.0, 0, 255).round().astype(np.uint8)
                    vf = av.VideoFrame.from_ndarray(arr, format="rgb24")
                    for packet in stream.encode(vf):
                        container.mux(packet)
                for packet in stream.encode():
                    container.mux(packet)
                container.close()
                input_video_path = str(temp_in)

        settings = dict(preset_settings)
        settings["image_enabled_stages"] = []
        settings["video_enabled_stages"] = [stage_id]

        if force_hdr_video:
            settings["hdr_mode"] = True
            settings["codec"] = "H.265"
            settings["container"] = "MP4"
            out_ext = "mp4"
            cli_codec = "hevc"
            cli_container = "mp4"
        else:
            settings.setdefault("codec", "H.264")
            settings.setdefault("container", "MP4")
            out_ext = "mp4"
            cli_codec = "h264"
            cli_container = "mp4"

        preset_path = work_dir / "preset.json"
        if use_preset and (not cmd_opts or "--preset" in cmd_opts):
            _write_preset_file(preset_path, feature_name, settings, schema_version)

        unique_tag = uuid.uuid4().hex[:10]
        final_video_path = comfy_temp_dir / f"ve_{stage_id}_{unique_tag}.{out_ext}"

        args = [cmd, input_video_path]
        if use_preset and (not cmd_opts or "--preset" in cmd_opts):
            args.extend(["--preset", str(preset_path)])
        args.extend(filtered_extra_args)
        if gpu and gpu != "auto" and (not cmd_opts or "--gpu" in cmd_opts):
            args.extend(["--gpu", gpu])
        if not cmd_opts or "--codec" in cmd_opts:
            args.extend(["--codec", cli_codec])
        if not cmd_opts or "--container" in cmd_opts:
            args.extend(["--container", cli_container])
        args.extend(["--output", str(final_video_path), "--json"])

        try:
            _run_ve_cli_command(cli_path, args, work_dir)
        except RuntimeError as err:
            if use_preset and "Unsupported preset schema version" in str(err):
                schema_version = _negotiate_schema_version(
                    cli_path, input_video_path, preset_path, feature_name, settings, schema_version
                )
                _write_preset_file(preset_path, feature_name, settings, schema_version)
                if final_video_path.exists():
                    final_video_path.unlink()
                _run_ve_cli_command(cli_path, args, work_dir)
            else:
                raise

        if not final_video_path.is_file():
            raise RuntimeError(f"[{feature_name}] VE_CLI.exe did not produce expected output video: {final_video_path}")

        if InputImpl is not None:
            result_video = InputImpl.VideoFromFile(str(final_video_path))
            if created_from_images:
                result_images = result_video.get_components().images
            else:
                result_images = _extract_first_frame_tensor(str(final_video_path))
            return (result_images, result_video)
        else:
            return (_extract_first_frame_tensor(str(final_video_path)), str(final_video_path))
