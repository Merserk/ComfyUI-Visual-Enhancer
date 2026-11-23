import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const VE_NODE_ORDER = [
    "VE_Connection",
    // Free Processing Features (First)
    "VE_DLSSNeuralRendering",
    "VE_Scaling",
    "VE_DLSSSuperResolution",
    "VE_DLSSRayReconstruction",
    "VE_RTXVideoSuperResolution",
    "VE_RTXVideoHDR",
    "VE_DLSSFrameGeneration",
    "VE_FSRFrameGeneration",
    "VE_VideoSuperResolution",
    "VE_UpscaleLightweight",
    "VE_VideoFrameGeneration",
    "VE_Coloring",
    "VE_Sharpening",
    "VE_Grain",
    // Paid (Subscription) Processing Features (Bottom)
    "VE_DenoisingPaid",
    "VE_DeblurringPaid",
    "VE_UpscalePaid",
    "VE_FrameInterpolationPaid",
];

const VE_ALL_NODES = new Set(VE_NODE_ORDER);

const VE_VIDEO_ONLY_NODES = new Set([
    "VE_RTXVideoHDR",
    "VE_DLSSFrameGeneration",
    "VE_FSRFrameGeneration",
    "VE_VideoSuperResolution",
    "VE_UpscaleLightweight",
    "VE_VideoFrameGeneration",
    "VE_FrameInterpolationPaid",
]);

const MODE_DEPENDENT_WIDGETS = {
    VE_DLSSNeuralRendering: {
        videoOnly: [
            "optical_flow_quality",
            "external_motion_vectors",
            "external_flow_path",
            "vector_format",
            "flip_x",
            "flip_y",
        ],
    },
    VE_Scaling: {
        imageOnly: ["image_scaling_method"],
        videoOnly: ["video_scaling_method"],
    },
    VE_DLSSSuperResolution: {
        videoOnly: ["optical_flow_quality"],
    },
    VE_DLSSRayReconstruction: {
        videoOnly: ["optical_flow_quality"],
    },
    VE_Grain: {
        videoOnly: ["animated_grain"],
    },
    VE_UpscalePaid: {
        imageOnly: [
            "image_model",
            "image_upscale_factor",
            "tile_size",
            "memory_budget",
            "lucid_sharpness",
            "lucid_deblur",
            "lucid_denoise",
            "lucid_decompression",
        ],
        videoOnly: [
            "video_model",
            "video_upscale_mode",
            "video_multiplier",
            "video_target_resolution",
        ],
    },
};

const veState = {
    connected: false,
    cliPath: "",
    message: "Checking %LOCALAPPDATA%\\Programs\\Visual Enhancer\\VE_CLI.exe...",
    devices: [],
};

function applyNodeWidgetState(node) {
    const comfyClass = node?.comfyClass || node?.type;
    if (!node || !comfyClass || !VE_ALL_NODES.has(comfyClass)) {
        return;
    }

    if (comfyClass === "VE_Connection") {
        node.boxcolor = veState.connected ? "#22c55e" : "#f59e0b";
        const pathWidget = node.widgets?.find((w) => w.name === "ve_cli_path");
        if (pathWidget && veState.cliPath && (!pathWidget.value || veState.connected)) {
            pathWidget.value = veState.cliPath;
        }
        const statusWidget = node.widgets?.find((w) => w.name === "ve_status_display");
        if (statusWidget) {
            statusWidget.value = veState.connected
                ? `Active: ${veState.message}`
                : `Not Found: Input path or click "Select VE_CLI.exe"`;
        }
        node.setDirtyCanvas?.(true, true);
        return;
    }

    const isVideoOnly = VE_VIDEO_ONLY_NODES.has(comfyClass);
    const modeWidget = node.widgets?.find((w) => w.name === "mode");

    if (isVideoOnly && modeWidget) {
        modeWidget.value = "Video";
        modeWidget.disabled = true;
    }

    const currentMode = isVideoOnly ? "Video" : modeWidget?.value || "Image";
    const rules = MODE_DEPENDENT_WIDGETS[comfyClass] || {};
    const imageOnlySet = new Set(rules.imageOnly || []);
    const videoOnlySet = new Set(rules.videoOnly || []);

    node.boxcolor = veState.connected ? "#22c55e" : "#ef4444";

    if (!node.widgets) {
        return;
    }

    for (const w of node.widgets) {
        if (!veState.connected) {
            w.disabled = true;
            continue;
        }
        if (w.name === "mode") {
            w.disabled = isVideoOnly;
            continue;
        }
        if (imageOnlySet.has(w.name)) {
            w.disabled = currentMode !== "Image";
        } else if (videoOnlySet.has(w.name)) {
            w.disabled = currentMode !== "Video";
        } else {
            w.disabled = false;
        }
    }

    node.setDirtyCanvas?.(true, true);
}

function syncAllGraphNodes() {
    const nodes = app.graph?._nodes || [];
    for (const node of nodes) {
        applyNodeWidgetState(node);
    }
}

async function verifyConnectionPath(customPath = null, force = false) {
    try {
        const params = new URLSearchParams();
        if (customPath) {
            params.set("path", customPath);
        }
        if (force) {
            params.set("force", "1");
        }
        const query = params.toString() ? `?${params.toString()}` : "";
        const resp = await api.fetchApi(`/visual_enhancer/status${query}`);
        if (resp.ok) {
            const data = await resp.json();
            veState.connected = Boolean(data.connected);
            veState.cliPath = data.cli_path || veState.cliPath;
            veState.message = data.message || (veState.connected ? "Connected" : "VE_CLI.exe not found");
            veState.devices = data.devices || [];
            syncAllGraphNodes();
            return data;
        }
    } catch (err) {
        console.warn("[Visual Enhancer] Failed to check VE_CLI.exe status:", err);
    }
    return null;
}

