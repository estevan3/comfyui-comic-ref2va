import inspect
import ipaddress
import json

import nodes

from .analysis import PanelAnalysis


def vision_class():
    cls = nodes.NODE_CLASS_MAPPINGS.get("LlamaVisionChat")
    if cls is None:
        raise RuntimeError("Install/enable comfyui-llama-server and restart ComfyUI; LlamaVisionChat was not registered.")
    inputs = {item.id: item for item in cls.define_schema().inputs}
    if not {"keep_alive", "max_tokens", "temperature", "response_schema"} <= inputs.keys():
        raise RuntimeError("Update comfyui-llama-server with the bundled keep_alive integration before using Comic Ref2VA.")
    return cls


def settings_inputs():
    # Reuse the installed node's interface and defaults, not a parallel model loader.
    return [i for i in vision_class().define_schema().inputs if i.id not in ("image", "prompt", "keep_alive", "response_schema")]


def validate_settings(settings):
    required = {i.id for i in settings_inputs()}
    optional_defaults = {"startup_timeout": 300, "request_timeout": 600, "reasoning": "off", "reasoning_budget": -1,
                        "no_mmproj_offload": False, "image_min_tokens": -1, "image_max_tokens": -1,
                        "mtp": False, "spec_draft_n_max": 3, "spec_draft_n_min": 0}
    accepted = required | optional_defaults.keys()
    if not required - optional_defaults.keys() <= settings.keys() or settings.keys() - accepted:
        raise ValueError("Llama settings do not match the installed LlamaVisionChat interface")
    settings = {**optional_defaults, **settings}
    host = settings["host"]
    if host != "localhost":
        try:
            local = ipaddress.ip_address(host).is_loopback
        except ValueError:
            local = False
        if not local:
            raise ValueError("Comic panel analysis requires a local loopback llama-server")
    if settings["parallel"] != 1:
        raise ValueError("Set Llama parallel=1 for sequential panel analysis")
    return settings


def release_vision_server():
    module = inspect.getmodule(vision_class())
    module.release_server()


def add_vision_node(graph, image, prompt, settings, node_id):
    settings = validate_settings(settings)
    return graph.node("LlamaVisionChat", id=node_id, image=image, prompt=prompt, keep_alive=True,
                      response_schema=json.dumps(PanelAnalysis.model_json_schema()), **settings)
