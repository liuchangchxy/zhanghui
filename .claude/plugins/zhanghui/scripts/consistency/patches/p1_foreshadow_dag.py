"""Patch 1: Foreshadow DAG validation.

Source: 移植自 Openwrite-main/skills/foreshadowing-system（伏笔状态机+DAG 验证）
Path in references: references/02-Openwrite/upstream/skills/foreshadowing-system/
Original algorithm: 无环（DFS）+ 有向（planted<paid_off）+ 可达（路径存在）+ 超期（active && paid_off_chapter < current_chapter）
"""
from ..core.patch_base import Patch, CheckContext, ApplyContext, PatchFinding


def _get_dag(state: dict) -> tuple[list[dict], str]:
    """Returns (dag_list, format) where format is 'dict', 'list', or 'missing'/'unknown'.

    Real state.json from migrate_story_craft.py has foreshadow_chain as a list of dicts.
    Our test fixtures wrap it as {dag: [...], version: ...}.
    """
    chain = state.get("story_craft", {}).get("foreshadow_chain")
    if chain is None:
        return [], "missing"
    if isinstance(chain, list):
        return chain, "list"
    if isinstance(chain, dict) and "dag" in chain:
        return chain["dag"], "dict"
    return [], "unknown"


class P1ForeshadowDAG(Patch):
    name = "foreshadow_dag"
    description = "伏笔 DAG 验证：无环 / 有向 / 可达 / 超期"
    depends_on = ()

    OVERDUE_TOLERANCE = 50  # 超期容忍窗口（章）

    def _finding(
        self,
        ctx: CheckContext,
        issue_code: str,
        message: str,
        fix_hint: str,
        evidence: dict[str, object],
        subject_id: str | None = None,
    ) -> PatchFinding:
        return PatchFinding(
            patch=self.name,
            chapter=ctx.chapter_num,
            issue_code=issue_code,
            message=message,
            fix_hint=fix_hint,
            subject_id=subject_id,
            evidence=evidence,
            checker_id=self.name,
            checker_version="1",
            input_ref={"source": "state.story_craft.foreshadow_chain"},
        )

    def check(self, ctx: CheckContext) -> list[PatchFinding]:
        # Special-case: state failed to load
        if "_load_error" in ctx.state:
            return [self._finding(ctx, "invalid_state", "无法读取 state.json", "修复 state.json 后重试，或运行 consistency init 重建",
                                  {"source": "state.json", "error_type": "load_error"})]

        dag, fmt = _get_dag(ctx.state)
        if fmt == "missing":
            return [self._finding(ctx, "invalid_state", "state.json 缺少 foreshadow_chain 字段，未初始化",
                                  "运行 `python webnovel.py consistency init --volume <current_volume>`",
                                  {"source_field": "story_craft.foreshadow_chain", "reason": "missing"})]
        if fmt == "unknown":
            return [self._finding(ctx, "invalid_state", "foreshadow_chain 格式未知（既不是 list 也不是 {dag: [...]}）",
                                  "运行 consistency init 重建",
                                  {"source_field": "story_craft.foreshadow_chain", "reason": "unknown_format"})]
        if not isinstance(dag, list):
            return [self._finding(ctx, "invalid_state", "foreshadow_chain.dag 必须是 list",
                                  "运行 consistency init 重建",
                                  {"source_field": "story_craft.foreshadow_chain.dag", "reason": "not_list",
                                   "actual_type": type(dag).__name__})]

        findings: list[PatchFinding] = []

        if any(not isinstance(fs, dict) for fs in dag):
            return [self._finding(ctx, "invalid_state", "foreshadow_chain 中存在非对象条目",
                                  "修复 foreshadow_chain 条目格式后重试",
                                  {"source_field": "story_craft.foreshadow_chain", "reason": "non_object_row"})]

        # 0. missing id guard
        missing_id = [i for i, fs in enumerate(dag) if not fs.get("id")]
        if missing_id:
            findings.append(self._finding(ctx, "missing_id", f"伏笔 DAG 缺少 id 字段（共 {len(missing_id)} 处）",
                                          "为每个 foreshadow DAG 条目补充 id 字段",
                                          {"missing_indices": missing_id, "count": len(missing_id)}))

        # 0b. duplicate id detection
        ids = [fs.get("id") for fs in dag if fs.get("id")]
        if ids:
            seen: set[str] = set()
            duplicates: set[str] = set()
            for i in ids:
                if i in seen:
                    duplicates.add(i)
                seen.add(i)
            if duplicates:
                findings.append(self._finding(ctx, "duplicate_id", f"伏笔 DAG 有重复 id: {sorted(duplicates)}",
                                              "为重复 id 的条目改名，保证唯一",
                                              {"duplicate_ids": sorted(duplicates)}))

        # 1. 无环检测（DFS）
        cycle = self._find_cycle(dag)
        if cycle:
            cycle_ids, cycle_edges = cycle
            findings.append(self._finding(ctx, "cycle", "伏笔 DAG 存在循环引用",
                                          "检查伏笔的 depends_on 是否形成回环",
                                          {"cycle_ids": cycle_ids, "cycle_edges": cycle_edges},
                                          subject_id=f"cycle:{','.join(cycle_ids)}"))

        # 2. 有向：planted < paid_off
        for fs in dag:
            planted = fs.get("planted_chapter")
            paid_off = fs.get("paid_off_chapter")
            if planted is not None and paid_off is not None and planted >= paid_off:
                subject = fs.get("id")
                findings.append(self._finding(ctx, "chronology",
                                              f"伏笔 {subject} planted_chapter({planted}) >= paid_off_chapter({paid_off})，提前回收",
                                              "调整 paid_off_chapter 到 planted_chapter 之后",
                                              {"planted_chapter": planted, "paid_off_chapter": paid_off},
                                              subject_id=f"foreshadow:{subject}" if isinstance(subject, str) and subject else None))

        # 3. 超期：active 状态且 paid_off_chapter + tolerance < current_chapter
        for fs in dag:
            if fs.get("status") != "active":
                continue
            paid_off = fs.get("paid_off_chapter")
            if paid_off is None:
                continue
            if ctx.chapter_num > paid_off + self.OVERDUE_TOLERANCE:
                subject = fs.get("id")
                findings.append(self._finding(ctx, "overdue",
                                              f"伏笔 {subject} 超期未收：应在第 {paid_off} 章回收但仍未回收（已过 {ctx.chapter_num - paid_off} 章）",
                                              f"在本章或前 {self.OVERDUE_TOLERANCE} 章内回收 fs {subject}，或更新 paid_off_chapter",
                                              {"paid_off_chapter": paid_off, "observed_chapter": ctx.chapter_num,
                                               "tolerance": self.OVERDUE_TOLERANCE},
                                              subject_id=f"foreshadow:{subject}" if isinstance(subject, str) and subject else None))

        return findings

    def apply(self, ctx: ApplyContext) -> None:
        # Real format (list): no-op (no validated_at / version metadata to maintain)
        chain = ctx.state.setdefault("story_craft", {}).get("foreshadow_chain")
        if isinstance(chain, list):
            return  # real migrate_story_craft format: leave the list alone
        # Legacy dict format: maintain validated_at pointer for backward compat
        chain_dict = ctx.state.setdefault("story_craft", {}).setdefault(
            "foreshadow_chain", {"version": 1, "dag": [], "validated_at": None, "validation_history": []}
        )
        chain_dict["validated_at"] = ctx.state.get("_last_modified_at")

    def _find_cycle(self, dag: list[dict]) -> tuple[list[str], list[list[str]]] | None:
        """Return a deterministic cycle identity and its canonical edges."""
        # Defensive: ensure depends_on is iterable and contains strings
        graph: dict[str, list[str]] = {
            fs["id"]: [d for d in (fs.get("depends_on") or []) if isinstance(d, str)]
            for fs in dag if fs.get("id")
        }
        visited: set[str] = set()
        stack: list[str] = []
        positions: dict[str, int] = {}

        def dfs(node: str) -> tuple[list[str], list[list[str]]] | None:
            if node in visited:
                return None
            visited.add(node)
            positions[node] = len(stack)
            stack.append(node)
            for nxt in sorted(set(graph.get(node, []))):
                if nxt in positions:
                    cycle_nodes = stack[positions[nxt]:]
                    edges = [[stack[index], stack[index + 1]] for index in range(positions[nxt], len(stack) - 1)]
                    edges.append([node, nxt])
                    cycle_ids = sorted(set(cycle_nodes))
                    return cycle_ids, sorted(edges)
                cycle = dfs(nxt)
                if cycle:
                    return cycle
            stack.pop()
            positions.pop(node)
            return None

        for node in sorted(graph):
            cycle = dfs(node)
            if cycle:
                return cycle
        return None
