import numpy as np


class ActionSafetyError(RuntimeError):
    """Raised when an action must not be sent to the arm."""


class ActionSafetyConfig:
    def __init__(self, min_value=0.0, max_value=1.0, max_step=0.15, timeout_s=1.0):
        self.min_value = min_value
        self.max_value = max_value
        self.max_step = max_step
        self.timeout_s = timeout_s


def clamp_and_validate_action(
    action,
    previous_action,
    action_timestamp,
    now,
    config=None,
    emergency_stop=False,
):
    """Clamp a normalized 6D action and reject unsafe execution states."""

    cfg = config or ActionSafetyConfig()
    if emergency_stop:
        raise ActionSafetyError("emergency stop is active")
    if now - action_timestamp > cfg.timeout_s:
        raise ActionSafetyError("stale action rejected")

    values = np.asarray(action, dtype=np.float32)
    if values.shape != (6,):
        raise ActionSafetyError("action must contain exactly 6 values")
    if not np.isfinite(values).all():
        raise ActionSafetyError("action contains non-finite values")

    values = np.clip(values, cfg.min_value, cfg.max_value)
    if previous_action is not None:
        previous = np.asarray(previous_action, dtype=np.float32)
        if previous.shape != (6,):
            raise ActionSafetyError("previous_action must contain exactly 6 values")
        lower = previous - cfg.max_step
        upper = previous + cfg.max_step
        values = np.clip(values, lower, upper)
    values = np.clip(values, cfg.min_value, cfg.max_value)
    return values.round(6).tolist()
