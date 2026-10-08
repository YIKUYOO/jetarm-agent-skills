from dataclasses import dataclass, field
import re


@dataclass
class ParsedCommand:
    intent: str
    args: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)


class RuleParser:
    COLOR_SYNONYMS = {
        "red": ("红色木块", "红色方块", "红色块", "红块", "红色的"),
        "green": ("绿色木块", "绿色方块", "绿色块", "绿块", "绿色的"),
        "blue": ("蓝色木块", "蓝色方块", "蓝色块", "蓝块", "蓝色的"),
    }
    LEFT_SYNONYMS = ("左边", "左侧", "左面")
    RIGHT_SYNONYMS = ("右边", "右侧", "右面")
    FRONT_SYNONYMS = ("前面", "前方", "面前")
    BLOCK_REFERENCES = ("木块", "方块", "块")
    OBSERVE_HINTS = ("如果", "先", "确认", "看看", "有没有", "在不在", "观察", "颜色")
    MOVE_HINTS = ("放", "移", "拿")
    PICK_LIFT_HINTS = ("抓起", "拿起", "举起来", "举起", "抬起来")
    OPEN_WORLD_HINTS = ("看看前面有什么", "前面有什么", "识别", "东西", "整理")
    GO_HOME_HINTS = ("回到初始位置", "回原位", "复位", "回到初始状态", "先回去")
    OPEN_DESKTOP_MOVE_PATTERN = re.compile(r"把(?P<source>.+?)(?:放到|放在|移到|移动到|拿到)(?P<target>.+)")

    def _extract_color(self, command: str) -> str | None:
        for color, variants in self.COLOR_SYNONYMS.items():
            if any(variant in command for variant in variants):
                return color
        return None

    def _mentions_block(self, command: str) -> bool:
        return any(block in command for block in self.BLOCK_REFERENCES)

    def _mentions_left(self, command: str) -> bool:
        return any(target in command for target in self.LEFT_SYNONYMS)

    def _extract_hint_sector(self, command: str) -> str | None:
        if any(target in command for target in self.LEFT_SYNONYMS):
            return "left"
        if any(target in command for target in self.RIGHT_SYNONYMS):
            return "right"
        if any(target in command for target in self.FRONT_SYNONYMS):
            return "front"
        return None

    def _mentions_observe(self, command: str) -> bool:
        return any(hint in command for hint in self.OBSERVE_HINTS)

    def _mentions_move(self, command: str) -> bool:
        return any(hint in command for hint in self.MOVE_HINTS)

    def _mentions_pick_lift(self, command: str) -> bool:
        return any(hint in command for hint in self.PICK_LIFT_HINTS)

    def _clean_object_phrase(self, phrase: str) -> str:
        cleaned = phrase.strip()
        for prefix in ("前面的", "面前的", "那个", "这个", "一个", "这一个", "那一个"):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):]
        return cleaned.strip("，。,. ")

    def _parse_open_desktop_move(self, command: str) -> ParsedCommand | None:
        match = self.OPEN_DESKTOP_MOVE_PATTERN.search(command)
        if not match:
            return None
        source = self._clean_object_phrase(match.group("source"))
        target_phrase = self._clean_object_phrase(match.group("target"))
        relation = "near"
        relation_suffixes = {
            "左边": "left",
            "左侧": "left",
            "右边": "right",
            "右侧": "right",
            "里面": "inside",
            "里": "inside",
            "旁边": "near",
            "附近": "near",
            "上面": "near",
            "上": "near",
        }
        for suffix, normalized in relation_suffixes.items():
            if target_phrase.endswith(suffix):
                relation = normalized
                target_phrase = target_phrase[: -len(suffix)]
                break
        target = self._clean_object_phrase(target_phrase)
        if not source or not target:
            return None
        return ParsedCommand(
            intent="open_desktop_manipulation",
            args={
                "source_object": source,
                "target_object": target,
                "placement_relation": relation,
            },
            metadata={
                "requires_observation": True,
                "requires_human_confirmation": True,
                "clarify_if_ambiguous": True,
                "confidence": 0.82,
                "llm_summary": f"我会先定位{source}和{target}，通过安全检查后等待人工确认。",
                "steps": ["扫描桌面", f"定位{source}和{target}", "执行安全检查并等待人工确认"],
                "plan": {
                    "goal": f"把{source}放到{target}{'旁边' if relation == 'near' else ''}",
                    "constraints": ["开放桌面任务必须先定位目标并通过安全门", "真实运动前需要人工确认"],
                    "steps": [
                        {"action": "scan_scene", "description": "获取当前桌面图像"},
                        {"action": "locate_scene_objects", "description": f"定位{source}和{target}"},
                        {"action": "safety_check", "description": "检查置信度、世界坐标和人工确认"},
                    ],
                    "safety_notes": ["低置信度、缺少世界坐标或未确认时不执行真实运动"],
                },
            },
        )

    def parse(self, command: str) -> ParsedCommand:
        if any(hint in command for hint in self.GO_HOME_HINTS):
            return ParsedCommand(intent="go_home", metadata={"confidence": 0.95})

        color = self._extract_color(command)
        mentions_left = self._mentions_left(command)
        hint_sector = self._extract_hint_sector(command)
        mentions_move = self._mentions_move(command)
        mentions_observe = self._mentions_observe(command)
        mentions_block = self._mentions_block(command)
        mentions_pick_lift = self._mentions_pick_lift(command)

        if any(hint in command for hint in ("看看前面有什么", "前面有什么", "观察周围环境", "看看周围", "周围环境")) and not color:
            return ParsedCommand(
                intent="observe_environment",
                metadata={
                    "confidence": 0.9,
                    "llm_summary": "我会先获取当前画面，再总结桌面和周围环境。",
                    "steps": ["获取当前画面", "总结周围环境"],
                    "plan": {
                        "goal": "观察并总结当前桌面环境",
                        "steps": [
                            {"action": "scan_scene", "description": "获取当前桌面图像"},
                            {"action": "summarize_scene", "description": "总结可见物体和环境"},
                        ],
                        "constraints": ["观察任务不执行抓取运动"],
                        "safety_notes": ["只进行摄像头观察或安全扫描"],
                    },
                },
            )

        if color and mentions_block and mentions_pick_lift and "放下" in command:
            return ParsedCommand(
                intent="pick_lift_place_red_block",
                args={
                    "target_color": color,
                    "return_policy": "pick_xy",
                },
                metadata={
                    "confidence": 0.93,
                    "llm_summary": "我会先搜索前方红色木块，抓起后举起来展示，再放回抓取点附近。",
                    "steps": ["搜索红色木块", "抓起红色木块", "举起展示", "放回抓取点附近"],
                    "plan": {
                        "goal": "抓起并展示红色木块后放回抓取点",
                        "constraints": ["只在当前安全工作区内搜索和抓取", "放回抓取点XY附近"],
                        "steps": [
                            {"action": "find_red_block", "description": "在前方搜索红色木块"},
                            {"action": "pick_red_block", "description": "抓起红色木块"},
                            {"action": "lift_red_block", "description": "举起展示"},
                            {"action": "place_red_block_back_to_pick_xy", "description": "放回抓取点附近"},
                        ],
                        "safety_notes": ["当前演示只在前方工作区搜索红色木块"],
                    },
                },
            )

        if color and mentions_move and mentions_left:
            return ParsedCommand(
                intent="pick_and_place_color",
                args={"target_color": color, "destination": "left"},
                metadata={
                    "requires_observation": True,
                    "clarify_if_ambiguous": True,
                    "confidence": 0.9,
                },
            )

        if mentions_move and mentions_left and mentions_block and not color:
            return ParsedCommand(
                intent="clarify",
                metadata={
                    "clarify_slot": "target_color",
                    "clarify_if_ambiguous": True,
                    "confidence": 0.7,
                },
            )

        open_desktop = self._parse_open_desktop_move(command)
        if open_desktop:
            return open_desktop

        if mentions_observe and mentions_block and not color:
            return ParsedCommand(
                intent="clarify",
                metadata={
                    "clarify_slot": "target_color",
                    "clarify_if_ambiguous": True,
                    "confidence": 0.7,
                },
            )

        if color and mentions_observe:
            intent = "check_color" if "是不是" in command else "detect_color"
            return ParsedCommand(
                intent=intent,
                args={"target_color": color},
                metadata={
                    "requires_observation": False,
                    "clarify_if_ambiguous": False,
                    "confidence": 0.9,
                },
            )

        raise ValueError("unsupported command")
