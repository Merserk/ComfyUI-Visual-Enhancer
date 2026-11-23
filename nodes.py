from typing import Any, Optional

from .ve_cli import (
    DEFAULT_CLI_PATH,
    check_connection,
    execute_ve_feature,
    resolve_candidate_cli_path,
)

CATEGORY = "Visual Enhancer"

FPS_CHOICES = [
    "23.976",
    "25",
    "29.97",
    "30",
    "50",
    "59.94",
    "60",
    "90",
    "119.88",
    "120",
    "144",
    "165",
    "180",
    "240",
    "360",
    "480",
]

MULTIPLIER_CHOICES = ["2x", "3x", "4x", "5x", "6x", "7x", "8x"]

SCALE_CHOICES_MAP = {
    "Source (Original)": 1.0,
    "1600%": 16.0,
    "800%": 8.0,
    "400%": 4.0,
    "300%": 3.0,
    "200%": 2.0,
    "175%": 1.75,
    "150%": 1.5,
    "125%": 1.25,
    "75%": 0.75,
    "50%": 0.5,
    "25%": 0.25,
}

VSR_QUALITY_MAP = {
    "4 - Ultra": 4,
    "3 - High": 3,
    "2 - Medium": 2,
    "1 - Low": 1,
}

RTX_SCALE_MAP = {
    "1×": 1.0,
    "1.5×": 1.5,
    "2×": 2.0,
    "3×": 3.0,
    "4×": 4.0,
}

AI_IMAGE_SCALE_MAP = {
    "1×": 1,
    "2×": 2,
    "4×": 4,
    "6×": 6,
    "8×": 8,
}

AI_VIDEO_SCALE_MAP = {
    "2×": 2,
    "4×": 4,
}

AI_VIDEO_TARGET_MAP = {
    "640x480 (480p)": "640x480",
    "1280x720 (720p)": "1280x720",
    "1920x1080 (Full HD)": "1920x1080",
    "2560x1440 (QHD)": "2560x1440",
    "3840x2160 (4K)": "3840x2160",
    "7680x4320 (8K)": "7680x4320",
}

LUT_RES_MAP = {
    "33³": 33,
    "65³": 65,
    "129³": 129,
}


def _optional_media_inputs() -> dict[str, Any]:
    return {
        "connection": ("VE_CONNECTION", {"tooltip": "Optional connection from the Visual Enhancer Connection node."}),
        "image": ("IMAGE", {"tooltip": "Input image or batch of images (used in Image mode)."}),
        "video": ("VIDEO", {"tooltip": "Input video from Load Video (used in Video mode)."}),
    }


class VE_Connection:
    """Visual Enhancer CLI Connection node. Auto-checks %LOCALAPPDATA%\\Programs\\Visual Enhancer\\VE_CLI.exe."""

    CATEGORY = CATEGORY
    FUNCTION = "connect"
    RETURN_TYPES = ("VE_CONNECTION",)
    RETURN_NAMES = ("connection",)
    OUTPUT_TOOLTIPS = ("Active Visual Enhancer CLI connection state.",)
    DESCRIPTION = (
        "Connects ComfyUI to Visual Enhancer (VE_CLI.exe). Automatically checks "
        "%LOCALAPPDATA%\\Programs\\Visual Enhancer\\VE_CLI.exe on open, or lets you choose VE_CLI.exe directly."
    )
    SEARCH_ALIASES = ["visual enhancer connection", "ve cli", "dlss connection"]

    @classmethod
    def INPUT_TYPES(cls):
        default_path = resolve_candidate_cli_path(str(DEFAULT_CLI_PATH))
        return {
            "required": {
                "ve_cli_path": (
                    "STRING",
                    {
                        "default": default_path,
                        "multiline": False,
                        "tooltip": "Path to VE_CLI.exe (auto-detected at %LOCALAPPDATA%\\Programs\\Visual Enhancer\\VE_CLI.exe).",
                    },
                ),
                "gpu": (
                    ["auto", "0", "1", "2", "3"],
                    {
                        "default": "auto",
                        "tooltip": "GPU device selection for VE_CLI.exe (--gpu auto or NVIDIA GPU index).",
                    },
                ),
            }
        }

    def connect(self, ve_cli_path: str, gpu: str = "auto"):
        status = check_connection(ve_cli_path)
        if not status.get("connected"):
            raise RuntimeError(
                status.get("message")
                or f"Could not find or validate VE_CLI.exe at '{ve_cli_path}'. Input a valid path or click 'Select VE_CLI.exe' on the Connection node."
            )
        return (
            {
                "cli_path": status["cli_path"],
                "gpu": gpu,
                "connected": True,
                "version": status.get("version", ""),
                "devices": status.get("devices", []),
            },
        )


# ============================================================================
# FREE PROCESSING FEATURE NODES (Listed First)
# ============================================================================


class VE_DLSSNeuralRendering:
    """DLSS Neural Rendering processing feature node (Image & Video)."""

    CATEGORY = CATEGORY
    FUNCTION = "process"
    RETURN_TYPES = ("IMAGE", "VIDEO")
    RETURN_NAMES = ("image", "video")
    OUTPUT_TOOLTIPS = ("Processed image (Image mode) or preview frame.", "Processed video (Video mode).")
    DESCRIPTION = "DLSS 5 Neural Rendering enhancement for images and videos via VE_CLI.exe."
    SEARCH_ALIASES = ["dlss 5", "neural rendering", "dlss nr", "visual enhancer"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["Image", "Video"], {"default": "Image", "tooltip": "Processing mode: Image or Video."}),
                "nr_style": (["Style 0", "Style 1", "Style 2"], {"default": "Style 0", "tooltip": "NR Style (--style 0|1|2)."}),
                "nr_preset": (["Preset A", "Preset B"], {"default": "Preset B", "tooltip": "NR Preset (--nr-preset a|b)."}),
                "nr_intensity": (
                    "FLOAT",
                    {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.05, "display": "slider", "tooltip": "NR Intensity (--strength 0..2)."},
                ),
                "nr_passes": (
                    "INT",
                    {"default": 1, "min": 1, "max": 4, "step": 1, "display": "slider", "tooltip": "Number of Neural Rendering passes (1..4)."},
                ),
                "local_tone_strength": (
                    "FLOAT",
                    {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05, "display": "slider", "tooltip": "Local Tone Strength (0..1)."},
                ),
                "local_structure_strength": (
                    "FLOAT",
                    {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05, "display": "slider", "tooltip": "Local Structure Strength (0..1)."},
                ),
                "automatic_mask": (
                    "BOOLEAN",
                    {"default": False, "tooltip": "Enable Automatic Mask for skin structure control."},
                ),
                "skin_structure_strength": (
                    "FLOAT",
                    {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05, "display": "slider", "tooltip": "Skin Structure Strength when Automatic Mask is active (0..1)."},
                ),
                "optical_flow_quality": (
                    ["High", "Medium", "Low"],
                    {"default": "High", "tooltip": "Video NVOFA Optical Flow Quality."},
                ),
                "external_motion_vectors": (
                    "BOOLEAN",
                    {"default": False, "tooltip": "Use external optical flow motion vectors (Video mode)."},
                ),
                "external_flow_path": (
                    "STRING",
                    {"default": "", "multiline": False, "tooltip": "Optional motion vector file (.exr/.flo/.npy) or folder (Video mode)."},
                ),
                "vector_format": (
                    ["Standard", "Blender EXR"],
                    {"default": "Standard", "tooltip": "External motion vector format convention."},
                ),
                "flip_x": ("BOOLEAN", {"default": False, "tooltip": "Flip external motion vector X axis."}),
                "flip_y": ("BOOLEAN", {"default": False, "tooltip": "Flip external motion vector Y axis."}),
            },
            "optional": _optional_media_inputs(),
        }

    def process(
        self,
        mode: str,
        nr_style: str,
        nr_preset: str,
        nr_intensity: float,
        nr_passes: int,
        local_tone_strength: float,
        local_structure_strength: float,
        automatic_mask: bool,
        skin_structure_strength: float,
        optical_flow_quality: str = "High",
        external_motion_vectors: bool = False,
        external_flow_path: str = "",
        vector_format: str = "Standard",
        flip_x: bool = False,
        flip_y: bool = False,
        connection: Optional[dict[str, Any]] = None,
        image=None,
        video=None,
    ):
        style_num = nr_style.replace("Style ", "").strip()
        preset_letter = "a" if nr_preset.endswith("A") else "b"
        ext_flow_clean = external_flow_path.strip().strip('"')
        ext_flow_active = bool(external_motion_vectors and ext_flow_clean)

        settings = {
            "nr_style": nr_style,
            "nr_preset": nr_preset,
            "nr_intensity": float(nr_intensity),
            "nr_passes": int(nr_passes),
            "local_tone_strength": float(local_tone_strength),
            "local_structure_strength": float(local_structure_strength),
            "automatic_mask": bool(automatic_mask),
            "skin_structure_strength": float(skin_structure_strength),
            "nr_optical_flow_quality": optical_flow_quality,
            "nr_external_flow_enabled": ext_flow_active,
            "nr_external_flow_path": ext_flow_clean if ext_flow_active else "",
            "nr_external_flow_convention": vector_format,
            "nr_external_flow_flip_x": bool(flip_x),
            "nr_external_flow_flip_y": bool(flip_y),
        }
        cli_args = [
            "--nr-preset",
            preset_letter,
            "--style",
            style_num,
            "--strength",
            f"{float(nr_intensity):.4g}",
        ]
        return execute_ve_feature(
            feature_name="DLSS Neural Rendering",
            mode=mode,
            stage_id="neural_model",
            preset_settings=settings,
            cli_command="render",
            cli_extra_args=cli_args,
            use_preset=True,
            connection=connection,
            image=image,
            video=video,
        )


