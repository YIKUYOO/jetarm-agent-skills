from pathlib import Path


CHANGE_ROOT = Path("openspec/changes")
HISTORICAL_EXEMPTIONS = {
    "formalize-board-baseline-and-closed-loop",
    "verify-low-level-control-services",
    "verify-control-stack-and-pick-place-foundation",
    "supervised-board-control-validation",
    "orchestrate-supervised-board-session",
}
REQUIRED_SECTIONS = [
    "## Upstream References",
    "## Asset Impact",
    "## Freeze Delta",
]
REQUIRED_UPSTREAM_REFS = [
    "docs/architecture/final_agent_system_architecture.md",
    "docs/governance/asset_governance_and_freeze_rules.md",
    "docs/governance/project_asset_registry.yaml",
    "doc/开发任务拆解_v_1.md",
]


def test_governance_change_itself_declares_required_sections():
    change_dir = CHANGE_ROOT / "freeze-phase1-validation-and-project-governance"
    for file_name in ("proposal.md", "design.md"):
        content = (change_dir / file_name).read_text(encoding="utf-8")
        for section in REQUIRED_SECTIONS:
            assert section in content
        for ref in REQUIRED_UPSTREAM_REFS:
            assert ref in content


def test_post_governance_changes_must_include_required_sections():
    for change_dir in CHANGE_ROOT.iterdir():
        if not change_dir.is_dir() or change_dir.name in HISTORICAL_EXEMPTIONS:
            continue
        proposal_path = change_dir / "proposal.md"
        design_path = change_dir / "design.md"
        if not proposal_path.exists() or not design_path.exists():
            continue
        proposal = proposal_path.read_text(encoding="utf-8")
        design = design_path.read_text(encoding="utf-8")
        for section in REQUIRED_SECTIONS:
            assert section in proposal
            assert section in design
        for ref in REQUIRED_UPSTREAM_REFS:
            assert ref in proposal
            assert ref in design
