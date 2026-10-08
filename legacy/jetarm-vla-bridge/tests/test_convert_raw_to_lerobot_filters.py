import json

from gpu.convert_raw_to_lerobot import load_episode_ids, select_episode_dirs


def _episode(root, name, success):
    episode_dir = root / name
    episode_dir.mkdir()
    (episode_dir / "meta.json").write_text(
        json.dumps({"episode_id": name, "success": success}),
        encoding="utf-8",
    )
    (episode_dir / "frames.jsonl").write_text("", encoding="utf-8")
    return episode_dir


def test_select_episode_dirs_can_filter_success_only(tmp_path):
    success = _episode(tmp_path, "ep_success", True)
    _episode(tmp_path, "ep_failure", False)

    selected = select_episode_dirs(tmp_path, success_only=True)

    assert selected == [success]


def test_select_episode_dirs_can_filter_by_episode_ids(tmp_path):
    first = _episode(tmp_path, "ep_first", False)
    _episode(tmp_path, "ep_second", True)

    selected = select_episode_dirs(tmp_path, episode_ids={"ep_first"})

    assert selected == [first]


def test_load_episode_ids_reads_cli_and_file_ids(tmp_path):
    episode_list = tmp_path / "episodes.txt"
    episode_list.write_text("# comment\nep_file\n\n", encoding="utf-8")

    assert load_episode_ids(["ep_cli"], episode_list) == {"ep_cli", "ep_file"}