class VE_Scaling:
    """Scaling processing feature node (Image & Video)."""

    CATEGORY = CATEGORY
    FUNCTION = "process"
    RETURN_TYPES = ("IMAGE", "VIDEO")
    RETURN_NAMES = ("image", "video")
    OUTPUT_TOOLTIPS = ("Scaled image (Image mode) or preview frame.", "Scaled video (Video mode).")
    DESCRIPTION = "High-precision spatial scaling (Lanczos4, Spline36, Area, Bicubic, Bilinear, Nearest) via VE_CLI.exe."
    SEARCH_ALIASES = ["resize", "scale", "lanczos4", "spline36"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["Image", "Video"], {"default": "Image", "tooltip": "Processing mode: Image or Video."}),
                "image_scaling_method": (
                    ["Lanczos4", "Area", "Bicubic", "Bilinear", "Nearest"],
                    {"default": "Lanczos4", "tooltip": "Scaling filter used in Image mode."},
                ),
                "video_scaling_method": (
                    ["Spline36", "Lanczos", "Bicubic", "Area", "Bilinear"],
                    {"default": "Spline36", "tooltip": "Scaling filter used in Video mode."},
                ),
                "scale": (
                    list(SCALE_CHOICES_MAP.keys()),
                    {"default": "200%", "tooltip": "Output resolution scale percentage."},
                ),
            },
            "optional": _optional_media_inputs(),
        }

    def process(
        self,
        mode: str,
        image_scaling_method: str,
        video_scaling_method: str,
        scale: str,
        connection: Optional[dict[str, Any]] = None,
        image=None,
        video=None,
    ):
        factor = SCALE_CHOICES_MAP.get(scale, 2.0)
        settings = {
            "image_scaling_filter": image_scaling_method,
            "video_scaling_filter": video_scaling_method,
            "upscaling_factor": float(factor),
        }
        return execute_ve_feature(
            feature_name="Scaling",
            mode=mode,
            stage_id="scale_method",
            preset_settings=settings,
            cli_command="render",
            use_preset=True,
            connection=connection,
            image=image,
            video=video,
        )


class VE_DLSSSuperResolution:
    """DLSS Super Resolution processing feature node (Image & Video)."""

    CATEGORY = CATEGORY
    FUNCTION = "process"
    RETURN_TYPES = ("IMAGE", "VIDEO")
    RETURN_NAMES = ("image", "video")
    OUTPUT_TOOLTIPS = ("Upscaled image (Image mode) or preview frame.", "Upscaled video (Video mode).")
    DESCRIPTION = "NVIDIA DLSS Super Resolution & DLAA upscaling for images and videos via VE_CLI.exe."
    SEARCH_ALIASES = ["dlss super resolution", "dlss upscale", "dlaa"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["Image", "Video"], {"default": "Image", "tooltip": "Processing mode: Image or Video."}),
                "dlss_mode": (
                    ["DLAA", "Quality", "Balanced", "Performance", "Ultra Performance"],
                    {"default": "Quality", "tooltip": "DLSS Mode (--mode dlaa|quality|balanced|performance|ultra-performance)."},
                ),
                "dlss_preset": (
                    ["Default", "J", "K", "L", "M"],
                    {"default": "Default", "tooltip": "DLSS Render Preset (Default, J, K, L, M)."},
                ),
                "optical_flow_quality": (
                    ["High", "Medium", "Low"],
                    {"default": "High", "tooltip": "Optical Flow Quality for Video mode."},
                ),
            },
            "optional": _optional_media_inputs(),
        }

    def process(
        self,
        mode: str,
        dlss_mode: str,
        dlss_preset: str,
        optical_flow_quality: str = "High",
        connection: Optional[dict[str, Any]] = None,
        image=None,
        video=None,
    ):
        cli_mode_map = {
            "DLAA": "dlaa",
            "Quality": "quality",
            "Balanced": "balanced",
            "Performance": "performance",
            "Ultra Performance": "ultra-performance",
        }
        settings = {
            "upscale_image_engine": "DLSS",
            "upscale_engine": "DLSS",
            "upscale_image_dlss_mode": dlss_mode,
            "upscale_dlss_mode": dlss_mode,
            "upscale_image_dlss_preset": dlss_preset,
            "upscale_dlss_preset": dlss_preset,
            "upscale_optical_flow_quality": optical_flow_quality,
        }
        cli_args = ["--engine", "dlss", "--mode", cli_mode_map.get(dlss_mode, "quality")]
        return execute_ve_feature(
            feature_name="DLSS Super Resolution",
            mode=mode,
            stage_id="dlss_super_resolution",
            preset_settings=settings,
            cli_command="upscale",
            cli_extra_args=cli_args,
            use_preset=True,
            connection=connection,
            image=image,
            video=video,
        )


class VE_DLSSRayReconstruction:
    """DLSS Ray Reconstruction processing feature node (Image & Video)."""

    CATEGORY = CATEGORY
    FUNCTION = "process"
    RETURN_TYPES = ("IMAGE", "VIDEO")
    RETURN_NAMES = ("image", "video")
    OUTPUT_TOOLTIPS = ("Reconstructed image (Image mode) or preview frame.", "Reconstructed video (Video mode).")
    DESCRIPTION = "Native-resolution (1x) NVIDIA DLSS Ray Reconstruction for images and videos via VE_CLI.exe."
    SEARCH_ALIASES = ["dlss ray reconstruction", "reconstruct", "dlss rr"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["Image", "Video"], {"default": "Image", "tooltip": "Processing mode: Image or Video."}),
                "optical_flow_quality": (
                    ["High", "Medium", "Low"],
                    {"default": "High", "tooltip": "Video NVOFA Optical Flow Quality (--flow-quality high|medium|low)."},
                ),
            },
            "optional": _optional_media_inputs(),
        }

    def process(
        self,
        mode: str,
        optical_flow_quality: str = "High",
        connection: Optional[dict[str, Any]] = None,
        image=None,
        video=None,
    ):
        settings = {
            "rr_optical_flow_quality": optical_flow_quality,
        }
        cli_args = ["--flow-quality", optical_flow_quality.lower()]
        return execute_ve_feature(
            feature_name="DLSS Ray Reconstruction",
            mode=mode,
            stage_id="dlss_ray_reconstruction",
            preset_settings=settings,
            cli_command="reconstruct",
            cli_extra_args=cli_args,
            use_preset=False,
            connection=connection,
            image=image,
            video=video,
        )


