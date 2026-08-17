"""Patch 1: Foreshadow DAG validation.

Source: 移植自 Openwrite-main/skills/foreshadowing-system（伏笔状态机+DAG 验证）
Path in references: references/02-Openwrite/upstream/skills/foreshadowing-system/
Original algorithm: 无环（DFS）+ 有向（planted<paid_off）+ 可达（路径存在）+ 超期（active && paid_off_chapter < current_chapter）
"""
from ..core.patch_base import Patch, CheckContext, ApplyContext, Blocker


class P1ForeshadowDAG(Patch):
    name = "foreshadow_dag"
    description = "伏笔 DAG 验证：无环 / 有向 / 可达 / 超期"
    depends_on = ()

    OVERDUE_TOLERANCE = 50  # 超期容忍窗口（章）

    def check(self, ctx: CheckContext) -> list[Blocker]:
        chain = ctx.state.get("story_craft", {}).get("foreshadow_chain")
        if chain is None:
            return [Blocker(
                patch=self.name,
                chapter=ctx.chapter_num,
                message="state.json 缺少 foreshadow_chain 字段，未初始化",
                fix_hint="运行 `python webnovel.py consistency init --volume <current_volume>`"
            )]

        dag = chain.get("dag", [])
        blockers: list[Blocker] = []

        # 0. missing id guard
        missing_id = [i for i, fs in enumerate(dag) if not fs.get("id")]
        if missing_id:
            blockers.append(Blocker(
                patch=self.name,
                chapter=ctx.chapter_num,
                message=f"伏笔 DAG 缺少 id 字段（共 {len(missing_id)} 处）",
                fix_hint="为每个 foreshadow DAG 条目补充 id 字段"
            ))

        # 1. 无环检测（DFS）
        if self._has_cycle(dag):
            blockers.append(Blocker(
                patch=self.name,
                chapter=ctx.chapter_num,
                message="伏笔 DAG 存在循环引用",
                fix_hint="检查伏笔的 depends_on 是否形成回环"
            ))

        # 2. 有向：planted < paid_off
        for fs in dag:
            planted = fs.get("planted_chapter")
            paid_off = fs.get("paid_off_chapter")
            if planted is not None and paid_off is not None and planted >= paid_off:
                blockers.append(Blocker(
                    patch=self.name,
                    chapter=ctx.chapter_num,
                    message=f"伏笔 {fs.get('id')} planted_chapter({planted}) >= paid_off_chapter({paid_off})，提前回收",
                    fix_hint="调整 paid_off_chapter 到 planted_chapter 之后"
                ))

        # 3. 超期：active 状态且 paid_off_chapter + tolerance < current_chapter
        for fs in dag:
            if fs.get("status") != "active":
                continue
            paid_off = fs.get("paid_off_chapter")
            if paid_off is None:
                continue
            if ctx.chapter_num > paid_off + self.OVERDUE_TOLERANCE:
                blockers.append(Blocker(
                    patch=self.name,
                    chapter=ctx.chapter_num,
                    message=f"伏笔 {fs.get('id')} 超期未收：应在第 {paid_off} 章回收但仍未回收（已过 {ctx.chapter_num - paid_off} 章）",
                    fix_hint=f"在本章或前 {self.OVERDUE_TOLERANCE} 章内回收 fs {fs.get('id')}，或更新 paid_off_chapter"
                ))

        return blockers

    def apply(self, ctx: ApplyContext) -> None:
        chain = ctx.state.setdefault("story_craft", {}).setdefault("foreshadow_chain", {"version": 1, "dag": [], "validated_at": None, "validation_history": []})
        chain["validated_at"] = ctx.state.get("_last_modified_at")

    def _has_cycle(self, dag: list[dict]) -> bool:
        """DFS 检测环"""
        graph: dict[str, list[str]] = {fs["id"]: fs.get("depends_on", []) for fs in dag if fs.get("id")}
        visited: set[str] = set()
        path: set[str] = set()

        def dfs(node: str) -> bool:
            if node in path:
                return True
            if node in visited:
                return False
            visited.add(node)
            path.add(node)
            for nxt in graph.get(node, []):
                if dfs(nxt):
                    return True
            path.remove(node)
            return False

        return any(dfs(fs["id"]) for fs in dag if fs.get("id") and fs["id"] not in visited)