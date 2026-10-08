#!/usr/bin/env python3
from __future__ import print_function

import argparse
import json
import os
import shlex
import subprocess
import sys
import time


ROS_SETUP = (
    "export ROS_HOSTNAME=${ROS_HOSTNAME:-localhost} && "
    "export ROS_MASTER_URI=${ROS_MASTER_URI:-http://localhost:11311} && "
    ". /opt/ros/melodic/setup.bash >/dev/null 2>&1 && "
    ". ~/jetarm/devel/setup.bash >/dev/null 2>&1"
)


TOOLS = [
    {"name": "list_tools", "group": "robot_safe_tools", "risk_level": "low"},
    {"name": "go_home", "group": "robot_safe_tools", "risk_level": "high"},
    {"name": "open_gripper", "group": "robot_safe_tools", "risk_level": "high"},
    {"name": "close_gripper", "group": "robot_safe_tools", "risk_level": "high"},
    {"name": "stop_all", "group": "robot_safe_tools", "risk_level": "critical"},
    {"name": "shell", "group": "robot_raw_tools", "risk_level": "critical"},
    {"name": "rostopic", "group": "robot_raw_tools", "risk_level": "critical"},
    {"name": "rosservice", "group": "robot_raw_tools", "risk_level": "critical"},
    {"name": "rosrun", "group": "robot_raw_tools", "risk_level": "critical"},
    {"name": "roslaunch", "group": "robot_raw_tools", "risk_level": "critical"},
    {"name": "python_script", "group": "robot_raw_tools", "risk_level": "critical"},
    {"name": "servo_debug", "group": "robot_raw_tools", "risk_level": "critical"},
]


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


def run_command(command, timeout):
    started = time.time()
    try:
        completed = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = completed.communicate(timeout=timeout)
        exit_code = completed.returncode
        timed_out = False
    except subprocess.TimeoutExpired:
        completed.kill()
        stdout, stderr = completed.communicate()
        exit_code = 124
        timed_out = True
    return {
        "exit_code": exit_code,
        "stdout": stdout.decode("utf-8", "replace"),
        "stderr": stderr.decode("utf-8", "replace"),
        "timed_out": timed_out,
        "duration_ms": int((time.time() - started) * 1000),
        "command": command,
    }


def run_ros_command(body, timeout):
    return run_command(ROS_SETUP + " && " + body, timeout)


def command_result(stage, command_data, motion_executed=False):
    ok = command_data["exit_code"] == 0 and not command_data["timed_out"]
    return result(
        ok,
        stage,
        motion_executed=motion_executed,
        stdout=command_data["stdout"],
        stderr=command_data["stderr"],
        telemetry={
            "command": command_data["command"],
            "exit_code": command_data["exit_code"],
            "timed_out": command_data["timed_out"],
            "duration_ms": command_data["duration_ms"],
        },
        error_code=None if ok else "COMMAND_FAILED",
        hint=None if ok else "Inspect stdout/stderr. If motion may still be active, call stop_all.",
    )


def bridge_go_home(args):
    script = """
import rospy
from hiwonder_interfaces.msg import MultiRawIdPosDur
from jetarm_sdk import bus_servo_control
rospy.init_node('jetarm_agent_bridge_go_home', anonymous=True, disable_signals=True, log_level=rospy.ERROR)
pub = rospy.Publisher('/controllers/multi_id_pos_dur', MultiRawIdPosDur, queue_size=1)
rospy.sleep(0.5)
bus_servo_control.set_servos(pub, 800, ((1, 500), (2, 560), (3, 130), (4, 115), (5, 500), (10, 200)))
rospy.sleep(1.0)
print('ok')
""".strip()
    return command_result("go_home", run_ros_command("python3 -c " + shlex.quote(script), int(args.get("timeout_seconds", 20))), True)


def bridge_gripper(args, opened):
    position = int(args.get("position", 200 if opened else 500))
    duration_ms = int(args.get("duration_ms", 450))
    script = """
import rospy
from hiwonder_interfaces.msg import MultiRawIdPosDur
from jetarm_sdk import bus_servo_control
rospy.init_node('jetarm_agent_bridge_gripper', anonymous=True, disable_signals=True, log_level=rospy.ERROR)
pub = rospy.Publisher('/controllers/multi_id_pos_dur', MultiRawIdPosDur, queue_size=1)
rospy.sleep(0.5)
bus_servo_control.set_servos(pub, %d, ((10, %d),))
rospy.sleep(0.7)
print('ok')
""" % (duration_ms, position)
    return command_result(
        "open_gripper" if opened else "close_gripper",
        run_ros_command("python3 -c " + shlex.quote(script), int(args.get("timeout_seconds", 20))),
        True,
    )


def bridge_stop_all(args):
    timeout = int(args.get("timeout_seconds", 20))
    steps = [
        ("disable_sortting", 'rosservice call /object_sortting/enable_sortting "data: false"'),
        ("unset_target", 'rosservice call /object_sortting/set_color_target "{data_str: \'red\', data_bool: false}"'),
        ("exit", "rosservice call /object_sortting/exit"),
    ]
    results = []
    ok = True
    for name, command in steps:
        data = run_ros_command(command, timeout)
        data["step"] = name
        results.append(data)
        ok = ok and data["exit_code"] == 0 and not data["timed_out"]
    return result(
        ok,
        "stop_all",
        motion_executed=False,
        telemetry={"stage_results": results, "continue_ready": ok},
        error_code=None if ok else "STOP_FAILED",
        hint=None if ok else "Inspect ROS workflow state manually before retrying motion.",
    )