class VE_RTXVideoSuperResolution:
    """RTX Video Super Resolution processing feature node (Image & Video)."""

    CATEGORY = CATEGORY
    FUNCTION = "process"
    RETURN_TYPES = ("IMAGE", "VIDEO")
    RETURN_NAMES = ("image", "video")
    OUTPUT_TOOLTIPS = ("Upscaled image (Image mode) or preview frame.", "Upscaled video (Video mode).")
    DESCRIPTION = "NVIDIA RTX Video Super Resolution for images and videos via VE_CLI.exe."
    SEARCH_ALIASES = ["rtx vsr", "rtx video super resolution", "rtx upscale"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["Image", "Video"], {"default": "Image", "tooltip": "Processing mode: Image or Video."}),
                "vsr_quality": (
                    ["4 - Ultra", "3 - High", "2 - Medium", "1 - Low"],
                    {"default": "4 - Ultra", "tooltip": "VSR Quality level (1 - Low to 4 - Ultra)."},
                ),
                "sizing_mode": (
                    ["Scale factor", "Custom dimensions"],
                    {"default": "Scale factor", "tooltip": "Output sizing mode: Scale factor or Custom dimensions."},
                ),
                "scale_factor": (
                    ["1×", "1.5×", "2×", "3×", "4×"],
                    {"default": "2×", "tooltip": "Scale Factor when Sizing Mode is Scale factor."},
                ),
                "width": (
                    "INT",
                    {"default": 3840, "min": 2, "max": 32768, "step": 2, "tooltip": "Target Width (px) when Sizing Mode is Custom dimensions."},
                ),
                "height": (
                    "INT",
                    {"default": 2160, "min": 2, "max": 32768, "step": 2, "tooltip": "Target Height (px) when Sizing Mode is Custom dimensions."},
                ),
                "lock_aspect_ratio": (
                    "BOOLEAN",
                    {"default": True, "tooltip": "Lock Aspect Ratio when using Custom dimensions."},
                ),
            },
            "optional": _optional_media_inputs(),
        }

    def process(
        self,
        mode: str,
        vsr_quality: str,
        sizing_mode: str,
        scale_factor: str,
        width: int,
        height: int,
        lock_aspect_ratio: bool,
        connection: Optional[dict[str, Any]] = None,
        image=None,
        video=None,
    ):
        q_val = VSR_QUALITY_MAP.get(vsr_quality, 4)
        s_val = RTX_SCALE_MAP.get(scale_factor, 2.0)
        settings = {
            "upscale_image_engine": "RTX Video Super Resolution",
            "upscale_engine": "RTX Video Super Resolution",
            "upscale_vsr_enabled": True,
            "upscale_image_vsr_quality": q_val,
            "upscale_vsr_quality": q_val,
            "upscale_image_size_mode": sizing_mode,
            "upscale_size_mode": sizing_mode,
            "upscale_image_scale_factor": float(s_val),
            "upscale_scale_factor": float(s_val),
            "upscale_image_width": int(width),
            "upscale_width": int(width),
            "upscale_image_height": int(height),
            "upscale_height": int(height),
            "upscale_image_aspect_lock": bool(lock_aspect_ratio),
            "upscale_aspect_lock": bool(lock_aspect_ratio),
        }
        return execute_ve_feature(
            feature_name="RTX Video Super Resolution",
            mode=mode,
            stage_id="super_resolution",
            preset_settings=settings,
            cli_command="render",
            use_preset=True,
            connection=connection,
            image=image,
            video=video,
        )


class VE_RTXVideoHDR:
    """RTX Video HDR processing feature node (Video only - automatically locked to Video mode)."""

    CATEGORY = CATEGORY
    FUNCTION = "process"
    RETURN_TYPES = ("IMAGE", "VIDEO")
    RETURN_NAMES = ("image", "video")
    OUTPUT_TOOLTIPS = ("Preview frame.", "HDR10 video output.")
    DESCRIPTION = "NVIDIA RTX Video HDR (SDR to 10-bit HDR conversion) for videos via VE_CLI.exe."
    SEARCH_ALIASES = ["rtx video hdr", "sdr to hdr", "hdr video"]
    VIDEO_ONLY = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["Image", "Video"], {"default": "Video", "tooltip": "Locked to Video mode (RTX Video HDR supports video only)."}),
                "hdr_contrast": (
                    "INT",
                    {"default": 100, "min": 0, "max": 200, "step": 1, "display": "slider", "tooltip": "HDR Contrast (0..200)."},
                ),
                "hdr_saturation": (
                    "INT",
                    {"default": 100, "min": 0, "max": 200, "step": 1, "display": "slider", "tooltip": "HDR Saturation (0..200)."},
                ),
                "middle_gray": (
                    "INT",
                    {"default": 50, "min": 10, "max": 100, "step": 1, "display": "slider", "tooltip": "Middle Gray (10..100)."},
                ),
                "peak_luminance": (
                    "INT",
                    {"default": 1000, "min": 400, "max": 2000, "step": 50, "display": "slider", "tooltip": "Peak Luminance in nits (400..2000)."},
                ),
                "hdr_precision": (
                    ["Packed 10-bit", "Packed 10-bit (FP16)"],
                    {"default": "Packed 10-bit", "tooltip": "HDR internal surface precision."},
                ),
            },
            "optional": _optional_media_inputs(),
        }

    def process(
        self,
        mode: str,
        hdr_contrast: int,
        hdr_saturation: int,
        middle_gray: int,
        peak_luminance: int,
        hdr_precision: str,
        connection: Optional[dict[str, Any]] = None,
        image=None,
        video=None,
    ):
        precision_val = "FP16" if "FP16" in hdr_precision else "Packed 10-bit"
        settings = {
            "upscale_hdr_enabled": True,
            "upscale_hdr_contrast": int(hdr_contrast),
            "upscale_hdr_saturation": int(hdr_saturation),
            "upscale_hdr_middle_gray": int(middle_gray),
            "upscale_hdr_peak_luminance": int(peak_luminance),
            "upscale_hdr_precision": precision_val,
            "hdr_mode": True,
        }
        return execute_ve_feature(
            feature_name="RTX Video HDR",
            mode="Video",
            stage_id="rtx_video_hdr",
            preset_settings=settings,
            cli_command="render",
            use_preset=True,
            connection=connection,
            image=image,
            video=video,
            video_only=True,
            force_hdr_video=True,
        )


