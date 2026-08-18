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

    # apply
    apply_p = subparsers.add_parser("apply", help="Apply patch state mutations and persist")
    apply_p.add_argument("--project-root", type=str, required=True)
    apply_p.add_argument("--chapter", type=int, required=True)

    return parser


def _require_project_root(args, stderr) -> int:
    """Return 2 (usage error) if --project-root is missing."""
    if not args.project_root:
        print("--project-root required for this command", file=stderr)
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    import sys
    parser = build_parser()
    args = parser.parse_args(argv)

    from pathlib import Path
    from .core.runner import ConsistencyRunner
    import json

    if args.command in ("check", "list"):
        rc = _require_project_root(args, sys.stderr)
        if rc != 0:
            return rc
        runner = ConsistencyRunner(project_root=Path(args.project_root))
        blockers = runner.run_all(chapter=args.chapter)
        if args.command == "check" and args.patch:
            blockers = [b for b in blockers if b.patch == args.patch]
        print(json.dumps([b.__dict__ for b in blockers], ensure_ascii=False, indent=2))
        return 1 if blockers else 0

    elif args.command == "init":
        rc = _require_project_root(args, sys.stderr)
        if rc != 0:
            return rc
        state_path = Path(args.project_root) / ".webnovel" / "state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
        else:
            state = {}
        # Touch all 7 patch field namespaces (idempotent)
        sc = state.setdefault("story_craft", {})
        sc.setdefault("foreshadow_chain", {"version": 1, "dag": [], "validated_at": None, "validation_history": []})
        sc.setdefault("volume_anchors", {"version": 1, "anchors": []})
        sc.setdefault("event_matrix_state", {"version": 1, "types": {}, "history": [], "gentle_window": 5, "max_consecutive_fast": 2})
        sc.setdefault("pacing_history", {"version": 1, "history": [], "rules": {"max_consecutive_fast": 1, "slow_per_4_chapters_min": 1}})
        sc.setdefault("reader_contract", {"version": 1, "expectation_debt": [], "causal_credits": {"protagonist_actions_used_without_setup": []}, "endgame_reserves": [], "swap_debts": []})
        sc.setdefault("derived_views", {"version": 1})
        sm = state.setdefault("state", {})
        sm.setdefault("_revision", 0)
        sm.setdefault("_last_modified_by", "init")
        sm.setdefault("_last_modified_at", "")
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Initialized {state_path}")
        return 0

    elif args.command == "override":
        rc = _require_project_root(args, sys.stderr)
        if rc != 0:
            return rc
        from datetime import datetime, timezone
        override_path = Path(args.project_root) / ".webnovel" / "consistency_overrides.json"
        if override_path.exists():
            overrides = json.loads(override_path.read_text(encoding="utf-8"))
        else:
            overrides = []
        overrides.append({
            "chapter": args.chapter,
            "reason": args.reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        override_path.parent.mkdir(parents=True, exist_ok=True)
        override_path.write_text(json.dumps(overrides, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Override recorded for chapter {args.chapter}")
        return 0

    elif args.command == "apply":
        runner = ConsistencyRunner(project_root=Path(args.project_root))
        runner.apply_all(chapter=args.chapter)
        print(f"Applied all patches for chapter {args.chapter}")
        return 0

    return 1  # unknown command


if __name__ == "__main__":
    raise SystemExit(main())
