import json
import logging
from typing import Dict, Generator, List, Optional

import httpx

from config import Config

logger = logging.getLogger("zhimei-backend.llm")


class LLMClient:
    """LLM 客户端：支持 OpenAI 兼容流式（/chat/completions）与校内 AIHub DM-1（/chat）。"""

    def __init__(self):
        self.api_base = Config.LLM_API_BASE.rstrip("/")
        self.api_key = Config.LLM_API_KEY
        path = getattr(Config, "LLM_CHAT_PATH", "/chat") or "/chat"
        self.chat_path = path if path.startswith("/") else f"/{path}"
        self.chat_type = getattr(Config, "LLM_CHAT_TYPE", "business")
        self.timeout = 120.0
        # 游戏 session_id → AIHub session_id 映射
        self._aihub_sessions: Dict[str, str] = {}

    def _is_mock_mode(self) -> bool:
        return not self.api_key

    def _is_openai_compatible_path(self) -> bool:
        return "chat/completions" in self.chat_path.lower()

    # ── 公开接口 ──────────────────────────────────────────

    def chat(self, messages: List[Dict], game_session_id: str = None) -> str:
        """非流式完整回复。"""
        if self._is_mock_mode():
            return self._mock_reply(messages)

        if self._is_openai_compatible_path():
            return self._openai_chat(messages)

        content = self._build_content(messages)
        aihub_sid = self._aihub_sessions.get(game_session_id) if game_session_id else None

        url, headers, params = self._request_parts()
        body = self._chat_body(content, aihub_sid, stream=False)

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, params=params, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()

        self._save_session_id(data, game_session_id)

        return self._extract_reply(data)

    def chat_stream(self, messages: List[Dict], game_session_id: str = None) -> Generator[str, None, None]:
        """流式回复片段。"""
        if self._is_mock_mode():
            yield from self._mock_reply_stream(messages)
            return

        if self._is_openai_compatible_path():
            yield from self._openai_chat_stream(messages)
            return

        content = self._build_content(messages)
        aihub_sid = self._aihub_sessions.get(game_session_id) if game_session_id else None

        url, headers, params = self._request_parts()
        body = self._chat_body(content, aihub_sid, stream=True)

        collected_sid = None

        with httpx.Client(timeout=self.timeout) as client:
            with client.stream("POST", url, params=params, headers=headers, json=body) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    raw = line.split(":", 1)[1].strip()
                    if not raw or raw == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    sid = chunk.get("sessionId")
                    if sid:
                        collected_sid = sid

                    status = chunk.get("status", "")
                    if status == "reply":
                        text = self._text_from_item(chunk)
                        if text:
                            yield text

        if collected_sid and game_session_id:
            self._aihub_sessions[game_session_id] = collected_sid

    # ── OpenAI 兼容（SiliconFlow、OpenAI 等）──────────────────

    @staticmethod
    def _normalize_openai_messages(messages: List[Dict]) -> List[Dict]:
        out: List[Dict] = []
        for m in messages:
            role = m.get("role")
            content = m.get("content", "")
            if role not in ("system", "user", "assistant"):
                continue
            if not isinstance(content, str):
                content = str(content)
            out.append({"role": role, "content": content})
        return out

    def _openai_chat(self, messages: List[Dict]) -> str:
        url = f"{self.api_base}{self.chat_path}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": Config.LLM_MODEL,
            "messages": self._normalize_openai_messages(messages),
            "stream": False,
        }
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        choices = data.get("choices") if isinstance(data, dict) else None
        if not choices:
            return ""
        msg = (choices[0] or {}).get("message") or {}
        return (msg.get("content") or "").strip()

    def _openai_chat_stream(self, messages: List[Dict]) -> Generator[str, None, None]:
        url = f"{self.api_base}{self.chat_path}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": Config.LLM_MODEL,
            "messages": self._normalize_openai_messages(messages),
            "stream": True,
        }
        with httpx.Client(timeout=self.timeout) as client:
            with client.stream("POST", url, headers=headers, json=payload) as resp:
                resp.raise_for_status()
                # 上游多为 UTF-8 JSON；避免 httpx 按 ISO-8859-1 误解码导致中文异常
                try:
                    resp.encoding = "utf-8"
                except Exception:
                    pass
                for line in resp.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data:"):
                        raw = line.split(":", 1)[1].strip()
                    elif line.startswith("{"):  # 少数网关不按 SSE 前缀返回
                        raw = line.strip()
                    else:
                        continue
                    if raw == "[DONE]":
                        break
                    try:
                        chunk = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = (choices[0] or {}).get("delta") or {}
                    piece = delta.get("content")
                    if isinstance(piece, str) and piece:
                        yield piece

    # ── 内部方法 ──────────────────────────────────────────

    def _request_parts(self):
        url = f"{self.api_base}{self.chat_path}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        params = {"externalUser": Config.EXTERNAL_USER_DEFAULT}
        return url, headers, params

    def _chat_body(self, content: str, aihub_sid: Optional[str], stream: bool) -> dict:
        body = {
            "content": content,
            "isRequestHold": False,
            "chatType": self.chat_type,
            "qaId": "",
            "stream": stream,
        }
        if aihub_sid:
            body["sessionId"] = aihub_sid
        return body

    def _build_content(self, messages: List[Dict]) -> str:
        """将 OpenAI 风格 messages 数组转为 AIHub content 字符串。

        DM-1 的 System Prompt 已在 AIHub 后台配置，这里只发角色指令 + 对话 + 当前输入。
        """
        parts = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                parts.append(f"[角色指令]\n{content}")
            elif role == "user":
                parts.append(f"[玩家]\n{content}")
            elif role == "assistant":
                parts.append(f"[助手]\n{content}")
        return "\n\n".join(parts)

    def _save_session_id(self, data, game_session_id: str):
        """从 AIHub 响应中提取并保存 sessionId。"""
        if not game_session_id:
            return
        sid = None
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("sessionId"):
                    sid = item["sessionId"]
                    break
        elif isinstance(data, dict):
            sid = data.get("sessionId")
        if sid:
            self._aihub_sessions[game_session_id] = sid

    def _extract_reply(self, data) -> str:
        """从 AIHub /chat 非流式响应中提取文本。

        AIHub 非流式返回格式为 list，每个元素是一个 chunk：
        - status=begin: 包含 roleFrom、用户输入回显、sessionId
        - status=reply: 包含 markdown（token片段或完整文本）
        - status=end: 结束标记

        同一次响应可能包含多个 agent turn（每个 turn = begin+reply(s)+end），
        第一个 turn 通常是 token-by-token 流式，后续 turn 包含完整文本。
        我们按 turn 分组，取每个 turn 的完整文本拼接。
        """
        if isinstance(data, list):
            # 按 agent turn 分组，收集每个 turn 的完整文本
            turns = []
            current_turn_parts = []
            in_reply = False

            for item in data:
                if not isinstance(item, dict):
                    continue
                status = item.get("status", "")

                if status == "begin":
                    # 新 turn 开始，如果之前有收集的内容则保存
                    if current_turn_parts:
                        turn_text = "".join(current_turn_parts).strip()
                        if turn_text:
                            turns.append(turn_text)
                        current_turn_parts = []
                    in_reply = False

                elif status == "reply":
                    md = item.get("markdown", "")
                    if md:
                        current_turn_parts.append(md)
                    in_reply = True

                elif status == "end":
                    in_reply = False

            # 保存最后一个 turn
            if current_turn_parts:
                turn_text = "".join(current_turn_parts).strip()
                if turn_text:
                    turns.append(turn_text)

            # 去重：如果 token-by-token 和完整文本 turn 内容相同，只保留一份
            if len(turns) >= 2:
                # 找出最长的 turn（通常是完整文本）
                longest = max(turns, key=len)
                # 检查其他 turn 是否是 longest 的子串
                deduped = []
                for t in turns:
                    if t == longest or len(t) < len(longest) * 0.8:
                        # 短文本很可能是 token-by-token 版本，跳过
                        continue
                    deduped.append(t)
                if longest:
                    deduped.append(longest)
                if deduped:
                    turns = deduped

            return "\n\n".join(turns).strip() if turns else ""

        elif isinstance(data, dict):
            items = data.get("data")
            if items and isinstance(items, list):
                return self._extract_reply(items)
            text = self._text_from_item(data)
            return text if text else json.dumps(data, ensure_ascii=False)

        return str(data)

    @staticmethod
    def _text_from_item(item) -> Optional[str]:
        """从单条 AIHub 响应项提取文本。"""
        if not isinstance(item, dict):
            return None
        # 优先级：receiveMessage.content > markdown > customObj.template
        rm = item.get("receiveMessage")
        if isinstance(rm, dict):
            c = rm.get("content")
            if isinstance(c, str) and c.strip():
                return c.strip()
        md = item.get("markdown")
        if isinstance(md, str) and md.strip():
            return md.strip()
        co = item.get("customObj")
        if isinstance(co, dict):
            t = co.get("template")
            if isinstance(t, str) and t.strip():
                return t.strip()
        return None

    # ── Mock 模式 ─────────────────────────────────────────

    @staticmethod
    def _mock_reply(messages: List[Dict]) -> str:
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = m.get("content", "")
                break
        if "采访" in last_user or "问" in last_user:
            return (
                "感谢你的提问。根据我掌握的信息，目前情况如下：\n"
                "火灾发生在阳光花园小区3号楼，消防队已到场扑救。"
                "具体起火原因还在调查中，我们会在确认后第一时间通报。"
                "[[INFO_GAIN 现场情况]] [[CREDIBILITY +2]]"
            )
        if "发布" in last_user or "报道" in last_user:
            return (
                "报道已提交审核。由于信息尚不完整，建议补充更多现场细节后再发布。"
                "[[REPORT_PUBLISHED]] [[CREDIBILITY -3]]"
            )
        return (
            "当前为本地演示模式，你可以继续采访或发布报道。"
            "[[INFO_GAIN 官方回应]]"
        )

    @staticmethod
    def _mock_reply_stream(messages: List[Dict]) -> Generator[str, None, None]:
        reply = LLMClient._mock_reply(messages)
        for char in reply:
            yield char


llm_client = LLMClient()
