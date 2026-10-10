# Runtime API v1 — Host-Independent Chapter Orchestration

> Issue #25 Architecture & Operational Contract.

## 1. Overview

Zhanghui Runtime API v1 provides a host-agnostic, machine-callable interface that decouples chapter orchestration from any particular AI agent environment (Claude Code, Antigravity, benchmark harness, or custom runners).

External hosts interact exclusively with the public runtime surface without managing:
- Internal outline layouts (`大纲/` naming conventions and parsing).
- Story System private contract JSON files (`MASTER_SETTING.json`, `chapter_xxx.contract.json`, etc.).
- Internal `ContextManager` source hierarchies.
- Temporary staging artifact directories.
- Canon projection writer fan-outs or internal schemas.

---

## 2. Division of Responsibilities

| Dimension | External Host Responsibilities | Zhanghui Runtime Responsibilities |
|---|---|---|
| **Context & State** | Requests chapter preparation by chapter number. | Resolves project, validates outline, builds/manages Story System contracts, gathers governed context. |
| **Model Transport** | Calls LLM providers, manages conversation sessions, prompts. | Emits sealed, stable `WriterPackage` with provenance fingerprints. |
| **Prose Ingestion** | Ingests generated prose along with package fingerprint. | Validates fingerprint freshness, stages draft artifact. Strictly enforces `draft != Canon`. |
| **Commit Authority** | Submits native review & extraction artifacts with draft prose. | Orchestrates validation via existing `ChapterCommitService` (single source of truth for Canon). |
| **Projections & Recovery** | Inspects commit outcome, queries status, triggers retry if needed. | Executes projection writers, maintains replay logs, reports granular projection status. |

---

## 3. Public Surfaces

### 3.1 Python Facade: `ChapterRuntime`

Located in [`.claude/plugins/zhanghui/scripts/data_modules/chapter_runtime.py`](file:///.claude/plugins/zhanghui/scripts/data_modules/chapter_runtime.py):

```python
from data_modules.chapter_runtime import ChapterRuntime

runtime = ChapterRuntime(project_root="/path/to/book")

# 1. Chapter preparation & Writer package
prep = runtime.prepare(chapter=1, with_package=True)
writer_pkg = prep.writer_package

# 2. Draft ingestion (Draft != Canon)
ingest = runtime.ingest_draft(
    chapter=1,
    prose=generated_prose,
    package_fingerprint=writer_pkg.package_fingerprint,
    metadata={"generator": "model-xyz"},
)

# 3. Status inspection
status = runtime.get_status(chapter=1)

# 4. Commit attempt
commit_res = runtime.commit(
    chapter=1,
    draft_id=ingest.draft_id,
    prose=generated_prose,
    package_fingerprint=writer_pkg.package_fingerprint,
    review_result=native_review_result,
    extraction_result=native_extraction_result,
)

# 5. Projection retry (if needed)
if not commit_res.projection_success and commit_res.can_retry_projection:
    retry_res = runtime.retry_projection(chapter=1)
```

### 3.2 CLI Interface: `webnovel.py runtime`

All operations are exposed via CLI with `--json` formatted outputs:

```bash
# 1. Prepare & obtain writer package
python3 .claude/plugins/zhanghui/scripts/data_modules/webnovel.py runtime prepare --chapter 1 --json

# 2. Ingest draft
python3 .claude/plugins/zhanghui/scripts/data_modules/webnovel.py runtime ingest-draft --chapter 1 --file draft.txt --fingerprint <pkg_hash> --json

# 3. Query status
python3 .claude/plugins/zhanghui/scripts/data_modules/webnovel.py runtime status --chapter 1 --json

# 4. Commit chapter
python3 .claude/plugins/zhanghui/scripts/data_modules/webnovel.py runtime commit --chapter 1 --draft-id <draft_id> --review-file review.json --extraction-file extraction.json --json

# 5. Retry projection
python3 .claude/plugins/zhanghui/scripts/data_modules/webnovel.py runtime retry-projection --chapter 1 --json
```

---

## 4. Key Architectural Guarantees

### 4.1 Writer Package Contract
The `WriterPackage` is a deterministic, self-contained contract:
- **Story Identity**: Title, genre, target readers, project constraints.
- **Current Intent**: Target chapter goals, must-cover nodes, forbidden zones, unresolved questions.
- **Future Intent Isolation**: Future chapter outlines are strictly filtered out to prevent narrative leaking.
- **Governed Canon**: Relevant entities, recent accepted story events, active promises.
- **Provenance Fingerprints**: Source-level hashes of outline and state, combined into a tamper-evident `package_fingerprint`.

### 4.2 Stale Package Protection
If authoritative inputs (such as outline or Canon state) change after a package was generated:
- Ingestion or commit attempts with an outdated `package_fingerprint` are immediately rejected with `STALE_WRITER_PACKAGE`.
- Prevents silent desynchronization when outlines are edited mid-generation.

### 4.3 `Draft != Canon` Invariant
- Ingesting a draft only writes a staging artifact into `.webnovel/runtime/chapter_XXX/`.
- No Canon projections, chapter indices, SQLite records, or state revisions are mutated until `commit` passes all gate decisions.

### 4.4 Single Commit Authority
- The runtime delegates strictly to the existing `ChapterCommitService`.
- Guarantees the unified invariant pipeline: `ProposedChanges` -> `ObservedChanges` -> `Reconciliation` -> `GateDecision` -> `ChapterCommit` -> `Projection`.
- No separate or shadow commit logic exists.

### 4.5 Granular Recovery & Partial Failure Visibility
- If durability succeeds but projection writers fail (e.g. downstream network blip), the commit remains durably accepted and `can_retry_projection=True`.
- The host can safely query `status` or invoke `retry-projection` without re-running the draft or altering accepted Canon.
