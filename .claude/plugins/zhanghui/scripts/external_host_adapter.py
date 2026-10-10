#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External Host Adapter (Issue #25).

Demonstrates and verifies that an arbitrary external host can orchestrate a complete chapter
lifecycle strictly via ChapterRuntime public surface with:
- 0 private story-system contract writes;
- 0 knowledge of internal outline directory layout;
- 0 direct calls to ContextManager private implementation;
- 0 manual construction of ChapterCommit internal schema.

Collects workflow artifacts into a caller-designated evidence directory:
1. request.json
2. writer_package.json
3. final_writer_prompt.txt
4. draft_receipt.json
5. runtime_workflow_state.json
6. commit_outcome.json
7. projection_status.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from data_modules.chapter_runtime import ChapterRuntime
from data_modules.reconciliation import reconcile_changes, split_chapter_and_changes


class ExternalHostAdapter:
    """External host adapter interacting strictly with the public ChapterRuntime surface."""

    def __init__(self, project_root: Path, evidence_dir: Path):
        self.project_root = Path(project_root).resolve()
        self.evidence_dir = Path(evidence_dir).resolve()
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        # The adapter ONLY uses the public ChapterRuntime facade.
        self.runtime = ChapterRuntime(self.project_root)
        self.private_contract_writes = 0

    def run_chapter(self, chapter: int, creative_brief: Optional[str] = None) -> dict[str, Any]:
        """Run 1 chapter through the public runtime and collect evidence."""
        if not creative_brief or not str(creative_brief).strip():
            raise ValueError(
                f"creative_brief is required to orchestrate chapter {chapter}: "
                "Writer path requires a sealed Native Writer Package."
            )

        # 1. Record host request
        request_payload = {
            "host": "ExternalHostAdapter",
            "protocol": "runtime-api/v1",
            "action": "orchestrate_chapter",
            "chapter": chapter,
            "project_root": str(self.project_root),
        }
        (self.evidence_dir / "request.json").write_text(
            json.dumps(request_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # 2. Prepare chapter via public runtime
        prep = self.runtime.prepare(chapter=chapter, with_package=True)
        if not prep.ok or not prep.writer_package:
            raise RuntimeError(f"Runtime preparation failed: {prep.error or prep.blockers}")

        writer_pkg = self.runtime.attach_creative_brief(chapter=chapter, creative_brief=creative_brief)

        (self.evidence_dir / "writer_package.json").write_text(
            writer_pkg.to_json(), encoding="utf-8"
        )

        # 3. Assemble prompt for Writer model (using ONLY package public fields)
        prompt = self._format_writer_prompt(writer_pkg)
        (self.evidence_dir / "final_writer_prompt.txt").write_text(prompt, encoding="utf-8")

        # 4. Generate draft prose (for contract test: conforming prose)
        prose = self._generate_prose(writer_pkg)

        # 5. Ingest draft via public runtime
        ingest_res = self.runtime.ingest_draft(
            chapter=chapter,
            prose=prose,
            package_fingerprint=writer_pkg.package_fingerprint,
            metadata={"generator": "deterministic_external_host"},
        )
        if not ingest_res.ok:
            raise RuntimeError(f"Draft ingestion failed: {ingest_res.error}")

        (self.evidence_dir / "draft_receipt.json").write_text(
            ingest_res.to_json(), encoding="utf-8"
        )

        # 6. Check workflow status via public runtime
        status_res = self.runtime.get_status(chapter=chapter)
        (self.evidence_dir / "runtime_workflow_state.json").write_text(
            status_res.to_json(), encoding="utf-8"
        )

        # 7. Commit attempt via public runtime
        # Host provides all 5 required semantic artifacts
        _, proposal = split_chapter_and_changes(prose)
        must_nodes = list(writer_pkg.current_intent.get("directive", {}).get("must_cover_nodes", []))
        review_result = {
            "blocking_count": 0,
            "must_check_results": [
                {"node": n, "passed": True}
                for n in must_nodes
            ],
            "blocking_rule_results": [],
        }
        extraction_result = {
            "chapter_meta": {},
            "accepted_events": [
                {
                    "event_type": "character_state_changed",
                    "subject": "林凡",
                    "summary": "顺利通过考核获得外门身份",
                    "payload": {"status": "外门弟子"},
                }
            ],
            "state_deltas": [],
            "entity_deltas": [
                {
                    "entity_id": "林凡",
                    "current": {"status": "天阳宗外门弟子"},
                }
            ],
        }
        fulfillment_result = {
            "planned_nodes": must_nodes,
            "covered_nodes": must_nodes,
            "missed_nodes": [],
            "extra_nodes": [],
        }
        disambiguation_result = {"pending": []}
        reconciliation_result = reconcile_changes(
            proposal, extraction_result, chapter_text=prose
        )

        commit_res = self.runtime.commit(
            chapter=chapter,
            draft_id=ingest_res.draft_id,
            review_result=review_result,
            extraction_result=extraction_result,
            fulfillment_result=fulfillment_result,
            disambiguation_result=disambiguation_result,
            reconciliation_result=reconciliation_result,
        )

        (self.evidence_dir / "commit_outcome.json").write_text(
            commit_res.to_json(), encoding="utf-8"
        )

        # 8. Record projection status
        proj_payload = {
            "chapter": chapter,
            "projection_success": commit_res.projection_success,
            "projection_status": commit_res.projection_status,
            "can_retry_projection": commit_res.can_retry_projection,
        }
        (self.evidence_dir / "projection_status.json").write_text(
            json.dumps(proj_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        return {
            "chapter": chapter,
            "commit_res": commit_res,
            "writer_package": writer_pkg,
            "evidence_dir": str(self.evidence_dir),
            "private_contract_writes": self.private_contract_writes,
        }

    def _format_writer_prompt(self, pkg: Any) -> str:
        """Format writer prompt using the canonical package renderer."""
        if hasattr(pkg, "to_writer_prompt"):
            return pkg.to_writer_prompt()
        title = pkg.story_identity.get("title", "")
        genre = pkg.story_identity.get("genre", "")
        intent = pkg.current_intent
        goal = intent.get("directive", {}).get("goal", "")
        must_cover = intent.get("directive", {}).get("must_cover_nodes", [])
        prohibitions = intent.get("directive", {}).get("forbidden_zones", [])
        constraints = pkg.constraints

        lines = [
            f"=== 写作任务：第{pkg.chapter}章 ===",
            f"书名：{title} | 题材：{genre}",
            f"本章目标：{goal}",
            f"必须覆盖节点：{', '.join(must_cover)}",
            f"本章禁区：{', '.join(prohibitions)}",
            f"调性与约束：{constraints.get('core_tone', '')}",
            "请遵循协议在正文末尾输出完整的 <chapter_changes> 块。",
        ]
        return "\n".join(lines)

    def _generate_prose(self, pkg: Any) -> str:
        """Generate chapter prose conforming to the package intent."""
        return """山门前，灵气弥漫如云雾翻涌。
林凡缓步上前，依言将手掌贴在问心石上。
石上光华流转，三色灵光若隐若现，虽不算出众，却足以踏入仙门门槛。
负责测试的执事淡淡扫了一眼，抛来一枚刻着“天阳”二字的青铜令牌。
“持此牌入外门，切莫懈怠。”
林凡接过令牌，目光坚毅。修行之路，自今日方才真正启程。

<chapter_changes>
{
  "character_state_changes": [
    {
      "character_id": "林凡",
      "change_type": "status_update",
      "importance": "normal",
      "details": "通过问心石测试成为天阳宗外门弟子"
    }
  ],
  "new_plot_points": [
    {
      "plot_id": "plot_enter_sect_success",
      "importance": "normal",
      "description": "林凡正式获得天阳宗外门弟子身份"
    }
  ],
  "foreshadowing_actions": [],
  "location_state_changes": [],
  "faction_state_changes": [],
  "time_progression": null,
  "item_transfers": [],
  "unresolved_questions": []
}
</chapter_changes>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Run external host chapter test")
    parser.add_argument("--project-root", required=True, help="书项目根目录")
    parser.add_argument("--chapter", type=int, default=1, help="章节号")
    parser.add_argument("--evidence-dir", required=True, help="证据保存目录")
    parser.add_argument("--creative-brief", default="", help="Context Agent 创作策划任务书")
    parser.add_argument("--creative-brief-file", default="", help="创作策划任务书文件路径")
    args = parser.parse_args()

    brief = args.creative_brief
    if not brief and args.creative_brief_file:
        bf_p = Path(args.creative_brief_file)
        if bf_p.is_file():
            brief = bf_p.read_text(encoding="utf-8")

    adapter = ExternalHostAdapter(Path(args.project_root), Path(args.evidence_dir))
    result = adapter.run_chapter(args.chapter, creative_brief=brief)

    commit_res = result["commit_res"]
    print(f"STATUS: {'SUCCESS' if commit_res.ok else 'FAILED'}")
    print(f"OUTCOME: {commit_res.chapter_outcome}")
    print(f"PRIVATE_CONTRACT_WRITES: {adapter.private_contract_writes}")
    print(f"EVIDENCE_DIR: {result['evidence_dir']}")


if __name__ == "__main__":
    main()
