# KNOWN_ISSUES — 项目已知缺陷与债务

**生成日期**：2026-08-11
**依据**：第三+四+五轮对抗式审查共 182 条 finding，扣除已修复后剩余 **~110 条**仍未处理
**目的**：把"知道有问题、修不完"的债务文档化，避免新用户 / 新开发者重复踩坑

---

## 阅读须知

- **本项目是个人自用工具**，不发出去，无法律风险考虑（LICENSE / GPL 传染已降级）
- 标注 **🔴 必修** = 数据丢失 / 流程阻断 / 安全风险
- 标注 **🟡 重要** = 影响日常使用体验
- 标注 **🟢 清理** = 代码质量，长期治理
- 标注 **🚧 已规避** = 已找到 workaround，无需修代码

---

## P0 已修复清单（避免误以为未修）

| ID | 修复 | Commit/Date |
|---|---|---|
| C-R4-1 | bash 智能引号 | 2026-08-11 |
| C-R4-2 | plugin ↔ 本地 SKILL.md 同步 | 2026-08-11 |
| C-R4-3 | style_fingerprint.py 部署 | 2026-08-11 |
| C-R4-4 | --rule R4b 大小写兼容 | 2026-08-11 |
| C-R4-5 | 双副本 md5 一致 | 2026-08-11 |
| C-R4-6/7/8/9/10/11/12 | style_fingerprint.py 8 项 CRITICAL | 2026-08-11 |
| H-R4-1 | state.json DoS 防护（MAX_STATE_BYTES=5MB） | 2026-08-11 |
| H-R4-2 | _resolve_int parity | 2026-08-11 |
| H-R4-14/15/16 | 模板路径 + 个人语料 + 宪法落库 | 2026-08-11 |
| 第三轮 C1-C8 | changes_gate.py 主要 CRITICAL | 之前 commit |
| M-C1 | .claude/plugins/ gitignore 注释化 | 2026-08-11 |
| M-H6 | README 软链命令加 `-n` | 2026-08-11 |
| M-C4 | webnovel-style-profile skill 复制 | 2026-08-11 |
| M-C5 | workflow → run-ledger | 2026-08-11 |
| M-C7 | normalize-punctuation.js banner | 2026-08-11 |
| M-C8 | plugin.json 加 deconstruction-agent | 2026-08-11 |

---

## 🔴 必修（剩余 ~12 条，2026-08-11 B 批 agent 处理中）

### 数据安全类（依赖 B 批 agent 完成）

- **M-H17**：`style_fingerprint.py` / `summary_projection_writer.py` / `review_pipeline.py` 非原子写入 → 改用 `atomic_write_json`
- **M-H18**：`index.db` 无显式事务 → `_get_conn` 加 BEGIN/COMMIT/ROLLBACK + WAL 模式
- **M-H21**：`atomic_write_json` 默认 backup 用时间戳而非 `.bak` 覆盖
- **M-H26**：`filelock` fallback 到 SQLite 锁

### 配置 / 架构类

- **M-H8**：CLAUDE_PLUGIN_ROOT 在项目级 symlink 安装时未设 → Step 0 直接 abort
  - 状态：webnovel-write/skill.md 已部分加 fallback（CLAUDE_PROJECT_DIR）但需要重新跑端到端验证
  - 影响：新 clone 项目跑 webnovel-init 时若 CLAUDE_PROJECT_DIR 未 set 仍会 abort

### 第三轮残留 HIGH（H1-H11 中未修）

- **H2**：`changes_gate.py:474` R3 对 `from_holder`/`to_holder` 误报
- **H3**：README:42 软链命令路径错 → M-H6 已修（README.md:42）
- **H5**：`webnovel-write/skill.md:170` Step 1.5 已废除但 resume 仍按 Step 1.5 处理
- **H6**：`webnovel-resume/skill.md` 整条恢复路径基于不存在的子命令 → M-C5 已修（workflow → run-ledger）
- **H8**：`test_cli_edge_cases.py:185` 假绿 → 同 H7（一起处理）
- **H9**：`test_cli_edge_cases.py:61` 断言被 `if stdout.strip()` 守卫
- **H10**：README:35 软链安装有 5 个未提的暗坑 → M-H6 已部分修
- **H11**：CLAUDE_PLUGIN_ROOT 在项目级 symlink 安装时未设 → M-H8

---

## 🟡 重要（剩余 ~30 条 MEDIUM）

### 配置参数类

- **MED-1**：`MAX_TRUST_DELTA=30` 是 magic number，无注释
- **MED-2**：`ITEM_STATE_TRANSITIONS` 硬编码，destroyed 阻挡"假死复活"
- **MED-3**：`repair_changes_json` 的"宽容修复"用户不知道

### UX/工作流类