class VE_DLSSFrameGeneration:
    """DLSS Frame Generation processing feature node (Video only - automatically locked to Video mode)."""

    CATEGORY = CATEGORY
    FUNCTION = "process"
    RETURN_TYPES = ("IMAGE", "VIDEO")
    RETURN_NAMES = ("image", "video")
    OUTPUT_TOOLTIPS = ("Preview frame.", "Frame-interpolated video output.")
    DESCRIPTION = "NVIDIA DLSS Frame Generation for videos (2x-8x multiplier or target FPS) via VE_CLI.exe."
    SEARCH_ALIASES = ["dlss frame generation", "dlss fg", "interpolate dlss"]
    VIDEO_ONLY = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["Image", "Video"], {"default": "Video", "tooltip": "Locked to Video mode (Frame Generation supports video only)."}),
                "frame_rate_mode": (
                    ["Multiplier", "Target FPS"],
                    {"default": "Multiplier", "tooltip": "Multiply source frame rate or target a specific FPS."},
                ),
                "multiplier": (
                    MULTIPLIER_CHOICES,
                    {"default": "2x", "tooltip": "Frame rate multiplier (2x to 8x) when Frame-rate mode is Multiplier."},
                ),
                "target_fps": (
                    FPS_CHOICES,
                    {"default": "60", "tooltip": "Target Output Frame Rate when Frame-rate mode is Target FPS."},
                ),
                "optical_flow_quality": (
                    ["High", "Medium", "Low"],
                    {"default": "High", "tooltip": "NVOFA Optical Flow Quality."},
                ),
            },
            "optional": _optional_media_inputs(),
        }

    def process(
        self,
        mode: str,
        frame_rate_mode: str,
        multiplier: str,
        target_fps: str,
        optical_flow_quality: str = "High",
        connection: Optional[dict[str, Any]] = None,
        image=None,
        video=None,
    ):
        mult_int = int(multiplier.lower().replace("x", "").strip())
        settings = {
            "frame_interpolation_provider": "DLSS",
            "frame_interpolation_frame_rate_mode": frame_rate_mode,
            "frame_interpolation_multiplier": mult_int,
            "frame_interpolation_target_fps": target_fps,
            "frame_interpolation_optical_flow_quality": optical_flow_quality,
        }
        cli_args = ["--interpolator", "dlss"]
        if frame_rate_mode == "Multiplier":
            cli_args.extend(["--multiplier", str(mult_int)])
        else:
            cli_args.extend(["--fps", str(target_fps)])

        return execute_ve_feature(
            feature_name="DLSS Frame Generation",
            mode="Video",
            stage_id="frame_generation",
            preset_settings=settings,
            cli_command="interpolate",
            cli_extra_args=cli_args,
            use_preset=True,
            connection=connection,
            image=image,
            video=video,
            video_only=True,
        )


class VE_FSRFrameGeneration:
    """FSR Frame Generation processing feature node (Video only - automatically locked to Video mode)."""

    CATEGORY = CATEGORY
    FUNCTION = "process"
    RETURN_TYPES = ("IMAGE", "VIDEO")
    RETURN_NAMES = ("image", "video")
    OUTPUT_TOOLTIPS = ("Preview frame.", "Frame-interpolated video output.")
    DESCRIPTION = "AMD FidelityFX Super Resolution 3 (FSR 3) Frame Generation for videos via VE_CLI.exe."
    SEARCH_ALIASES = ["fsr frame generation", "fsr3", "amd frame generation"]
    VIDEO_ONLY = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["Image", "Video"], {"default": "Video", "tooltip": "Locked to Video mode (FSR Frame Generation supports video only)."}),
                "frame_rate_mode": (
                    ["Multiplier", "Target FPS"],
                    {"default": "Multiplier", "tooltip": "Multiply source frame rate or target a specific FPS."},
                ),
                "multiplier": (
                    MULTIPLIER_CHOICES,
                    {"default": "2x", "tooltip": "Frame rate multiplier (2x to 8x) when Frame-rate mode is Multiplier."},
                ),
                "target_fps": (
                    FPS_CHOICES,
                    {"default": "60", "tooltip": "Target Output Frame Rate when Frame-rate mode is Target FPS."},
                ),
                "fsr_gpu": (
                    "STRING",
                    {"default": "auto", "multiline": False, "tooltip": "DirectX 12 / FidelityFX GPU adapter (auto, DXGI index, or DXGI ID)."},
                ),
            },
            "optional": _optional_media_inputs(),
        }

    def process(
        self,
        mode: str,
        frame_rate_mode: str,
        multiplier: str,
        target_fps: str,
        fsr_gpu: str = "auto",
        connection: Optional[dict[str, Any]] = None,
        image=None,
        video=None,
    ):
        mult_int = int(multiplier.lower().replace("x", "").strip())
        fsr_gpu_clean = (fsr_gpu or "auto").strip() or "auto"
        settings = {
            "frame_interpolation_provider": "FSR 3",
            "fsr_frame_generation_frame_rate_mode": frame_rate_mode,
            "fsr_frame_generation_multiplier": mult_int,
            "fsr_frame_generation_target_fps": target_fps,
            "fsr_adapter_id": fsr_gpu_clean,
        }
        cli_args = ["--interpolator", "fsr3", "--fsr-gpu", fsr_gpu_clean]
        if frame_rate_mode == "Multiplier":
            cli_args.extend(["--multiplier", str(mult_int)])
        else:
            cli_args.extend(["--fps", str(target_fps)])

        return execute_ve_feature(
            feature_name="FSR Frame Generation",
            mode="Video",
            stage_id="fsr_frame_generation",
            preset_settings=settings,
            cli_command="interpolate",
            cli_extra_args=cli_args,
            use_preset=False,
            connection=connection,
            image=image,
            video=video,
            video_only=True,
        )


class VE_VideoSuperResolution:
    """NVIDIA VFX Video Super Resolution processing feature node (Video only - automatically locked to Video mode)."""

    CATEGORY = CATEGORY
    FUNCTION = "process"
    RETURN_TYPES = ("IMAGE", "VIDEO")
    RETURN_NAMES = ("image", "video")
    OUTPUT_TOOLTIPS = ("Preview frame.", "Enhanced video output.")
    DESCRIPTION = "NVIDIA VFX Video Super Resolution (Standard Upscaling, Denoise, Deblur, High-Bitrate modes) via VE_CLI.exe."
    SEARCH_ALIASES = ["video super resolution", "vfx vsr", "nvidia vfx"]
    VIDEO_ONLY = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["Image", "Video"], {"default": "Video", "tooltip": "Locked to Video mode (Video Super Resolution supports video only)."}),
                "mode_family": (
                    ["Standard Upscaling Modes", "Denoise Modes", "Deblur Modes", "High-Bitrate Modes"],
                    {"default": "Standard Upscaling Modes", "tooltip": "VFX VSR mode family."},
                ),
                "quality": (
                    ["Bicubic", "Low", "Medium", "High", "Ultra"],
                    {"default": "High", "tooltip": "Quality preset within the selected Mode family."},
                ),
                "strength": (
                    "FLOAT",
                    {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01, "display": "slider", "tooltip": "Effect strength (0..1)."},
                ),
                "sizing_mode": (
                    ["Scale factor", "Custom dimensions"],
                    {"default": "Scale factor", "tooltip": "Sizing Mode (applies to non-restoration upscaling modes)."},
                ),
                "scale_factor": (
                    ["1x", "1.5x", "2x", "3x", "4x"],
                    {"default": "2x", "tooltip": "Scale factor when Sizing Mode is Scale factor."},
                ),
                "width": (
                    "INT",
                    {"default": 3840, "min": 2, "max": 32768, "step": 2, "tooltip": "Target Width (px) when Sizing Mode is Custom dimensions."},
                ),
                "height": (
                    "INT",
                    {"default": 2160, "min": 2, "max": 32768, "step": 2, "tooltip": "Target Height (px) when Sizing Mode is Custom dimensions."},
                ),
                "lock_aspect_ratio": (
                    "BOOLEAN",
                    {"default": True, "tooltip": "Lock Aspect Ratio when using Custom dimensions."},
                ),
            },
            "optional": _optional_media_inputs(),
        }

    def process(
        self,
        mode: str,
        mode_family: str,
        quality: str,
        strength: float,
        sizing_mode: str,
        scale_factor: str,
        width: int,
        height: int,
        lock_aspect_ratio: bool,
        connection: Optional[dict[str, Any]] = None,
        image=None,
        video=None,
    ):
        family_bases = {
            "Standard Upscaling Modes": 0,
            "Denoise Modes": 8,
            "Deblur Modes": 12,
            "High-Bitrate Modes": 16,
        }
        base = family_bases.get(mode_family, 0)
        if base == 0:
            q_offset = {"Bicubic": 0, "Low": 1, "Medium": 2, "High": 3, "Ultra": 4}.get(quality, 3)
            vsr_mode = q_offset
        else:
            q_offset = {"Bicubic": 0, "Low": 0, "Medium": 1, "High": 2, "Ultra": 3}.get(quality, 2)
            vsr_mode = base + q_offset

        scale_val = float(scale_factor.lower().replace("x", "").strip())
        settings = {
            "vfx_vsr_enabled": True,
            "vfx_vsr_mode": int(vsr_mode),
            "vfx_vsr_strength": float(strength),
            "vfx_size_mode": sizing_mode,
            "vfx_scale_factor": scale_val,
            "vfx_width": int(width),
            "vfx_height": int(height),
            "vfx_aspect_lock": bool(lock_aspect_ratio),
        }
        return execute_ve_feature(
            feature_name="Video Super Resolution",
            mode="Video",
            stage_id="vfx_vsr",
            preset_settings=settings,
            cli_command="render",
            use_preset=True,
            connection=connection,
            image=image,
            video=video,
            video_only=True,
        )


