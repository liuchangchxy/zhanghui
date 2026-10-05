"""Repository-only ownership inventory validation and coverage checks."""

import ast
from pathlib import Path
import re

DOMAINS = {
    "CANON_COMMIT", "EVENTS", "STATE_JSON", "INDEX_DB", "SUMMARIES",
    "MEMORY", "VECTORS", "INTENT", "CRAFT", "WORKFLOW_METADATA",
    "MIGRATION", "COMPATIBILITY",
}
STATUSES = {"allowed", "guarded", "deprecated", "compatibility_only"}
MODE_STATUSES = {"allowed", "guarded", "rejected", "projection_only", "not_applicable"}
CLAIMS = {
    "CANON_AUTHORITY", "VERIFIED_PROJECTION", "LEGACY_COMPATIBILITY",
    "INTENT", "CRAFT", "WORKFLOW", "REFERENCE", "PRESERVE_ONLY", "UNKNOWN",
}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_inventory(inventory, repository_root):
    """Validate required contracts without importing plugin runtime modules."""
    _require(inventory.get("schema_version") == 1, "schema_version must be 1")
    _require(len(inventory.get("baseline", "")) >= 7, "baseline is required")
    for family, id_key in (("writers", "writer_id"), ("readers", "reader_id"),
                           ("migrations", "migration_id")):
        records = inventory.get(family)
        _require(isinstance(records, list) and records, f"{family} must be non-empty")
        seen = set()
        for record in records:
            identity = record.get(id_key)
            _require(identity and identity not in seen, f"duplicate or missing {id_key}: {identity}")
            seen.add(identity)
            _require(isinstance(record.get("implementation"), dict), f"{identity}: implementation required")
            _require(record.get("active_consumers"), f"{identity}: active_consumers required")
            _require("replacement" in record, f"{identity}: replacement field required")
            _require(record.get("retirement_criterion") and len(record["retirement_criterion"]) >= 8,
                     f"{identity}: retirement_criterion required")
            _require(isinstance(record.get("evidence"), list) and record["evidence"],
                     f"{identity}: evidence required")
            implementation = record.get("implementation", {})
            path = repository_root / implementation.get("path", "")
            symbol = implementation.get("symbol", "")
            _require(path.is_file(), f"{identity}: implementation path unresolved: {path}")
            text = path.read_text(encoding="utf-8", errors="replace")
            _require(symbol in text, f"{identity}: implementation symbol unresolved: {symbol}")
            for evidence in record.get("evidence", []):
                source = repository_root / evidence.get("path", "")
                _require(source.is_file(), f"{identity}: evidence path missing: {source}")
                _require(evidence.get("anchor") in source.read_text(encoding="utf-8", errors="replace"),
                         f"{identity}: evidence anchor missing")
            if family == "writers":
                _require(record.get("owner"), f"{identity}: owner required")
                domains = record.get("data_domains", [])
                _require(domains and set(domains) <= DOMAINS, f"{identity}: data_domains invalid")
                _require(record.get("lifecycle_status") in STATUSES,
                         f"{identity}: lifecycle_status invalid")
                for mode in ("story_system_mode", "legacy_mode"):
                    _require(record.get(mode, {}).get("behavior"), f"{identity}: {mode} behavior missing")
                    _require(record.get(mode, {}).get("mode") in MODE_STATUSES,
                             f"{identity}: {mode} value invalid")
            elif family == "readers":
                _require(record.get("lifecycle_status") in STATUSES,
                         f"{identity}: lifecycle_status invalid")
                edges = record.get("read_edges", [])
                _require(edges, f"{identity}: read_edges required")
                for edge in edges:
                    for mode in ("story_system", "legacy"):
                        details = edge.get(mode, {})
                        for field in ("primary_source", "authority_claim", "condition", "fallback"):
                            _require(field in details, f"{identity}: {mode}.{field} missing")
                        claim = details["authority_claim"]
                        _require(claim in CLAIMS, f"{identity}: authority_claim invalid")
                        source = details["primary_source"].lower()
                        _require(not (claim == "CANON_AUTHORITY" and
                                      ("legacy" in source or "state.json" in source)),
                                 f"{identity}: legacy source cannot claim CANON_AUTHORITY")
            else:
                for field in ("source", "target", "supported_project_modes", "preflight", "backup",
                              "idempotency", "postcondition", "rollback", "ambiguity_handling"):
                    _require(record.get(field), f"{identity}: migration {field} missing")
    return True


def runtime_inventory_references(plugin_root):
    """Return production Python sources that try to read the governance inventory."""
    hits = []
    scripts = plugin_root / "scripts"
    for path in scripts.rglob("*.py"):
        if "tests" in path.parts:
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        if "ownership-inventory.json" in source or "ownership-inventory.schema.json" in source:
            hits.append(path)
    return hits


