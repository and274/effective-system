from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import uuid


PHASE_CONFIG = {
    "信息采集": {
        "limit": 28,
        "next": "初步报道",
        "available_roles": ["消防队长老张", "急救医生李薇", "现场群众王阿姨", "新闻发言人赵明"],
    },
    "初步报道": {
        "limit": 5,
        "next": "舆论应对",
        "available_roles": ["新闻发言人赵明"],
    },
    "舆论应对": {
        "limit": 7,
        "next": "最终发布",
        "available_roles": ["新闻发言人赵明", "网友模拟器"],
    },
    "最终发布": {
        "limit": 6,
        "next": None,
        "available_roles": ["新闻发言人赵明"],
    },
}


@dataclass
class GameState:
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: datetime = field(default_factory=datetime.now)

    phase: str = "信息采集"
    phase_time_limit: int = PHASE_CONFIG["信息采集"]["limit"]
    time_elapsed: int = 0
    total_time_elapsed: int = 0

    credibility: int = 100
    info_completeness: Dict[str, bool] = field(
        default_factory=lambda: {
            "火情起因": False,
            "伤亡人数": False,
            "救援进度": False,
            "官方回应": False,
            "目击证词": False,
            "现场照片": False,
        }
    )

    interviewed: List[str] = field(default_factory=list)
    interview_count: Dict[str, int] = field(default_factory=dict)

    reports_published: int = 0
    reports_fact_checks: int = 0  # 辟谣/核实性报道

    rumors_active: List[Dict] = field(default_factory=list)
    rumors_addressed: List[str] = field(default_factory=list)

    # ===== 事件持续影响系统 =====
    active_effects: List[Dict] = field(default_factory=list)
    resolved_effects: List[Dict] = field(default_factory=list)

    # ===== 舆情评论 =====
    netizen_comments: List[Dict] = field(default_factory=list)

    event_log: List[Dict] = field(default_factory=list)
    random_events_triggered: List[str] = field(default_factory=list)
    messages: List[Dict] = field(default_factory=list)

    game_over: bool = False
    game_result: Optional[str] = None
    failure_reason: Optional[str] = None

    press_conference_held: bool = False
    npc_actions_log: List[Dict] = field(default_factory=list)

    # ===== 基础查询 =====

    def get_info_completion_rate(self) -> float:
        total = len(self.info_completeness)
        completed = sum(1 for v in self.info_completeness.values() if v)
        return round((completed / total) * 100, 1) if total else 0.0

    def is_info_complete(self) -> bool:
        return self.get_info_completion_rate() >= 80

    def check_victory(self) -> Tuple[bool, Optional[str]]:
        if (
            self.credibility >= 60
            and self.is_info_complete()
            and self.press_conference_held
            and len(self.rumors_active) <= 2
        ):
            return True, "胜利"
        return False, None

    def check_failure(self) -> Tuple[bool, Optional[str]]:
        if self.credibility < 30:
            return True, "公信力崩盘"
        return False, None

    def advance_phase(self) -> Optional[str]:
        next_phase = PHASE_CONFIG[self.phase]["next"]
        if next_phase is None:
            return None
        self.phase = next_phase
        self.phase_time_limit = PHASE_CONFIG[next_phase]["limit"]
        self.time_elapsed = 0
        return next_phase

    # ===== 持续效果管理 =====

    def add_active_effect(self, effect: Dict) -> None:
        """添加一个持续影响效果，同时同步 rumors_active"""
        self.active_effects.append(effect)
        if effect.get("category") == "rumor":
            self.rumors_active.append({
                "id": effect["id"],
                "title": effect["title"],
                "severity": effect.get("severity", "medium"),
            })

    def apply_persistent_effects(self) -> List[Dict]:
        """每回合应用所有持续效果，返回本回合的应用记录"""
        applied = []
        to_remove = []

        for effect in self.active_effects:
            effect["turns_active"] = effect.get("turns_active", 0) + 1

            persistent = effect.get("persistent_effects", {})
            cred_per_turn = persistent.get("credibility_per_turn", 0)
            if cred_per_turn != 0:
                old_cred = self.credibility
                self.credibility = max(0, min(100, self.credibility + cred_per_turn))
                actual = self.credibility - old_cred
                if actual != 0:
                    applied.append({
                        "effect_id": effect["id"],
                        "title": effect["title"],
                        "type": "credibility_drain",
                        "delta": actual,
                        "detail": f"[{effect['title']}] 公信力{actual:+d}",
                    })

            max_turns = effect.get("max_turns")
            if max_turns is not None and effect["turns_active"] >= max_turns:
                to_remove.append(effect["id"])
                applied.append({
                    "effect_id": effect["id"],
                    "title": effect["title"],
                    "type": "auto_resolve",
                    "detail": f"[{effect['title']}] 持续时间结束，自动解除",
                })

        for eid in to_remove:
            self._resolve_effect_by_id(eid, reason="max_turns_reached")

        return applied

    def resolve_effects_by_condition(self, condition: str) -> List[Dict]:
        """根据条件解除效果，如 press_conference / fact_check / npc_rumor_resolved"""
        resolved = []
        to_remove = []

        for effect in self.active_effects:
            resolution = effect.get("resolution", {})
            conditions = resolution.get("conditions", {})
            if condition in conditions:
                to_remove.append(effect["id"])
                resolved.append({
                    "effect_id": effect["id"],
                    "title": effect["title"],
                    "category": effect.get("category", ""),
                    "resolved_by": condition,
                    "detail": f"[{effect['title']}] 被[{condition}]解除",
                })

        for eid in to_remove:
            self._resolve_effect_by_id(eid, reason=condition)

        return resolved

    def resolve_effects_by_category(self, category: str, condition: str) -> List[Dict]:
        """解除指定类别的所有效果"""
        resolved = []
        to_remove = []
        for effect in self.active_effects:
            if effect.get("category") == category:
                to_remove.append(effect["id"])
                resolved.append({
                    "effect_id": effect["id"],
                    "title": effect["title"],
                    "category": category,
                    "resolved_by": condition,
                    "detail": f"[{effect['title']}] 被[{condition}]解除",
                })
        for eid in to_remove:
            self._resolve_effect_by_id(eid, reason=condition)
        return resolved

    def _resolve_effect_by_id(self, effect_id: str, reason: str = "") -> None:
        """移除指定效果并记录到 resolved_effects"""
        for i, effect in enumerate(self.active_effects):
            if effect["id"] == effect_id:
                effect_copy = dict(effect)
                effect_copy["resolved_at_turn"] = self.total_time_elapsed
                effect_copy["resolved_at_phase"] = self.phase
                effect_copy["resolve_reason"] = reason
                self.resolved_effects.append(effect_copy)
                self.active_effects.pop(i)
                # 同步 rumors_active
                if effect.get("category") == "rumor":
                    self.rumors_active = [
                        r for r in self.rumors_active if r.get("id") != effect_id
                    ]
                    self.rumors_addressed.append(effect["title"])
                break

    def get_active_effects_summary(self) -> Dict:
        """获取当前持续效果摘要"""
        by_category: Dict[str, list] = {}
        for effect in self.active_effects:
            cat = effect.get("category", "other")
            by_category.setdefault(cat, []).append({
                "id": effect["id"],
                "title": effect["title"],
                "severity": effect.get("severity", "medium"),
                "turns_active": effect.get("turns_active", 0),
                "persistent_effects": effect.get("persistent_effects", {}),
                "resolution_hint": effect.get("resolution", {}).get("hint", ""),
            })
        return {
            "total": len(self.active_effects),
            "by_category": by_category,
            "credibility_drain_per_turn": sum(
                e.get("persistent_effects", {}).get("credibility_per_turn", 0)
                for e in self.active_effects
            ),
        }

    # ===== 舆情评论 =====

    def add_netizen_comments(self, comments: List[Dict]) -> None:
        """添加舆情评论，保留最近 30 条"""
        self.netizen_comments.extend(comments)
        self.netizen_comments = self.netizen_comments[-30:]

    # ===== 时间推进 =====

    def add_time(self, minutes: int = 2) -> Dict:
        self.time_elapsed += minutes
        self.total_time_elapsed += minutes

        result: Dict = {
            "phase_advanced": False,
            "new_phase": None,
            "persistent_effects": [],
            "npc_events": [],
        }

        # 应用持续效果
        result["persistent_effects"] = self.apply_persistent_effects()

        # 检查阶段推进
        if self.time_elapsed >= self.phase_time_limit:
            result["phase_advanced"] = True
            result["new_phase"] = self.advance_phase()

            # 阶段变化时解除 phase-bound 效果
            self.resolve_effects_by_condition("phase_change")

            if result["new_phase"] is None:
                won, _ = self.check_victory()
                lost, reason = self.check_failure()
                self.game_over = True
                self.game_result = "胜利" if won else "失败"
                if not won:
                    self.failure_reason = reason or "未在规定时间内完成任务"

        # 检查胜负
        lost, reason = self.check_failure()
        if lost and not self.game_over:
            self.game_over = True
            self.game_result = "失败"
            self.failure_reason = reason

        return result

    # ===== 序列化 =====

    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "phase": self.phase,
            "phase_time_limit": self.phase_time_limit,
            "time_elapsed": self.time_elapsed,
            "total_time_elapsed": self.total_time_elapsed,
            "credibility": self.credibility,
            "info_completeness": self.info_completeness,
            "info_completion_rate": self.get_info_completion_rate(),
            "interviewed": self.interviewed,
            "reports_published": self.reports_published,
            "reports_fact_checks": self.reports_fact_checks,
            "rumors_active": [r.get("title", "") for r in self.rumors_active],
            "active_effects": self.active_effects,
            "active_effects_summary": self.get_active_effects_summary(),
            "resolved_effects_count": len(self.resolved_effects),
            "netizen_comments": self.netizen_comments[-10:],
            "game_over": self.game_over,
            "game_result": self.game_result,
            "failure_reason": self.failure_reason,
            "npc_actions_log": self.npc_actions_log[-5:],
        }