class VE_UpscaleLightweight:
    """Upscale (Lightweight) processing feature node (Video only - automatically locked to Video mode)."""

    CATEGORY = CATEGORY
    FUNCTION = "process"
    RETURN_TYPES = ("IMAGE", "VIDEO")
    RETURN_NAMES = ("image", "video")
    OUTPUT_TOOLTIPS = ("Preview frame.", "Upscaled video output.")
    DESCRIPTION = "Fast lightweight spatial video upscaling with sharpening via VE_CLI.exe."
    SEARCH_ALIASES = ["upscale lightweight", "vfx upscale", "fast video upscale"]
    VIDEO_ONLY = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["Image", "Video"], {"default": "Video", "tooltip": "Locked to Video mode (Upscale Lightweight supports video only)."}),
                "scale_factor": (
                    ["4/3x", "1.5x", "2x", "3x", "4x"],
                    {"default": "2x", "tooltip": "Lightweight upscale factor."},
                ),
                "sharpening_strength": (
                    "FLOAT",
                    {"default": 0.4, "min": 0.0, "max": 1.0, "step": 0.01, "display": "slider", "tooltip": "Sharpening strength (0..1)."},
                ),
            },
            "optional": _optional_media_inputs(),
        }

    def process(
        self,
        mode: str,
        scale_factor: str,
        sharpening_strength: float,
        connection: Optional[dict[str, Any]] = None,
        image=None,
        video=None,
    ):
        scale_map = {
            "4/3x": 4.0 / 3.0,
            "1.5x": 1.5,
            "2x": 2.0,
            "3x": 3.0,
            "4x": 4.0,
        }
        settings = {
            "vfx_upscale_enabled": True,
            "vfx_upscale_scale": float(scale_map.get(scale_factor, 2.0)),
            "vfx_upscale_strength": float(sharpening_strength),
        }
        return execute_ve_feature(
            feature_name="Upscale (Lightweight)",
            mode="Video",
            stage_id="vfx_upscale",
            preset_settings=settings,
            cli_command="render",
            use_preset=True,
            connection=connection,
            image=image,
            video=video,
            video_only=True,
        )


class VE_VideoFrameGeneration:
    """Video Frame Generation processing feature node (Video only - automatically locked to Video mode)."""

    CATEGORY = CATEGORY
    FUNCTION = "process"
    RETURN_TYPES = ("IMAGE", "VIDEO")
    RETURN_NAMES = ("image", "video")
    OUTPUT_TOOLTIPS = ("Preview frame.", "Frame-generated video output.")
    DESCRIPTION = "NVIDIA VFX Video Frame Generation with automatic scene-cut detection via VE_CLI.exe."
    SEARCH_ALIASES = ["video frame generation", "vfx frame generation"]
    VIDEO_ONLY = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["Image", "Video"], {"default": "Video", "tooltip": "Locked to Video mode (Video Frame Generation supports video only)."}),
                "model": (
                    ["Low", "Medium", "High"],
                    {"default": "Medium", "tooltip": "VFX Frame Generation model quality."},
                ),
                "frame_rate_mode": (
                    ["Multiplier", "Target FPS"],
                    {"default": "Multiplier", "tooltip": "Frame-rate mode: Multiplier or Target FPS."},
                ),
                "multiplier": (
                    MULTIPLIER_CHOICES,
                    {"default": "2x", "tooltip": "Multiplier (2x to 8x) when Frame-rate mode is Multiplier."},
                ),
                "target_fps": (
                    "STRING",
                    {"default": "60", "multiline": False, "tooltip": "Target FPS (> 0 and <= 1000) when Frame-rate mode is Target FPS."},
                ),
                "automatic_scene_cut_detection": (
                    "BOOLEAN",
                    {"default": True, "tooltip": "Enable automatic scene-cut detection."},
                ),
            },
            "optional": _optional_media_inputs(),
        }

    def process(
        self,
        mode: str,
        model: str,
        frame_rate_mode: str,
        multiplier: str,
        target_fps: str,
        automatic_scene_cut_detection: bool,
        connection: Optional[dict[str, Any]] = None,
        image=None,
        video=None,
    ):
        model_idx = {"Low": 0, "Medium": 1, "High": 2}.get(model, 1)
        mult_int = int(multiplier.lower().replace("x", "").strip())
        fps_clean = (target_fps or "60").strip() or "60"
        settings = {
            "vfx_frame_generation_enabled": True,
            "vfx_frame_generation_model": int(model_idx),
            "vfx_frame_rate_mode": frame_rate_mode,
            "vfx_frame_multiplier": mult_int,
            "vfx_target_fps": fps_clean,
            "vfx_automatic_shot_detection": bool(automatic_scene_cut_detection),
        }
        return execute_ve_feature(
            feature_name="Video Frame Generation",
            mode="Video",
            stage_id="vfx_frame_generation",
            preset_settings=settings,
            cli_command="render",
            use_preset=True,
            connection=connection,
            image=image,
            video=video,
            video_only=True,
        )


