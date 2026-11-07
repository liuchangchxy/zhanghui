# 文学减法编辑正式集成 — 短 E2E 验收报告

- 日期：2026-11-07
- 分支：`feat/literary-finalizer-integration`
- 基线：`a41ac35`
- 判定：**PARTIAL**（核心机制已接入并安全回退；一个清晰的局部阻塞导致 3/3 真实章节最终正文未获得文学增益）
- 合并条件：**未满足**（安全的一半成立，增益的一半未在正式最终正文中成立）

---

## 1. 一句话结论

文学减法编辑已经以**很小的代码面**接入正式 `webnovel-write` 的 Step 2B，成为唯一的文学编辑环节；
确定性护栏、既有语义 Judge、失败回退 Writer 原稿都能在真实章节上正确工作。
但在 3 个真实章节上，**编辑模型持续删掉用户明确保护的承载句**（潜台词动作、短情绪落点、因果连接、
唯一线索/归属、首次性事实），因此 3/3 被语义门禁拒绝、最终正文全部回退 Writer raw。
候选稿在盲评中以 **36/36 全票**优于 Writer raw，说明“文学增益”存在且方向正确，但它没有进入最终正文。

---

## 2. 修改文件

| 文件 | 类型 | 内容 |
|---|---|---|
| `.claude/plugins/zhanghui/scripts/data_modules/literary_finalizer.py` | 新增 450 行 | 五原则/三护栏/保护清单、prompt 组装、确定性校验、语义门禁复用、失败回退 |
| `.claude/plugins/zhanghui/scripts/data_modules/webnovel.py` | +226 行 | `prose literary-finalize-prompt`、`prose literary-finalize-validate` |
| `.claude/plugins/zhanghui/skills/webnovel-write/SKILL.md` | +160/−84 | Step 2B 改为文学减法定稿；Step 4 删除整章文学润色、保留定向修复；边界与回退规则 |
| `.claude/plugins/zhanghui/skills/webnovel-fast-write/SKILL.md` | +16/−? | 快车道跳过文学定稿与定向润色 |
| `tests/unit/test_literary_finalizer.py` | 新增 264 行 | 8 个机制测试 |
| `study/audits/2026-11-07-literary-finalizer-integration.md` | 新增 | 决策记录 |
| `experiments/literary-finalizer-integration-20261107/` | 新增 | 短 E2E 输入、脚本、输出、盲评、内容检查 |

未新增 Agent、Router、数据库、状态系统、文学评分系统或语义分类框架。

---

## 3. 正式流程修改前后对照

**修改前**

```
Step 2A 草稿
  → Step 2B 文风适配（rewrite-only：只改措辞，不增删动作/线索） + prose validate
  → Step 3 Reviewer（8 维）
  → Step 4 诊断驱动整章润色（加载 polish-guide.md）+ 事实修复
  → Step 4.5 changes gate → Step 4.6 anti-slop → Step 5/6
```

同一正文实际上要经过 **两轮文学后处理**（2B 改写 + 4 整章润色），而且 2B 的 rewrite-only
从定义上无法减少作者解释。

**修改后**

```
Step 2A 草稿
  → Step 2B 文学减法定稿（唯一文学编辑环节）
       确定性护栏：正文 ≥90% / 数字·日期·编号按值集合 / 受保护术语
       语义门禁：复用现有宿主 Judge + compare_semantic_facts
       仅 accepted=true 且 STYLE_ONLY_SAFE 才覆盖；否则回退 Writer raw，不重试
  → Step 3 Reviewer（不扩权，只判事实/Canon/连贯/真剧情问题）
  → Step 4 定向修复（仅 Reviewer 定位的问题 + 事实纠错；不再整章润色）
  → Step 4.5 → Step 4.6 → Step 5/6
```

**结果：文学后处理从两轮降为一轮；`--fast` / `--minimal` 为 0 轮。**

---

## 4. Step 2B / Step 4 最终处理方式

