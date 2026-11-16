"""对 py-fsrs 的薄封装：复习一次、预览各评分的下次间隔、计算记忆保持率。

评分含义（与界面按钮对应）：
    1 = 忘记 (Again)   2 = 模糊 (Hard)   3 = 认识 (Good)   4 = 太简单 (Easy)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fsrs import Card, Rating, Scheduler, State

NEW, LEARNING, REVIEW, RELEARNING = 0, int(State.Learning), int(State.Review), int(State.Relearning)


def utc(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, timezone.utc)


def fmt_interval(seconds: float) -> str:
    """把间隔秒数写成“10 分钟 / 3 天 / 1.5 个月”。"""
    s = max(0.0, seconds)
    if s < 90:
        return "1 分钟"
    if s < 3600:
        return f"{round(s / 60)} 分钟"
    if s < 86400:
        return f"{round(s / 3600)} 小时"
    d = s / 86400
    if d < 30.5:
        return f"{round(d)} 天"
    if d < 365:
        return f"{d / 30.4:.1f}".rstrip("0").rstrip(".") + " 个月"
    return f"{d / 365:.1f}".rstrip("0").rstrip(".") + " 年"


class Srs:
    def __init__(self, retention: float = 0.9):
        self.set_retention(retention)

    def set_retention(self, retention: float) -> None:
        r = min(0.97, max(0.70, float(retention)))
        self.retention = r
        self._sched = Scheduler(desired_retention=r)
        self._plain = Scheduler(desired_retention=r, enable_fuzzing=False)  # 预览用，不加随机抖动
        w = self._sched.parameters
        self._decay = -w[20]
        self._factor = 0.9 ** (1 / self._decay) - 1

    @staticmethod
    def load(data: str | None) -> Card:
        return Card.from_json(data) if data else Card()

    def review(self, data: str | None, rating: int, now: float) -> Card:
        card, _ = self._sched.review_card(self.load(data), Rating(rating), utc(now))
        return card

    def preview(self, data: str | None, now: float) -> dict[str, str]:
        out = {}
        for r in (1, 2, 3, 4):
            card, _ = self._plain.review_card(self.load(data), Rating(r), utc(now))
            out[str(r)] = fmt_interval((card.due - utc(now)).total_seconds())
        return out

    def recall(self, stability: float | None, elapsed_days: float) -> float:
        """FSRS 遗忘曲线：稳定度为 S 的记忆在 t 天后还能想起来的概率。"""
        if not stability:
            return 0.0
        return (1 + self._factor * max(0.0, elapsed_days) / stability) ** self._decay

    def curve(self, stability: float, days: float, n: int = 48) -> list[list[float]]:
        return [[round(days * i / n, 3), round(self.recall(stability, days * i / n), 4)] for i in range(n + 1)]


__all__ = ["Srs", "Card", "State", "NEW", "LEARNING", "REVIEW", "RELEARNING", "fmt_interval", "utc", "timedelta"]
