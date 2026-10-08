from __future__ import annotations

from jetarm_demo_agent.schemas import ManipulationGoal, SkillResult


def _pose_available(goal: ManipulationGoal) -> bool:
    return bool(goal.source_object.world_pose_optional and goal.target_object_or_region.world_pose_optional)


def evaluate_manipulation_goal(goal: ManipulationGoal, confidence_threshold: float = 0.70) -> SkillResult:
    if goal.source_object.confidence < confidence_threshold or goal.target_object_or_region.confidence < confidence_threshold:
        return SkillResult(
            ok=False,
            stage="locating",
            motion_executed=False,
            object_locked=False,
            summary="VLM 目标定位置信度不足，已阻止开放桌面真实运动。",
            error_code="LOW_VLM_CONFIDENCE",
            evidence_frames=[],
        )

    if not _pose_available(goal):
        return SkillResult(
            ok=False,
            stage="localizing",
            motion_executed=False,
            object_locked=False,
            summary="开放桌面任务缺少世界坐标，不能进入真实运动。",
            error_code="WORLD_POSE_MISSING",
            evidence_frames=[],
        )

    if goal.requires_human_confirmation:
        return SkillResult(
            ok=False,
            stage="safety_check",
            motion_executed=False,
            object_locked=True,
            pose=goal.source_object.world_pose_optional,
            summary="开放桌面任务已定位目标，但需要人工确认后才能执行真实运动。",
            error_code="HUMAN_CONFIRMATION_REQUIRED",
            evidence_frames=[],
        )

    return SkillResult(
        ok=True,
        stage="ready",
        motion_executed=False,
        object_locked=True,
        pose=goal.source_object.world_pose_optional,
        summary="开放桌面任务已通过安全检查，可交给受限技能执行。",
        evidence_frames=[],
    )
