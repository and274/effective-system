"""
事件系统 v2：持续影响 + 解除机制 + NPC自主行为

设计原则：
- 事件触发后效果持续生效，直到被解除条件满足
- 谣言类事件必须通过玩家行动或NPC自主行为来解除
- 正面事件自动到期消退
- NPC根据局势自主行动，玩家无法直接控制
"""
from typing import Dict, List, Optional
import random


# ===== 事件定义 =====
# instant_effects: 触发时一次性应用
# persistent_effects: 每回合持续应用
# resolution.conditions: 满足任一条件即解除
# resolution.max_turns: 最大持续回合（None=必须主动解除）

EVENT_DEFINITIONS = [
    {
        "id": "secondary_fire",
        "title": "次生火灾",
        "description": "火势蔓延到相邻仓库，情况紧急！",
        "category": "disaster",
        "trigger_phase": ["信息采集"],
        "probability": 0.15,
        "severity": "high",
        "instant_effects": {"credibility": -5},
        "persistent_effects": {"credibility_per_turn": -2},
        "resolution": {
            "conditions": {
                "interview_fire_chief_after": True,
            },
            "hint": "采访消防队长了解最新救援进展可能缓解局势",
            "max_turns": 4,
        },
    },
    {
        "id": "rumor_death_toll",
        "title": "谣言：死亡人数超50人",
        "description": "网络出现'死亡人数超50人'的谣言并快速扩散，引发公众恐慌。",
        "category": "rumor",
        "trigger_phase": ["信息采集", "初步报道"],
        "probability": 0.2,
        "severity": "high",
        "instant_effects": {"credibility": -5},
        "persistent_effects": {"credibility_per_turn": -3},
        "resolution": {
            "conditions": {
                "press_conference": True,
                "fact_check": True,
            },
            "hint": "发布核实报道或等待官方召开新闻发布会",
            "max_turns": None,
        },
    },
    {
        "id": "rumor_government_coverup",
        "title": "谣言：政府隐瞒真相",
        "description": "网络出现'政府在隐瞒事故真相'的阴谋论调，舆论进一步恶化。",
        "category": "rumor",
        "trigger_phase": ["初步报道", "舆论应对"],
        "probability": 0.25,
        "severity": "critical",
        "instant_effects": {"credibility": -8},
        "persistent_effects": {"credibility_per_turn": -4},
        "resolution": {
            "conditions": {
                "press_conference": True,
                "fact_check": True,
                "official_statement": True,
            },
            "hint": "需要官方召开新闻发布会或发布权威声明来辟谣",
            "max_turns": None,
        },
    },
    {
        "id": "official_attention",
        "title": "上级关注",
        "description": "上级部门密切关注事故进展，要求全力救援并严查责任。",
        "category": "official",
        "trigger_phase": ["最终发布"],
        "probability": 0.4,
        "severity": "low",
        "instant_effects": {"credibility": +5},
        "persistent_effects": {"credibility_per_turn": +1},
        "resolution": {
            "conditions": {
                "phase_change": True,
            },
            "hint": "上级关注将持续到阶段结束",
            "max_turns": 3,
        },
    },
    {
        "id": "witness_viral",
        "title": "现场视频流出",
        "description": "一段现场群众拍摄的视频在网上传播，画面触目惊心，引发广泛关注。",
        "category": "social",
        "trigger_phase": ["信息采集", "初步报道"],
        "probability": 0.2,
        "severity": "medium",
        "instant_effects": {"credibility": -3},
        "persistent_effects": {"credibility_per_turn": -1},
        "resolution": {
            "conditions": {
                "fact_check": True,
                "interview_witness": True,
            },
            "hint": "采访现场群众确认视频真实性，或发布核实报道",
            "max_turns": 5,
        },
    },
    {
        "id": "rescue_breakthrough",
        "title": "救援突破",
        "description": "消防队成功救出被困人员，救援取得重大进展！",
        "category": "disaster",
        "trigger_phase": ["初步报道", "舆论应对"],
        "probability": 0.3,
        "severity": "low",
        "instant_effects": {"credibility": +5},
        "persistent_effects": {"credibility_per_turn": +2},
        "resolution": {
            "conditions": {},
            "hint": "好消息将持续提振公众信心",
            "max_turns": 2,
        },
    },
]


# ===== NPC 自主行为触发条件 =====
# NPC 根据局势自动做出决策，玩家无法直接控制
# 记者是观察者和影响者，不是决策者

NPC_TRIGGERS = [
    {
        "id": "npc_press_conference",
        "npc": "新闻发言人赵明",
        "action": "召开新闻发布会",
        "conditions": {
            "rumor_count_gte": 2,
            "credibility_lt": 60,
        },
        "alternative_conditions": {
            "phase": "舆论应对",
            "reports_published_gte": 3,
        },
        "effects": {
            "resolve_category": "rumor",
            "credibility": +10,
        },
        "message": "新闻发言人赵明决定召开新闻发布会，正面回应舆论关切。",
    },
    {
        "id": "npc_official_statement",
        "npc": "新闻发言人赵明",
        "action": "发布官方声明",
        "conditions": {
            "credibility_lt": 50,
            "rumor_count_gte": 1,
        },
        "effects": {
            "resolve_category": "rumor",
            "credibility": +5,
        },
        "message": "新闻发言人赵明发布官方声明，澄清事实，回应谣言。",
    },
    {
        "id": "npc_rescue_update",
        "npc": "消防队长老张",
        "action": "更新救援进展",
        "conditions": {
            "phase": "舆论应对",
            "info_completion_gte": 50,
        },
        "effects": {
            "credibility": +3,
            "resolve_category": "disaster",
        },
        "message": "消防队长老张主动向媒体通报最新救援进展，火势已基本得到控制。",
    },
]


