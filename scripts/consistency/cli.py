"""CLI for consistency runner.

Source: 原創（參考 webnovel.py 的 argparse 風格）
"""
import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="consistency", description="Cross-volume consistency checker")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # check
    check = subparsers.add_parser("check", help="Run consistency checks on a chapter")
    check.add_argument("--project-root", type=str, required=True)
    check.add_argument("--chapter", type=int, required=True)
    check.add_argument("--patch", type=str, default=None, help="Run only this patch")

    # list
    lst = subparsers.add_parser("list", help="List blockers for a chapter")
    lst.add_argument("--project-root", type=str, default=None)
    lst.add_argument("--chapter", type=int, required=True)

    # init
    init = subparsers.add_parser("init", help="Initialize patch fields in state.json")
    init.add_argument("--project-root", type=str, default=None)
    init.add_argument("--volume", type=int, required=True)

    # override
    override = subparsers.add_parser("override", help="Force-bypass blockers (emergency)")
    override.add_argument("--project-root", type=str, default=None)
    override.add_argument("--chapter", type=int, required=True)
    override.add_argument("--reason", type=str, required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    print(f"[stub] command={args.command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
