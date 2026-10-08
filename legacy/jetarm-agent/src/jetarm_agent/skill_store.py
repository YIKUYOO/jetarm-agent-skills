from __future__ import annotations

import json
import shutil
from pathlib import Path

from jetarm_agent.agent_protocol import SkillInstallState, SkillManifest


MANIFEST_FILENAME = "manifest.json"
SKILL_FILENAME = "SKILL.md"


class SkillStore:
    def __init__(self, *, root: Path):
        self.root = root
        self.quarantine_dir = root / "quarantine"
        self.active_dir = root / "active"
        self.disabled_dir = root / "disabled"

    def ensure_layout(self) -> None:
        for directory in (self.quarantine_dir, self.active_dir, self.disabled_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def create_local_skill(self, manifest: SkillManifest, body: str) -> Path:
        self.ensure_layout()
        skill_dir = self._state_dir(manifest.install_state) / manifest.name
        skill_dir.mkdir(parents=True, exist_ok=True)
        self._write_manifest(skill_dir, manifest)
        (skill_dir / SKILL_FILENAME).write_text(body.rstrip() + "\n", encoding="utf-8")
        return skill_dir

    def import_downloaded_skill(self, source_dir: Path, *, review_notes: str = "") -> Path:
        self.ensure_layout()
        manifest = self._read_manifest(source_dir)
        quarantined = manifest.model_copy(
            update={
                "source": str(source_dir),
                "install_state": SkillInstallState.QUARANTINED,
                "review_notes": review_notes,
            }
        )
        target_dir = self.quarantine_dir / quarantined.name
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(source_dir, target_dir)
        self._write_manifest(target_dir, quarantined)
        return target_dir

    def activate_skill(self, name: str, *, review_notes: str) -> Path:
        return self._transition(name, SkillInstallState.ACTIVE, review_notes=review_notes)

    def disable_skill(self, name: str, *, review_notes: str = "") -> Path:
        return self._transition(name, SkillInstallState.DISABLED, review_notes=review_notes)

    def list_manifests(self) -> list[SkillManifest]:
        self.ensure_layout()
        manifests = []
        for directory in (self.quarantine_dir, self.active_dir, self.disabled_dir):
            for skill_dir in sorted(path for path in directory.iterdir() if path.is_dir()):
                manifest_path = skill_dir / MANIFEST_FILENAME
                if manifest_path.exists():
                    manifests.append(SkillManifest.model_validate_json(manifest_path.read_text(encoding="utf-8")))
        return manifests

    def _transition(self, name: str, state: SkillInstallState, *, review_notes: str) -> Path:
        self.ensure_layout()
        source_dir = self._find_skill_dir(name)
        if source_dir is None:
            raise FileNotFoundError(f"skill not found: {name}")
        manifest = self._read_manifest(source_dir).model_copy(
            update={
                "install_state": state,
                "review_notes": review_notes or self._read_manifest(source_dir).review_notes,
            }
        )
        target_dir = self._state_dir(state) / manifest.name
        if target_dir.resolve() != source_dir.resolve():
            if target_dir.exists():
                shutil.rmtree(target_dir)
            shutil.move(str(source_dir), str(target_dir))
        self._write_manifest(target_dir, manifest)
        return target_dir

    def _find_skill_dir(self, name: str) -> Path | None:
        for directory in (self.quarantine_dir, self.active_dir, self.disabled_dir):
            candidate = directory / name
            if candidate.exists():
                return candidate
        return None

    def _state_dir(self, state: SkillInstallState) -> Path:
        if state is SkillInstallState.ACTIVE:
            return self.active_dir
        if state is SkillInstallState.DISABLED:
            return self.disabled_dir
        return self.quarantine_dir

    @staticmethod
    def _read_manifest(skill_dir: Path) -> SkillManifest:
        return SkillManifest.model_validate_json((skill_dir / MANIFEST_FILENAME).read_text(encoding="utf-8"))

    @staticmethod
    def _write_manifest(skill_dir: Path, manifest: SkillManifest) -> None:
        (skill_dir / MANIFEST_FILENAME).write_text(
            json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
