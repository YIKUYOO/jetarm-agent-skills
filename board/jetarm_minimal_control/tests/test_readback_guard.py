import importlib.util
from pathlib import Path
from types import SimpleNamespace


def load_guard():
    path = Path(__file__).resolve().parents[1] / "integration/readback_guard.py"
    spec = importlib.util.spec_from_file_location("readback_guard", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_unsigned_readback_boundaries_are_preserved():
    guard = load_guard()
    logger = SimpleNamespace(warn=lambda *_: None)
    assert guard.as_uint16_sequence([0, 65535], "position", logger, 1) == [0, 65535]
    assert guard.as_uint16_sequence(None, "position", logger, 1) is None


def test_invalid_readback_is_not_assigned_to_ros_message():
    guard = load_guard()
    warnings = []
    logger = SimpleNamespace(warn=warnings.append)
    assert guard.as_uint16_sequence([-1], "position", logger, 1) is None
    assert guard.as_uint16_sequence([65536], "position", logger, 1) is None
    assert len(warnings) == 2
