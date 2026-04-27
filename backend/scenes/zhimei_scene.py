from typing import Dict, Generator, Tuple
from dataclasses import asdict
from datetime import datetime

from game.engine import engine
from game.roles import ROLE_INFO, get_publish_prompt
from game.state import GameState
from scenes.base import BaseScene
from services.llm_client import llm_client


class ZhimeiScene(BaseScene):
    scene_id = "zhimei"
    display_name = "智媒火灾演练"

    def create_state(self) -> GameState:
        return GameState()

    def get_role_info(self, role_key: str) -> Dict:
        return ROLE_INFO.get(role_key, ROLE_INFO["dm"])

    def run_turn(self, user_message: str, state: GameState) -> Dict:
        context = engine.dispatch(user_message, state)

        # 根据意图选择 prompt
        if context.get("dm_override"):
            messages = engine.build_llm_messages(context, state)
        elif context["intent"] in ("publish", "publish_fact_check", "advise"):
            messages = self._build_action_messages(context, state)
        else:
            messages = engine.build_llm_messages(context, state)

        reply = llm_client.chat(messages, game_session_id=state.session_id)
        result = engine.process_llm_response(reply, state)

        state.messages.append({"role": "user", "content": user_message})
        state.messages.append({"role": "assistant", "content": result["reply"]})

        return {
            "role": self.get_role_info(context["role_key"]),
            "reply": result["reply"],
            "state": state.to_dict(),
            "state_changes": result["state_changes"],
            "random_event": context.get("random_event"),
            "npc_events": context.get("npc_events", []),
            "resolution_results": context.get("resolution_results", []),
        }

    def stream_turn(self, user_message: str, state: GameState) -> Tuple[Dict, Generator[str, None, None]]:
        context = engine.dispatch(user_message, state)

        # 根据意图选择 prompt
        if context.get("dm_override"):
            messages = engine.build_llm_messages(context, state)
        elif context["intent"] in ("publish", "publish_fact_check", "advise"):
            messages = self._build_action_messages(context, state)
        else:
            messages = engine.build_llm_messages(context, state)

        role_info = self.get_role_info(context["role_key"])

        def token_stream() -> Generator[str, None, None]:
            for token in llm_client.chat_stream(messages, game_session_id=state.session_id):
                yield token

        def finalize(full_reply: str) -> Dict:
            result = engine.process_llm_response(full_reply, state)
            state.messages.append({"role": "user", "content": user_message})
            state.messages.append({"role": "assistant", "content": result["reply"]})
            return {
                "reply": result["reply"],
                "state": state.to_dict(),
                "state_changes": result["state_changes"],
                "random_event": context.get("random_event"),
                "npc_events": context.get("npc_events", []),
                "resolution_results": context.get("resolution_results", []),
            }

        return {
            "role": role_info,
            "finalize": finalize,
        }, token_stream()

    def _build_action_messages(self, context: Dict, state: GameState) -> list:
        """为 publish / advise 等非采访动作构建消息"""
        action_type = context["intent"]
        if action_type.startswith("advise"):
            action_type = "advise"
        system_prompt = get_publish_prompt(action_type, state)
        messages = [{"role": "system", "content": system_prompt}]
        history = state.messages[-10:] if len(state.messages) > 10 else state.messages
        messages.extend(history)
        messages.append({"role": "user", "content": context.get("user_input", "")})
        return messages

    def serialize_state(self, state: GameState) -> Dict:
        payload = asdict(state)
        payload["created_at"] = state.created_at.isoformat()
        return payload

    def deserialize_state(self, payload: Dict) -> GameState:
        data = dict(payload)
        created_at_raw = data.get("created_at")
        if isinstance(created_at_raw, str):
            data["created_at"] = datetime.fromisoformat(created_at_raw)
        return GameState(**data)