def discovered_writer_coordinates(plugin_root):
    """Find protected write entrypoints from source, plus explicit API families."""
    candidates = {
        ("scripts/data_modules/chapter_commit_service.py", "ChapterCommitService"),
        ("scripts/data_modules/event_log_store.py", "write_events"),
        ("scripts/data_modules/event_projection_router.py", "EventProjectionRouter"),
        ("scripts/data_modules/state_projection_writer.py", "StateProjectionWriter"),
        ("scripts/data_modules/index_projection_writer.py", "IndexProjectionWriter"),
        ("scripts/data_modules/summary_projection_writer.py", "SummaryProjectionWriter"),
        ("scripts/data_modules/memory_projection_writer.py", "MemoryProjectionWriter"),
        ("scripts/data_modules/vector_projection_writer.py", "VectorProjectionWriter"),
        ("scripts/data_modules/state_manager.py", "StateManager"),
        ("scripts/data_modules/sql_state_manager.py", "SQLStateManager"),
        ("scripts/data_modules/index_manager.py", "IndexManager"),
        ("scripts/update_state.py", "main"),
        ("scripts/story_craft.py", "StoryCraftFieldError"),
        ("scripts/data_modules/volume_state.py", "VolumeStateManager"),
        ("scripts/data_modules/promise_ledger.py", "PromiseLedger"),
        ("scripts/consistency/core/runner.py", "apply_all"),
        ("scripts/init_project.py", "init_project"),
        ("scripts/migrate_story_craft.py", "migrate_state_json"),
        ("scripts/data_modules/migrate_state_to_sqlite.py", "migrate_state_to_sqlite"),
        ("scripts/changes_gate.py", "main"),
    }
    protected_calls = {
        "write_events", "process_chapter_data", "process_chapter_entities",
        "process_chapter_result",
    }
    for path in (plugin_root / "scripts").rglob("*.py"):
        if "tests" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue

        def visit(node, class_name=None, function_name=None):
            if isinstance(node, ast.ClassDef):
                class_name = node.name
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function_name = node.name
            if isinstance(node, ast.Call):
                call_name = (node.func.id if isinstance(node.func, ast.Name) else
                             node.func.attr if isinstance(node.func, ast.Attribute) else "")
                protected_state_write = False
                if call_name == "atomic_write_json" and node.args:
                    target = ast.unparse(node.args[0]).lower()
                    protected_state_write = any(
                        marker in target for marker in
                        ("state", "index", "summary", "memory", "vector", "craft")
                    )
                if call_name in protected_calls or protected_state_write:
                    symbol = class_name or function_name
                    if symbol:
                        candidates.add((path.relative_to(plugin_root).as_posix(), symbol))
            for child in ast.iter_child_nodes(node):
                visit(child, class_name, function_name)

        visit(tree)
    return candidates


def writer_coverage(inventory, plugin_root):
    prefix = ".claude/plugins/zhanghui/"
    declared = {(Path(row["implementation"]["path"]).as_posix().removeprefix(prefix),
                 row["implementation"]["symbol"]) for row in inventory["writers"]}
    candidates = discovered_writer_coordinates(plugin_root)
    missing = sorted(candidates - declared)
    return missing


def reader_family_coverage(inventory):
    covered = {record.get("reader_family") for record in inventory["readers"]}
    required = set(inventory.get("required_reader_families", []))
    return sorted(required - covered)


def is_historical_claim(text):
    return bool(re.search(r"\b(historical|legacy|历史|旧版|旧流程|兼容模式)\b", text, re.I))


def unqualified_ownership_claims(text):
    patterns = (
        r"data agent.{0,100}(?:唯一|写入|更新|writer|write).{0,80}(?:index\.db|state\.json|projection)",
        r"(?:index\.db|state\.json).{0,80}(?:权威|真相|authoritative|story truth)",
        r"step\s*5.{0,40}(?:已)?回写.{0,100}(?:state\.json|index\.db|summary)",
    )
    violations = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if is_historical_claim(line):
            continue
        if "projection" in line.lower() and "story system commit" in line.lower():
            continue
        if "state.json" in line.lower() and "投影" in line and "commit" in line.lower() and "权威" in line:
            continue
        if "data agent" in line.lower() and ("生成临时" in line or "只生成" in line):
            continue
        if "data agent" in line.lower() and "does not write canonical facts or projections" in line.lower():
            continue
        if any(re.search(pattern, line, re.I) for pattern in patterns):
            violations.append((line_number, line.strip()))
    return violations
