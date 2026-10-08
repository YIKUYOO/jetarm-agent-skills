#!/usr/bin/env python3
from __future__ import print_function

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
try:
    from urllib import request as urlrequest
    from urllib import error as urlerror
except ImportError:  # pragma: no cover - Python 2 fallback is not a target, but keeps syntax harmless.
    urlrequest = None
    urlerror = None


VERSION = "0.1.0"

DEFAULT_TRANSCRIPT = os.path.expanduser("~/.jetarm_agent/logs/full-control-transcript.jsonl")
DEFAULT_SKILL_ROOT = os.path.expanduser("~/.jetarm_agent/skills")
DEFAULT_LLM_MODEL = os.environ.get("JETARM_LLM_MODEL", "gpt-5.5")
DEFAULT_LLM_BASE_URL = os.environ.get("JETARM_LLM_BASE_URL", "")
ROS_SETUP = (
    "export ROS_HOSTNAME=${ROS_HOSTNAME:-localhost} && "
    "export ROS_MASTER_URI=${ROS_MASTER_URI:-http://localhost:11311} && "
    ". /opt/ros/melodic/setup.bash >/dev/null 2>&1 && "
    ". ~/jetarm/devel/setup.bash >/dev/null 2>&1"
)


TOOL_SPECS = [
    ("help", "agent", "Show available REPL commands and tools.", "low"),
    ("list_tools", "agent", "List full-control JetArm tools.", "low"),
    ("list_skills", "agent", "List installed skills under the skill root.", "low"),
    ("create_skill", "agent", "Create a local quarantined skill.", "medium"),
    ("activate_skill", "agent", "Activate a reviewed skill.", "medium"),
    ("shell", "raw", "Run unrestricted shell command on Jetson.", "critical"),
    ("python_script", "raw", "Run arbitrary Python through python3.", "critical"),
    ("ros", "raw", "Run arbitrary command after sourcing ROS and JetArm workspaces.", "critical"),
    ("rostopic", "raw", "Run rostopic with arbitrary arguments.", "critical"),
    ("rosservice", "raw", "Run rosservice with arbitrary arguments.", "critical"),
    ("rosrun", "raw", "Run rosrun package executable args.", "critical"),
    ("roslaunch", "raw", "Run roslaunch package launch_file args.", "critical"),
    ("go_home", "robot", "Move arm to a known JetArm home pose.", "critical"),
    ("open_gripper", "robot", "Open gripper through servo 10.", "critical"),
    ("close_gripper", "robot", "Close gripper through servo 10.", "critical"),
    ("servo_debug", "robot", "Move any servo id to a raw pulse position.", "critical"),
    ("stop_all", "robot", "Best-effort stop/cleanup of JetArm workflows.", "critical"),
    ("camera_frame", "robot", "Capture one RGB frame to a local file.", "high"),
    ("agent_chat", "agent", "Ask the configured LLM to reply or choose one full-control tool.", "critical"),
]


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def ensure_parent(path):
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory)


