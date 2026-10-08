from jetarm_demo_agent.config import Settings
from jetarm_demo_agent.orchestration.safety import choose_execution_mode


def test_detect_color_defaults_to_safe():
    assert choose_execution_mode("detect_color") == "safe"


def test_pick_and_place_defaults_to_dry_run():
    assert choose_execution_mode("pick_and_place_color") == "dry_run"


def test_pick_and_place_can_switch_to_live_when_enabled():
    settings = Settings(account_file="/tmp/does-not-exist-account.txt", allow_live_motion=True)
    assert choose_execution_mode("pick_and_place_color", settings) == "live"
