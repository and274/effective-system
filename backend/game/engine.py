"""
游戏引擎 v2：玩家/ NPC 行为分离 + 角色权限控制

核心改动：
1. 意图解析区分玩家行为（记者）和 NPC 行为
2. 记者无权召开新闻发布会、发布官方通报等，需通过影响 NPC 间接实现
3. 每回合结束后：应用持续效果 → 检查 NPC 触发 → 检查事件解除
4. 新增 LLM 标记：[[FACT_CHECK]]、[[DEBUNK_RUMOR xxx]]
5. 移除玩家直接触发 [[PRESS_CONFERENCE]] 的能力
"""
import logging
import re
from typing import Dict, List, Tuple

from game.events import EventSystem
from game.roles import ROLE_INFO, get_role_prompt
from game.state import GameState, PHASE_CONFIG

logger = logging.getLogger("zhimei-backend.engine")

# ===== 记者可执行的动作 =====
PLAYER_ACTIONS = {
    "interview": "采访NPC",
    "publish": "发稿/报道",
    "publish_fact_check": "发布核实/辟谣报道",
    "monitor": "监控舆情",
    "advise": "向NPC建议/请求",
    "wait": "等待观察",
    "check_status": "查看状态",
}

# ===== 记者无权执行的动作（需 NPC 自主触发） =====
RESTRICTED_ACTIONS = {
    "press_conference": "召开新闻发布会 — 只有官方发言人可以决定",
    "official_statement": "发布官方通报 — 只有官方发言人可以发布",
    "rescue_command": "指挥救援 — 只有消防队长可以决定",
}