class VE_Coloring:
    """Coloring & 3D LUT grading processing feature node (Image & Video)."""

    CATEGORY = CATEGORY
    FUNCTION = "process"
    RETURN_TYPES = ("IMAGE", "VIDEO")
    RETURN_NAMES = ("image", "video")
    OUTPUT_TOOLTIPS = ("Color-graded image (Image mode) or preview frame.", "Color-graded video (Video mode).")
    DESCRIPTION = "3D .cube LUT & parametric color grading (Light & Color adjustments) for images and videos via VE_CLI.exe."
    SEARCH_ALIASES = ["color grading", "lut", "coloring", "exposure", "contrast"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["Image", "Video"], {"default": "Image", "tooltip": "Processing mode: Image or Video."}),
                "lut_file": (
                    "STRING",
                    {"default": "", "multiline": False, "tooltip": "Optional path to a 3D .cube LUT file."},
                ),
                "lut_resolution": (
                    ["33³", "65³", "129³"],
                    {"default": "33³", "tooltip": "3D LUT grid resolution."},
                ),
                "lut_strength": (
                    "INT",
                    {"default": 100, "min": 0, "max": 200, "step": 1, "display": "slider", "tooltip": "LUT Strength / Mix % (0..200)."},
                ),
                "exposure": (
                    "FLOAT",
                    {"default": 0.0, "min": -3.0, "max": 3.0, "step": 0.05, "display": "slider", "tooltip": "Exposure in EV (-3.0..3.0)."},
                ),
                "contrast": (
                    "INT",
                    {"default": 0, "min": -100, "max": 100, "step": 1, "display": "slider", "tooltip": "Contrast % (-100..100)."},
                ),
                "highlights": (
                    "INT",
                    {"default": 0, "min": -100, "max": 100, "step": 1, "display": "slider", "tooltip": "Highlights % (-100..100)."},
                ),
                "shadows": (
                    "INT",
                    {"default": 0, "min": -100, "max": 100, "step": 1, "display": "slider", "tooltip": "Shadows % (-100..100)."},
                ),
                "whites": (
                    "INT",
                    {"default": 0, "min": -100, "max": 100, "step": 1, "display": "slider", "tooltip": "Whites % (-100..100)."},
                ),
                "blacks": (
                    "INT",
                    {"default": 0, "min": -100, "max": 100, "step": 1, "display": "slider", "tooltip": "Blacks % (-100..100)."},
                ),
                "midtones": (
                    "INT",
                    {"default": 0, "min": -100, "max": 100, "step": 1, "display": "slider", "tooltip": "Midtones % (-100..100)."},
                ),
                "temperature": (
                    "INT",
                    {"default": 0, "min": -100, "max": 100, "step": 1, "display": "slider", "tooltip": "Color Temperature (-100..100)."},
                ),
                "tint": (
                    "INT",
                    {"default": 0, "min": -100, "max": 100, "step": 1, "display": "slider", "tooltip": "Color Tint (-100..100)."},
                ),
                "hue_shift": (
                    "INT",
                    {"default": 0, "min": -180, "max": 180, "step": 1, "display": "slider", "tooltip": "Hue Shift in degrees (-180..180)."},
                ),
                "vibrance": (
                    "INT",
                    {"default": 0, "min": -100, "max": 100, "step": 1, "display": "slider", "tooltip": "Vibrance % (-100..100)."},
                ),
                "saturation": (
                    "INT",
                    {"default": 0, "min": -100, "max": 100, "step": 1, "display": "slider", "tooltip": "Saturation % (-100..100)."},
                ),
            },
            "optional": _optional_media_inputs(),
        }

    def process(
        self,
        mode: str,
        lut_file: str,
        lut_resolution: str,
        lut_strength: int,
        exposure: float,
        contrast: int,
        highlights: int,
        shadows: int,
        whites: int,
        blacks: int,
        midtones: int,
        temperature: int,
        tint: int,
        hue_shift: int,
        vibrance: int,
        saturation: int,
        connection: Optional[dict[str, Any]] = None,
        image=None,
        video=None,
    ):
        settings = {
            "lut_path": lut_file.strip().strip('"'),
            "lut_resolution": LUT_RES_MAP.get(lut_resolution, 33),
            "lut_mix": int(lut_strength),
            "lut_exposure": round(float(exposure), 2),
            "lut_contrast": int(contrast),
            "lut_highlights": int(highlights),
            "lut_shadows": int(shadows),
            "lut_whites": int(whites),
            "lut_blacks": int(blacks),
            "lut_midtones": int(midtones),
            "lut_temperature": int(temperature),
            "lut_tint": int(tint),
            "lut_hue": int(hue_shift),
            "lut_vibrance": int(vibrance),
            "lut_saturation": int(saturation),
        }
        return execute_ve_feature(
            feature_name="Coloring",
            mode=mode,
            stage_id="coloring",
            preset_settings=settings,
            cli_command="render",
            use_preset=True,
            connection=connection,
            image=image,
            video=video,
        )


class VE_Sharpening:
    """Sharpening (AMD CAS / NVIDIA NIS) processing feature node (Image & Video)."""

    CATEGORY = CATEGORY
    FUNCTION = "process"
    RETURN_TYPES = ("IMAGE", "VIDEO")
    RETURN_NAMES = ("image", "video")
    OUTPUT_TOOLTIPS = ("Sharpened image (Image mode) or preview frame.", "Sharpened video (Video mode).")
    DESCRIPTION = "AMD FidelityFX Contrast Adaptive Sharpening (CAS) and NVIDIA Image Sharpening (NIS) via VE_CLI.exe."
    SEARCH_ALIASES = ["sharpen", "amd cas", "nvidia nis", "sharpening"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["Image", "Video"], {"default": "Image", "tooltip": "Processing mode: Image or Video."}),
                "sharpening_method": (
                    ["AMD CAS", "NVIDIA NIS"],
                    {"default": "AMD CAS", "tooltip": "Sharpening algorithm: AMD CAS or NVIDIA NIS."},
                ),
                "sharpness": (
                    "INT",
                    {"default": 50, "min": 0, "max": 100, "step": 1, "display": "slider", "tooltip": "Sharpness strength % (0..100)."},
                ),
            },
            "optional": _optional_media_inputs(),
        }

    def process(
        self,
        mode: str,
        sharpening_method: str,
        sharpness: int,
        connection: Optional[dict[str, Any]] = None,
        image=None,
        video=None,
    ):
        settings = {
            "sharpening_method": sharpening_method,
            "cas_sharpness": int(sharpness),
        }
        return execute_ve_feature(
            feature_name="Sharpening",
            mode=mode,
            stage_id="cas_sharpening",
            preset_settings=settings,
            cli_command="render",
            use_preset=True,
            connection=connection,
            image=image,
            video=video,
        )


class VE_Grain:
    """Film Grain processing feature node (Image & Video)."""

    CATEGORY = CATEGORY
    FUNCTION = "process"
    RETURN_TYPES = ("IMAGE", "VIDEO")
    RETURN_NAMES = ("image", "video")
    OUTPUT_TOOLTIPS = ("Grained image (Image mode) or preview frame.", "Grained video (Video mode).")
    DESCRIPTION = "Realistic film grain synthesis with tonal response and temporal animation via VE_CLI.exe."
    SEARCH_ALIASES = ["film grain", "grain", "noise"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["Image", "Video"], {"default": "Image", "tooltip": "Processing mode: Image or Video."}),
                "grain_amount": (
                    "INT",
                    {"default": 20, "min": 0, "max": 100, "step": 1, "display": "slider", "tooltip": "Grain Amount % (0..100)."},
                ),
                "grain_size": (
                    "FLOAT",
                    {"default": 1.0, "min": 0.5, "max": 4.0, "step": 0.05, "display": "slider", "tooltip": "Grain Size in px (0.5..4.0)."},
                ),
                "color_grain": (
                    "INT",
                    {"default": 0, "min": 0, "max": 100, "step": 1, "display": "slider", "tooltip": "Color Grain chroma amount % (0..100)."},
                ),
                "tonal_response": (
                    "INT",
                    {"default": 70, "min": 0, "max": 100, "step": 1, "display": "slider", "tooltip": "Tonal Response % (0..100)."},
                ),
                "grain_seed": (
                    "INT",
                    {"default": 0, "min": 0, "max": 65535, "step": 1, "display": "slider", "tooltip": "Deterministic Grain Seed (0..65535)."},
                ),
                "animated_grain": (
                    "BOOLEAN",
                    {"default": True, "tooltip": "Animate grain across frames (Video mode)."},
                ),
            },
            "optional": _optional_media_inputs(),
        }

    def process(
        self,
        mode: str,
        grain_amount: int,
        grain_size: float,
        color_grain: int,
        tonal_response: int,
        grain_seed: int,
        animated_grain: bool = True,
        connection: Optional[dict[str, Any]] = None,
        image=None,
        video=None,
    ):
        settings = {
            "grain_amount": int(grain_amount),
            "grain_size": float(grain_size),
            "grain_color": int(color_grain),
            "grain_response": int(tonal_response),
            "grain_seed": int(grain_seed),
            "grain_animated": bool(animated_grain),
        }
        return execute_ve_feature(
            feature_name="Grain",
            mode=mode,
            stage_id="grain",
            preset_settings=settings,
            cli_command="render",
            use_preset=True,
            connection=connection,
            image=image,
            video=video,
        )


