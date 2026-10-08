from jetarm_demo_agent.config import Settings


def choose_execution_mode(intent: str, settings: Settings | None = None) -> str:
    active_settings = settings or Settings()
    if intent == "detect_color":
        return "safe"
    if intent in {
        "pick_and_place_color",
        "scan_scene",
        "find_red_block",
        "pick_red_block",
        "lift_red_block",
        "place_red_block_near_origin",
        "place_red_block_back_to_pick_xy",
        "open_desktop_manipulation",
    }:
        if active_settings.allow_live_motion:
            return "live"
        return "dry_run"
    return "safe"
