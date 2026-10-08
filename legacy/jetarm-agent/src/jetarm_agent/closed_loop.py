from __future__ import annotations

from typing import Protocol

from jetarm_agent.schemas import CalibrationProfile, DetectedTarget, PickPlaceRequest, PickPlaceResult


class BoardClosedLoopAdapter(Protocol):
    def observe_scene(self, profile: CalibrationProfile) -> list[DetectedTarget]:
        """Collect structured observation results for the current workcell."""

    def execute_pick_place(self, request: PickPlaceRequest) -> PickPlaceResult:
        """Execute a fixed-scene pick/place request through the board pipeline."""


class BoardClosedLoopService:
    def __init__(self, adapter: BoardClosedLoopAdapter):
        self.adapter = adapter

    def observe_scene(self, profile: CalibrationProfile) -> list[DetectedTarget]:
        return list(self.adapter.observe_scene(profile))

    def run_pick_place(self, request: PickPlaceRequest) -> PickPlaceResult:
        return self.adapter.execute_pick_place(request)