- **MED-4**：Step 3 review_metrics 落库 vs Step 4 polish 输出无关联
- **MED-5**：Step 4.5/4.6 用 CLAUDE_PROJECT_DIR 拼接，但 PROJECT_ROOT 在嵌套项目下不同
- **MED-6**：Step 5 data-agent 与 chapter-commit 职责未互锁
- **MED-7**：fast-write 跳 Step 1 cat protocol，易漏 CHANGES 块
- **MED-8**：`repair_changes_json` 静默吞字符串值内逗号（line 107）
- **MED-9**：单引号转换正则误伤 `it's`/`don't`（line 104）
- **MED-10**：`---CHANGES---` 容器正则会被字符串内的 `---` 提前截断（line 35）
- **MED-11**：末尾 JSON 兜底在 CRLF 文件失效（line 88）
- **MED-12**：「取最后一个块」混用容器时选错（line 82）

### R 规则语义类

- **MED-13**：`involved_characters` 写字符串时被逐字符迭代产生垃圾 R3 误报（line 459）
- **MED-14**：R3 `check_ref` 对非字符串引用静默放行（line 441）
- **MED-15**：`time_progression` 非 dict 非 null 时 R1+R2 都有盲区（line 266）
- **MED-16**：R4 依赖不存在的 `foreshadowing` 表，注释把责任推给 R4（line 493）→ 与 changes-protocol 设计一致
- **MED-17**：`--strict` 把"未初始化项目"判失败（line 935）
- **MED-18**：`--rule R0` 把全部规则过滤掉（line 929）

### 跨 skill 一致性类

- **MED-19**：webnovel-init 引用 `templates/写作宪法.md` 后未在"执行生成"段定义"创作宪法"如何被写到 state.json
- **MED-20**：shuangwen 触发条件表述模糊，且不同文件 canonical 列表不一致
- **MED-21**：init "Step 5/Step 6 注入" 个人语料与 write skill 实际注入位置（Step 1 / Step 2A）不匹配

### 数据安全 / 跨项目类（部分 B 批 agent 处理）

- **MED-22**：B1 `--project-root` 跨项目污染主路径未全部修
- **MED-23**：B2 `--project-root` 误指向路径回退到 last_used_project_root
- **MED-24**：B4 `webnovel-current-project` 指针文件可被任意进程写入
- **MED-25**：C1 `state.json.bak` 单一文件覆盖式
- **MED-26**：C4 `backups/` 目录只保留 10 个快照
- **MED-27**：D1 `--chapter-file` 接受任意路径（包括 `/etc/passwd`）
- **MED-28**：D2 `--db` 接受任意路径
- **MED-29**：D3 LLM 写的 CHANGES JSON 解析没有 schema 严格校验
- **MED-30**：D6 `security_utils.create_secure_directory` 在 Windows 上放弃权限控制
- **MED-31**：D7 `--chapter-file` 接受远程 URL / UNC 路径
- **MED-32**：E2 `index.db` 没有 WAL 模式（B 批处理）

### 反 AI 写作脚本协作类

- **MED-33**：C2 text_humanizer vs check-ai-patterns 规则重叠/盲区无仲裁
- **MED-34**：C3 4 个脚本输入格式不一致（单文件 vs 多文件、JSON vs 文本）
- **MED-35**：C4 失败模式差异
- **MED-36**：C6 `changes_gate.py` 与其他三个脚本无任何代码共享（Python+Node.js 不能 import）
- **MED-37**：H15 text_humanizer 对非 UTF-8 输入假阴性 ok:true
- **MED-38**：H16 text_humanizer vs check-ai-patterns 仲裁规则缺失

### 配置层 / 性能 / license 类

- **MED-39**：M-A2 settings.json 无 `permissions.allow` → 每次写章节触发 8+ permission prompts
- **MED-40**：M-A3 完全缺失 `model` 字段 → 长任务无声升级到 opus
- **MED-41**：M-A4 完全缺失项目级 `hooks` 字段
- **MED-42**：M-B2 hooks timeout 5s 在 Windows 杀软下易 fail-open
- **MED-43**：M-B4 `guard_runtime_write.py` 路径归一化在 Cygwin/MSYS 边界有 bug
- **MED-44**：M-E1 filelock advisory 跨进程不可靠
- **MED-45**：M-M7 性能 / token 预算：Step 0-6 每章 25-50k tokens；长篇 review_metrics 累计可能超过 100MB

### 安装 / 仓库目录类

- **MED-46**：M3-1 `ai-webnovel-repos/` 占 1.6GB、含 25+ 嵌套 `.git`，22/26 仓库零代码引用
- **MED-47**：M3-2 `.claude/sources/webnovel-writer-upstream/` 占 8.5MB
- **MED-48**：M3-4 `.pytest_cache/`、`.claude/plugins/.tmp/pytest/` 等临时产物在 `.gitignore` 漏配
- **MED-49**：M-M8 文档示例硬编码 Windows 路径 `D:\wk\xiaoshuo\凡人资本论`
- **MED-50**：M-M10 `tracking_query.py` 在 `.claude/scripts/` 但全项目 0 处调用
- **MED-51**：M-M17 Skill 命名不一致（`skill.md` vs `SKILL.md`）
- **MED-52**：M-M18 `.claude/.webnovel-current-project` 是项目级状态泄漏

### 元分析（系统性）