class EventSystem:
    """事件系统：随机事件触发 + 持续效果管理 + NPC自主行为"""

    def __init__(self):
        self.events = EVENT_DEFINITIONS
        self.npc_triggers = NPC_TRIGGERS

    def check_and_trigger(self, state) -> Optional[Dict]:
        """检查并触发随机事件"""
        available = [
            e for e in self.events
            if state.phase in e["trigger_phase"]
            and e["id"] not in state.random_events_triggered
        ]
        if not available:
            return None

        for event in available:
            if random.random() < event["probability"]:
                state.random_events_triggered.append(event["id"])

                # 应用即时效果
                self._apply_instant_effects(state, event.get("instant_effects", {}))

                # 添加持续效果
                active_effect = {
                    "id": event["id"],
                    "title": event["title"],
                    "category": event.get("category", "other"),
                    "severity": event.get("severity", "medium"),
                    "persistent_effects": event.get("persistent_effects", {}),
                    "resolution": event.get("resolution", {}),
                    "turns_active": 0,
                    "triggered_at_phase": state.phase,
                    "max_turns": event.get("resolution", {}).get("max_turns"),
                }
                state.add_active_effect(active_effect)

                return {
                    "id": event["id"],
                    "title": event["title"],
                    "description": event["description"],
                    "category": event.get("category", "other"),
                    "severity": event.get("severity", "medium"),
                    "persistent_effects": event.get("persistent_effects", {}),
                    "resolution_hint": event.get("resolution", {}).get("hint", ""),
                }
        return None

    def check_npc_triggers(self, state) -> List[Dict]:
        """检查NPC自主行为触发条件，返回触发的行为列表"""
        triggered = []

        for trigger in self.npc_triggers:
            trigger_id = trigger["id"]
            # 避免同一NPC行为重复触发
            if any(a.get("trigger_id") == trigger_id for a in state.npc_actions_log):
                continue

            if self._check_conditions(trigger, state):
                self._apply_npc_effects(state, trigger.get("effects", {}))

                action_record = {
                    "trigger_id": trigger_id,
                    "npc": trigger["npc"],
                    "action": trigger["action"],
                    "message": trigger["message"],
                    "turn": state.total_time_elapsed,
                    "phase": state.phase,
                }
                state.npc_actions_log.append(action_record)
                triggered.append(action_record)

        return triggered

    def check_player_resolution(self, state, action_type: str) -> List[Dict]:
        """检查玩家行为是否能解除某些持续效果

        action_type:
          - "fact_check" → 发布核实报道
          - "interview_witness" → 采访目击者
          - "interview_fire_chief_after" → 采访消防队长(次生火灾后)
        """
        return state.resolve_effects_by_condition(action_type)

    # ===== 内部方法 =====

    def _check_conditions(self, trigger: Dict, state) -> bool:
        """检查NPC触发条件是否满足（主条件 或 替代条件）"""
        main = trigger.get("conditions", {})
        if main and self._evaluate_conditions(main, state):
            return True
        alt = trigger.get("alternative_conditions", {})
        if alt and self._evaluate_conditions(alt, state):
            return True
        return False

    def _evaluate_conditions(self, conditions: Dict, state) -> bool:
        """评估条件是否全部满足"""
        for key, value in conditions.items():
            if key == "rumor_count_gte" and len(state.rumors_active) < value:
                return False
            elif key == "credibility_lt" and state.credibility >= value:
                return False
            elif key == "credibility_gt" and state.credibility <= value:
                return False
            elif key == "phase" and state.phase != value:
                return False
            elif key == "reports_published_gte" and state.reports_published < value:
                return False
            elif key == "reports_fact_checks_gte" and state.reports_fact_checks < value:
                return False
            elif key == "info_completion_gte" and state.get_info_completion_rate() < value:
                return False
        return True

    def _apply_instant_effects(self, state, effects: Dict) -> None:
        """应用即时效果（一次性）"""
        if "credibility" in effects:
            state.credibility = max(0, min(100, state.credibility + effects["credibility"]))
        for key, value in effects.get("info_update", {}).items():
            if key in state.info_completeness:
                state.info_completeness[key] = value

    def _apply_npc_effects(self, state, effects: Dict) -> None:
        """应用NPC行为效果"""
        if "credibility" in effects:
            state.credibility = max(0, min(100, state.credibility + effects["credibility"]))

        resolve_cat = effects.get("resolve_category")
        if resolve_cat:
            state.resolve_effects_by_category(resolve_cat, condition=f"npc_{resolve_cat}_resolved")
            # 谣言类：同时通过 press_conference 条件解除
            if resolve_cat == "rumor":
                state.resolve_effects_by_condition("press_conference")
                state.press_conference_held = True
