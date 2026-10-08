from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple

from servo_controller_msgs.msg import ServoPosition, ServosPosition

ServoGoal = Tuple[int, int]

ALLOWED_SERVO_IDS = {1, 2, 3, 4, 5, 10}
MIN_PULSE = 0
MAX_PULSE = 1000
MIN_DURATION = 0.05
MAX_DURATION = 5.0


@dataclass(frozen=True)
class MotionStep:
    duration: float
    goals: Tuple[ServoGoal, ...]
    note: str = ""


@dataclass(frozen=True)
class PresetAction:
    name: str
    description: str
    steps: Tuple[MotionStep, ...]


PRESET_ACTIONS: Dict[str, PresetAction] = {
    # Official bringup/actions.py safe home posture.
    "go_home": PresetAction(
        name="go_home",
        description="Open gripper, move arm joints to the official home posture, then center base.",
        steps=(
            MotionStep(0.5, ((10, 200),), "open gripper first"),
            MotionStep(1.0, ((2, 560), (3, 130), (4, 115), (5, 500), (10, 200)), "home arm joints"),
            MotionStep(1.0, ((1, 500),), "center base"),
        ),
    ),
    "goto_home": PresetAction(
        name="goto_home",
        description="Center base first, then move arm joints to the official home posture.",
        steps=(
            MotionStep(1.0, ((1, 500),), "center base"),
            MotionStep(1.0, ((2, 560), (3, 130), (4, 115), (5, 500), (10, 200)), "home arm joints"),
        ),
    ),
    # Official object_sorting/app observation posture.
    "observe_sorting": PresetAction(
        name="observe_sorting",
        description="Observation posture used by the official object sorting demo.",
        steps=(
            MotionStep(1.0, ((10, 200),), "open gripper"),
            MotionStep(1.2, ((1, 500), (2, 520), (3, 210), (4, 50), (5, 500), (10, 200)), "object sorting observe pose"),
        ),
    ),
    "place_center": PresetAction(
        name="place_center",
        description="Official center place posture from servo_controller.actions.place.",
        steps=(
            MotionStep(1.5, ((1, 500), (2, 610), (3, 70), (4, 140), (5, 500), (10, 200)), "center place pose"),
        ),
    ),
    "goto_left": PresetAction(
        name="goto_left",
        description="Official left placement posture.",
        steps=(
            MotionStep(1.5, ((1, 875), (2, 610), (3, 70), (4, 140), (5, 500), (10, 200)), "left place pose"),
        ),
    ),
    "goto_right": PresetAction(
        name="goto_right",
        description="Official right placement posture.",
        steps=(
            MotionStep(1.5, ((1, 125), (2, 610), (3, 70), (4, 140), (5, 500), (10, 200)), "right place pose"),
        ),
    ),
    "go_back": PresetAction(
        name="go_back",
        description="Official back posture with gripper closed.",
        steps=(
            MotionStep(1.0, ((1, 500), (2, 560), (3, 130), (4, 115), (5, 500), (10, 550)), "back pose"),
        ),
    ),
    "open_gripper": PresetAction(
        name="open_gripper",
        description="Open the gripper only.",
        steps=(
            MotionStep(0.5, ((10, 200),), "open gripper"),
        ),
    ),
    "close_gripper": PresetAction(
        name="close_gripper",
        description="Close the gripper only.",
        steps=(
            MotionStep(0.5, ((10, 550),), "close gripper"),
        ),
    ),
}


def normalize_action_name(name: str) -> str:
    normalized = name.strip().lower().replace("-", "_")
    aliases = {
        "home": "go_home",
        "default": "go_home",
        "observe": "observe_sorting",
        "sorting_observe": "observe_sorting",
        "place": "place_center",
        "left": "goto_left",
        "right": "goto_right",
        "back": "go_back",
        "open": "open_gripper",
        "close": "close_gripper",
    }
    return aliases.get(normalized, normalized)


def list_action_names() -> List[str]:
    return sorted(PRESET_ACTIONS)


def get_action(name: str) -> PresetAction:
    normalized = normalize_action_name(name)
    try:
        return PRESET_ACTIONS[normalized]
    except KeyError as exc:
        known = ", ".join(list_action_names())
        raise ValueError(f"Unknown JetArm preset '{name}'. Known presets: {known}") from exc


def validate_step(step: MotionStep) -> None:
    if not MIN_DURATION <= float(step.duration) <= MAX_DURATION:
        raise ValueError(f"Duration {step.duration} is outside [{MIN_DURATION}, {MAX_DURATION}] seconds")
    if not step.goals:
        raise ValueError("Motion step must contain at least one servo goal")
    seen = set()
    for servo_id, pulse in step.goals:
        if servo_id not in ALLOWED_SERVO_IDS:
            raise ValueError(f"Servo id {servo_id} is not allowed")
        if servo_id in seen:
            raise ValueError(f"Servo id {servo_id} appears more than once in one step")
        seen.add(servo_id)
        if not MIN_PULSE <= int(pulse) <= MAX_PULSE:
            raise ValueError(f"Servo {servo_id} pulse {pulse} is outside [{MIN_PULSE}, {MAX_PULSE}]")


def action_to_lines(action: PresetAction) -> List[str]:
    lines = []
    for index, step in enumerate(action.steps, start=1):
        goals = " ".join(f"{servo_id}:{pulse}" for servo_id, pulse in step.goals)
        suffix = f" # {step.note}" if step.note else ""
        lines.append(f"{index}. {step.duration:.2f}s {goals}{suffix}")
    return lines


def make_servos_position(step: MotionStep) -> ServosPosition:
    validate_step(step)
    msg = ServosPosition()
    msg.duration = float(step.duration)
    msg.position_unit = "pulse"
    positions = []
    for servo_id, pulse in step.goals:
        position = ServoPosition()
        position.id = int(servo_id)
        position.position = float(pulse)
        positions.append(position)
    msg.position = positions
    return msg


def iter_messages(action: PresetAction) -> Iterable[Tuple[MotionStep, ServosPosition]]:
    for step in action.steps:
        yield step, make_servos_position(step)