| 原职责 | 处理 | 理由 |
|---|---|---|
| Step 2B 文风适配（rewrite-only） | **替换**为文学减法定稿 | rewrite-only 无法改善场景张力或减少作者解释；held-out 已证明减法有效 |
| Step 2B 的 `prose validate` | **合并**进 `literary-finalize-validate` | 同一对 before/after 只跑一次语义比对 |
| Step 4 加载 `polish-guide.md`、诊断驱动整章润色 | **删除** | 与 2B 重复，且会导致同一正文连续多次文学润色 |
| Step 4 Reviewer 问题路由 / `revise plan/apply/verify` | **保留** | Reviewer 定位的问题仍需最小修复 |
| Step 4 事实纠错 / `PENDING_REREVIEW` 重审 | **保留** | 独立、必要，不属于文学润色 |
| Step 4 `typesetting.md` | **保留** | 移动端排版是独立职责 |
| Step 3 Reviewer | **不扩权** | Reviewer 判“是否有真问题”；Finalizer 判“怎么写更好” |
| `--fast` / `--minimal` 跳过 2B | **保留** | 快车道不做文学定稿；Step 4 也不再补做 |

没有“同一正文跑三次文学润色”的路径。

---

## 5. 测试结果

```
python3 -m pytest tests/unit/test_literary_finalizer.py -q
8 passed in 0.18s

python3 -m pytest tests/unit -q
1 failed, 386 passed in 8.34s
```

8 个新测试覆盖用户要求的最小集合：

1. 定稿 prompt 可调用，且携带冻结的五原则/三护栏与纯正文 source；
2. 低于 90% 的候选被拒绝，Writer raw 保留；
3. 日期被改写时拒绝，改写值不会进入最终正文；
4. 新增数字被当作新事实拒绝；
5. 语义门禁拒绝时返回**含 `<chapter_changes>` 的完整 Writer raw**；
6. 仅当门禁通过时返回候选；
7. 空 source 被拒绝；
8. Skill 结构断言：只有一个文学定稿环节，Step 4 不再润色。

唯一失败是**既有**用例
`tests/unit/test_stage2_repair_regression.py::test_canonical_cli_invocations_are_identical_across_skills`：
它比对 skills 与未跟踪的 `references/draft-review-lifecycle.md`，后者缺少 `--enforce-auto-budget`。
与本轮改动无关（可用 `git diff a41ac35` 确认 reviewer 命令未变），未修改。

---

## 6. 短 E2E

输入是真实 Writer 草稿（不是本轮重新生成），来自
`zhanghui-benchmark/runs/clean-e2e-jarvis-vs-zhanghui-2026-10-29/e2e/zhanghui/`：

| 章 | 类型 | 原始正文字数 | 候选长度比 | 确定性护栏 | 语义门禁 | 最终 |
|---|---|---:|---:|---|---|---|
| ch03 | 信息/推理密集 | 3413 | 91.53% | 通过 | 拒绝（2 处） | Writer raw |
| ch05 | 常规对话/人物冲突 | 2948 | 90.66% | 通过 | 拒绝（6 处） | Writer raw |
| ch07 | 明确章末钩子 | 2386 | 93.90% | 通过 | 拒绝（4 处） | Writer raw |

每章只生成一次；没有重试、没有换 prompt、没有用 Step 4 补做文学润色。
判定与回退记录见 `results/run_records.json`、`outputs/chNN_gate.json`。

---

## 7. 文学盲评（诊断性质）

盲评对象：**Writer raw（A）vs 被门禁拒绝的候选稿（B）**。
因为 B 不是最终正文，这组结果**不能**证明正式流程产出了增益；它只用于确认编辑方向本身是否有效。

设置：2 个评审（`codex/gpt-6.1-terra`、Gemini 3.8 Flash）× 3 章 × 正反两次位置 × 6 维。

| 维度 | A（Writer raw） | B（候选） | SPLIT | TIE |
|---|---:|---:|---:|---:|
| OVERALL_PREFERENCE | 0 | **6** | 0 | 0 |
| READING_APPEAL | 0 | **6** | 0 | 0 |
| LOW_AUTHOR_EXPLANATION | 0 | **6** | 0 | 0 |
| SENTENCE_NATURALNESS | 0 | **6** | 0 | 0 |
| SCENE_IMMERSION | 0 | **6** | 0 | 0 |
| SUBTEXT | 0 | **6** | 0 | 0 |

- 章级 OVERALL：strict B **3/3**，leaning B **3/3**。
- 位置反转后无 SPLIT、无 TIE，两个不同模型家族结论一致。

