from scripts.consistency.cli import build_parser
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
