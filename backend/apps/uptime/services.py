from enum import Enum
from django.conf import settings


class TransitionAction(Enum):
    NONE = "none"
    FIRE_FAILURE = "fire_failure"
    FIRE_RECOVERY = "fire_recovery"


def decide_transition(monitor, *, is_up: bool) -> TransitionAction:
    """决定给定当前监控状态和最新检查结果应触发的副作用。

    纯函数 — 不修改监控对象。调用方负责应用状态更新
    （last_status、consecutive_failures 等）并分发对应动作。
    """
    threshold = settings.UPTIME_FAILURE_THRESHOLD

    if is_up:
        if monitor.last_status == "down":
            return TransitionAction.FIRE_RECOVERY
        return TransitionAction.NONE

    # is_up = False
    if monitor.last_status == "down":
        return TransitionAction.NONE
    # last_status is up or unknown
    if monitor.consecutive_failures + 1 >= threshold:
        return TransitionAction.FIRE_FAILURE
    return TransitionAction.NONE