# ============================================================================
# PAID (SUBSCRIPTION) PROCESSING FEATURE NODES (Listed at Bottom)
# ============================================================================


class VE_DenoisingPaid:
    """Denoising (Paid) processing feature node (Image & Video)."""

    CATEGORY = CATEGORY
    FUNCTION = "process"
    RETURN_TYPES = ("IMAGE", "VIDEO")
    RETURN_NAMES = ("image", "video")
    OUTPUT_TOOLTIPS = ("Denoised image (Image mode) or preview frame.", "Denoised video (Video mode).")
    DESCRIPTION = "AI Denoising (ClearMagnetar) with optional Noise Adaptation via VE_CLI.exe. Requires an active Visual Enhancer subscription."
    SEARCH_ALIASES = ["denoise", "denoising", "clearmagnetar"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["Image", "Video"], {"default": "Image", "tooltip": "Processing mode: Image or Video."}),
                "noise_adaptation": (
                    "BOOLEAN",
                    {"default": False, "tooltip": "Enable Noise Adaptation translator network."},
                ),
            },
            "optional": _optional_media_inputs(),
        }

    def process(
        self,
        mode: str,
        noise_adaptation: bool = False,
        connection: Optional[dict[str, Any]] = None,
        image=None,
        video=None,
    ):
        settings = {
            "denoise_image_translator": bool(noise_adaptation),
            "denoise_video_translator": bool(noise_adaptation),
        }
        return execute_ve_feature(
            feature_name="Denoising (Paid)",
            mode=mode,
            stage_id="denoising",
            preset_settings=settings,
            cli_command="render",
            use_preset=True,
            connection=connection,
            image=image,
            video=video,
        )


class VE_DeblurringPaid:
    """Deblurring (Paid) processing feature node (Image & Video)."""

    CATEGORY = CATEGORY
    FUNCTION = "process"
    RETURN_TYPES = ("IMAGE", "VIDEO")
    RETURN_NAMES = ("image", "video")
    OUTPUT_TOOLTIPS = ("Deblurred image (Image mode) or preview frame.", "Deblurred video (Video mode).")
    DESCRIPTION = "AI Deblurring (FocusPulsar) for images and videos via VE_CLI.exe. Requires an active Visual Enhancer subscription."
    SEARCH_ALIASES = ["deblur", "deblurring", "focuspulsar"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["Image", "Video"], {"default": "Image", "tooltip": "Processing mode: Image or Video."}),
            },
            "optional": _optional_media_inputs(),
        }

    def process(
        self,
        mode: str,
        connection: Optional[dict[str, Any]] = None,
        image=None,
        video=None,
    ):
        return execute_ve_feature(
            feature_name="Deblurring (Paid)",
            mode=mode,
            stage_id="deblurring",
            preset_settings={},
            cli_command="render",
            use_preset=True,
            connection=connection,
            image=image,
            video=video,
        )


class VE_UpscalePaid:
    """Upscale (Paid) AI Upscaling processing feature node (Image & Video)."""

    CATEGORY = CATEGORY
    FUNCTION = "process"
    RETURN_TYPES = ("IMAGE", "VIDEO")
    RETURN_NAMES = ("image", "video")
    OUTPUT_TOOLTIPS = ("AI-upscaled image (Image mode) or preview frame.", "AI-upscaled video (Video mode).")
    DESCRIPTION = (
        "AI Upscale (VisionNext, RazorNext, PeakMagnetar, OptiPulsar, Lucid, Lucid 2) for images and videos "
        "via VE_CLI.exe. Requires an active Visual Enhancer subscription."
    )
    SEARCH_ALIASES = ["ai upscale", "visionnext", "razornext", "peakmagnetar", "optipulsar", "lucid"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["Image", "Video"], {"default": "Image", "tooltip": "Processing mode: Image or Video."}),
                "image_model": (
                    ["VisionNext", "RazorNext", "PeakMagnetar", "OptiPulsar", "Lucid", "Lucid 2"],
                    {"default": "VisionNext", "tooltip": "AI Upscale model for Image mode."},
                ),
                "image_upscale_factor": (
                    ["1×", "2×", "4×", "6×", "8×"],
                    {"default": "2×", "tooltip": "Upscale Factor (1x, 2x, 4x, 6x, 8x) for Image mode."},
                ),
                "video_model": (
                    ["PeakMagnetar", "OptiPulsar", "RazorNext", "VisionNext"],
                    {"default": "PeakMagnetar", "tooltip": "AI Upscale model for Video mode."},
                ),
                "video_upscale_mode": (
                    ["Multiplier", "Target Resolution"],
                    {"default": "Multiplier", "tooltip": "Video upscale sizing mode: Multiplier (2x/4x) or Target Resolution."},
                ),
                "video_multiplier": (
                    ["2×", "4×"],
                    {"default": "2×", "tooltip": "Video upscale multiplier (2x or 4x) when Video Upscale Mode is Multiplier."},
                ),
                "video_target_resolution": (
                    list(AI_VIDEO_TARGET_MAP.keys()),
                    {"default": "1920x1080 (Full HD)", "tooltip": "Target Output Resolution when Video Upscale Mode is Target Resolution."},
                ),
                "tile_size": (
                    ["auto", "256", "512"],
                    {"default": "auto", "tooltip": "VisionNext tile size (--tile auto|256|512)."},
                ),
                "memory_budget": (
                    ["auto", "unlimited", "12", "8", "6"],
                    {"default": "auto", "tooltip": "RazorNext GPU memory budget in GB (--memory-budget auto|unlimited|12|8|6)."},
                ),
                "ai_framework": (
                    ["auto", "cuda", "xpu", "rocm"],
                    {"default": "auto", "tooltip": "AI Inferencing Framework."},
                ),
                "upscale_gpu": (
                    "STRING",
                    {"default": "auto", "multiline": False, "tooltip": "Upscale GPU selection (auto or DXGI adapter ID)."},
                ),
                "lucid_sharpness": (
                    "INT",
                    {"default": 0, "min": 0, "max": 100, "step": 1, "display": "slider", "tooltip": "Lucid / Lucid 2 Sharpness (0..100)."},
                ),
                "lucid_deblur": (
                    "INT",
                    {"default": 0, "min": 0, "max": 100, "step": 1, "display": "slider", "tooltip": "Lucid / Lucid 2 Deblur (0..100)."},
                ),
                "lucid_denoise": (
                    "INT",
                    {"default": 0, "min": 0, "max": 100, "step": 1, "display": "slider", "tooltip": "Lucid / Lucid 2 Denoise (0..100)."},
                ),
                "lucid_decompression": (
                    "INT",
                    {"default": 0, "min": 0, "max": 100, "step": 1, "display": "slider", "tooltip": "Lucid / Lucid 2 Decompression (0..100)."},
                ),
            },
            "optional": _optional_media_inputs(),
        }

    def process(
        self,
        mode: str,
        image_model: str,
        image_upscale_factor: str,
        video_model: str,
        video_upscale_mode: str,
        video_multiplier: str,
        video_target_resolution: str,
        tile_size: str = "auto",
        memory_budget: str = "auto",
        ai_framework: str = "auto",
        upscale_gpu: str = "auto",
        lucid_sharpness: int = 0,
        lucid_deblur: int = 0,
        lucid_denoise: int = 0,
        lucid_decompression: int = 0,
        connection: Optional[dict[str, Any]] = None,
        image=None,
        video=None,
    ):
        img_scale = AI_IMAGE_SCALE_MAP.get(image_upscale_factor, 2)
        vid_scale = AI_VIDEO_SCALE_MAP.get(video_multiplier, 2)
        vid_target = AI_VIDEO_TARGET_MAP.get(video_target_resolution, "1920x1080")
        tile_int = 0 if tile_size == "auto" else int(tile_size)
        mem_int = -1 if memory_budget == "auto" else (0 if memory_budget == "unlimited" else int(memory_budget))
        gpu_clean = (upscale_gpu or "auto").strip() or "auto"

        settings = {
            "upscale_image_engine": "AI Upscale",
            "upscale_image_model": image_model,
            "upscale_image_visionnext_scale": float(img_scale),
            "upscale_image_razornext_scale": float(img_scale),
            "upscale_image_magnetar_scale": int(img_scale),
            "upscale_image_lucid_scale": int(img_scale),
            "upscale_image_lucid2_scale": int(img_scale),
            "upscale_image_visionnext_tile": tile_int,
            "upscale_image_razornext_memory": mem_int,
            "upscale_image_visionnext_gpu": gpu_clean,
            "upscale_ai_framework": ai_framework,
            "upscale_image_lucid_sharpness": int(lucid_sharpness),
            "upscale_image_lucid_deblur": int(lucid_deblur),
            "upscale_image_lucid_denoise": int(lucid_denoise),
            "upscale_image_lucid_decompression": int(lucid_decompression),
            "upscale_image_lucid2_sharpness": int(lucid_sharpness),
            "upscale_image_lucid2_deblur": int(lucid_deblur),
            "upscale_image_lucid2_denoise": int(lucid_denoise),
            "upscale_image_lucid2_decompression": int(lucid_decompression),
            "upscale_engine": video_model,
            "upscale_video_model": video_model,
            "upscale_peakmagnetar_mode": video_upscale_mode,
            "upscale_peakmagnetar_scale": int(vid_scale),
            "upscale_peakmagnetar_target": vid_target,
        }

        stage_id = "visionnext" if mode == "Image" else "peakmagnetar"
        return execute_ve_feature(
            feature_name="Upscale (Paid)",
            mode=mode,
            stage_id=stage_id,
            preset_settings=settings,
            cli_command="render",
            use_preset=True,
            connection=connection,
            image=image,
            video=video,
        )


