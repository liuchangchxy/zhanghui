#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
webnovel 统一入口（面向 skills / agents 的稳定 CLI）

设计目标：
- 只有一个入口命令，避免到处拼 `python -m data_modules.xxx ...` 导致参数位置/引号/路径炸裂。
- 自动解析正确的 book project_root（包含 `.webnovel/state.json` 的目录）。
- 所有写入类命令在解析到 project_root 后，统一前置 `--project-root` 传给具体模块。

典型用法（推荐，不依赖 PYTHONPATH / 不要求 cd）：
  python "<SCRIPTS_DIR>/webnovel.py" preflight
  python "<SCRIPTS_DIR>/webnovel.py" where
  python "<SCRIPTS_DIR>/webnovel.py" use "<PROJECT_ROOT>"
  python "<SCRIPTS_DIR>/webnovel.py" --project-root "<PROJECT_ROOT>" index stats
  python "<SCRIPTS_DIR>/webnovel.py" --project-root "<PROJECT_ROOT>" state process-chapter --chapter 100 --data @payload.json
  python "<SCRIPTS_DIR>/webnovel.py" --project-root "<PROJECT_ROOT>" extract-context --chapter 100 --format json

也支持（不推荐，容易踩 PYTHONPATH/cd/参数顺序坑）：
  python -m data_modules.webnovel where