def bridge_shell(args):
    command = args.get("command", "").strip()
    if not command:
        return result(False, "schema", error_code="INVALID_TOOL_ARGUMENTS", stderr="command is required")
    return command_result("shell", run_command(command, int(args.get("timeout_seconds", 20))))


def bridge_prefixed(args, prefix, stage):
    raw_args = args.get("args", "").strip()
    if not raw_args:
        return result(False, "schema", error_code="INVALID_TOOL_ARGUMENTS", stderr="args is required")
    return command_result(stage, run_ros_command(prefix + " " + raw_args, int(args.get("timeout_seconds", 20))))


def bridge_rosrun(args):
    package = args.get("package", "").strip()
    executable = args.get("executable", "").strip()
    extra = args.get("args", "").strip()
    if not package or not executable:
        return result(False, "schema", error_code="INVALID_TOOL_ARGUMENTS", stderr="package and executable are required")
    command = "rosrun %s %s %s" % (shlex.quote(package), shlex.quote(executable), extra)
    return command_result("rosrun", run_ros_command(command, int(args.get("timeout_seconds", 20))))


def bridge_roslaunch(args):
    package = args.get("package", "").strip()
    launch_file = args.get("launch_file", "").strip()
    extra = args.get("args", "").strip()
    if not package or not launch_file:
        return result(False, "schema", error_code="INVALID_TOOL_ARGUMENTS", stderr="package and launch_file are required")
    command = "roslaunch %s %s %s" % (shlex.quote(package), shlex.quote(launch_file), extra)
    return command_result("roslaunch", run_ros_command(command, int(args.get("timeout_seconds", 20))))


def bridge_python_script(args):
    script = args.get("script", "").strip()
    if not script:
        return result(False, "schema", error_code="INVALID_TOOL_ARGUMENTS", stderr="script is required")
    command = "python3 -c " + shlex.quote(script)
    if args.get("with_ros", False):
        return command_result("python_script", run_ros_command(command, int(args.get("timeout_seconds", 20))))
    return command_result("python_script", run_command(command, int(args.get("timeout_seconds", 20))))


def bridge_servo_debug(args):
    args = dict(args)
    args.setdefault("timeout_seconds", 20)
    args.setdefault("duration_ms", 500)
    args["position"] = int(args.get("position"))
    args["servo_id"] = int(args.get("servo_id"))
    script = """
import rospy
from hiwonder_interfaces.msg import MultiRawIdPosDur
from jetarm_sdk import bus_servo_control
rospy.init_node('jetarm_agent_bridge_servo_debug', anonymous=True, disable_signals=True, log_level=rospy.ERROR)
pub = rospy.Publisher('/controllers/multi_id_pos_dur', MultiRawIdPosDur, queue_size=1)
rospy.sleep(0.5)
bus_servo_control.set_servos(pub, %(duration_ms)d, ((%(servo_id)d, %(position)d),))
rospy.sleep(0.7)
print('ok')
""" % args
    return command_result("servo_debug", run_ros_command("python3 -c " + shlex.quote(script), int(args["timeout_seconds"])), True)


def call_tool(name, args):
    if name == "list_tools":
        return result(True, "list_tools", telemetry={"tools": TOOLS})
    if name == "go_home":
        return bridge_go_home(args)
    if name == "open_gripper":
        return bridge_gripper(args, True)
    if name == "close_gripper":
        return bridge_gripper(args, False)
    if name == "stop_all":
        return bridge_stop_all(args)
    if name == "shell":
        return bridge_shell(args)
    if name == "rostopic":
        return bridge_prefixed(args, "rostopic", "rostopic")
    if name == "rosservice":
        return bridge_prefixed(args, "rosservice", "rosservice")
    if name == "rosrun":
        return bridge_rosrun(args)
    if name == "roslaunch":
        return bridge_roslaunch(args)
    if name == "python_script":
        return bridge_python_script(args)
    if name == "servo_debug":
        return bridge_servo_debug(args)
    return result(False, "dispatch", error_code="UNKNOWN_TOOL", hint="Call list_tools first.")


def append_transcript(path, tool_name, args, output):
    if not path:
        return
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory)
    entry = {
        "tool_name": tool_name,
        "args": args,
        "result": output,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(path, "a") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("tool_name", nargs="?", default="list_tools")
    parser.add_argument("--args-json", default="{}")
    parser.add_argument("--transcript", default=os.environ.get("JETARM_AGENT_TRANSCRIPT", ""))
    args = parser.parse_args(argv or sys.argv[1:])
    try:
        tool_args = json.loads(args.args_json)
    except ValueError as exc:
        output = result(False, "schema", stderr=str(exc), error_code="INVALID_JSON")
        print(json.dumps(output, ensure_ascii=False))
        return 2
    output = call_tool(args.tool_name, tool_args)
    append_transcript(args.transcript, args.tool_name, tool_args, output)
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0 if output["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