class VE_FrameInterpolationPaid:
    """Frame Interpolation (Paid) Glide processing feature node (Video only - automatically locked to Video mode)."""

    CATEGORY = CATEGORY
    FUNCTION = "process"
    RETURN_TYPES = ("IMAGE", "VIDEO")
    RETURN_NAMES = ("image", "video")
    OUTPUT_TOOLTIPS = ("Preview frame.", "Glide frame-interpolated video output.")
    DESCRIPTION = "Glide AI Frame Interpolation for videos via VE_CLI.exe. Requires an active Visual Enhancer subscription."
    SEARCH_ALIASES = ["glide", "frame interpolation", "glide interpolation"]
    VIDEO_ONLY = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["Image", "Video"], {"default": "Video", "tooltip": "Locked to Video mode (Frame Interpolation supports video only)."}),
                "model": (["Glide"], {"default": "Glide", "tooltip": "Frame interpolation model."}),
                "frame_rate_mode": (
                    ["Multiplier", "Target FPS"],
                    {"default": "Multiplier", "tooltip": "Multiply source frame rate or target a specific FPS."},
                ),
                "multiplier": (
                    MULTIPLIER_CHOICES,
                    {"default": "2x", "tooltip": "Frame rate multiplier (2x to 8x) when Frame-rate mode is Multiplier."},
                ),
                "target_fps": (
                    FPS_CHOICES,
                    {"default": "60", "tooltip": "Target Output Frame Rate when Frame-rate mode is Target FPS."},
                ),
                "scene_cut_detection": (
                    "BOOLEAN",
                    {"default": True, "tooltip": "Enable scene cut detection to prevent artifacts across cuts."},
                ),
            },
            "optional": _optional_media_inputs(),
        }

    def process(
        self,
        mode: str,
        model: str,
        frame_rate_mode: str,
        multiplier: str,
        target_fps: str,
        scene_cut_detection: bool = True,
        connection: Optional[dict[str, Any]] = None,
        image=None,
        video=None,
    ):
        mult_int = int(multiplier.lower().replace("x", "").strip())
        settings = {
            "frame_interpolation_provider": "Glide",
            "glide_frame_rate_mode": frame_rate_mode,
            "glide_multiplier": mult_int,
            "glide_target_fps": target_fps,
            "glide_scene_cut_detection": bool(scene_cut_detection),
        }
        cli_args = ["--interpolator", "glide"]
        if frame_rate_mode == "Multiplier":
            cli_args.extend(["--multiplier", str(mult_int)])
        else:
            cli_args.extend(["--fps", str(target_fps)])

        return execute_ve_feature(
            feature_name="Frame Interpolation (Paid)",
            mode="Video",
            stage_id="glide",
            preset_settings=settings,
            cli_command="interpolate",
            cli_extra_args=cli_args,
            use_preset=True,
            connection=connection,
            image=image,
            video=video,
            video_only=True,
        )


# Ordered dictionary: Connection first, Free processing nodes next, Paid processing nodes at the bottom.
NODE_CLASS_MAPPINGS = {
    "VE_Connection": VE_Connection,
    # Free Features
    "VE_DLSSNeuralRendering": VE_DLSSNeuralRendering,
    "VE_Scaling": VE_Scaling,
    "VE_DLSSSuperResolution": VE_DLSSSuperResolution,
    "VE_DLSSRayReconstruction": VE_DLSSRayReconstruction,
    "VE_RTXVideoSuperResolution": VE_RTXVideoSuperResolution,
    "VE_RTXVideoHDR": VE_RTXVideoHDR,
    "VE_DLSSFrameGeneration": VE_DLSSFrameGeneration,
    "VE_FSRFrameGeneration": VE_FSRFrameGeneration,
    "VE_VideoSuperResolution": VE_VideoSuperResolution,
    "VE_UpscaleLightweight": VE_UpscaleLightweight,
    "VE_VideoFrameGeneration": VE_VideoFrameGeneration,
    "VE_Coloring": VE_Coloring,
    "VE_Sharpening": VE_Sharpening,
    "VE_Grain": VE_Grain,
    # Paid Features (Subscription - moved to bottom)
    "VE_DenoisingPaid": VE_DenoisingPaid,
    "VE_DeblurringPaid": VE_DeblurringPaid,
    "VE_UpscalePaid": VE_UpscalePaid,
    "VE_FrameInterpolationPaid": VE_FrameInterpolationPaid,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "VE_Connection": "Connection",
    # Free Features
    "VE_DLSSNeuralRendering": "DLSS Neural Rendering",
    "VE_Scaling": "Scaling",
    "VE_DLSSSuperResolution": "DLSS Super Resolution",
    "VE_DLSSRayReconstruction": "DLSS Ray Reconstruction",
    "VE_RTXVideoSuperResolution": "RTX Video Super Resolution",
    "VE_RTXVideoHDR": "RTX Video HDR",
    "VE_DLSSFrameGeneration": "DLSS Frame Generation",
    "VE_FSRFrameGeneration": "FSR Frame Generation",
    "VE_VideoSuperResolution": "Video Super Resolution",
    "VE_UpscaleLightweight": "Upscale (Lightweight)",
    "VE_VideoFrameGeneration": "Video Frame Generation",
    "VE_Coloring": "Coloring",
    "VE_Sharpening": "Sharpening",
    "VE_Grain": "Grain",
    # Paid Features (Subscription - moved to bottom)
    "VE_DenoisingPaid": "Denoising (Paid)",
    "VE_DeblurringPaid": "Deblurring (Paid)",
    "VE_UpscalePaid": "Upscale (Paid)",
    "VE_FrameInterpolationPaid": "Frame Interpolation (Paid)",
}