"""

from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

from runtime_compat import enable_windows_utf8_stdio, normalize_windows_path
from project_locator import resolve_project_root, write_current_project_pointer, update_global_registry_current_project

from .story_runtime_health import build_story_runtime_health


if sys.platform == "win32":
    enable_windows_utf8_stdio(skip_in_pytest=True)


def _scripts_dir() -> Path:
    # data_modules/webnovel.py -> data_modules -> scripts
    return Path(__file__).resolve().parent.parent


def _resolve_root(explicit_project_root: Optional[str]) -> Path:
    # 允许显式传入工作区根目录或书项目根目录
    raw = explicit_project_root
    if raw:
        return resolve_project_root(raw)
    return resolve_project_root()


def _strip_project_root_args(argv: list[str]) -> list[str]:
    """
    下游工具统一由本入口注入 `--project-root`，避免重复传参导致 argparse 报错/歧义。
    """
    out: list[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--project-root":
            i += 2
            continue
        if tok.startswith("--project-root="):
            i += 1
            continue
        out.append(tok)
        i += 1
    return out


PASSTHROUGH_TOOLS = {
    "index",
    "state",
    "rag",
    "style",
    "entity",
    "context",
    "memory",
    "migrate",
    "status",
    "update-state",
    "backup",
    "archive",
    "init",
    "story-system",
    "memory-contract",
    "project-memory",
    "correction",
}


def _passthrough_tail(argv: list[str], tool: str) -> list[str]:
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == "--project-root":
            i += 2
            continue
        if token.startswith("--project-root="):
            i += 1
            continue
        if token == tool:
            return list(argv[i + 1 :])
        i += 1
    return []


def _run_data_module(module: str, argv: list[str]) -> int:
    """
    Import `data_modules.<module>` and call its main(), while isolating sys.argv.
    """
    mod = importlib.import_module(f"data_modules.{module}")
    main = getattr(mod, "main", None)
    if not callable(main):
        raise RuntimeError(f"data_modules.{module} 缺少可调用的 main()")

    old_argv = sys.argv
    try:
        sys.argv = [f"data_modules.{module}"] + argv
        try:
            main()
            return 0
        except SystemExit as e:
            return int(e.code or 0)
    finally:
        sys.argv = old_argv


def _run_script(script_name: str, argv: list[str]) -> int:
    """
    Run a script under `.claude/scripts/` via a subprocess.

    用途：兼容没有 main() 的脚本。
    """
    script_path = _scripts_dir() / script_name
    if not script_path.is_file():
        raise FileNotFoundError(f"未找到脚本: {script_path}")
    proc = subprocess.run([sys.executable, str(script_path), *argv])
    return int(proc.returncode or 0)


def cmd_where(args: argparse.Namespace) -> int:
    try:
        root = _resolve_root(args.project_root)
    except FileNotFoundError as exc:
        print(_project_root_diagnostic(args.project_root, exc), file=sys.stderr)
        return 1
    print(str(root))
    return 0


def _project_root_diagnostic(
    explicit_project_root: Optional[str], exc: FileNotFoundError
) -> str:
    if explicit_project_root:
        return (
            "未找到有效书项目根目录（需要包含 .webnovel/state.json）: "
            f"{explicit_project_root}\n"
            f"detail: {exc}"
        )
    return (
        "当前工作区还没有激活的书项目（未找到 .webnovel/state.json）。\n"
        "请先运行 webnovel init 创建项目，或运行 webnovel use <project_root> 绑定已有书项目。\n"
        f"detail: {exc}"
    )


def _build_preflight_report(explicit_project_root: Optional[str]) -> dict:
    scripts_dir = _scripts_dir().resolve()
    plugin_root = scripts_dir.parent
    skill_root = plugin_root / "skills" / "webnovel-write"
    entry_script = scripts_dir / "webnovel.py"
    extract_script = scripts_dir / "extract_chapter_context.py"

    checks: list[dict[str, object]] = [
        {"name": "scripts_dir", "ok": scripts_dir.is_dir(), "path": str(scripts_dir)},
        {"name": "entry_script", "ok": entry_script.is_file(), "path": str(entry_script)},
        {"name": "extract_context_script", "ok": extract_script.is_file(), "path": str(extract_script)},
        {"name": "skill_root", "ok": skill_root.is_dir(), "path": str(skill_root)},
    ]

    project_root = ""
    project_root_error = ""
    story_runtime: dict = {}
    try:
        resolved_root = _resolve_root(explicit_project_root)
        project_root = str(resolved_root)
        checks.append({"name": "project_root", "ok": True, "path": project_root})
        story_runtime = build_story_runtime_health(resolved_root)
    except FileNotFoundError as exc:
        project_root_error = _project_root_diagnostic(explicit_project_root, exc)
        checks.append(
            {
                "name": "project_root",
                "ok": False,
                "path": explicit_project_root or "",
                "error": project_root_error,
            }
        )
    except Exception as exc:
        project_root_error = str(exc)
        checks.append({"name": "project_root", "ok": False, "path": explicit_project_root or "", "error": project_root_error})

    return {
        "ok": all(bool(item["ok"]) for item in checks),
        "project_root": project_root,
        "scripts_dir": str(scripts_dir),
        "skill_root": str(skill_root),
        "checks": checks,
        "project_root_error": project_root_error,
        "story_runtime": story_runtime,
    }


def cmd_preflight(args: argparse.Namespace) -> int:
    report = _build_preflight_report(args.project_root)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for item in report["checks"]:
            status = "OK" if item["ok"] else "ERROR"
            path = item.get("path") or ""
            print(f"{status} {item['name']}: {path}")
            if item.get("error"):
                print(f"  detail: {item['error']}")
        story_runtime = report.get("story_runtime") or {}
        if story_runtime:
            print(
                "INFO story_runtime: "
                f"chapter={story_runtime.get('chapter')} "
                f"mainline_ready={story_runtime.get('mainline_ready')} "
                f"latest_commit_status={story_runtime.get('latest_commit_status')}"
            )
    return 0 if report["ok"] else 1


def cmd_project_status(args: argparse.Namespace) -> int:
    from .project_status import build_project_status, format_project_status

    try:
        root: Path | str | None = _resolve_root(args.project_root)
    except FileNotFoundError:
        root = args.project_root or None
    report = build_project_status(root, chapter=args.chapter)
    print(format_project_status(report, args.format))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from .doctor import build_doctor_report, format_doctor_report

    preflight_report = _build_preflight_report(args.project_root)
    root: Path | str | None = preflight_report.get("project_root") or args.project_root or None
    report = build_doctor_report(
        root,
        chapter=args.chapter,
        deep=bool(args.deep),
        preflight_report=preflight_report,
    )
    print(format_doctor_report(report, args.format))
    return 0 if report.get("ok") else 1


def cmd_write_gate(args: argparse.Namespace) -> int:
    from .write_gates import format_gate_report, run_write_gate

    root = _resolve_root(args.project_root)
    report = run_write_gate(root, chapter=args.chapter, stage=args.stage)
    print(format_gate_report(report, args.format))
    return 0 if report.get("ok") else 1


def cmd_projections(args: argparse.Namespace) -> int:
    from .projections import format_projection_report, replay_projections, retry_projection

    root = _resolve_root(args.project_root)
    if args.projection_action == "retry":
        report = retry_projection(root, chapter=args.chapter)
    else:
        report = replay_projections(
            root,
            start_chapter=args.from_chapter,
            end_chapter=args.to_chapter,
        )
    print(format_projection_report(report, args.format))
    return 0 if report.get("ok") else 1


def cmd_runtime(args: argparse.Namespace) -> int:
    from .chapter_runtime import ChapterRuntime
    root = _resolve_root(args.project_root)
    runtime = ChapterRuntime(root)

    action = args.runtime_action
    if action == "prepare":
        res = runtime.prepare(chapter=args.chapter, with_package=bool(getattr(args, "with_package", False)))
        if args.format == "json":
            print(res.to_json())
        else:
            status = "OK" if res.ok else "FAILED"
            print(f"{status} prepare chapter {args.chapter}: {res.status}")
            for b in res.blockers:
                print(f"  BLOCKER: {b}")
            for a in res.advisories:
                print(f"  ADVISORY: {a}")
        return 0 if res.ok else 1

    if action == "governed-context":
        try:
            ctx = runtime.get_governed_context(chapter=args.chapter)
            if args.format == "json":
                print(json.dumps(ctx, ensure_ascii=False, indent=2))
            else:
                print(f"OK governed-context chapter {args.chapter}")
            return 0
        except Exception as exc:
            if args.format == "json":
                print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
            else:
                print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    if action == "package":
        try:
            brief = getattr(args, "brief", None)
            brief_file = getattr(args, "brief_file", None)
            if not brief and brief_file:
                bf_p = Path(brief_file)
                if bf_p.is_file():
                    brief = bf_p.read_text(encoding="utf-8")
            pkg = runtime.get_writer_package(chapter=args.chapter, creative_brief=brief)
            if args.format == "json":
                print(pkg.to_json())
            elif args.format == "prompt":
                print(pkg.to_writer_prompt())
            else:
                print(f"OK package chapter {args.chapter} fingerprint={pkg.package_fingerprint}")
            return 0
        except Exception as exc:
            if args.format == "json":
                print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
            else:
                print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    if action == "attach-creative-brief":
        try:
            brief = getattr(args, "brief", "") or ""
            brief_file = getattr(args, "brief_file", "") or ""
            if not brief and brief_file:
                bf_p = Path(brief_file)
                if bf_p.is_file():
                    brief = bf_p.read_text(encoding="utf-8")
            if not brief:
                raise ValueError("Either --brief or --brief-file must be provided and non-empty")
            pkg = runtime.attach_creative_brief(chapter=args.chapter, creative_brief=brief)
            if args.format == "json":
                print(pkg.to_json())
            elif args.format == "prompt":
                print(pkg.to_writer_prompt())
            else:
                print(f"OK attach-creative-brief chapter {args.chapter} fingerprint={pkg.package_fingerprint}")
            return 0
        except Exception as exc:
            if args.format == "json":
                print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
            else:
                print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    if action == "ingest-draft":
        prose = getattr(args, "prose", "") or ""
        draft_file = getattr(args, "draft_file", "") or ""
        if not prose and draft_file:
            draft_p = Path(draft_file)
            prose = draft_p.read_text(encoding="utf-8") if draft_p.is_file() else ""
        meta_json = getattr(args, "metadata_json", "") or ""
        meta = json.loads(meta_json) if meta_json else None
        res = runtime.ingest_draft(
            chapter=args.chapter,
            prose=prose,
            package_fingerprint=args.package_fingerprint,
            metadata=meta,
        )
        if args.format == "json":
            print(res.to_json())
        else:
            status = "OK" if res.ok else "FAILED"
            print(f"{status} ingest-draft chapter {args.chapter}: {res.status}")
            if res.error:
                print(f"  error: {res.error}")
        return 0 if res.ok else 1

    if action == "status":
        res = runtime.get_status(chapter=args.chapter)
        if args.format == "json":
            print(res.to_json())
        else:
            print(f"Chapter {args.chapter} status:")
            print(f"  draft: {res.draft_status}")
            print(f"  commit: {res.commit_status}")
            print(f"  projection: {res.projection_status}")
        return 0

    if action == "commit":
        def _load_json_opt(p: str | None) -> dict | None:
            if p and Path(p).is_file():
                return json.loads(Path(p).read_text(encoding="utf-8"))
            return None

        review_res = _load_json_opt(getattr(args, "review_result", None))
        fulfillment_res = _load_json_opt(getattr(args, "fulfillment_result", None))
        disambiguation_res = _load_json_opt(getattr(args, "disambiguation_result", None))
        extraction_res = _load_json_opt(getattr(args, "extraction_result", None))
        reconciliation_res = _load_json_opt(getattr(args, "reconciliation_result", None))

        res = runtime.commit(
            chapter=args.chapter,
            draft_id=getattr(args, "draft_id", None) or None,
            review_result=review_res,
            fulfillment_result=fulfillment_res,
            disambiguation_result=disambiguation_res,
            extraction_result=extraction_res,
            reconciliation_result=reconciliation_res,
            on_conflict=getattr(args, "on_conflict", None),
        )
        if args.format == "json":
            print(res.to_json())
        else:
            status = "OK" if res.ok else "FAILED"
            print(f"{status} commit chapter {args.chapter}: {res.chapter_outcome}")
            if res.error:
                print(f"  error: {res.error}")
        return 0 if res.ok else 1

    if action == "publish-draft":
        try:
            target = runtime.publish_accepted_draft(
                chapter=args.chapter,
                draft_id=args.draft_id,
            )
            if args.format == "json":
                print(json.dumps({"ok": True, "published_file": str(target)}, ensure_ascii=False, indent=2))
            else:
                print(f"OK publish-draft chapter {args.chapter} to {target}")
            return 0
        except Exception as exc:
            if args.format == "json":
                print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
            else:
                print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    if action == "retry-projection":
        report = runtime.retry_projection(chapter=args.chapter)
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            from .projections import format_projection_report
            print(format_projection_report(report, args.format))
        return 0 if report.get("ok") else 1

    return 2


def cmd_prose(args: argparse.Namespace) -> int:
    """Dispatch prose-quality v2 pipeline subcommands (Issue #26)."""
    try:
        root = _resolve_root(args.project_root)
    except Exception:
        root = Path(".")
    action = args.prose_action

    from .prose_pipeline import ProseQualityPipeline
    pipeline = ProseQualityPipeline(root)

    if action == "voice-target":
        chapter = getattr(args, "chapter", 1) or 1
        vt = pipeline.get_voice_target(chapter=chapter)
        if args.format == "json":
            print(vt.to_json())
        else:
            print(vt.format_prompt_block())
        return 0

    if action == "diagnose":
        text = ""
        if getattr(args, "file", None):
            fp = Path(args.file)
            if fp.is_file():
                text = fp.read_text(encoding="utf-8")
        elif getattr(args, "text", None):
            text = args.text
        if not text:
            print("ERROR: --file or --text is required", file=sys.stderr)
            return 2
        diag = pipeline.diagnose(text)
        if args.format == "json":
            print(diag.to_json())
        else:
            print(diag.format_markdown_report())
        return 0

    if action == "diff-semantic":
        before_text = ""
        after_text = ""
        if getattr(args, "before_file", None):
            p = Path(args.before_file)
            if p.is_file():
                before_text = p.read_text(encoding="utf-8")
        elif getattr(args, "before", None):
            before_text = args.before

        if getattr(args, "after_file", None):
            p = Path(args.after_file)
            if p.is_file():
                after_text = p.read_text(encoding="utf-8")
        elif getattr(args, "after", None):
            after_text = args.after

        judge_callable = None
        judge_payload = getattr(args, "judge_result", "") or ""
        judge_file = getattr(args, "judge_file", "") or ""
        if judge_file and Path(judge_file).is_file():
            judge_payload = Path(judge_file).read_text(encoding="utf-8")
        if judge_payload:
            judge_callable = lambda b, a: judge_payload

        from .prose_semantic_diff import compare_semantic_facts
        res = compare_semantic_facts(before_text, after_text, semantic_judge=judge_callable)
        if args.format == "json":
            print(res.to_json())
        else:
            print(f"Outcome: {res.outcome.value} (Safe: {res.safe})")
            print(f"Summary: {res.summary}")
            for d in res.drift_items:
                print(f"  - [{d.dimension}] {d.description}")
        return 0 if res.safe else 1

    if action == "validate":
        before_text = ""
        after_text = ""
        if getattr(args, "before_file", None):
            p = Path(args.before_file)
            if p.is_file():
                before_text = p.read_text(encoding="utf-8")
        elif getattr(args, "before", None):
            before_text = args.before

        if getattr(args, "after_file", None):
            p = Path(args.after_file)
            if p.is_file():
                after_text = p.read_text(encoding="utf-8")
        elif getattr(args, "after", None):
            after_text = args.after

        judge_callable = None
        judge_payload = getattr(args, "judge_result", "") or ""
        judge_file = getattr(args, "judge_file", "") or ""
        if judge_file and Path(judge_file).is_file():
            judge_payload = Path(judge_file).read_text(encoding="utf-8")
        if judge_payload:
            judge_callable = lambda b, a: judge_payload

        chapter = getattr(args, "chapter", 1) or 1
        res = pipeline.process_and_validate(before_text, after_text, chapter=chapter, semantic_judge=judge_callable)
        if args.format == "json":
            print(res.to_json())
        else:
            status = "ACCEPTED" if res.ok else "ROLLEDBACK"
            print(f"Status: {status} | Semantic: {res.semantic_outcome}")
            if res.rollback_reason:
                print(f"Rollback reason: {res.rollback_reason}")
        return 0 if res.ok else 1

    return 2


def cmd_migration(args: argparse.Namespace) -> int:
    from dataclasses import asdict
    from .project_migration import (
        BackupManifest, MigrationError, create_verified_backup, dry_run_migration,
        migrate_project, preflight_project, replace_generation, restore_mutable_layout,
    )

    root = _resolve_root(args.project_root)
    try:
        if args.migration_action == "preflight":
            payload = asdict(preflight_project(root))
        elif args.migration_action == "dry-run":
            payload = asdict(dry_run_migration(root, args.report_digest))
        elif args.migration_action == "backup":
            report = preflight_project(root)
            plan = dry_run_migration(root, args.report_digest or report.report_digest)
            payload = asdict(create_verified_backup(root, plan))
        elif args.migration_action == "migrate":
            report = preflight_project(root)
            plan = dry_run_migration(root, args.report_digest)
            manifest_path = Path(args.backup_path).expanduser().resolve() / "manifest.json"
            from .project_migration import _json_file
            manifest = _json_file(manifest_path)
            if not manifest:
                raise MigrationError("BACKUP_MANIFEST_INVALID")
            backup = BackupManifest(
                schema_version=manifest.get("schema_version", ""), project_root=str(root),
                backup_path=str(manifest_path.parent), plan_digest=manifest.get("plan_digest", ""),
                file_count=len(manifest.get("files", [])), files=manifest.get("files", []),
                sqlite_integrity=manifest.get("sqlite_integrity", {}), restore_verified=True,
                manifest_sha256=manifest.get("manifest_sha256", ""))
            payload = asdict(migrate_project(root, args.report_digest, args.plan_digest, backup))
        else:
            if args.migration_action == "replace-generation":
                publication = replace_generation(root, args.generation_id)
                payload = {"publication_record_id": publication.publication_record_id,
                           "record_sha256": publication.record_sha256,
                           "path": str(publication.path), "body": publication.body}
            else:
                manifest_path = Path(args.backup_path).expanduser().resolve() / "manifest.json"
                from .project_migration import _json_file
                manifest = _json_file(manifest_path)
                if not manifest:
                    raise MigrationError("BACKUP_MANIFEST_INVALID")
                backup = BackupManifest(
                    schema_version=manifest.get("schema_version", ""), project_root=str(root),
                    backup_path=str(manifest_path.parent), plan_digest=manifest.get("plan_digest", ""),
                    file_count=len(manifest.get("files", [])), files=manifest.get("files", []),
                    sqlite_integrity=manifest.get("sqlite_integrity", {}), restore_verified=True,
                    manifest_sha256=manifest.get("manifest_sha256", ""))
                payload = restore_mutable_layout(
                    root, backup,
                    {"ok": True, "conflicts": [], "expected_current_hashes": {
                        ".webnovel/state-overlay.json": args.overlay_sha256}},
                    expected_semantic_activation_id=args.semantic_activation_id,
                    expected_effective_history_digest=args.effective_history_digest)
    except MigrationError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok", True) and not payload.get("unresolved_decisions") else 1


def cmd_user_report(args: argparse.Namespace) -> int:
    from .user_report import build_user_report, format_user_report

    root = _resolve_root(args.project_root)
    report = build_user_report(
        root,
        stage=args.stage,
        chapter=args.chapter,
        volume=args.volume,
    )
    print(format_user_report(report, args.format))
    return 0


def cmd_run_ledger(args: argparse.Namespace) -> int:
    from .run_ledger import (
        build_write_resume_plan,
        format_resume_plan,
        record_write_step,
    )

    root = _resolve_root(args.project_root)
    if args.ledger_action == "record-write-step":
        try:
            inputs = json.loads(args.inputs_json)
            outputs = json.loads(args.outputs_json)
            problems = json.loads(args.problems_json)
            auto_handled = json.loads(args.auto_handled_json)
        except json.JSONDecodeError as exc:
            print(f"ledger JSON 参数不合法: {exc}", file=sys.stderr)
            return 2
        if not isinstance(inputs, dict) or not isinstance(outputs, dict):
            print("inputs-json / outputs-json 必须是 JSON object", file=sys.stderr)
            return 2
        if not isinstance(problems, list) or not isinstance(auto_handled, list):
            print("problems-json / auto-handled-json 必须是 JSON list", file=sys.stderr)
            return 2
        entry = record_write_step(
            root,
            chapter=args.chapter,
            step=args.step,
            status=args.status,
            mode=args.mode,
            inputs={str(key): str(value) for key, value in inputs.items()},
            outputs={str(key): str(value) for key, value in outputs.items()},
            problems=[str(item) for item in problems],
            auto_handled=[str(item) for item in auto_handled],
            duration_ms=args.duration_ms,
        )
        if args.format == "json":
            print(json.dumps(entry, ensure_ascii=False, indent=2))
        else:
            print(f"{entry['step']}: {entry['status']}")
        return 0
    if args.ledger_action == "write-resume":
        report = build_write_resume_plan(
            root,
            chapter=args.chapter,
            mode=args.mode,
        )
        print(format_resume_plan(report, args.format))
        return 0
    return 2


def cmd_run_log(args: argparse.Namespace) -> int:
    from .run_logger import write_run_log

    try:
        root = _resolve_root(args.project_root)
    except FileNotFoundError:
        root = normalize_windows_path(args.project_root).expanduser()
        try:
            root = root.resolve()
        except Exception:
            root = root
    try:
        payload = json.loads(args.payload_json)
    except json.JSONDecodeError as exc:
        print(f"payload-json 不是合法 JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(payload, dict):
        print("payload-json 必须是 JSON object", file=sys.stderr)
        return 2
    result = write_run_log(root, event=args.event, payload=payload, append=args.append)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["path"])
    return 0


def cmd_use(args: argparse.Namespace) -> int:
    project_root = normalize_windows_path(args.project_root).expanduser()
    try:
        project_root = project_root.resolve()
    except Exception as exc:
        import sys
        print(f"⚠️ path.resolve() 失败 ({project_root}): {exc}", file=sys.stderr)
        project_root = project_root

    workspace_root: Optional[Path] = None
    if args.workspace_root:
        workspace_root = normalize_windows_path(args.workspace_root).expanduser()
        try:
            workspace_root = workspace_root.resolve()
        except Exception as exc:
            import sys
            print(f"⚠️ path.resolve() 失败 ({workspace_root}): {exc}", file=sys.stderr)
            workspace_root = workspace_root

    # 1) 写入工作区指针（若工作区内存在 `.claude/`）
    pointer_file = write_current_project_pointer(project_root, workspace_root=workspace_root)
    if pointer_file is not None:
        print(f"workspace pointer: {pointer_file}")
    else:
        print("workspace pointer: (skipped)")

    # 2) 写入用户级 registry（保证全局安装/空上下文可恢复）
    reg_path = update_global_registry_current_project(workspace_root=workspace_root, project_root=project_root)
    if reg_path is not None:
        print(f"global registry: {reg_path}")
    else:
        print("global registry: (skipped)")

    return 0


def _save_state_via_atomic(project_root: Path, state: dict) -> None:
    """Persist mutable state through the active owner view when enrolled."""
    from .owned_project_view import OwnedProjectView

    view = OwnedProjectView.pin_active(project_root)
    if view is not None:
        from .owned_project_view import OwnedViewError
        from story_craft import classify_story_craft_field

        read_view = state.get("_view")
        required_snapshot_fields = ("generation_id", "semantic_activation_id", "publication_record_id",
                                    "publication_record_sha256", "owner_overlay_revision")
        if (not isinstance(read_view, dict)
                or any(field not in read_view for field in required_snapshot_fields)
                or any(not isinstance(read_view.get(field), str) or not read_view[field]
                       for field in required_snapshot_fields[:-1])
                or not isinstance(read_view.get("owner_overlay_revision"), int)
                or isinstance(read_view.get("owner_overlay_revision"), bool)
                or read_view["owner_overlay_revision"] < 0):
            raise OwnedViewError("OWNER_READ_SNAPSHOT_REQUIRED")
        pinned = view.pinned
        if (read_view.get("generation_id") != pinned.generation_id
                or read_view.get("semantic_activation_id") != pinned.semantic_activation_id
                or read_view.get("publication_record_id") != pinned.publication_record_id
                or read_view.get("publication_record_sha256") != pinned.publication_record_sha256):
            raise OwnedViewError("ACTIVE_PUBLICATION_CHANGED_DURING_OPERATION")
        current = view.state_view()
        read_revision = read_view.get("owner_overlay_revision")
        current_revision = current.get("_view", {}).get("owner_overlay_revision")
        if read_revision != current_revision:
            raise OwnedViewError("OWNER_STATE_REVISION_CONFLICT")
        owner_roots = ("story_craft", "planning", "promise_ledger", "review_checkpoints",
                       "workflow", "craft", "intent", "disambiguation_warnings",
                       "disambiguation_pending", "project_info", "volumes")
        values = {key: state[key] for key in owner_roots
                  if key in state and state.get(key) != current.get(key)}
        metadata = state.get("chapter_meta")
        current_metadata = current.get("chapter_meta")
        if isinstance(metadata, dict):
            for chapter_key, fields in metadata.items():
                if not isinstance(fields, dict):
                    raise OwnedViewError(f"UNMAPPED_CHAPTER_META:{chapter_key}")
                before = current_metadata.get(chapter_key, {}) if isinstance(current_metadata, dict) else {}
                for field_name, value in fields.items():
                    if before.get(field_name) == value:
                        continue
                    semantic = classify_story_craft_field(f"chapter_meta.{chapter_key}.{field_name}")
                    if semantic not in {"CRAFT", "INTENT"}:
                        raise OwnedViewError(f"UNMAPPED_CHAPTER_META:{chapter_key}.{field_name}")
                    values[f"chapter_meta.{chapter_key}.{field_name}"] = value
        for path in ("progress.current_volume", "progress.volumes_planned",
                     "progress.volumes_completed", "progress.total_volumes", "progress.last_updated"):
            parts = path.split(".")
            source = state
            target = current
            for part in parts:
                source = source.get(part, {}) if isinstance(source, dict) else {}
                target = target.get(part, {}) if isinstance(target, dict) else {}
            if source != target and source != {}:
                values[path] = source
        if values:
            view.write_owner_values(values, expected_revision=read_revision)
            verified = view.state_view()
            for key, expected in values.items():
                target = verified
                for part in key.split("."):
                    target = target.get(part) if isinstance(target, dict) else None
                matches = (isinstance(target, dict) and all(target.get(k) == v for k, v in expected.items())
                           if key == "progress.chapter_status" and isinstance(expected, dict) else target == expected)
                if not matches:
                    raise OwnedViewError(f"OWNER_STATE_READ_AFTER_WRITE_MISMATCH:{key}")
        return

    """Base-only compatibility writer."""
    from security_utils import atomic_write_json

    state_path = project_root / ".webnovel" / "state.json"
    atomic_write_json(
        state_path,
        state,
        indent=2,
        use_lock=True,
        backup=False,
    )


def cmd_story_craft(args: argparse.Namespace) -> int:
    """Dispatch story-craft subcommands."""
    from security_utils import read_json_safe
    from .owned_project_view import OwnedProjectView

    root = _resolve_root(args.project_root)
    state_path = root / ".webnovel" / "state.json"
    view = OwnedProjectView.pin_active(root)
    state = view.state_view() if view is not None else read_json_safe(state_path, default={})

    action = args.story_craft_action
    if action == "init-volume-beat":
        if not args.total_chapters or args.total_chapters <= 0:
            raise ValueError(f"total-chapters must be positive, got {args.total_chapters}")
        from story_craft import init_volume_beat

        init_volume_beat(
            state,
            volume=args.volume,
            total_chapters=args.total_chapters,
        )
        _save_state_via_atomic(root, state)
        return 0
    if action == "fill-beat":
        from story_craft import fill_beat

        fill_beat(
            state,
            volume=args.volume,
            beat_name=args.beat_name,
            chapter=args.chapter,
            notes=args.notes or "",
        )
        _save_state_via_atomic(root, state)
        return 0
    if action == "check-volume":
        from story_craft import (
            check_volume_beat, check_rhythm_status,
            check_timed_lock_deadlines, check_scene_sequel,
        )

        issues: list[str] = []
        # Craft observations remain advisory; malformed required state stays a blocker.
        try:
            vol_issues = [f"ADVISORY: {issue}" for issue in check_volume_beat(state, volume=args.volume, current_chapter=args.chapter)]
        except ValueError as exc:
            vol_issues = [f"BLOCKER: {exc}"]
        issues.extend(vol_issues)
        # 2. Rhythm curve status
        if state.get("story_craft", {}).get("rhythm_curve"):
            rhythm_status = check_rhythm_status(state)
            if rhythm_status == "block":
                n = state["story_craft"]["rhythm_curve"].get("chapters_since_peak", "?")
                issues.append(f"ADVISORY: 节奏曲线建议复核：chapters_since_peak={n}")
            elif rhythm_status == "warning":
                issues.append("WARN: 节奏曲线 WARNING")
        # 3. Timed locks + 4. Scene-Sequel (chapter-aware)
        if args.chapter is not None:
            overdue = check_timed_lock_deadlines(state, current_chapter=args.chapter)
            for lock in overdue:
                issues.append(f"ADVISORY: 定时锁计划偏差：{lock['id']} deadline={lock['deadline_chapter']}")
            cm = state.get("chapter_meta", {})
            if isinstance(cm, dict):
                cm_entry = cm.get(str(args.chapter), {})
                if isinstance(cm_entry, dict):
                    for issue in check_scene_sequel(cm_entry):
                        issues.append(f"ADVISORY: {issue}")
                    if not cm_entry.get("hook_type"):
                        issues.append("ADVISORY: 章末 hook_type 未声明")
        # 5. Foreshadow chain per-depth count
        foreshadow_chain = state.get("story_craft", {}).get("foreshadow_chain", [])
        if isinstance(foreshadow_chain, list):
            depth_counts = {"表层": 0, "中层": 0, "深层": 0}
            for f in foreshadow_chain:
                if isinstance(f, dict) and f.get("depth") in depth_counts:
                    depth_counts[f["depth"]] += 1
            if depth_counts["表层"] < 5:
                issues.append(f"WARN: 表层伏笔 < 5 (当前 {depth_counts['表层']})")
            if depth_counts["中层"] < 3:
                issues.append(f"WARN: 中层伏笔 < 3 (当前 {depth_counts['中层']})")
            if depth_counts["深层"] < 1:
                issues.append("WARN: 深层伏笔 = 0")
        # 6. Thematic echoes + 7. Character arc presence
        thematic = state.get("story_craft", {}).get("thematic_echoes", [])
        if not thematic:
            issues.append("WARN: thematic_echoes 为空")
        if not state.get("story_craft", {}).get("character_arc"):
            issues.append("WARN: character_arc 未设置")
        # 7+. .md 文件存在性检查（P0 修复）
        from pathlib import Path
        outline_dir = root / "大纲"
        expected_md = [
            outline_dir / f"第{args.volume}卷-节拍表.md",
            outline_dir / f"第{args.volume}卷-时间线.md",
            outline_dir / f"第{args.volume}卷-详细大纲.md",
        ]
        for md in expected_md:
            if not md.is_file():
                issues.append(f"BLOCKER: {md.relative_to(root)} 不存在")

        for issue in issues:
            print(issue)
        return 1 if any("BLOCKER" in i for i in issues) else 0
    if action == "init-forechains":
        from story_craft import add_foreshadow

        # Ensure story_craft substructure exists.
        state.setdefault("story_craft", {}).setdefault("foreshadow_chain", [])
        chain = state["story_craft"]["foreshadow_chain"]

        # Volume context (defaults to 1 when --volume omitted).
        volume = getattr(args, "volume", None) or 1

        # Per-volume depth counts (foreshadows now carry a `volume` field).
        existing_by_depth = {"表层": 0, "中层": 0, "深层": 0}
        for item in chain:
            if not isinstance(item, dict):
                continue
            if item.get("volume") != volume:
                continue
            d = item.get("depth")
            if d in existing_by_depth:
                existing_by_depth[d] += 1

        total_chapters = (
            state.get("story_craft", {}).get("volume_beat", {}).get("total_chapters")
            or 50
        )
        # Approximate per-volume chapter span (best-effort placeholder).
        vol_start = max(1, (volume - 1) * total_chapters + 1)
        vol_end = volume * total_chapters

        added = 0
        # Surface (表层) ≥5 — one per chapter-ish across the volume.
        surface_needed = max(0, 5 - existing_by_depth["表层"])
        for i in range(surface_needed):
            ch = vol_start + i * max(1, (vol_end - vol_start) // max(surface_needed, 1))
            add_foreshadow(state, {
                "type": "环境",
                "depth": "表层",
                "volume": volume,
                "content": f"[auto] 表层伏笔 #{i + 1}（卷{volume} 待补具体内容）",
                "buried_chapter": ch,
                "expected_payoff_chapter": min(vol_end, ch + max(5, total_chapters // 5)),
                "payoff_method": "[auto] 章末揭晓或对白回收（待细化）",
                "linked_entities": [],
            })
            added += 1
        # Mid (中层) ≥3.
        mid_needed = max(0, 3 - existing_by_depth["中层"])
        for i in range(mid_needed):
            ch = vol_start + (vol_end - vol_start) * (i + 1) // (mid_needed + 1)
            add_foreshadow(state, {
                "type": "物谶",
                "depth": "中层",
                "volume": volume,
                "content": f"[auto] 中层伏笔 #{i + 1}（卷{volume} 待补具体内容）",
                "buried_chapter": ch,
                "expected_payoff_chapter": min(vol_end, ch + max(10, total_chapters // 3)),
                "payoff_method": "[auto] 卷中/卷末重大事件回收（待细化）",
                "linked_entities": [],
            })
            added += 1
        # Deep (深层) ≥1.
        deep_needed = max(0, 1 - existing_by_depth["深层"])
        for i in range(deep_needed):
            add_foreshadow(state, {
                "type": "诗谶",
                "depth": "深层",
                "volume": volume,
                "content": f"[auto] 深层伏笔 #{i + 1}（全书级主题伏笔，待补具体内容）",
                "buried_chapter": vol_start,
                "expected_payoff_chapter": vol_end,
                "payoff_method": "[auto] 全书主线回收（待细化）",
                "linked_entities": [],
            })
            added += 1

        _save_state_via_atomic(root, state)
        print(
            f"init-forechains: added {added} foreshadow(s) for volume {volume} "
            f"(表层={existing_by_depth['表层'] + sum(1 for x in range(surface_needed))}, "
            f"中层={existing_by_depth['中层'] + mid_needed}, "
            f"深层={existing_by_depth['深层'] + deep_needed})"
        )
        return 0
    if action == "init-locks":
        from story_craft import add_timed_lock

        state.setdefault("story_craft", {}).setdefault("timed_locks", [])
        locks = state["story_craft"]["timed_locks"]
        volume = getattr(args, "volume", None) or 1
        total_chapters = (
            state.get("story_craft", {}).get("volume_beat", {}).get("total_chapters")
            or 50
        )
        vol_start = max(1, (volume - 1) * total_chapters + 1)
        vol_end = volume * total_chapters

        # Genre-aware chapter-level placeholder lock.
        # Reads genre from project_info; falls back to 玄幻.
        genre = (
            state.get("project_info", {}).get("genre", "玄幻")
            if isinstance(state.get("project_info"), dict)
            else "玄幻"
        )
        chapter_level_lock_desc = {
            "玄幻": "主角 3 章内出村",
            "修仙": "主角 3 章内踏入修仙门派",
            "都市": "金手指第 1 章出现，第 2 章起作用",
            "system_flow": "系统第 1 章出现，第 2 章起作用",
        }.get(genre, "主角 3 章内出村")  # fallback to 玄幻

        # Target volume-level locks: Midpoint / All Is Lost / 卷末新钩子。
        targets = [
            ("Midpoint 必须发生", int(vol_start + (vol_end - vol_start) * 0.5)),
            ("All Is Lost 必须到达", int(vol_start + (vol_end - vol_start) * 0.75)),
            ("卷末新钩子必须留", vol_end),
        ]

        def _has(needle: str) -> bool:
            return any(needle in (l.get("description") or "") for l in locks)

        added = 0
        for desc, deadline in targets:
            if _has(desc):
                continue
            add_timed_lock(state, {
                "description": desc,
                "deadline_chapter": deadline,
            })
            added += 1

        if not _has(chapter_level_lock_desc):
            add_timed_lock(state, {
                "description": chapter_level_lock_desc,
                "deadline_chapter": vol_start + 2,
            })
            added += 1

        _save_state_via_atomic(root, state)
        print(f"init-locks: added {added} timed_lock(s) for volume {volume} (total now {len(state['story_craft']['timed_locks'])})")
        return 0
    if action == "set-chapter-meta":
        from story_craft import set_chapter_meta

        fields: dict[str, object] = {}
        if args.beat_position:
            fields["beat_position"] = args.beat_position
        if args.hook_type:
            fields["hook_type"] = args.hook_type
        if args.scene_goal:
            fields["scene_goal"] = args.scene_goal
        if args.scene_conflict:
            fields["scene_conflict"] = args.scene_conflict
        if args.scene_setback:
            fields["scene_setback"] = args.scene_setback
        if args.scene_resolution:
            fields["scene_resolution"] = args.scene_resolution
        if args.sequel_reaction:
            fields["sequel_reaction"] = args.sequel_reaction
        if args.sequel_dilemma:
            fields["sequel_dilemma"] = args.sequel_dilemma
        if args.sequel_decision:
            fields["sequel_decision"] = args.sequel_decision
        set_chapter_meta(state, chapter=args.chapter, **fields)
        _save_state_via_atomic(root, state)
        return 0
    print(f"unknown story-craft action: {action}", file=sys.stderr)
    return 2


def main() -> None:
    parser = argparse.ArgumentParser(description="webnovel unified CLI")
    parser.add_argument("--project-root", help="书项目根目录或工作区根目录（可选，默认自动检测）")

    sub = parser.add_subparsers(dest="tool", required=True)

    p_where = sub.add_parser("where", help="打印解析出的 project_root")
    p_where.set_defaults(func=cmd_where)

    p_preflight = sub.add_parser("preflight", help="校验统一 CLI 运行环境与 project_root")
    p_preflight.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    p_preflight.set_defaults(func=cmd_preflight)

    p_project_status = sub.add_parser("project-status", help="输出机器可读的项目短状态")
    p_project_status.add_argument("--chapter", type=int, default=None, help="目标章节号")
    p_project_status.add_argument("--format", choices=["summary", "json"], default="summary", help="输出格式")
    p_project_status.set_defaults(func=cmd_project_status)

    p_doctor = sub.add_parser("doctor", help="阶段感知的只读项目体检")
    p_doctor.add_argument("--chapter", type=int, default=None, help="目标章节号")
    p_doctor.add_argument("--deep", action="store_true", help="包含 dashboard 等较深检查")
    p_doctor.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    p_doctor.set_defaults(func=cmd_doctor)

    p_write_gate = sub.add_parser("write-gate", help="写章自然边界校验")
    p_write_gate.add_argument("--chapter", type=int, required=True, help="目标章节号")
    p_write_gate.add_argument("--stage", choices=["prewrite", "precommit", "postcommit"], required=True, help="校验阶段")
    p_write_gate.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")
    p_write_gate.set_defaults(func=cmd_write_gate)

    p_projections = sub.add_parser("projections", help="从已有 commit 补跑或重放 projection")
    projections_sub = p_projections.add_subparsers(dest="projection_action", required=True)
    p_projection_retry = projections_sub.add_parser("retry", help="补跑单章 projection")
    p_projection_retry.add_argument("--chapter", type=int, required=True, help="目标章节号")
    p_projection_retry.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")
    p_projection_retry.set_defaults(func=cmd_projections)
    p_projection_replay = projections_sub.add_parser("replay", help="按章节范围重放 projection")
    p_projection_replay.add_argument("--from-chapter", type=int, required=True, help="起始章节号")
    p_projection_replay.add_argument("--to-chapter", type=int, required=True, help="结束章节号")
    p_projection_replay.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")
    p_projection_replay.set_defaults(func=cmd_projections)

    p_runtime = sub.add_parser("runtime", help="Runtime API v1 章节编排公共入口")
    runtime_sub = p_runtime.add_subparsers(dest="runtime_action", required=True)

    p_rt_prep = runtime_sub.add_parser("prepare", help="准备章节环境与合同")
    p_rt_prep.add_argument("--chapter", type=int, required=True, help="章节号")
    p_rt_prep.add_argument("--with-package", action="store_true", help="同时返回 Writer Package")
    p_rt_prep.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")
    p_rt_prep.set_defaults(func=cmd_runtime)

    p_rt_gov = runtime_sub.add_parser("governed-context", help="获取受治理的上下文 (ContextManager authority)")
    p_rt_gov.add_argument("--chapter", type=int, required=True, help="章节号")
    p_rt_gov.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")
    p_rt_gov.set_defaults(func=cmd_runtime)

    p_rt_pkg = runtime_sub.add_parser("package", help="获取指定章节的 Writer Package")
    p_rt_pkg.add_argument("--chapter", type=int, required=True, help="章节号")
    p_rt_pkg.add_argument("--brief", default=None, help="Context Agent 提供的 Creative Brief 文本")
    p_rt_pkg.add_argument("--brief-file", default=None, help="Context Agent 提供的 Creative Brief 文件路径")
    p_rt_pkg.add_argument("--format", choices=["json", "text", "prompt"], default="json", help="输出格式")
    p_rt_pkg.set_defaults(func=cmd_runtime)

    p_rt_brief = runtime_sub.add_parser("attach-creative-brief", help="将 Context Agent 的 Creative Brief 封入 Native Writer Package")
    p_rt_brief.add_argument("--chapter", type=int, required=True, help="章节号")
    p_rt_brief.add_argument("--brief", default="", help="Creative Brief 文本")
    p_rt_brief.add_argument("--brief-file", default="", help="Creative Brief 文件路径")
    p_rt_brief.add_argument("--format", choices=["json", "text", "prompt"], default="json", help="输出格式")
    p_rt_brief.set_defaults(func=cmd_runtime)

    p_rt_ingest = runtime_sub.add_parser("ingest-draft", help="摄入正文草稿（draft != Canon）")
    p_rt_ingest.add_argument("--chapter", type=int, required=True, help="章节号")
    p_rt_ingest.add_argument("--package-fingerprint", required=True, help="Writer Package 指纹")
    p_rt_ingest.add_argument("--prose", default="", help="正文文本")
    p_rt_ingest.add_argument("--draft-file", default="", help="正文文件路径")
    p_rt_ingest.add_argument("--metadata-json", default="", help="执行元数据 JSON")
    p_rt_ingest.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")
    p_rt_ingest.set_defaults(func=cmd_runtime)

    p_rt_status = runtime_sub.add_parser("status", help="查询章节运行时状态")
    p_rt_status.add_argument("--chapter", type=int, required=True, help="章节号")
    p_rt_status.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")
    p_rt_status.set_defaults(func=cmd_runtime)

    p_rt_commit = runtime_sub.add_parser("commit", help="尝试提交章节至 Canon")
    p_rt_commit.add_argument("--chapter", type=int, required=True, help="章节号")
    p_rt_commit.add_argument("--draft-id", default="", help="草稿 ID（从 ingest-draft 获取）")
    p_rt_commit.add_argument("--review-result", default="", help="review_result JSON 路径")
    p_rt_commit.add_argument("--fulfillment-result", default="", help="fulfillment_result JSON 路径")
    p_rt_commit.add_argument("--disambiguation-result", default="", help="disambiguation_result JSON 路径")
    p_rt_commit.add_argument("--extraction-result", default="", help="extraction_result JSON 路径")
    p_rt_commit.add_argument("--reconciliation-result", default="", help="reconciliation_result JSON 路径")
    p_rt_commit.add_argument("--on-conflict", choices=["overwrite", "skip"], default=None, help="冲突策略")
    p_rt_commit.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")
    p_rt_commit.set_defaults(func=cmd_runtime)

    p_rt_publish = runtime_sub.add_parser("publish-draft", help="将已 accepted 的草稿发布至 正文/")
    p_rt_publish.add_argument("--chapter", type=int, required=True, help="章节号")
    p_rt_publish.add_argument("--draft-id", required=True, help="草稿 ID（必需，必须与 accepted commit 一致）")
    p_rt_publish.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")
    p_rt_publish.set_defaults(func=cmd_runtime)

    p_rt_retry = runtime_sub.add_parser("retry-projection", help="重试或重放指定章节的 projection")
    p_rt_retry.add_argument("--chapter", type=int, required=True, help="章节号")
    p_rt_retry.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")
    p_rt_retry.set_defaults(func=cmd_runtime)

    p_prose = sub.add_parser("prose", help="Prose Quality v2 润色与文风安全入口 (Issue #26)")
    prose_sub = p_prose.add_subparsers(dest="prose_action", required=True)

    p_prose_vt = prose_sub.add_parser("voice-target", help="获取章节正向文风锚 (Voice Target)")
    p_prose_vt.add_argument("--chapter", type=int, default=1, help="章节号")
    p_prose_vt.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")
    p_prose_vt.set_defaults(func=cmd_prose)

    p_prose_diag = prose_sub.add_parser("diagnose", help="定向诊断章节正文瑕疵 (Diagnose First)")
    p_prose_diag.add_argument("--file", default="", help="章节正文文件路径")
    p_prose_diag.add_argument("--text", default="", help="章节正文内容")
    p_prose_diag.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")
    p_prose_diag.set_defaults(func=cmd_prose)

    p_prose_diff = prose_sub.add_parser("diff-semantic", help="事实安全语义比对 (Fact-safe Semantic Diff)")
    p_prose_diff.add_argument("--before", default="", help="修改前正文内容")
    p_prose_diff.add_argument("--before-file", default="", help="修改前正文文件")
    p_prose_diff.add_argument("--after", default="", help="修改后正文内容")
    p_prose_diff.add_argument("--after-file", default="", help="修改后正文文件")
    p_prose_diff.add_argument("--judge-result", default="", help="Semantic Judge 裁决结果 JSON 字符串")
    p_prose_diff.add_argument("--judge-file", default="", help="Semantic Judge 裁决结果 JSON 文件路径")
    p_prose_diff.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")
    p_prose_diff.set_defaults(func=cmd_prose)

    p_prose_val = prose_sub.add_parser("validate", help="润色稿综合质检与回滚裁决")
    p_prose_val.add_argument("--before", default="", help="修改前正文内容")
    p_prose_val.add_argument("--before-file", default="", help="修改前正文文件")
    p_prose_val.add_argument("--after", default="", help="修改后正文内容")
    p_prose_val.add_argument("--after-file", default="", help="修改后正文文件")
    p_prose_val.add_argument("--chapter", type=int, default=1, help="章节号")
    p_prose_val.add_argument("--judge-result", default="", help="Semantic Judge 裁决结果 JSON 字符串")
    p_prose_val.add_argument("--judge-file", default="", help="Semantic Judge 裁决结果 JSON 文件路径")
    p_prose_val.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")
    p_prose_val.set_defaults(func=cmd_prose)

    p_migration = sub.add_parser("phase9-migration", help="Phase 9 migration preflight, dry run, and verified backup")
    migration_sub = p_migration.add_subparsers(dest="migration_action", required=True)
    p_migration_preflight = migration_sub.add_parser("preflight", help="read-only ownership and candidate preflight")
    p_migration_preflight.set_defaults(func=cmd_migration)
    p_migration_dry_run = migration_sub.add_parser("dry-run", help="read-only exact migration plan")
    p_migration_dry_run.add_argument("--report-digest", required=True)
    p_migration_dry_run.set_defaults(func=cmd_migration)
    p_migration_backup = migration_sub.add_parser("backup", help="create and verify the planned project backup")
    p_migration_backup.add_argument("--report-digest", required=True)
    p_migration_backup.set_defaults(func=cmd_migration)
    p_migration_execute = migration_sub.add_parser("migrate", help="explicitly enroll a project using a reviewed plan and verified backup")
    p_migration_execute.add_argument("--report-digest", required=True)
    p_migration_execute.add_argument("--plan-digest", required=True)
    p_migration_execute.add_argument("--backup-path", required=True)
    p_migration_execute.set_defaults(func=cmd_migration)
    p_migration_replace = migration_sub.add_parser("replace-generation", help="publish a same-semantic verified generation for recovery")
    p_migration_replace.add_argument("--generation-id", required=True)
    p_migration_replace.set_defaults(func=cmd_migration)
    p_migration_restore = migration_sub.add_parser("restore-layout", help="restore only verified mutable overlay layout after exact conflict review")
    p_migration_restore.add_argument("--backup-path", required=True)
    p_migration_restore.add_argument("--overlay-sha256", required=True)
    p_migration_restore.add_argument("--semantic-activation-id", required=True)
    p_migration_restore.add_argument("--effective-history-digest", required=True)
    p_migration_restore.set_defaults(func=cmd_migration)

    p_user_report = sub.add_parser("user-report", help="渲染作者友好的最终报告")
    p_user_report.add_argument("--stage", choices=["init", "plan", "write", "review"], required=True, help="报告阶段")
    p_user_report.add_argument("--chapter", type=int, default=None, help="目标章节号")
    p_user_report.add_argument("--volume", type=int, default=None, help="目标卷号")
    p_user_report.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    p_user_report.set_defaults(func=cmd_user_report)

    p_run_ledger = sub.add_parser("run-ledger", help="记录或查询写章断点续跑状态")
    run_ledger_sub = p_run_ledger.add_subparsers(dest="ledger_action", required=True)
    p_record_write_step = run_ledger_sub.add_parser("record-write-step", help="记录写章步骤状态")
    p_record_write_step.add_argument("--chapter", type=int, required=True, help="目标章节号")
    p_record_write_step.add_argument("--step", choices=["draft", "review", "data", "commit", "projection", "backup"], required=True)
    p_record_write_step.add_argument("--status", required=True)
    p_record_write_step.add_argument("--mode", default="default")
    p_record_write_step.add_argument("--inputs-json", default="{}")
    p_record_write_step.add_argument("--outputs-json", default="{}")
    p_record_write_step.add_argument("--problems-json", default="[]")
    p_record_write_step.add_argument("--auto-handled-json", default="[]")
    p_record_write_step.add_argument("--duration-ms", type=int, default=0)
    p_record_write_step.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")
    p_record_write_step.set_defaults(func=cmd_run_ledger)
    p_write_resume = run_ledger_sub.add_parser("write-resume", help="输出写章断点续跑建议")
    p_write_resume.add_argument("--chapter", type=int, required=True, help="目标章节号")
    p_write_resume.add_argument("--mode", default="default", help="写章模式")
    p_write_resume.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")
    p_write_resume.set_defaults(func=cmd_run_ledger)

    p_run_log = sub.add_parser("run-log", help="写入脱敏运行日志")
    p_run_log.add_argument("--event", required=True, help="事件名")
    p_run_log.add_argument("--payload-json", default="{}", help="要写入日志的 JSON 对象")
    p_run_log.add_argument("--append", action="store_true", help="追加而不是覆盖 run_last.log")
    p_run_log.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")
    p_run_log.set_defaults(func=cmd_run_log)

    p_use = sub.add_parser("use", help="绑定当前工作区使用的书项目（写入指针/registry）")
    p_use.add_argument("project_root", help="书项目根目录（必须包含 .webnovel/state.json）")
    p_use.add_argument("--workspace-root", help="工作区根目录（可选；默认由运行环境推断）")
    p_use.set_defaults(func=cmd_use)

    craft_parser = sub.add_parser("story-craft", help="Story craft operations")
    craft_parser.add_argument("story_craft_action", choices=[
        "init-volume-beat", "fill-beat", "check-volume",
        "init-forechains", "init-locks", "set-chapter-meta",
    ])
    craft_parser.add_argument("--volume", type=int)
    craft_parser.add_argument("--total-chapters", type=int)
    craft_parser.add_argument("--beat-name")
    craft_parser.add_argument("--chapter", type=int)
    craft_parser.add_argument("--notes")
    # set-chapter-meta per-field arguments
    craft_parser.add_argument("--beat-position")
    craft_parser.add_argument("--hook-type")
    craft_parser.add_argument("--scene-goal")
    craft_parser.add_argument("--scene-conflict")
    craft_parser.add_argument("--scene-setback")
    craft_parser.add_argument("--scene-resolution")
    craft_parser.add_argument("--sequel-reaction")
    craft_parser.add_argument("--sequel-dilemma")
    craft_parser.add_argument("--sequel-decision")
    craft_parser.set_defaults(func=cmd_story_craft)

    # Pass-through to data modules
    p_index = sub.add_parser("index", help="转发到 index_manager")
    p_index.add_argument("args", nargs=argparse.REMAINDER)

    p_state = sub.add_parser("state", help="转发到 state_manager")
    p_state.add_argument("args", nargs=argparse.REMAINDER)

    p_rag = sub.add_parser("rag", help="转发到 rag_adapter")
    p_rag.add_argument("args", nargs=argparse.REMAINDER)

    p_style = sub.add_parser("style", help="转发到 style_sampler")
    p_style.add_argument("args", nargs=argparse.REMAINDER)

    p_entity = sub.add_parser("entity", help="转发到 entity_linker")
    p_entity.add_argument("args", nargs=argparse.REMAINDER)

    p_context = sub.add_parser("context", help="转发到 context_manager")
    p_context.add_argument("args", nargs=argparse.REMAINDER)

    p_memory = sub.add_parser("memory", help="转发到 memory.store")
    p_memory.add_argument("args", nargs=argparse.REMAINDER)

    p_migrate = sub.add_parser("migrate", help="转发到 migrate_state_to_sqlite")
    p_migrate.add_argument("args", nargs=argparse.REMAINDER)

    # Pass-through to scripts
    p_status = sub.add_parser("status", help="转发到 status_reporter.py")
    p_status.add_argument("args", nargs=argparse.REMAINDER)

    p_update_state = sub.add_parser("update-state", help="转发到 update_state.py")
    p_update_state.add_argument("args", nargs=argparse.REMAINDER)

    p_backup = sub.add_parser("backup", help="转发到 backup_manager.py")
    p_backup.add_argument("args", nargs=argparse.REMAINDER)

    p_archive = sub.add_parser("archive", help="转发到 archive_manager.py")
    p_archive.add_argument("args", nargs=argparse.REMAINDER)

    p_init = sub.add_parser("init", help="转发到 init_project.py（初始化项目）")
    p_init.add_argument("args", nargs=argparse.REMAINDER)

    p_extract_context = sub.add_parser("extract-context", help="转发到 extract_chapter_context.py")
    p_extract_context.add_argument("--chapter", type=int, required=True, help="目标章节号")
    p_extract_context.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")

    p_story_system = sub.add_parser("story-system", help="转发到 story_system.py")
    p_story_system.add_argument("args", nargs=argparse.REMAINDER)

    p_story_events = sub.add_parser("story-events", help="转发到 story_events.py")
    p_story_events.add_argument("--chapter", type=int, default=0, help="目标章节号")
    p_story_events.add_argument("--limit", type=int, default=200, help="查询条数")
    p_story_events.add_argument("--health", action="store_true", help="输出事件链健康信息")

    p_commit = sub.add_parser("chapter-commit", help="转发到 chapter_commit.py")
    p_commit.add_argument("--chapter", type=int, required=True, help="目标章节号")
    p_commit.add_argument("--review-result", default="", help="review_result JSON 文件")
    p_commit.add_argument("--fulfillment-result", default="", help="fulfillment_result JSON 文件")
    p_commit.add_argument("--disambiguation-result", default="", help="disambiguation_result JSON 文件")
    p_commit.add_argument("--extraction-result", default="", help="extraction_result JSON 文件")
    p_commit.add_argument("--reconciliation-result", default="", help="reconciliation_result JSON 文件")
    p_commit.add_argument("--chapter-file", default="", help="生成 reconciliation 时的最终正文文件")

    p_memory_contract = sub.add_parser("memory-contract", help="转发到 memory_cli.py")
    p_memory_contract.add_argument("args", nargs=argparse.REMAINDER)

    p_project_memory = sub.add_parser("project-memory", help="转发到 project_memory.py")
    p_project_memory.add_argument("args", nargs=argparse.REMAINDER)

    p_correction = sub.add_parser("correction", help="Phase 9 human-reviewed Canon correction workflow")
    p_correction.add_argument("args", nargs=argparse.REMAINDER)

    p_review_pipeline = sub.add_parser("review-pipeline", help="转发到 review_pipeline.py")
    p_review_pipeline.add_argument("--chapter", type=int, required=True, help="目标章节号")
    p_review_pipeline.add_argument("--review-results", required=True, help="reviewer 原始结果 JSON 文件")
    p_review_pipeline.add_argument("--metrics-out", default="", help="metrics 输出文件")
    p_review_pipeline.add_argument("--report-file", default="", help="审查报告路径")
    p_review_pipeline.add_argument("--save-metrics", action="store_true", help="直接写入 index.db")

    p_placeholder_scan = sub.add_parser("placeholder-scan", help="扫描大纲/设定集未补齐占位")
    p_placeholder_scan.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")

    p_master_outline_sync = sub.add_parser("master-outline-sync", help="当前卷规划完成后写回 V+1 最小总纲锚点")
    p_master_outline_sync.add_argument("--volume", type=int, required=True, help="当前已完成规划的卷号")
    p_master_outline_sync.add_argument("--writeback-file", default="", help="显式结构化写回 JSON")
    p_master_outline_sync.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")

    knowledge_parser = sub.add_parser("knowledge", help="时序知识查询")
    knowledge_sub = knowledge_parser.add_subparsers(dest="knowledge_action")

    qs_parser = knowledge_sub.add_parser("query-entity-state", help="查询实体在指定章节的状态")
    qs_parser.add_argument("--entity", required=True, help="实体 ID")
    qs_parser.add_argument("--at-chapter", type=int, required=True, help="目标章节号")

    qr_parser = knowledge_sub.add_parser("query-relationships", help="查询实体在指定章节的关系")
    qr_parser.add_argument("--entity", required=True, help="实体 ID")
    qr_parser.add_argument("--at-chapter", type=int, required=True, help="目标章节号")

    # 兼容：允许 `--project-root` 出现在任意位置（减少 agents/skills 拼命令的出错率）
    from .cli_args import normalize_global_project_root

    argv = normalize_global_project_root(sys.argv[1:])
    args, unknown_args = parser.parse_known_args(argv)

    # where/use 直接执行
    if hasattr(args, "func"):
        if unknown_args:
            parser.error(f"unrecognized arguments: {' '.join(unknown_args)}")
        code = int(args.func(args) or 0)
        raise SystemExit(code)

    tool = args.tool
    if unknown_args and tool not in PASSTHROUGH_TOOLS:
        parser.error(f"unrecognized arguments: {' '.join(unknown_args)}")

    rest = _passthrough_tail(argv, tool) if tool in PASSTHROUGH_TOOLS else list(getattr(args, "args", []) or [])
    # argparse.REMAINDER 可能以 `--` 开头占位，这里去掉
    if rest[:1] == ["--"]:
        rest = rest[1:]
    rest = _strip_project_root_args(rest)

    # init 是创建项目，不应该依赖/注入已存在 project_root
    if tool == "init":
        raise SystemExit(_run_script("init_project.py", rest))

    # 其余工具：统一解析 project_root 后前置给下游
    project_root = _resolve_root(args.project_root)
    forward_args = ["--project-root", str(project_root)]

    if tool == "index":
        raise SystemExit(_run_data_module("index_manager", [*forward_args, *rest]))
    if tool == "state":
        raise SystemExit(_run_data_module("state_manager", [*forward_args, *rest]))
    if tool == "rag":
        raise SystemExit(_run_data_module("rag_adapter", [*forward_args, *rest]))
    if tool == "style":
        raise SystemExit(_run_data_module("style_sampler", [*forward_args, *rest]))
    if tool == "entity":
        raise SystemExit(_run_data_module("entity_linker", [*forward_args, *rest]))
    if tool == "context":
        raise SystemExit(_run_data_module("context_manager", [*forward_args, *rest]))
    if tool == "memory":
        raise SystemExit(_run_data_module("memory.store", [*forward_args, *rest]))
    if tool == "correction":
        raise SystemExit(_run_data_module("canon_correction_workflow", [*forward_args, *rest]))
    if tool == "migrate":
        raise SystemExit(_run_data_module("migrate_state_to_sqlite", [*forward_args, *rest]))

    if tool == "status":
        raise SystemExit(_run_script("status_reporter.py", [*forward_args, *rest]))
    if tool == "update-state":
        raise SystemExit(_run_script("update_state.py", [*forward_args, *rest]))
    if tool == "backup":
        raise SystemExit(_run_script("backup_manager.py", [*forward_args, *rest]))
    if tool == "archive":
        raise SystemExit(_run_script("archive_manager.py", [*forward_args, *rest]))
    if tool == "extract-context":
        return_args = [*forward_args, "--chapter", str(args.chapter), "--format", str(args.format)]
        raise SystemExit(_run_script("extract_chapter_context.py", return_args))
    if tool == "story-system":
        raise SystemExit(_run_script("story_system.py", [*forward_args, *rest]))
    if tool == "story-events":
        return_args = [*forward_args, "--limit", str(args.limit)]
        if args.chapter:
            return_args.extend(["--chapter", str(args.chapter)])
        if args.health:
            return_args.append("--health")
        raise SystemExit(_run_script("story_events.py", return_args))
    if tool == "chapter-commit":
        return_args = [*forward_args, "--chapter", str(args.chapter)]
        if args.review_result:
            return_args.extend(["--review-result", str(args.review_result)])
        if args.fulfillment_result:
            return_args.extend(["--fulfillment-result", str(args.fulfillment_result)])
        if args.disambiguation_result:
            return_args.extend(["--disambiguation-result", str(args.disambiguation_result)])
        if args.extraction_result:
            return_args.extend(["--extraction-result", str(args.extraction_result)])
        if args.reconciliation_result:
            return_args.extend(["--reconciliation-result", str(args.reconciliation_result)])
        if args.chapter_file:
            return_args.extend(["--chapter-file", str(args.chapter_file)])
        raise SystemExit(_run_script("chapter_commit.py", return_args))
    if tool == "memory-contract":
        raise SystemExit(_run_script("memory_cli.py", [*forward_args, *rest]))
    if tool == "project-memory":
        raise SystemExit(_run_script("project_memory.py", [*forward_args, *rest]))
    if tool == "review-pipeline":
        return_args = [
            *forward_args,
            "--chapter", str(args.chapter),
            "--review-results", str(args.review_results),
        ]
        if args.metrics_out:
            return_args.extend(["--metrics-out", str(args.metrics_out)])
        if args.report_file:
            return_args.extend(["--report-file", str(args.report_file)])
        if args.save_metrics:
            return_args.append("--save-metrics")
        raise SystemExit(_run_script("review_pipeline.py", return_args))
    if tool == "placeholder-scan":
        raise SystemExit(_run_data_module("placeholder_scanner", [*forward_args, "--format", str(args.format)]))
    if tool == "master-outline-sync":
        return_args = [*forward_args, "--volume", str(args.volume), "--format", str(args.format)]
        if args.writeback_file:
            return_args.extend(["--writeback-file", str(args.writeback_file)])
        raise SystemExit(_run_script("update_master_outline.py", return_args))

    if tool == "knowledge":
        from .knowledge_query import KnowledgeQuery
        from .cli_output import print_success
        kq = KnowledgeQuery(project_root)
        if args.knowledge_action == "query-entity-state":
            result = kq.entity_state_at_chapter(args.entity, args.at_chapter)
            print_success(result, message="entity_state_at_chapter")
            raise SystemExit(0)
        elif args.knowledge_action == "query-relationships":
            result = kq.entity_relationships_at_chapter(args.entity, args.at_chapter)
            print_success(result, message="entity_relationships_at_chapter")
            raise SystemExit(0)

    raise SystemExit(2)


if __name__ == "__main__":
    main()
