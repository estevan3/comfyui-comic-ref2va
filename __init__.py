from comfy_api.latest import ComfyExtension

from .nodes import ComicPanelRequest, ComicPanelValidate, ComicPanelsToMiniMaxH3Ref2VA, ComicRef2VAAssemble
from .scene import ComicPageToMiniMaxH3Ref2VA, ComicSceneAssemble, ComicSceneDirect, ComicSceneReadRequest


class ComicRef2VAExtension(ComfyExtension):
    async def get_node_list(self):
        return [ComicPanelsToMiniMaxH3Ref2VA, ComicPanelRequest, ComicPanelValidate, ComicRef2VAAssemble,
                ComicPageToMiniMaxH3Ref2VA, ComicSceneReadRequest, ComicSceneDirect, ComicSceneAssemble]


async def comfy_entrypoint():
    return ComicRef2VAExtension()
