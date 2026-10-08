from __future__ import annotations

from jetarm_demo_agent.config import Settings
from jetarm_demo_agent.understanding.deepseek_client import DeepSeekClient
from jetarm_demo_agent.understanding.openai_vision_client import OpenAIVisionClient
from jetarm_demo_agent.understanding.llm_parser import parse_llm_json
from jetarm_demo_agent.understanding.normalizer import normalize_candidate
from jetarm_demo_agent.understanding.rule_parser import ParsedCommand
from jetarm_demo_agent.understanding.rule_parser import RuleParser
from jetarm_demo_agent.orchestration.safety import choose_execution_mode
from jetarm_demo_agent.schemas import ExecutionMode


class Dispatcher:
    def __init__(self, transport, deepseek_client: DeepSeekClient | None = None, vision_client: OpenAIVisionClient | None = None, settings: Settings | None = None):
        self.transport = transport
        self.rule_parser = RuleParser()
        self.settings = settings or Settings()
        self.deepseek_client = deepseek_client or DeepSeekClient(self.settings)
        self.vision_client = vision_client or OpenAIVisionClient(self.settings)

    def _merge_candidates(
        self,
        raw_command: str,
        rule_candidate: ParsedCommand | None,
        llm_payload: dict | None,
    ) -> dict:
        llm_candidate = parse_llm_json(llm_payload) if llm_payload else None
        if rule_candidate and llm_candidate:
            if rule_candidate.intent == "abort" and llm_candidate.intent != "abort":
                candidate = llm_candidate
                parsed_by = "llm"
                llm_used_for_display = True
            else:
                candidate = rule_candidate
                candidate.metadata["steps"] = llm_candidate.metadata.get("steps", [])
                candidate.metadata["llm_summary"] = llm_candidate.metadata.get("llm_summary")
                if llm_candidate.metadata.get("plan"):
                    candidate.metadata["plan"] = llm_candidate.metadata["plan"]
                for key in ("requires_observation", "clarify_if_ambiguous", "confidence"):
                    if key not in candidate.metadata and key in llm_candidate.metadata:
                        candidate.metadata[key] = llm_candidate.metadata[key]
                parsed_by = "rule+llm"
                llm_used_for_display = True
        elif llm_candidate:
            candidate = llm_candidate
            parsed_by = "llm"
            llm_used_for_display = True
        elif rule_candidate:
            candidate = rule_candidate
            parsed_by = "rule"
            llm_used_for_display = False
        else:
            raise ValueError("unsupported command")

        task = normalize_candidate(
            raw_command=raw_command,
            candidate=candidate,
            parsed_by=parsed_by,
            llm_used_for_display=llm_used_for_display,
        )
        interaction_type = candidate.metadata.get("interaction_type")
        if not interaction_type:
            interaction_type = "chat" if task.intent.value == "chat" else ("clarify" if task.intent.value == "clarify" else ("abort" if task.intent.value == "abort" else "task"))
        return {
            "raw_command": raw_command,
            "llm_understanding": {
                "interaction_type": interaction_type,
                "intent": candidate.intent,
                "args": candidate.args,
                "steps": candidate.metadata.get("steps", []),
                "llm_summary": candidate.metadata.get("llm_summary"),
                "chat_reply": candidate.metadata.get("chat_reply"),
                "capability_summary": candidate.metadata.get("capability_summary"),
                "plan": candidate.metadata.get("plan"),
                "control": task.control,
            },
            "approved_task": task,
        }

    def stream_understand(self, raw_command: str):
        try:
            rule_candidate = self.rule_parser.parse(raw_command)
        except ValueError:
            rule_candidate = None

        if rule_candidate and rule_candidate.intent != "abort":
            yield {
                "type": "understanding_ready",
                "data": self._merge_candidates(raw_command, rule_candidate, None),
            }
            return

        llm_payload = None
        for chunk in self.deepseek_client.stream_enrich_command(raw_command):
            if chunk["type"] == "display_delta":
                yield {"type": "llm_stream_delta", "text": chunk["text"], "display_only": True}
            elif chunk["type"] == "result":
                llm_payload = chunk["payload"]

        yield {
            "type": "understanding_ready",
            "data": self._merge_candidates(raw_command, rule_candidate, llm_payload),
        }

    def understand(self, raw_command: str) -> dict:
        try:
            rule_candidate = self.rule_parser.parse(raw_command)
        except ValueError:
            rule_candidate = None
        if rule_candidate and rule_candidate.intent != "abort":
            return self._merge_candidates(raw_command, rule_candidate, None)
        llm_payload = self.deepseek_client.enrich_command(raw_command)
        return self._merge_candidates(raw_command, rule_candidate, llm_payload)

    def execute_task(self, task) -> dict:
        task.mode = ExecutionMode(choose_execution_mode(task.intent.value, self.settings))
        health = self.transport.health()
        execution_result = self.transport.run_task(task)
        return {
            "health": health,
            "execution_result": execution_result,
        }

    def summarize_scene(self, scan_result: dict, task) -> dict:
        frames = scan_result.get("result", {}).get("frames") or scan_result.get("frames") or []
        prompt = task.display.get("llm_summary") or task.source.get("raw_command") or "总结当前环境"
        return self.vision_client.summarize_scene(frames, prompt)

    def locate_scene_objects(self, scan_result: dict, task) -> dict:
        frames = scan_result.get("result", {}).get("frames") or scan_result.get("frames") or []
        prompt = task.source.get("raw_command") or task.display.get("llm_summary") or "定位当前桌面物体"
        return self.vision_client.locate_scene_objects(frames, prompt)

    def handle(self, raw_command: str) -> dict:
        understood = self.understand(raw_command)
        task = understood["approved_task"]
        execution = self.execute_task(task)
        return {
            "raw_command": understood["raw_command"],
            "llm_understanding": understood["llm_understanding"],
            "approved_task": {
                "task_id": task.task_id,
                "intent": task.intent.value,
                "args": task.args,
                "mode": task.mode.value,
                "source": task.source,
                "control": task.control,
            },
            "health": execution["health"],
            "execution_result": execution["execution_result"],
        }
