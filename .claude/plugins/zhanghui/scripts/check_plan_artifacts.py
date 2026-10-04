"""扫描 plan / init / review 重跑前需要检查的 .md artifact 集合。

返回 JSON：{volume, artifacts: [{path, last_modified}]}

用于让 3 个 SKILL.md (plan/init/review) 在重跑前显式感知文件存在状态。

注意：缺失文件不计入 artifacts 列表（仅存在的文件被列入）。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def _resolve_project_root(args_project_root: str | None) -> Path:
    if args_project_root:
        return Path(args_project_root).expanduser().resolve()
    return Path.cwd()


def _check_artifact(project_root: Path, outline_dir: Path, name: str) -> dict | None:
    path = outline_dir / name
    if not path.is_file():
        return None
    mtime = datetime.fromtimestamp(path.stat().st_mtime).isoformat()
    # Use path relative to project_root so output is project-local
    rel_path = path.relative_to(project_root)
    return {"path": str(rel_path), "last_modified": mtime}


def collect_plan_artifacts(project_root: Path, volume: int) -> dict:
    outline_dir = project_root / "大纲"
    names = [
        f"第{volume}卷-节拍表.md",
        f"第{volume}卷-时间线.md",
        f"第{volume}卷-详细大纲.md",
    ]
    artifacts = []
    for n in names:
        entry = _check_artifact(project_root, outline_dir, n)
        if entry is not None:
            artifacts.append(entry)
    return {"volume": volume, "artifacts": artifacts}


def main() -> int:
    parser = argparse.ArgumentParser(description="Check plan artifacts existence")
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--volume", type=int, required=True)
    args = parser.parse_args()
    root = _resolve_project_root(args.project_root)
    result = collect_plan_artifacts(root, args.volume)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())