def run_command(command, timeout):
    started = time.time()
    actual_command = command
    if os.name != "nt":
        actual_command = "bash -lc " + shlex.quote(command)
    try:
        proc = subprocess.Popen(actual_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate(timeout=timeout)
        exit_code = proc.returncode
        timed_out = False
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        exit_code = 124
        timed_out = True
    return {
        "exit_code": exit_code,
        "stdout": stdout.decode("utf-8", "replace"),
        "stderr": stderr.decode("utf-8", "replace"),
        "timed_out": timed_out,
        "duration_ms": int((time.time() - started) * 1000),
        "command": command,
        "actual_command": actual_command,
    }


def result(ok, stage, motion_executed=False, stdout="", stderr="", telemetry=None, artifacts=None, error_code=None, hint=None):
    return {
        "ok": bool(ok),
        "stage": stage,
        "motion_executed": bool(motion_executed),
        "stdout": stdout or "",
        "stderr": stderr or "",
        "telemetry": telemetry or {},
        "artifacts": artifacts or {},
        "error_code": error_code,
        "next_recovery_hint": hint,
    }


def command_result(stage, data, motion_executed=False):
    ok = data["exit_code"] == 0 and not data["timed_out"]
    return result(
        ok,
        stage,
        motion_executed=motion_executed,
        stdout=data["stdout"],
        stderr=data["stderr"],
        telemetry={
            "command": data["command"],
            "actual_command": data.get("actual_command", data["command"]),
            "exit_code": data["exit_code"],
            "timed_out": data["timed_out"],
            "duration_ms": data["duration_ms"],
        },
        error_code=None if ok else "COMMAND_FAILED",
        hint=None if ok else "Inspect stdout/stderr. If motion may be active, run stop_all.",
    )


def ros_command(body):
    return ROS_SETUP + " && " + body


def redact_secrets(value):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if "api_key" in lowered or "authorization" in lowered or lowered in ("key", "token"):
                redacted[key] = "<redacted>"
            else:
                redacted[key] = redact_secrets(item)
        return redacted
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value


class OpenAICompatibleClient(object):
    def __init__(self, model=DEFAULT_LLM_MODEL, base_url=DEFAULT_LLM_BASE_URL, api_key=None, timeout_seconds=60):
        self.model = model
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or os.environ.get("JETARM_LLM_API_KEY", "")
        self.timeout_seconds = timeout_seconds

    def configured(self):
        return bool(self.model and self.base_url and self.api_key)

    def chat(self, messages, temperature=0.2):
        if not self.configured():
            raise RuntimeError("LLM is not configured. Set JETARM_LLM_MODEL, JETARM_LLM_BASE_URL, and JETARM_LLM_API_KEY.")
        payload = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
            }
        ).encode("utf-8")
        req = urlrequest.Request(
            self.base_url + "/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.api_key,
            },
        )
        try:
            response = urlrequest.urlopen(req, timeout=self.timeout_seconds)
            body = response.read().decode("utf-8", "replace")
        except urlerror.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise RuntimeError("LLM HTTP %s: %s" % (exc.code, body[:1000]))
        data = json.loads(body)
        return data["choices"][0]["message"]["content"]