class GameEngine:
    # 预编译正则
    _CRED_RE = re.compile(r"\[\[CREDIBILITY\s+([+-]?\d+)\]\]")
    _INFO_RE = re.compile(r"\[\[INFO_GAIN\s+(.+?)\]\]")
    _REPORT_RE = re.compile(r"\[\[REPORT_PUBLISHED\]\]")
    _FACT_CHECK_RE = re.compile(r"\[\[FACT_CHECK\]\]")
    _RUMOR_RE = re.compile(r"\[\[RUMOR_ADD\s+(.+?)\]\]")
    _DEBUNK_RE = re.compile(r"\[\[DEBUNK_RUMOR\s+(.+?)\]\]")

    def __init__(self):
        self.event_system = EventSystem()

    def dispatch(self, user_input: str, state: GameState) -> Dict:
        action, role_key, params = self._parse_intent(user_input, state)

        # ===== 权限检查 =====
        if action == "press_conference":
            return self._permission_denied(state, user_input, "press_conference")

        # ===== 阶段角色限制 =====
        if role_key in ROLE_INFO and role_key != "dm":
            role_name = ROLE_INFO[role_key]["name"]
            allowed = PHASE_CONFIG[state.phase]["available_roles"]
            if role_name not in allowed:
                role_key = "dm"
                action = f"阶段限制:{state.phase}"

        # ===== 时间推进 =====
        time_result = state.add_time(2)

        # ===== 随机事件 =====
        random_event = None
        if not state.game_over:
            random_event = self.event_system.check_and_trigger(state)

        # ===== 采访记录 =====
        if role_key in ROLE_INFO and role_key not in ("dm", "netizen"):
            role_name = ROLE_INFO[role_key]["name"]
            if role_name not in state.interviewed:
                state.interviewed.append(role_name)
            state.interview_count[role_name] = state.interview_count.get(role_name, 0) + 1

        # ===== NPC 自主行为 =====
        npc_events = []
        if not state.game_over:
            npc_events = self.event_system.check_npc_triggers(state)

        # ===== 玩家行为触发效果解除 =====
        resolution_results = []
        if action == "publish_fact_check":
            state.reports_fact_checks += 1
            resolution_results = self.event_system.check_player_resolution(state, "fact_check")
        elif role_key == "witness":
            resolution_results = self.event_system.check_player_resolution(state, "interview_witness")
        elif role_key == "fire_chief":
            resolution_results = self.event_system.check_player_resolution(
                state, "interview_fire_chief_after"
            )

        return {
            "intent": action,
            "role_key": role_key,
            "user_input": user_input,
            "state": state.to_dict(),
            "time_advanced": time_result,
            "random_event": random_event,
            "npc_events": npc_events,
            "resolution_results": resolution_results,
        }

    def _parse_intent(self, user_input: str, state: GameState) -> Tuple[str, str, Dict]:
        """解析玩家意图，返回 (action, role_key, params)"""
        text = user_input.strip().lower()
        params: Dict = {}

        # ===== 1. 权限受限动作检测 =====
        if any(k in text for k in ["召开新闻发布会", "开发布会", "举办发布会"]):
            return "press_conference", "dm", params

        # ===== 2. 记者主动行为 =====
        # 发布核实/辟谣报道
        if any(k in text for k in ["核实", "辟谣", "澄清", "调查报道", "事实核查"]):
            if any(k in text for k in ["发布", "写", "发稿", "报道", "稿"]):
                return "publish_fact_check", "dm", params

        # 发稿/报道
        if any(k in text for k in ["发稿", "报道", "写稿", "发布新闻", "发新闻", "写报道"]):
            return "publish", "dm", params

        # 监控舆情
        if any(k in text for k in ["舆情", "网友", "评论", "看看网上", "舆论"]):
            # 但如果明确要采访发言人关于舆情，路由到发言人
            if any(k in text for k in ["发言人", "官方", "赵明"]):
                return "interview", "spokesperson", params
            return "monitor", "netizen", params

        # 向NPC建议（明确表达"建议"/"请求"）
        if any(k in text for k in ["建议", "请求", "提议", "能不能", "可不可以"]):
            if any(k in text for k in ["发布会", "通报", "声明"]):
                return "advise:press_conference", "spokesperson", params
            if any(k in text for k in ["发言人", "官方", "赵明"]):
                return "advise", "spokesperson", params
            return "advise", "dm", params

        # ===== 3. 采访 NPC =====
        if any(k in text for k in ["消防", "队长", "老张", "火情", "救援"]):
            return "interview", "fire_chief", params
        if any(k in text for k in ["医生", "急救", "李薇", "伤亡", "伤员"]):
            return "interview", "doctor", params
        if any(k in text for k in ["群众", "目击", "王阿姨", "居民", "现场"]):
            return "interview", "witness", params
        if any(k in text for k in ["发言人", "官方", "赵明", "通报"]):
            return "interview", "spokesperson", params

        # ===== 4. 查看状态 =====
        if any(k in text for k in ["状态", "进度", "情况", "总结"]):
            return "check_status", "dm", params

        return "unclear", "dm", params

    def _permission_denied(self, state: GameState, user_input: str, action: str) -> Dict:
        """权限不足时的响应"""
        reason = RESTRICTED_ACTIONS.get(action, "你没有权限执行此操作")
        return {
            "intent": f"权限不足:{action}",
            "role_key": "dm",
            "user_input": user_input,
            "state": state.to_dict(),
            "time_advanced": {"phase_advanced": False, "new_phase": None, "persistent_effects": []},
            "random_event": None,
            "npc_events": [],
            "resolution_results": [],
            "dm_override": (
                f"你是记者，{reason}。"
                "但你可以：\n"
                "1. 向新闻发言人赵明建议召开发布会\n"
                "2. 通过发布报道制造舆论压力，间接促成发布会\n"
                "3. 继续采访获取更多事实信息"
            ),
        }

    def build_llm_messages(self, context: Dict, state: GameState) -> List[Dict]:
        """构建 LLM 消息列表"""
        messages: List[Dict] = [
            {"role": "system", "content": get_role_prompt(context["role_key"], state)}
        ]

        # 如果有 dm_override，替换 system prompt
        if context.get("dm_override"):
            messages[0]["content"] = (
                get_role_prompt("dm", state) + "\n\n" + context["dm_override"]
            )

        history = state.messages[-20:] if len(state.messages) > 20 else state.messages
        messages.extend(history)

        # 构建用户消息
        intent = context.get("intent", "")
        user_msg = context.get("user_input", "")
        if intent == "publish":
            user_msg = f"[记者发稿] {user_msg}"
        elif intent == "publish_fact_check":
            user_msg = f"[记者发布核实报道] {user_msg}"
        elif intent == "monitor":
            user_msg = f"[记者监控舆情] {user_msg}"
        elif intent.startswith("advise"):
            user_msg = f"[记者提出建议] {user_msg}"

        messages.append({"role": "user", "content": user_msg})
        return messages

    def process_llm_response(self, response: str, state: GameState) -> Dict:
        """解析 LLM 响应中的标记，更新游戏状态"""
        result: Dict = {"reply": response, "state_changes": []}

        # 1. 公信力变化 [[CREDIBILITY +5]]
        for match in self._CRED_RE.findall(response):
            try:
                delta = int(match)
                state.credibility = max(0, min(100, state.credibility + delta))
                result["state_changes"].append(f"公信力{delta:+d}")
            except ValueError:
                logger.warning("无法解析公信力数值: %s", match)
        response = self._CRED_RE.sub("", response)

        # 2. 信息获取 [[INFO_GAIN xxx]]
        for info_key in self._INFO_RE.findall(response):
            info_key = info_key.strip()
            if info_key in state.info_completeness:
                state.info_completeness[info_key] = True
                result["state_changes"].append(f"获得信息:{info_key}")
            else:
                logger.warning("未知信息键: %s (可用: %s)", info_key, list(state.info_completeness.keys()))
        response = self._INFO_RE.sub("", response)

        # 3. 报道发布 [[REPORT_PUBLISHED]]
        if self._REPORT_RE.search(response):
            state.reports_published += 1
            result["state_changes"].append("报道已发布")
            response = self._REPORT_RE.sub("", response)

        # 4. 核实报道 [[FACT_CHECK]] — 解除谣言类效果
        if self._FACT_CHECK_RE.search(response):
            state.reports_fact_checks += 1
            resolved = state.resolve_effects_by_condition("fact_check")
            for r in resolved:
                result["state_changes"].append(f"核实报道解除效果:{r['title']}")
            response = self._FACT_CHECK_RE.sub("", response)

        # 5. 辟谣 [[DEBUNK_RUMOR xxx]] — 解除特定谣言
        for rumor_title in self._DEBUNK_RE.findall(response):
            rumor_title = rumor_title.strip()
            for effect in state.active_effects:
                if effect.get("category") == "rumor" and rumor_title in effect.get("title", ""):
                    state._resolve_effect_by_id(effect["id"], reason="debunk")
                    result["state_changes"].append(f"辟谣成功:{rumor_title}")
                    break
        response = self._DEBUNK_RE.sub("", response)

        # 6. 新谣言 [[RUMOR_ADD xxx]]
        for rumor in self._RUMOR_RE.findall(response):
            rumor = rumor.strip()
            if rumor:
                rumor_id = f"rumor_{len(state.rumors_active)}"
                state.rumors_active.append(
                    {"id": rumor_id, "title": rumor, "severity": "medium"}
                )
                # 同时作为持续效果
                state.add_active_effect({
                    "id": rumor_id,
                    "title": rumor,
                    "category": "rumor",
                    "severity": "medium",
                    "persistent_effects": {"credibility_per_turn": -2},
                    "resolution": {
                        "conditions": {
                            "press_conference": True,
                            "fact_check": True,
                        },
                        "hint": "需要官方回应或发布核实报道",
                        "max_turns": None,
                    },
                    "turns_active": 0,
                    "triggered_at_phase": state.phase,
                    "max_turns": None,
                })
                result["state_changes"].append(f"新谣言:{rumor}")
        response = self._RUMOR_RE.sub("", response)

        # 7. 兜底：检查未解析的标记
        leftover = re.findall(r"\[\[.*?\]\]", response)
        if leftover:
            logger.warning("LLM 输出中存在未解析的标记: %s", leftover)

        result["reply"] = response.strip()
        return result


engine = GameEngine()
