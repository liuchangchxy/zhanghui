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

# 1. Chapter preparation & Writer package (reuses native ContextManager)
prep = runtime.prepare(chapter=1, with_package=True)
writer_pkg = prep.writer_package

# 2. Draft ingestion (Draft != Canon; returns staged draft_id)
ingest = runtime.ingest_draft(
    chapter=1,
    prose=generated_prose,
    package_fingerprint=writer_pkg.package_fingerprint,
    metadata={"generator": "model-xyz"},
)

# 3. Status inspection
status = runtime.get_status(chapter=1)

# 4. Commit attempt (strictly bound to staged draft_id + 5 required semantic artifacts)
commit_res = runtime.commit(
    chapter=1,
    draft_id=ingest.draft_id,
    package_fingerprint=writer_pkg.package_fingerprint,
    review_result=native_review_result,
    extraction_result=native_extraction_result,
    fulfillment_result=native_fulfillment_result,
    disambiguation_result=native_disambiguation_result,
    reconciliation_result=native_reconciliation_result,
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
python3 .claude/plugins/zhanghui/scripts/data_modules/webnovel.py runtime commit \
  --chapter 1 \
  --draft-id <draft_id> \
  --review-file review.json \
  --extraction-file extraction.json \
  --fulfillment-file fulfillment.json \
  --disambiguation-file disambiguation.json \
  --reconciliation-file reconciliation.json \
  --json

# 5. Retry projection
python3 .claude/plugins/zhanghui/scripts/data_modules/webnovel.py runtime retry-projection --chapter 1 --json
```

---

## 4. Key Architectural Guarantees

### 4.1 Single Authority Context Assembly
`WriterPackage` delegates context construction strictly to `ContextManager.build_context(chapter)`. There is zero parallel or shadow context assembly.
- **Story Identity**: Title, genre, target readers, project constraints.
- **Current Intent**: Target chapter goals, must-cover nodes, forbidden zones, unresolved questions.
- **Future Intent Isolation**: Future chapter outlines are strictly filtered out to prevent narrative leaking.
- **Governed Canon**: Relevant entities, recent accepted story events, active promises from native `ContextManager`.
- **Provenance Fingerprints**: Source-level hashes of outline and state, combined into a tamper-evident `package_fingerprint`.

### 4.2 Stale Package Protection
If authoritative inputs (such as outline or Canon state) change after a package was generated:
- Ingestion or commit attempts with an outdated `package_fingerprint` are immediately rejected with `STALE_WRITER_PACKAGE`.
- Prevents silent desynchronization when outlines are edited mid-generation.

### 4.3 `Draft != Canon` & Mandatory `draft_id` Binding
- Ingesting a draft only writes a staging artifact into `.webnovel/runtime/chapter_XXX/`.
- No Canon projections, chapter indices, SQLite records, or state revisions are mutated until `commit` passes all gate decisions.
- Public `commit()` strictly requires `draft_id` from ingestion. It validates:
  1. `draft.chapter == requested_chapter`
  2. Staged draft file existence (`drafts/{draft_id}.json` or `draft.json`)
  3. Staged prose hash matching (`DRAFT_FINGERPRINT_MISMATCH` if altered)
  4. Package fingerprint matching current authoritative state (`STALE_WRITER_PACKAGE`).

### 4.4 Prohibition of Fake Semantic Artifacts
The runtime does NOT synthesize or fake default semantic artifacts. External hosts or agents must provide all 5 semantic artifacts:
- `review_result`
- `extraction_result`
- `fulfillment_result`
- `disambiguation_result`
- `reconciliation_result`

Missing any required artifact halts commit with `REQUIRED_ARTIFACTS_MISSING` and provides actionable `next_required_action`.

### 4.5 Authoritative Changes-Gate Execution
Changes-gate validation is executed via the single shared authority `run_changes_gate` from `changes_gate.py`. Shadow or simplified gate checks have been removed, ensuring 100% parity with native commit pipelines.

### 4.6 Granular Recovery & Partial Failure Visibility
- If durability succeeds but projection writers fail (e.g. downstream network blip), the commit remains durably accepted and `can_retry_projection=True`.
- The host can safely query `status` or invoke `retry-projection` without re-running the draft or altering accepted Canon.

---

## 5. Verification & Testing Strategy

- **External Host Contract Tests** (`tests/integration/test_external_host_contract.py`):
  Deterministic protocol test verifying that any external host can interact strictly via the public `ChapterRuntime` surface without touching private layouts.
- **Live Antigravity Canary**:
  Live execution verifying `prepare -> WriterPackage -> fresh Antigravity agentapi invocation -> real model prose -> ingest_draft`. Temporary artifacts are isolated to test scratch/tmp dirs, preserving zero unintended repository modifications.