class FullControlAgent(object):
    def __init__(self, transcript_path=DEFAULT_TRANSCRIPT, skill_root=DEFAULT_SKILL_ROOT, llm_client=None):
        self.transcript_path = transcript_path
        self.skill_root = skill_root
        self.llm_client = llm_client or OpenAICompatibleClient()

    def record(self, tool_name, args, output):
        ensure_parent(self.transcript_path)
        entry = {
            "created_at": now_iso(),
            "mode": "full-control",
            "tool_name": tool_name,
            "args": args,
            "result": output,
        }
        with open(self.transcript_path, "a") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")

    def call(self, tool_name, args):
        handlers = {
            "help": self.tool_help,
            "list_tools": self.tool_list_tools,
            "list_skills": self.tool_list_skills,
            "create_skill": self.tool_create_skill,
            "activate_skill": self.tool_activate_skill,
            "shell": self.tool_shell,
            "python_script": self.tool_python_script,
            "ros": self.tool_ros,
            "rostopic": self.tool_rostopic,
            "rosservice": self.tool_rosservice,
            "rosrun": self.tool_rosrun,
            "roslaunch": self.tool_roslaunch,
            "go_home": self.tool_go_home,
            "open_gripper": self.tool_open_gripper,
            "close_gripper": self.tool_close_gripper,
            "servo_debug": self.tool_servo_debug,
            "stop_all": self.tool_stop_all,
            "camera_frame": self.tool_camera_frame,
            "agent_chat": self.tool_agent_chat,
        }
        if tool_name not in handlers:
            output = result(False, "dispatch", error_code="UNKNOWN_TOOL", hint="Run list_tools.")
        else:
            try:
                output = handlers[tool_name](args or {})
            except Exception as exc:
                output = result(False, "runtime", stderr=str(exc), error_code="TOOL_EXCEPTION", hint="Inspect transcript and run stop_all if needed.")
        self.record(tool_name, redact_secrets(args or {}), output)
        return output

    def tool_help(self, args):
        return result(
            True,
            "help",
            stdout=(
                "Commands:\n"
                "  /tool NAME JSON      call any full-control tool\n"
                "  /ask TEXT            ask the configured LLM to reply or choose a tool\n"
                "  /shell COMMAND       run unrestricted shell\n"
                "  /ros COMMAND         run command after ROS setup\n"
                "  /go_home             move arm home\n"
                "  /open_gripper        open gripper\n"
                "  /close_gripper       close gripper\n"
                "  /stop_all            best-effort stop/cleanup\n"
                "  /skills              list skills\n"
                "  /exit                quit\n"
            ),
        )

    def tool_list_tools(self, args):
        tools = [
            {"name": name, "group": group, "description": description, "risk_level": risk}
            for name, group, description, risk in TOOL_SPECS
        ]
        return result(True, "list_tools", telemetry={"tools": tools})

    def tool_agent_chat(self, args):
        user_message = args.get("message", "").strip()
        if not user_message:
            return result(False, "schema", stderr="message is required", error_code="INVALID_TOOL_ARGUMENTS")
        max_tool_calls = int(args.get("max_tool_calls", 1))
        transcript_tail = []
        for entry in self._read_transcript_tail(limit=5):
            transcript_tail.append(
                {
                    "tool_name": entry.get("tool_name"),
                    "ok": entry.get("result", {}).get("ok"),
                    "stage": entry.get("result", {}).get("stage"),
                    "error_code": entry.get("result", {}).get("error_code"),
                    "stdout_excerpt": (entry.get("result", {}).get("stdout") or "")[:300],
                    "stderr_excerpt": (entry.get("result", {}).get("stderr") or "")[:300],
                }
            )
        tools = [
            {"name": name, "group": group, "description": description, "risk_level": risk}
            for name, group, description, risk in TOOL_SPECS
        ]
        system = (
            "You are the JetArm full-control embodied coding and robotics agent running on the Jetson Nano. "
            "You may use unrestricted shell, ROS, Python, and raw servo tools. "
            "For this CLI bridge, respond with strict JSON only. "
            "Either return {\"reply\":\"text\"} or {\"tool_name\":\"name\",\"args\":{...},\"reason\":\"text\"}. "
            "Prefer observing and debugging before risky motion. Never include API keys or secrets in tool args."
        )
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "user_message": user_message,
                        "available_tools": tools,
                        "recent_transcript": transcript_tail,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        content = self.llm_client.chat(messages)
        parsed = self._parse_llm_json(content)
        if "reply" in parsed:
            return result(True, "agent_chat", stdout=parsed.get("reply", ""), telemetry={"model": self.llm_client.model})
        tool_name = parsed.get("tool_name")
        tool_args = parsed.get("args") or {}
        if not tool_name:
            return result(False, "agent_chat", stdout=content, error_code="MODEL_DID_NOT_RETURN_ACTION")
        if max_tool_calls <= 0:
            return result(True, "agent_chat", stdout=json.dumps(parsed, ensure_ascii=False), telemetry={"tool_call_suppressed": True})
        tool_output = self.call(tool_name, tool_args)
        return result(
            tool_output["ok"],
            "agent_chat",
            motion_executed=tool_output.get("motion_executed", False),
            stdout=json.dumps({"reason": parsed.get("reason", ""), "tool_name": tool_name, "tool_result": tool_output}, ensure_ascii=False),
            telemetry={"model": self.llm_client.model, "delegated_tool": tool_name},
            error_code=tool_output.get("error_code"),
            hint=tool_output.get("next_recovery_hint"),
        )

    def _parse_llm_json(self, content):
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        try:
            return json.loads(text)
        except ValueError:
            extracted = self._extract_first_json_object(text)
            if extracted is not None:
                return extracted
            return {"reply": content}

    def _extract_first_json_object(self, text):
        start = text.find("{")
        if start < 0:
            return None
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : index + 1])
                    except ValueError:
                        return None
        return None

    def _read_transcript_tail(self, limit=5):
        if not os.path.exists(self.transcript_path):
            return []
        with open(self.transcript_path) as handle:
            lines = handle.readlines()[-limit:]
        entries = []
        for line in lines:
            try:
                entries.append(json.loads(line))
            except ValueError:
                pass
        return entries

    def tool_list_skills(self, args):
        root = args.get("root", self.skill_root)
        skills = []
        for state in ("quarantine", "active", "disabled"):
            directory = os.path.join(root, state)
            if not os.path.isdir(directory):
                continue
            for name in sorted(os.listdir(directory)):
                manifest_path = os.path.join(directory, name, "manifest.json")
                if os.path.exists(manifest_path):
                    with open(manifest_path) as handle:
                        manifest = json.load(handle)
                    skills.append(manifest)
        return result(True, "list_skills", telemetry={"skills": skills, "root": root})

    def tool_create_skill(self, args):
        name = args.get("name", "").strip()
        description = args.get("description", "JetArm full-control skill").strip()
        if not name:
            return result(False, "schema", stderr="name is required", error_code="INVALID_TOOL_ARGUMENTS")
        root = args.get("root", self.skill_root)
        target = os.path.join(root, "quarantine", name)
        if not os.path.exists(target):
            os.makedirs(target)
        manifest = {
            "name": name,
            "description": description,
            "version": args.get("version", "0.1.0"),
            "source": args.get("source", "local"),
            "allowed_tools": args.get("allowed_tools", ["shell", "ros", "rostopic", "rosservice", "stop_all"]),
            "risk_level": args.get("risk_level", "critical"),
            "install_state": "quarantined",
            "review_notes": args.get("review_notes", ""),
        }
        with open(os.path.join(target, "manifest.json"), "w") as handle:
            handle.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        with open(os.path.join(target, "SKILL.md"), "w") as handle:
            handle.write("# %s\n\n%s\n" % (name, description))
        return result(True, "create_skill", telemetry={"path": target, "manifest": manifest})

    def tool_activate_skill(self, args):
        name = args.get("name", "").strip()
        review_notes = args.get("review_notes", "").strip()
        if not name or not review_notes:
            return result(False, "schema", stderr="name and review_notes are required", error_code="INVALID_TOOL_ARGUMENTS")
        root = args.get("root", self.skill_root)
        source = os.path.join(root, "quarantine", name)
        target = os.path.join(root, "active", name)
        if not os.path.isdir(source):
            return result(False, "activate_skill", stderr="quarantined skill not found", error_code="SKILL_NOT_FOUND")
        if not os.path.isdir(os.path.dirname(target)):
            os.makedirs(os.path.dirname(target))
        if os.path.exists(target):
            return result(False, "activate_skill", stderr="active skill already exists", error_code="SKILL_ALREADY_ACTIVE")
        os.rename(source, target)
        manifest_path = os.path.join(target, "manifest.json")
        with open(manifest_path) as handle:
            manifest = json.load(handle)
        manifest["install_state"] = "active"
        manifest["review_notes"] = review_notes
        with open(manifest_path, "w") as handle:
            handle.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        return result(True, "activate_skill", telemetry={"path": target, "manifest": manifest})

    def tool_shell(self, args):
        command = args.get("command", "").strip()
        if not command:
            return result(False, "schema", stderr="command is required", error_code="INVALID_TOOL_ARGUMENTS")
        return command_result("shell", run_command(command, int(args.get("timeout_seconds", 20))))

    def tool_python_script(self, args):
        script = args.get("script", "").strip()
        if not script:
            return result(False, "schema", stderr="script is required", error_code="INVALID_TOOL_ARGUMENTS")
        command = "python3 -c " + shlex.quote(script)
        if args.get("with_ros", False):
            command = ros_command(command)
        return command_result("python_script", run_command(command, int(args.get("timeout_seconds", 20))))

    def tool_ros(self, args):
        command = args.get("command", "").strip()
        if not command:
            return result(False, "schema", stderr="command is required", error_code="INVALID_TOOL_ARGUMENTS")
        return command_result("ros", run_command(ros_command(command), int(args.get("timeout_seconds", 20))))

    def tool_rostopic(self, args):
        raw_args = args.get("args", "").strip()
        if not raw_args:
            return result(False, "schema", stderr="args is required", error_code="INVALID_TOOL_ARGUMENTS")
        return command_result("rostopic", run_command(ros_command("rostopic " + raw_args), int(args.get("timeout_seconds", 20))))

    def tool_rosservice(self, args):
        raw_args = args.get("args", "").strip()
        if not raw_args:
            return result(False, "schema", stderr="args is required", error_code="INVALID_TOOL_ARGUMENTS")
        return command_result("rosservice", run_command(ros_command("rosservice " + raw_args), int(args.get("timeout_seconds", 20))))

    def tool_rosrun(self, args):
        package = args.get("package", "").strip()
        executable = args.get("executable", "").strip()
        extra = args.get("args", "").strip()
        if not package or not executable:
            return result(False, "schema", stderr="package and executable are required", error_code="INVALID_TOOL_ARGUMENTS")
        command = "rosrun %s %s %s" % (shlex.quote(package), shlex.quote(executable), extra)
        return command_result("rosrun", run_command(ros_command(command), int(args.get("timeout_seconds", 20))))

    def tool_roslaunch(self, args):
        package = args.get("package", "").strip()
        launch_file = args.get("launch_file", "").strip()
        extra = args.get("args", "").strip()
        if not package or not launch_file:
            return result(False, "schema", stderr="package and launch_file are required", error_code="INVALID_TOOL_ARGUMENTS")
        command = "roslaunch %s %s %s" % (shlex.quote(package), shlex.quote(launch_file), extra)
        return command_result("roslaunch", run_command(ros_command(command), int(args.get("timeout_seconds", 20))))

    def tool_go_home(self, args):
        script = """
import rospy
from hiwonder_interfaces.msg import MultiRawIdPosDur
from jetarm_sdk import bus_servo_control
rospy.init_node('jetarm_full_control_go_home', anonymous=True, disable_signals=True, log_level=rospy.ERROR)
pub = rospy.Publisher('/controllers/multi_id_pos_dur', MultiRawIdPosDur, queue_size=1)
rospy.sleep(0.5)
bus_servo_control.set_servos(pub, 800, ((1, 500), (2, 560), (3, 130), (4, 115), (5, 500), (10, 200)))
rospy.sleep(1.0)
print('ok')
""".strip()
        return command_result("go_home", run_command(ros_command("python3 -c " + shlex.quote(script)), int(args.get("timeout_seconds", 20))), True)

    def tool_open_gripper(self, args):
        args = dict(args)
        args.setdefault("position", 200)
        return self._gripper(args, True)

    def tool_close_gripper(self, args):
        args = dict(args)
        args.setdefault("position", 500)
        return self._gripper(args, False)

    def _gripper(self, args, opened):
        position = int(args.get("position"))
        duration_ms = int(args.get("duration_ms", 450))
        script = """
import rospy
from hiwonder_interfaces.msg import MultiRawIdPosDur
from jetarm_sdk import bus_servo_control
rospy.init_node('jetarm_full_control_gripper', anonymous=True, disable_signals=True, log_level=rospy.ERROR)
pub = rospy.Publisher('/controllers/multi_id_pos_dur', MultiRawIdPosDur, queue_size=1)
rospy.sleep(0.5)
bus_servo_control.set_servos(pub, %d, ((10, %d),))
rospy.sleep(0.7)
print('ok')
""" % (duration_ms, position)
        stage = "open_gripper" if opened else "close_gripper"
        return command_result(stage, run_command(ros_command("python3 -c " + shlex.quote(script)), int(args.get("timeout_seconds", 20))), True)

    def tool_servo_debug(self, args):
        servo_id = int(args.get("servo_id"))
        position = int(args.get("position"))
        duration_ms = int(args.get("duration_ms", 500))
        script = """
import rospy
from hiwonder_interfaces.msg import MultiRawIdPosDur
from jetarm_sdk import bus_servo_control
rospy.init_node('jetarm_full_control_servo_debug', anonymous=True, disable_signals=True, log_level=rospy.ERROR)
pub = rospy.Publisher('/controllers/multi_id_pos_dur', MultiRawIdPosDur, queue_size=1)
rospy.sleep(0.5)
bus_servo_control.set_servos(pub, %d, ((%d, %d),))
rospy.sleep(max(%d / 1000.0, 0.5))
print('ok')
""" % (duration_ms, servo_id, position, duration_ms)
        return command_result("servo_debug", run_command(ros_command("python3 -c " + shlex.quote(script)), int(args.get("timeout_seconds", 20))), True)

    def tool_stop_all(self, args):
        timeout = int(args.get("timeout_seconds", 20))
        steps = [
            ("disable_sortting", 'rosservice call /object_sortting/enable_sortting "data: false"'),
            ("unset_target", 'rosservice call /object_sortting/set_color_target "{data_str: \'red\', data_bool: false}"'),
            ("exit_sortting", "rosservice call /object_sortting/exit"),
            ("servo_stop", "rostopic pub -1 /jetarm_sdk/serial_servo/stop std_msgs/UInt16 'data: 0'"),
        ]
        stage_results = []
        ok = True
        for name, command in steps:
            data = run_command(ros_command(command), timeout)
            data["step"] = name
            stage_results.append(data)
            ok = ok and data["exit_code"] == 0 and not data["timed_out"]
        return result(
            ok,
            "stop_all",
            telemetry={"stage_results": stage_results, "continue_ready": ok},
            error_code=None if ok else "STOP_FAILED",
            hint=None if ok else "Inspect ROS/servo state manually before retrying motion.",
        )

    def tool_camera_frame(self, args):
        output = args.get("output", os.path.expanduser("~/jetarm_frame.jpg"))
        topic = args.get("topic", "/rgbd_cam/color/image_rect_color")
        script = """
import cv2
import rospy
from sensor_msgs.msg import Image
rospy.init_node('jetarm_full_control_camera_frame', anonymous=True, disable_signals=True, log_level=rospy.ERROR)
msg = rospy.wait_for_message(%r, Image, timeout=5.0)
image = memoryview(msg.data)
import numpy as np
arr = np.ndarray(shape=(msg.height, msg.width, 3), dtype=np.uint8, buffer=image)
cv2.imwrite(%r, cv2.cvtColor(arr, cv2.COLOR_RGB2BGR))
print(%r)
""" % (topic, output, output)
        data = run_command(ros_command("python3 -c " + shlex.quote(script)), int(args.get("timeout_seconds", 20)))
        out = command_result("camera_frame", data)
        out["artifacts"]["image_path"] = output
        return out


