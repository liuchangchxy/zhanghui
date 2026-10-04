# NOTICE — 来源与许可

本项目名为 **章回（Zhanghui）**，是 [webnovel-writer](https://github.com/lingfengQAQ/webnovel-writer)
的个人 fork，遵循上游的 **GPL-3.0** 许可（见 `LICENSE`）。

## 上游

| 项目 | 许可 | 关系 |
|---|---|---|
| [lingfengQAQ/webnovel-writer](https://github.com/lingfengQAQ/webnovel-writer) | GPL-3.0 | 本仓库的 fork 基座 |

上游 GPL-3.0 代码位于 `.claude/plugins/webnovel-writer_chang/`，包含其 `vendor/uv/`
（uv 二进制，随上游一同分发；`hooks/install_python_deps.py` 依赖它自动安装 Python 依赖）。

## 已吸收的第三方成果

开发过程中参考并吸收了以下项目的设计或代码，在此致谢：

| 来源 | 许可 | 吸收内容 |
|---|---|---|
| oh-story-claudecode | MIT | `scripts/_shared/check-ai-patterns.js`（AI 句式检测）；`scripts/consistency/` 下的事务模式与派生视图设计（`core/runner.py`、`patches/p6_reader_contract.py`、`patches/p7_derived_views.py`）；`scripts/tracking_query.py` 的端口设计 |
| novel-creator-skill | 快照中无 LICENSE 文件；`text_humanizer.py` 文件头注释声明为 MIT | `scripts/_shared/text_humanizer.py`（AI 词 / 弱化副词检测），已 fork 改造 |
| tianming-novel-ai-writer | 快照中无 LICENSE 文件 | 仅借鉴 CHANGES 字段设计思路（`scripts/changes_gate.py`），**未复制代码** |

> 注：`novel-creator-skill` 与 `tianming-novel-ai-writer` 的本地快照中未找到 LICENSE 文件。
> 前者按代码内注释记为 MIT；后者仅借鉴字段设计这一不受版权保护的思路。
> 若权利人认为此处标注有误，请提 issue，我会立即修正或移除相关代码。

## 未纳入版本管理的参考库

`references/` 目录（2.1 GB，含 20 余个第三方项目的完整克隆）**仅用于本地调研，
已在 `.gitignore` 中排除，不随本仓库分发**。清单见 `references/INDEX.md`。
