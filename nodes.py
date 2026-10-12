import json
import logging

from comfy_api.latest import io
from comfy_execution.graph_utils import GraphBuilder, is_link

from .adapter import add_vision_node, release_vision_server, validate_settings
from .analysis import DEFAULT_ANALYSIS_PROMPT, analysis_request, clear_non_speech_speakers, parse_analysis
from .compose import assemble, timing


Settings = io.Custom("LLAMA_VISION_SETTINGS")


def image_inputs(raw_link=False):
    return io.Autogrow.Input("images", template=io.Autogrow.TemplateNames(
        io.Image.Input("image", raw_link=raw_link), names=[f"image_{i}" for i in range(1, 10)], min=1,
    ))


def ordered_images(images):
    # Socket order is the reference order; never depend on API dictionary insertion order.
    names = [f"image_{i}" for i in range(1, 10)]
    if not images or any(k not in names for k in images):
        raise ValueError("connect image_1 through image_9 in panel order")
    connected = [(name, images[name]) for name in names if name in images and images[name] is not None]
    if [name for name, _ in connected] != names[:len(connected)]:
        raise ValueError("image sockets contain a gap; reconnect panels consecutively from image_1 and mirror that order in MiniMax")
    if not connected:
        raise ValueError("at least image_1 is required")
    return connected


class ComicPanelsToMiniMaxH3Ref2VA(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ComicPanelsToMiniMaxH3Ref2VA", display_name="Comic Panels to MiniMax H3 Ref2VA", category="comic/Ref2VA",
            description="Analyze individual panels sequentially with the installed Llama Vision Chat. Reconnect the same original images in the same order to MiniMax. Does not generate video.",
            inputs=[Settings.Input("llama_settings"), image_inputs(raw_link=True),
                    io.Int.Input("duration", default=10, min=4, max=15),
                    io.String.Input("analysis_prompt", default=DEFAULT_ANALYSIS_PROMPT, multiline=True),
                    io.String.Input("extra_instructions", default="", multiline=True, tooltip="Safe directives: camera=static|slow_zoom_in; pace=slow|natural; motion=subtle|hold. Unsupported instructions produce warnings."),
                    io.Boolean.Input("strict_mode", default=True), io.Boolean.Input("debug", default=False),
                    io.String.Input("subject_overrides", default="", multiline=True,
                                    optional=True,
                                    tooltip="Optional JSON edits to existing Subject descriptions. Strict mode accepts only observed details.")],
            outputs=[io.String.Output("prompt"), io.String.Output("analysis_json"), io.String.Output("warnings")],
            enable_expand=True,
        )

    @classmethod
    def execute(cls, llama_settings, images, duration=10, analysis_prompt=DEFAULT_ANALYSIS_PROMPT, extra_instructions="", strict_mode=True, debug=False, subject_overrides=""):
        connected = ordered_images(images)
        timing(duration, len(connected))
        validate_settings(llama_settings)
        graph = GraphBuilder()
        previous = None
        analyses = {}
        for index, (name, image) in enumerate(connected, 1):
            if not is_link(image):
                raise ValueError(f"{name} must be connected to an IMAGE output")
            request = graph.node("ComicPanelRequest", id=f"request_{index}", image=image, panel_index=index,
                                 analysis_prompt=analysis_prompt, previous=previous)
            vision = add_vision_node(graph, image, request.out(0), llama_settings, f"vision_{index}")
            parsed = graph.node("ComicPanelValidate", id=f"validate_{index}", response=vision.out(0),
                                monochrome=request.out(1), panel_index=index, image=image,
                                llama_settings=llama_settings, analysis_prompt=analysis_prompt)
            previous = parsed.out(1)
            analyses[f"panels.panel_{index}"] = parsed.out(0)
        composer = graph.node("ComicRef2VAAssemble", id="assemble", duration=duration, extra_instructions=extra_instructions,
                              strict_mode=strict_mode, debug=debug, subject_overrides=subject_overrides, **analyses)
        return io.NodeOutput(composer.out(0), composer.out(1), composer.out(2), expand=graph.finalize())


class ComicPanelRequest(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="ComicPanelRequest", category="comic/Ref2VA/internal",
                         inputs=[io.Image.Input("image"), io.Int.Input("panel_index"), io.String.Input("analysis_prompt"), io.Int.Input("previous", optional=True)],
                         outputs=[io.String.Output("prompt"), io.Boolean.Output("monochrome")])

    @classmethod
    def execute(cls, image, panel_index, analysis_prompt, previous=None):
        try:
            if (panel_index > 1 and previous != panel_index - 1) or (panel_index == 1 and previous is not None):
                raise ValueError("previous panel has not completed validation")
            if image.ndim != 4 or image.shape[0] != 1 or image.shape[-1] != 3:
                raise ValueError("each socket requires one RGB image, not a batch; split the batch explicitly before connecting")
            monochrome = bool((image[..., 0] - image[..., 1]).abs().max() <= 1 / 255 and (image[..., 1] - image[..., 2]).abs().max() <= 1 / 255)
            return io.NodeOutput(analysis_request(analysis_prompt), monochrome)
        except ValueError as error:
            release_vision_server()
            raise ValueError(f"Panel {panel_index}: {error}") from error