def parse_json(value):
    if not value:
        return {}
    try:
        return json.loads(value)
    except ValueError as exc:
        raise SystemExit("invalid JSON: %s" % exc)


def print_result(output):
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))


def repl(agent):
    print("JetArm Full-Control Agent CLI %s" % VERSION)
    print("Mode: full-control. Raw shell, ROS and servo tools are enabled.")
    print("Transcript: %s" % agent.transcript_path)
    print("Type /help or /tools. Type /exit to quit.")
    while True:
        try:
            line = input("jetarm> ").strip()
        except EOFError:
            print()
            return 0
        if not line:
            continue
        if line in ("/exit", "/quit", "exit", "quit"):
            return 0
        if line in ("/help", "help"):
            print_result(agent.call("help", {}))
            continue
        if line in ("/tools", "tools"):
            print_result(agent.call("list_tools", {}))
            continue
        if line.startswith("/ask "):
            print_result(agent.call("agent_chat", {"message": line[len("/ask "):]}))
            continue
        if line in ("/skills", "skills"):
            print_result(agent.call("list_skills", {}))
            continue
        if line == "/go_home":
            print_result(agent.call("go_home", {}))
            continue
        if line == "/open_gripper":
            print_result(agent.call("open_gripper", {}))
            continue
        if line == "/close_gripper":
            print_result(agent.call("close_gripper", {}))
            continue
        if line == "/stop_all":
            print_result(agent.call("stop_all", {}))
            continue
        if line.startswith("/shell "):
            print_result(agent.call("shell", {"command": line[len("/shell "):]}))
            continue
        if line.startswith("/ros "):
            print_result(agent.call("ros", {"command": line[len("/ros "):]}))
            continue
        if line.startswith("/tool "):
            parts = line.split(" ", 2)
            tool_name = parts[1]
            tool_args = parse_json(parts[2] if len(parts) > 2 else "{}")
            print_result(agent.call(tool_name, tool_args))
            continue
        print_result(agent.call("agent_chat", {"message": line}))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="jetarm-full-control-agent")
    parser.add_argument("--transcript", default=os.environ.get("JETARM_AGENT_TRANSCRIPT", DEFAULT_TRANSCRIPT))
    parser.add_argument("--skill-root", default=os.environ.get("JETARM_SKILL_ROOT", DEFAULT_SKILL_ROOT))
    parser.add_argument("--llm-model", default=os.environ.get("JETARM_LLM_MODEL", DEFAULT_LLM_MODEL))
    parser.add_argument("--llm-base-url", default=os.environ.get("JETARM_LLM_BASE_URL", DEFAULT_LLM_BASE_URL))
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("repl")
    subparsers.add_parser("list-tools")
    call_parser = subparsers.add_parser("call")
    call_parser.add_argument("tool_name")
    call_parser.add_argument("--args-json", default="{}")
    args = parser.parse_args(argv or sys.argv[1:])
    llm_client = OpenAICompatibleClient(model=args.llm_model, base_url=args.llm_base_url)
    agent = FullControlAgent(transcript_path=args.transcript, skill_root=args.skill_root, llm_client=llm_client)
    if args.command in (None, "repl"):
        return repl(agent)
    if args.command == "list-tools":
        print_result(agent.call("list_tools", {}))
        return 0
    if args.command == "call":
        output = agent.call(args.tool_name, parse_json(args.args_json))
        print_result(output)
        return 0 if output["ok"] else 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