async function browseForCliPath(node) {
    const statusWidget = node?.widgets?.find((w) => w.name === "ve_status_display");
    if (statusWidget) {
        statusWidget.value = "Opening file dialog to select VE_CLI.exe...";
        node.setDirtyCanvas?.(true, true);
    }

    try {
        const resp = await api.fetchApi("/visual_enhancer/browse", {
            method: "POST",
        });
        if (resp.ok) {
            const data = await resp.json();
            if (!data.cancelled) {
                veState.connected = Boolean(data.connected);
                veState.cliPath = data.cli_path || veState.cliPath;
                veState.message = data.message || "";
                const pathWidget = node?.widgets?.find((w) => w.name === "ve_cli_path");
                if (pathWidget && data.cli_path) {
                    pathWidget.value = data.cli_path;
                }
                syncAllGraphNodes();
                return;
            } else {
                applyNodeWidgetState(node);
                return;
            }
        }
    } catch (err) {
        console.warn("[Visual Enhancer] Native file dialog unavailable, using prompt fallback:", err);
    }

    const pathWidget = node?.widgets?.find((w) => w.name === "ve_cli_path");
    const manual = window.prompt(
        "Enter the full path to VE_CLI.exe:",
        pathWidget?.value || veState.cliPath || "%LOCALAPPDATA%\\Programs\\Visual Enhancer\\VE_CLI.exe"
    );
    if (manual && manual.trim()) {
        if (pathWidget) {
            pathWidget.value = manual.trim();
        }
        await verifyConnectionPath(manual.trim(), true);
    } else {
        applyNodeWidgetState(node);
    }
}

function initializeVeNode(node) {
    const comfyClass = node?.comfyClass || node?.type;
    if (!node || !VE_ALL_NODES.has(comfyClass) || node.__veInitialized) {
        return;
    }
    node.__veInitialized = true;

    if (comfyClass === "VE_Connection") {
        const pathWidget = node.widgets?.find((w) => w.name === "ve_cli_path");
        if (pathWidget) {
            const origCallback = pathWidget.callback;
            pathWidget.callback = async function (value, ...rest) {
                if (origCallback) {
                    origCallback.call(this, value, ...rest);
                }
                await verifyConnectionPath(value, true);
            };
        }

        if (!node.widgets?.some((w) => w.name === "select_ve_cli_btn")) {
            const btn = node.addWidget("button", "Select VE_CLI.exe", null, () => {
                browseForCliPath(node);
            });
            btn.name = "select_ve_cli_btn";
            btn.label = "Select VE_CLI.exe";
            btn.serialize = false;
        }

        if (!node.widgets?.some((w) => w.name === "ve_status_display")) {
            const statusW = node.addWidget(
                "text",
                "Status",
                veState.connected ? `Active: ${veState.message}` : "Checking VE_CLI.exe...",
                () => {}
            );
            statusW.name = "ve_status_display";
            statusW.disabled = true;
            statusW.serialize = false;
        }

        verifyConnectionPath(pathWidget?.value || null, false);
    } else {
        const modeWidget = node.widgets?.find((w) => w.name === "mode");
        if (modeWidget) {
            if (VE_VIDEO_ONLY_NODES.has(comfyClass)) {
                modeWidget.value = "Video";
                modeWidget.disabled = true;
            }
            const origModeCallback = modeWidget.callback;
            modeWidget.callback = function (value, ...rest) {
                if (VE_VIDEO_ONLY_NODES.has(comfyClass)) {
                    this.value = "Video";
                    value = "Video";
                }
                if (origModeCallback) {
                    origModeCallback.call(this, value, ...rest);
                }
                applyNodeWidgetState(node);
            };
        }
    }

    const origOnConfigure = node.onConfigure;
    node.onConfigure = function (info) {
        if (origOnConfigure) {
            origOnConfigure.call(this, info);
        }
        if (comfyClass === "VE_Connection") {
            const pw = this.widgets?.find((w) => w.name === "ve_cli_path");
            verifyConnectionPath(pw?.value || null, false);
        }
        applyNodeWidgetState(this);
    };

    applyNodeWidgetState(node);
}

app.registerExtension({
    name: "Merserk.VisualEnhancer",

    async setup() {
        if (window.LiteGraph && typeof window.LiteGraph.getNodeTypesInCategory === "function") {
            const origGetNodes = window.LiteGraph.getNodeTypesInCategory.bind(window.LiteGraph);
            window.LiteGraph.getNodeTypesInCategory = function (category, filter) {
                const list = origGetNodes(category, filter);
                if (category === "Visual Enhancer" && Array.isArray(list)) {
                    list.sort((a, b) => {
                        const tA = a?.comfyClass || a?.type || "";
                        const tB = b?.comfyClass || b?.type || "";
                        const iA = VE_NODE_ORDER.indexOf(tA);
                        const iB = VE_NODE_ORDER.indexOf(tB);
                        return (iA === -1 ? 999 : iA) - (iB === -1 ? 999 : iB);
                    });
                }
                return list;
            };
        }

        await verifyConnectionPath();
    },

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!nodeData || !VE_ALL_NODES.has(nodeData.name)) {
            return;
        }
        const origOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = origOnNodeCreated ? origOnNodeCreated.apply(this, arguments) : undefined;
            initializeVeNode(this);
            return r;
        };
    },

    nodeCreated(node) {
        initializeVeNode(node);
    },
});