class ComicPanelValidate(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="ComicPanelValidate", category="comic/Ref2VA/internal",
                         inputs=[io.String.Input("response"), io.Boolean.Input("monochrome"), io.Int.Input("panel_index"),
                                 io.Image.Input("image", raw_link=True), Settings.Input("llama_settings"),
                                 io.String.Input("analysis_prompt"), io.Boolean.Input("retry", default=False, optional=True)],
                         outputs=[io.String.Output("analysis"), io.Int.Output("completed_panel")], enable_expand=True)

    @classmethod
    def execute(cls, response, monochrome, panel_index, image, llama_settings, analysis_prompt, retry=False):
        try:
            response, cleared_speakers = clear_non_speech_speakers(response)
            data = parse_analysis(response, panel_index, monochrome)
            envelope = {"panel_index": panel_index, "analysis": data.model_dump(), "repaired": retry,
                        "cleared_non_speech_speakers": cleared_speakers}
            return io.NodeOutput(json.dumps(envelope, ensure_ascii=False), panel_index)
        except ValueError as error:
            if retry or response.strip().startswith("Error:"):
                release_vision_server()
                raise
            graph = GraphBuilder()
            prompt = analysis_request(analysis_prompt) + "\nReinspect the same image. Your previous response failed validation:\n" + str(error) + "\nCorrect these errors without adding facts. Return a complete valid JSON object."
            vision = add_vision_node(graph, image, prompt, llama_settings, "repair_vision")
            validated = graph.node("ComicPanelValidate", id="repair_validate", response=vision.out(0), monochrome=monochrome,
                                   panel_index=panel_index, image=image, llama_settings=llama_settings, analysis_prompt=analysis_prompt, retry=True)
            return io.NodeOutput(validated.out(0), validated.out(1), expand=graph.finalize())


class ComicRef2VAAssemble(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="ComicRef2VAAssemble", category="comic/Ref2VA/internal",
                         inputs=[io.Autogrow.Input("panels", template=io.Autogrow.TemplateNames(io.String.Input("panel"), names=[f"panel_{i}" for i in range(1, 10)], min=1)),
                                 io.Int.Input("duration", default=10, min=4, max=15), io.String.Input("extra_instructions", default=""),
                                 io.Boolean.Input("strict_mode", default=True), io.Boolean.Input("debug", default=False),
                                 io.String.Input("subject_overrides", default="", multiline=True, optional=True)],
                         outputs=[io.String.Output("prompt"), io.String.Output("analysis_json"), io.String.Output("warnings")])

    @classmethod
    def execute(cls, panels, duration, extra_instructions, strict_mode, debug, subject_overrides=""):
        # Runs after all vision nodes, including when the final analyses were cached.
        release_vision_server()
        data = []
        repaired = []
        cleared_speakers = []
        for i in range(1, len(panels) + 1):
            key = f"panel_{i}"
            if key not in panels:
                raise ValueError(f"missing analysis for Panel {i}")
            envelope = json.loads(panels[key])
            if envelope["panel_index"] != i:
                raise ValueError(f"analysis order mismatch for Panel {i}")
            data.append(parse_analysis(json.dumps(envelope["analysis"], ensure_ascii=False), i, False))
            if envelope.get("repaired", False):
                repaired.append(f"Panel {i}: structured analysis required one correction pass; review the diagnostic output.")
            if envelope.get("cleared_non_speech_speakers", 0):
                cleared_speakers.append(f"Panel {i}: ignored {envelope['cleared_non_speech_speakers']} speaker attribution(s) on non-speech text.")
        prompt, diagnostics, warnings = assemble(data, duration, extra_instructions, strict_mode, subject_overrides)
        warnings.extend(repaired)
        warnings.extend(cleared_speakers)
        if repaired or cleared_speakers:
            report = json.loads(diagnostics)
            report["warnings"] = warnings
            diagnostics = json.dumps(report, ensure_ascii=False, indent=2)
        for warning in warnings:
            logging.warning("Comic Ref2VA: %s", warning)
        if debug:
            logging.info("Comic Ref2VA analysis:\n%s", diagnostics)
        return io.NodeOutput(prompt, diagnostics, "\n".join(warnings), ui={"text": [diagnostics if debug else "\n".join(warnings)]})
