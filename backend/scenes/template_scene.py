from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Generator, List, Tuple
import uuid

from scenes.base import BaseScene


@dataclass
class TemplateSceneState:
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: datetime = field(default_factory=datetime.now)
    messages: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "message_count": len(self.messages),
        }


class TemplateScene(BaseScene):
    """
    新场景接入模板：
    1) 替换 scene_id / display_name
    2) 替换 State 数据结构
    3) 实现 run_turn / stream_turn 业务逻辑
    """

    scene_id = "template"
    display_name = "模板场景"

    def create_state(self) -> TemplateSceneState:
        return TemplateSceneState()

    def get_role_info(self, role_key: str) -> Dict:
        return {"name": "模板助手", "color": "#6B7280", "avatar": "🤖", "role_key": role_key}

    def run_turn(self, user_message: str, state: TemplateSceneState) -> Dict:
        reply = f"[template] 已收到: {user_message}"
        state.messages.append({"role": "user", "content": user_message})
        state.messages.append({"role": "assistant", "content": reply})
        return {
            "role": self.get_role_info("assistant"),
            "reply": reply,
            "state": state.to_dict(),
            "state_changes": [],
            "random_event": None,
        }

    def stream_turn(
        self, user_message: str, state: TemplateSceneState
    ) -> Tuple[Dict, Generator[str, None, None]]:
        full_reply = f"[template] 已收到: {user_message}"

        def token_stream() -> Generator[str, None, None]:
            for token in full_reply:
                yield token

        def finalize(reply: str) -> Dict:
            state.messages.append({"role": "user", "content": user_message})
            state.messages.append({"role": "assistant", "content": reply})
            return {
                "reply": reply,
                "state": state.to_dict(),
                "state_changes": [],
                "random_event": None,
            }

        return {"role": self.get_role_info("assistant"), "finalize": finalize}, token_stream()

    def serialize_state(self, state: TemplateSceneState) -> Dict:
        return {
            "session_id": state.session_id,
            "created_at": state.created_at.isoformat(),
            "messages": state.messages,
        }

    def deserialize_state(self, payload: Dict) -> TemplateSceneState:
        return TemplateSceneState(
            session_id=payload.get("session_id", str(uuid.uuid4())[:8]),
            created_at=datetime.fromisoformat(payload.get("created_at", datetime.now().isoformat())),
            messages=payload.get("messages", []),
        )
