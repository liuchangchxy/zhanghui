# webnovel-chart-scan

扫起点/番茄/纵横/七猫/刺猬猫五个网文平台分类榜单的 Claude Code skill。

## 快速开始

```bash
cd /Users/chang/Desktop/zhanghui/.claude/skills/webnovel-chart-scan
pip install -e ".[fanqie,dev]"
playwright install chromium  # 仅番茄需要

# 跑一次扫描
cd /path/to/your-novel-project
python /Users/chang/Desktop/zhanghui/.claude/skills/webnovel-chart-scan/scripts/scan.py \
    --platform=qidian,fanqie \
    --category=玄幻,都市 \
    --top=30 \
    --period=weekly
```

输出落在 `./chart-scan/`。

## 架构

详见 `docs/superpowers/specs/2026-08-12-webnovel-chart-scan-design.md`。

## 开发

```bash
pytest tests/ -v
pytest tests/ --cov=scripts --cov-report=term-missing
```

## License

个人自用，未明确开源协议。vendored 上游代码遵循各自协议（见 `references/upstream-survey.md`）。