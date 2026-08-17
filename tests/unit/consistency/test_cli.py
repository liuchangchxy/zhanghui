from scripts.consistency.cli import build_parser, main
import pytest


def test_parser_check_command():
    parser = build_parser()
    args = parser.parse_args(["check", "--project-root", "/tmp/proj", "--chapter", "5"])
    assert args.command == "check"
    assert args.project_root == "/tmp/proj"
    assert args.chapter == 5
    assert args.patch is None


def test_parser_check_specific_patch():
    parser = build_parser()
    args = parser.parse_args(["check", "--project-root", "/tmp/proj", "--chapter", "5", "--patch", "foreshadow_dag"])
    assert args.patch == "foreshadow_dag"


def test_parser_list_command():
    parser = build_parser()
    args = parser.parse_args(["list", "--chapter", "5"])
    assert args.command == "list"


def test_parser_init_command():
    parser = build_parser()
    args = parser.parse_args(["init", "--volume", "1"])
    assert args.command == "init"
    assert args.volume == 1


def test_parser_override_command():
    parser = build_parser()
    args = parser.parse_args(["override", "--chapter", "5", "--reason", "user confirmed"])
    assert args.command == "override"
    assert args.reason == "user confirmed"


def test_cli_init_creates_state(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    rc = main(["init", "--project-root", str(proj), "--volume", "1"])
    assert rc == 0
    state_path = proj / ".webnovel" / "state.json"
    assert state_path.exists()
    import json
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert "story_craft" in state


def test_cli_override_writes_override_file(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".webnovel").mkdir()
    rc = main(["override", "--project-root", str(proj), "--chapter", "5", "--reason", "test"])
    assert rc == 0
    override_path = proj / ".webnovel" / "consistency_overrides.json"
    assert override_path.exists()