评审引用的具体现象（原文）：
- ch03：“RIGHT 删去‘这个由头不算牵强’‘韩策说的不是问句’等解释，让对白和事实本身承担更多意思。”
- ch05：“LEFT 额外解释‘不问比问更压人’、纸与网络记录的区别……RIGHT 将这些判断更多留给读者。”
- ch07：“RIGHT 保留了钥匙交接时的迟疑和出门后的空口袋，删去 LEFT 对交易风险的重复总结。”

即：**减法本身确实产生文学增益，且稳定。**

---

## 8. 内容检查结果

完整逐句核对见 `analysis/CONTENT_CHECK.md`，diff 见 `analysis/DIFFS.md`。

确定性屏幕（`analysis/CONTENT_CHECK_AUTO.json`）：
- 数字、编号：3 章**无新增、无缺失、无改写**；
- 日期：3 章值集合不变；ch05 少了一次 `八月八日` 的**重复出现**（2→1），值仍在，属于删重复转述；
- 章末段落 8-gram 保留：ch03 0.00 / ch05 1.00 / ch07 1.00（ch03 章末被重排，钩子仍在）。

人工核对（按用户清单）：三章均存在**真实**的受保护内容删除，不是门禁误杀。

| 章 | HARD 损失 | 结论 |
|---|---|---|
| ch03 | 删“他没问。”（潜台词动作）；删“那是他自己瞒下的”（已知情状态）；删“林越没觉得他在撒谎”（判断） | 拒绝成立 |
| ch05 | 删“不问比问更压人……只是被存下了”（短情绪落点 + 判断）；删“这在乔宁身上是头一回”（首次性事实） | 拒绝成立 |
| ch07 | 删“但这句话他没处说去”（情绪落点）；删“一登记就等于当众揭了梅叔的盖子”（因果连接）；删“钥匙不在他身上了。唯一能带出档案屋的实物……”（归属 + 唯一线索） | 拒绝成立 |

其余删除（如“林越听懂了”“辨认一个对手”“整段复盘”）属于原则 1/2/3 的目标，判为 SOFT 或无损失。

**因此：语义门禁的拒绝是正确的；问题在编辑执行，不在保护机制。**

---

## 9. PASS / PARTIAL / FAIL

**判定：PARTIAL。**

- ✅ 核心机制可运行：prompt 生成、候选、确定性护栏、宿主 Judge、绑定校验、失败回退；
- ✅ 正式主链已改：2B 成为唯一文学环节，Step 4 不再整章润色，无重复后处理；
- ✅ 无 HARD 内容进入最终正文：3/3 回退 Writer raw；
- ✅ 没有新增 Agent / semantic gate / 评分 / 状态系统；
- ❌ **一个清晰的局部阻塞**：编辑模型在真实章节上仍会删掉保护清单里的承载句，
  导致 3/3 候选被拒绝，**最终正文在本轮 E2E 中没有获得文学增益**。

边界说明：若验收口径严格要求“最终正文必须出现增益”，本轮应记为 FAIL；
按用户给出的 PARTIAL 定义（核心机制成立、存在一个明确局部阻塞），判为 PARTIAL 更准确。
不把“候选 36/36 全票更好”当成正式增益，因为候选没有进入最终正文。

---

## 10. 是否满足合并条件

**不满足本轮验收的合并条件。** 理由：目标同时要求“文学性获得稳定增益”和“不破坏事实”；
本轮只证明了后者，前者在最终正文上是 0/3。

代码本身是安全增量的：失败 fail-closed、无重试、无回归、无架构膨胀；
但按本轮 PASS 标准，不能声称目标达成。建议保留 PR 作为 PARTIAL 结论与后续修复依据，不合并。

后续若要推进（不属于本轮）：需要让编辑模型真正遵守“不得删除”清单（例如在生成后增加一次
只针对保护句的**确定性保留检查**，或把保护清单转成更可执行的约束），而不是放宽语义门禁。

---

## 11. 最终回答

**文学减法编辑是否已经以最小复杂度安全接入正式 Zhanghui 写作流程，并在真实章节中继续产生文学收益？**

已经以最小复杂度**安全接入**（Step 2B 单一文学环节、确定性护栏 + 既有 Judge、失败回退、无重复润色），
但在本轮 3 个真实章节中，最终正文**没有**继续产生文学收益：编辑模型删除了受保护的承载内容，
3/3 被门禁拒绝并回退 Writer raw。候选稿本身仍有稳定文学增益（盲评 36/36），
因此结论是 **PARTIAL**：机制成立，一个局部阻塞未解决。
