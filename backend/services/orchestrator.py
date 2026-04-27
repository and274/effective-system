import json
import logging
import re
from typing import Dict, List, Optional

import httpx
from config import Config

logger = logging.getLogger("zhimei-backend.orchestrator")


class ScenarioOrchestrator:
    def __init__(self):
        self.default_scene_id = Config.DEFAULT_SCENE_ID
        self.enabled = Config.ORCHESTRATOR_ENABLED
        self.api_base = Config.ORCHESTRATOR_API_BASE.rstrip("/")
        self.api_key = Config.ORCHESTRATOR_API_KEY
        self.model = Config.ORCHESTRATOR_MODEL
        self.chat_path = Config.ORCHESTRATOR_CHAT_PATH
        self.chat_type = Config.ORCHESTRATOR_CHAT_TYPE
        self.timeout = Config.ORCHESTRATOR_TIMEOUT_SECONDS
        self.confidence_threshold = Config.ORCHESTRATOR_CONFIDENCE_THRESHOLD
        self.system_prompt = (
            "你是智媒沙盘总调度器，只负责路由，不负责剧情内容。"
            "请仅输出JSON: "
            '{"scene_id":"...", "intent":"...", "confidence":0.0, "reason":"..."}'
        )

    def route(
        self,
        user_message: str,
        requested_scene_id: Optional[str] = None,
        external_user: str = "",
        available_scenes: Optional[List[str]] = None,
    ) -> Dict:
        if requested_scene_id:
            return {"scene_id": requested_scene_id, "source": "request"}
        if not user_message.strip():
            return {"scene_id": self.default_scene_id, "source": "default_empty_message"}
        if not self._is_remote_enabled():
            return {"scene_id": self.default_scene_id, "source": "default_local"}

        allowed_scenes = available_scenes or [self.default_scene_id]
        try:
            text = self._call_remote(user_message=user_message, external_user=external_user)
            parsed = self._parse_result(text)
            scene_id = str(parsed.get("scene_id", "")).strip()
            confidence = float(parsed.get("confidence", 0))
            if scene_id not in allowed_scenes or confidence < self.confidence_threshold:
                logger.info(
                    "Orchestrator 路由置信度不足或场景不可用: scene_id=%s confidence=%.2f allowed=%s",
                    scene_id, confidence, allowed_scenes
                )
                return {
                    "scene_id": self.default_scene_id,
                    "source": "default_remote_fallback",
                    "raw_scene_id": scene_id,
                    "confidence": confidence,
                }
            return {
                "scene_id": scene_id,
                "source": "remote",
                "intent": parsed.get("intent", ""),
                "confidence": confidence,
                "reason": parsed.get("reason", ""),
            }
        except httpx.TimeoutException as exc:
            logger.warning("Orchestrator 远程调用超时: %s", exc)
            return {"scene_id": self.default_scene_id, "source": "default_remote_timeout"}
        except httpx.HTTPStatusError as exc:
            logger.warning("Orchestrator 远程调用返回错误状态: %s %s", exc.response.status_code, exc.response.text[:200])
            return {"scene_id": self.default_scene_id, "source": "default_remote_http_error"}
        except Exception as exc:
            logger.warning("Orchestrator 远程调用失败: %s", exc, exc_info=True)
            return {"scene_id": self.default_scene_id, "source": "default_remote_error"}

    def _is_remote_enabled(self) -> bool:
        return self.enabled and bool(self.api_base) and bool(self.api_key)

    def _call_remote(self, user_message: str, external_user: str) -> str:
        path = self.chat_path if self.chat_path.startswith("/") else f"/{self.chat_path}"
        url = f"{self.api_base}{path}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        params = {"externalUser": external_user or Config.EXTERNAL_USER_DEFAULT}
        body = {
            "content": (
                f"{self.system_prompt}\n"
                f"可选场景: zhimei, pr, public\n"
                f"用户输入: {user_message}"
            ),
            "isRequestHold": False,
            "chatType": self.chat_type,
            "qaId": "",
            "stream": False,
        }
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, params=params, headers=headers, json=body)
            resp.raise_for_status()
            payload = resp.json()
        return self._extract_text(payload)

    @staticmethod
    def _extract_text(payload) -> str:
        if isinstance(payload, dict):
            if isinstance(payload.get("data"), list):
                payload = payload.get("data")
            else:
                return json.dumps(payload, ensure_ascii=False)
        if not isinstance(payload, list):
            return str(payload)

        markdown_parts = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            custom_obj = item.get("customObj")
            if isinstance(custom_obj, dict):
                template = custom_obj.get("template")
                if isinstance(template, str) and template.strip():
                    markdown_parts.append(template.strip())
            receive_message = item.get("receiveMessage")
            if isinstance(receive_message, dict):
                content = receive_message.get("content")
                if isinstance(content, str) and content.strip():
                    markdown_parts.append(content.strip())
            markdown = item.get("markdown")
            if isinstance(markdown, str) and markdown.strip():
                markdown_parts.append(markdown.strip())
        return "\n".join(markdown_parts).strip()

    @staticmethod
    def _parse_result(text: str) -> Dict:
        source = (text or "").strip()
        if not source:
            raise ValueError("empty orchestrator response")
        fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", source, flags=re.IGNORECASE)
        if fenced:
            source = fenced.group(1).strip()
        else:
            brace = re.search(r"\{[\s\S]*\}", source)
            if brace:
                source = brace.group(0)
        return json.loads(source)


orchestrator = ScenarioOrchestrator()
