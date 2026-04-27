from typing import Dict

from scenes.base import BaseScene
from scenes.template_scene import TemplateScene
from scenes.zhimei_scene import ZhimeiScene


class SceneRegistry:
    def __init__(self):
        self._scenes: Dict[str, BaseScene] = {}

    def register(self, scene: BaseScene) -> None:
        self._scenes[scene.scene_id] = scene

    def get(self, scene_id: str) -> BaseScene:
        if scene_id not in self._scenes:
            raise KeyError(f"unknown scene_id: {scene_id}")
        return self._scenes[scene_id]

    def list_scene_ids(self):
        return sorted(self._scenes.keys())


scene_registry = SceneRegistry()
scene_registry.register(ZhimeiScene())
scene_registry.register(TemplateScene())