- **MED-53**：M-H1 智能引号是全仓爆发（104 个文件仍含）
- **MED-54**：M-H2 三层 `.claude/` 路径系统本身是坏设计
- **MED-55**：M-H3 CHANGES 协议无 schema 演进路径
- **MED-56**：M-H4 CHANGES 协议被破坏性"修复"（角色对话里写 JSON 会被误改成协议声明）
- **MED-57**：M-M1 大小写/拼写错配同类未爆，无 lint 拦截
- **MED-58**：M-M2 format-string 残留（`{genre}` / `{character}` 占位符解释不一致）

### 反 AI 工具栈

- **MED-59**：M-M14 有 timing 但无 token 计量、无章节成本面板
- **MED-60**：M-M15 `webnovel-doctor` skill 存在但 README 没告诉用户
- **MED-61**：M-M16 `guard_runtime_write.py` hook 误伤场景未在文档说明

### 第三轮 MEDIUM 中未修

- **MED-62**：R3 `check_ref` 对非字符串引用静默放行（line 441）→ 同 MED-14
- **MED-63**：解析鲁棒性 5 条 + R 规则语义 6 条 + 测试覆盖 4 条 + 配置参数 3 条 + UX 工作流 4 条 + 文档 3 条 = 25 条，详见 `docs/对抗式审查-第三轮-多维并行+对抗验证.md:180-219`

---

## 🟢 清理（剩余 ~15 条 LOW）

### 代码质量

- **LOW-1**：`ITEM_STATE_TRANSITIONS` 自环不对称
- **LOW-2**：`_extract_chapter_number` `or 0` 把缺失态吞成 0，R8 静默失效
- **LOW-3**：`extract_chapter_entities` 一旦开启就是假阳性机器（已默认禁用）
- **LOW-4**：`_extract_chapter_number` 不识别序章/楔子/番外/卷末/第一章（中文数字）
- **LOW-5**：db 校验与使用之间有 TOCTOU 窗口（changes_gate.py:348 行二次 connect）
- **LOW-6**：测试 `run_gate` 的 `returncode in (0,1)` 无法区分失败 vs 崩溃
- **LOW-7**：`conftest.py` 的 `sample_chapter` / `valid_changes_xml` 是死代码
- **LOW-8**：resume 的"Step 6 中断（$0.15 双章审查）"措辞错位
- **LOW-9**：webnovel-write step-id 白名单只列 7 个但实际定义 11 个
- **LOW-10**：`test_chapter_file_truncated_utf8` 不测合法前缀+非法后缀
- **LOW-11**：`test_r05_fails_with_negative_delta_exceeded` 不验消息内容

### style_fingerprint 代码质量（修复后残留）

- **LOW-12**：`SPEECH_VERBS` 列表有 4 个重复（"答道"×3、"问道"×2、"答"×2、"喊"×2）
- **LOW-13**：CLI `--compare A B` 接受相同章号（A=B）不报错
- **LOW-14**：死代码 `total_chars = sum(...)` 计算结果从未使用
- **LOW-15**：行 419-422 `_severity_for` 用 `>= threshold` 而非 `>`

---

## 🚧 已规避（无需修代码）

| ID | 规避方案 |
|---|---|
| M-C6 | 混合架构 drift 风险：自用下本地 fork 在被项目级 skill 调用就够用，plugin 端 v6.2.1 不动 |
| M-C2/M-C3 | 不发出去，纯自用，无法律风险 |
| M-H11 | v6.2.1 vs v5.5.4 版本错位：自用项目直接 vendor v6.2.1 |
| M-C7 替代方案 | 用 `webnovel-deslop-check` 的 polish 流程替代 `normalize-punctuation.js` |
| M-M5 | 跨项目数据隔离：自用单项目，无需多项目切换 |
| M-M6 | 备份膨胀：自用项目写 200 章 < 10 年，10 快照够用 |

---

## 修复优先级（按"效果最好"原则）

**A 批已完成**：P0 全部 5 + P1 的 M-C7/M-C8
**B 批进行中**：4 个最关键的数据安全
**C 批已完成**：本文档

**剩余 MEDIUM 处理建议**（按 ROI 排序）：
1. **MED-39**：加 permissions.allow（5 分钟，省 8+ permission prompts/章）
2. **MED-21**：init/write 个人语料注入位置对齐（15 分钟）
3. **MED-53**：全仓智能引号批量清（30 分钟，可写脚本）
4. **MED-51**：skill.md → SKILL.md 统一命名（20 分钟，git mv）
5. **MED-33/34**：text_humanizer ↔ check-ai-patterns 仲裁 + 输入格式统一（1-2 小时）

**剩余 LOW**：清理期处理或不处理（影响小）

---

## 怎么用本文档

- 新 bug 报告 → 先查本文档是否已知 → 已在则用 workaround；不在则排查
- 提交 PR → 先查本文档确认是否修复了某项；若修复则更新本文档
- 半年回顾 → 根据 P0 / P1 / P2 节奏决定批量修复优先级

## 相关文档

- `对抗式审查-第三轮-多维并行+对抗验证.md`：完整 5 轮审查记录（182 条 finding）
- `集成情况盘点报告.md`：26 个外部仓库的集成情况
- `docs/superpowers/specs/` 与 `docs/superpowers/plans/`：fork 设计文档