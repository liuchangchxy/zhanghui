"""Repository-only ownership inventory validation and coverage checks."""

import ast
from pathlib import Path
import re

DOMAINS = {
    "CANON_COMMIT", "EVENTS", "STATE_JSON", "INDEX_DB", "SUMMARIES",
    "MEMORY", "VECTORS", "INTENT", "CRAFT", "WORKFLOW_METADATA",
    "MIGRATION", "COMPATIBILITY",
    "REFERENCE",
}
STATUSES = {"allowed", "guarded", "deprecated", "compatibility_only"}
MODE_STATUSES = {"allowed", "guarded", "rejected", "projection_only", "not_applicable"}
CLAIMS = {
    "CANON_AUTHORITY", "VERIFIED_PROJECTION", "LEGACY_COMPATIBILITY",
    "INTENT", "CRAFT", "WORKFLOW", "REFERENCE", "PRESERVE_ONLY", "UNKNOWN",
}
REASON_CODES = {"DYNAMIC_TARGET_REVIEWED", "OPAQUE_ADAPTER_REVIEWED", "NON_STORY_STORE"}
SQL_DOMAINS = {
    "INDEX_DB": {"chapters", "scenes", "appearances", "entities", "aliases", "state_changes",
                 "relationships", "story_events", "chapter_reading_power", "invalid_facts",
                 "review_metrics", "writing_checklist_scores", "override_contracts", "chase_debt",
                 "debt_events", "foreshadowing", "promise_ledger", "intent", "planning_horizon",
                 "relationship_events", "timeline", "locks", "samples", "tool_call_stats"},
    "VECTORS": {"vectors", "vectors_migrating", "bm25_index", "doc_stats", "rag_schema_meta", "rag_query_log"},
    "WORKFLOW_METADATA": {"gate_decisions", "workflow_events", "review_attempts", "projection_runs"},
}
PROTECTED_SOURCE_HINTS = (
    "state", "index", "commit", "event", "projection", "summary", "memory", "vector",
    "intent", "craft", "review", "workflow", "migration", "init_project", "volume_state",
    "promise_ledger", "context_manager", "tracking_query", "archive_manager",
)


def _domain_for_text(value):
    text = str(value or "").lower()
    domains = set()
    if any(token in text for token in (".story-system/commits", "commits/", "commit_path", "commit_dir")):
        domains.add("CANON_COMMIT")
    if any(token in text for token in ("events/", ".story-system/events", "event_path", "event_file")):
        domains.add("EVENTS")
    if any(token in text for token in ("state.json", "state_path", "state_file", "state")):
        domains.add("STATE_JSON")
    if any(token in text for token in ("index.db", "index_path", "db_path", "sqlite")):
        domains.add("INDEX_DB")
    if any(token in text for token in ("summary", "summaries")):
        domains.add("SUMMARIES")
    if any(token in text for token in ("memory", "scratchpad")):
        domains.add("MEMORY")
    if any(token in text for token in ("vector", "bm25")):
        domains.add("VECTORS")
    if any(token in text for token in ("intent", "promise", "foreshadow", "strand", "planning")):
        domains.add("INTENT")
    if any(token in text for token in ("craft", "style_profile")):
        domains.add("CRAFT")
    if any(token in text for token in ("workflow", "gate_decision", "review_attempt", "projection_run", "projection_log")):
        domains.add("WORKFLOW_METADATA")
    if any(token in text for token in ("chapter_file", "chapter.md", "taxonomy", "profile_path", "archive_file", "init_project.py")):
        domains.add("COMPATIBILITY")
    if "review" in text and any(token in text for token in ("pipeline", "result", "schema", "artifact")):
        domains.add("WORKFLOW_METADATA")
    if "commit" in text:
        domains.add("CANON_COMMIT")
    if "index_projection_writer" in text:
        domains.add("INDEX_DB")
    return domains


def _resolve_expr(node, aliases):
    if isinstance(node, ast.Constant):
        return repr(node.value) if isinstance(node.value, str) else str(node.value)
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.JoinedStr):
        return " ".join(_resolve_expr(part, aliases) for part in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _resolve_expr(node.left, aliases) + _resolve_expr(node.right, aliases)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return _resolve_expr(node.func.value, aliases) + "." + node.func.attr
    if isinstance(node, ast.Attribute):
        return _resolve_expr(node.value, aliases) + "." + node.attr
    return ast.unparse(node)


def _sql_resources(sql):
    text = str(sql or "")
    mutation = bool(re.search(r"\b(insert|update|delete|replace|create|alter|drop)\b", text, re.I))
    access = "write" if mutation else "read" if re.search(r"\b(select|pragma|with)\b", text, re.I) else None
    if not access:
        return []
    names = set(re.findall(r"\b(?:from|join|into|update|table)\s+[\"'`]?([a-z_][\w]*)", text, re.I))
    return [(domain, name, access) for domain, tables in SQL_DOMAINS.items()
            for name in names if name.lower() in tables]


def _protected_candidates(plugin_root, *, writers):
    candidates, unresolved = set(), set()
    for path in (plugin_root / "scripts").rglob("*.py"):
        if "tests" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        relative = path.relative_to(plugin_root).as_posix()
        path_hints = any(hint in relative.lower() for hint in PROTECTED_SOURCE_HINTS)

        def visit(node, class_name=None, function_name=None, aliases=None):
            aliases = aliases if aliases is not None else {}
            if isinstance(node, ast.ClassDef):
                class_name = node.name
                aliases = {}
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function_name = node.name
                aliases = {}
            if isinstance(node, ast.Assign):
                value = _resolve_expr(node.value, aliases)
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        aliases[target.id] = value
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
                aliases[node.target.id] = _resolve_expr(node.value, aliases)

            if isinstance(node, ast.Call):
                name = (node.func.id if isinstance(node.func, ast.Name) else
                        node.func.attr if isinstance(node.func, ast.Attribute) else "")
                coordinate = (relative, class_name or function_name or "<module>")
                found = []
                unresolved_domains = set()
                if writers and name == "atomic_write_json" and node.args:
                    target = _resolve_expr(node.args[0], aliases)
                    domains = _domain_for_text(target)
                    if domains == {"COMPATIBILITY"}:
                        unresolved.add((coordinate[0], coordinate[1], "COMPATIBILITY", name, target))
                    elif domains:
                        found.extend((domain, name) for domain in domains)
                    elif path_hints or any(token in (class_name or "").lower() + (function_name or "").lower()
                                           for token in PROTECTED_SOURCE_HINTS):
                        unresolved_domains |= _domain_for_text(relative + " " + (class_name or "") + " " + (function_name or "")) or {"COMPATIBILITY"}
                if name in {"execute", "executemany", "executescript"} and node.args:
                    sql = _resolve_expr(node.args[0], aliases)
                    resources = _sql_resources(sql)
                    found.extend((domain, "SQL:" + table) for domain, table, access in resources
                                 if access == "write")
                    if not resources and path_hints and not re.search(r"\b(select|insert|update|delete|replace|create|alter|drop|pragma|begin|commit|rollback)\b", sql, re.I):
                        unresolved_domains |= _domain_for_text(relative + " " + (class_name or "") + " " + (function_name or "")) or {"COMPATIBILITY"}
                if not writers and name in {"execute", "executemany", "executescript"} and node.args:
                    sql = _resolve_expr(node.args[0], aliases)
                    resources = _sql_resources(sql)
                    found.extend((domain, "SQL:" + table) for domain, table, access in resources if access == "read")
                    if not resources and path_hints and not re.search(r"\b(select|insert|update|delete|replace|create|alter|drop|pragma|begin|commit|rollback)\b", sql, re.I):
                        unresolved_domains |= _domain_for_text(relative + " " + (class_name or "") + " " + (function_name or "")) or {"COMPATIBILITY"}
                if writers and name in {"write_events", "process_chapter_data", "process_chapter_entities",
                                        "process_chapter_result", "apply_projection_writers"}:
                    domain = "EVENTS" if name == "write_events" else "INDEX_DB" if name == "process_chapter_data" else "STATE_JSON"
                    found.append((domain, name))
                if not writers and name in {"read_durable_commit", "read_validated_chapter_commit", "_load_latest_commit",
                                            "_load_latest_accepted_commit"}:
                    found.append(("CANON_COMMIT", name))
                if not writers and name in {"read_events", "load_events", "get_events"}:
                    found.append(("EVENTS", name))
                if name in {"read_text", "read_bytes", "read_json", "load_json", "write_text", "write_bytes", "open", "glob", "rglob", "iterdir"}:
                    is_path_open = name == "open" and isinstance(node.func, ast.Attribute)
                    is_builtin_open = name == "open" and isinstance(node.func, ast.Name)
                    if is_path_open:
                        target_nodes = [node.func.value]
                        mode_node = node.args[0] if node.args else next((kw.value for kw in node.keywords if kw.arg == "mode"), None)
                    elif is_builtin_open:
                        target_nodes = [node.args[0]] if node.args else []
                        mode_node = node.args[1] if len(node.args) > 1 else next((kw.value for kw in node.keywords if kw.arg == "mode"), None)
                    else:
                        target_nodes = [node.func.value] if isinstance(node.func, ast.Attribute) else list(node.args[:1])
                        mode_node = None
                    if name == "open":
                        mode = _resolve_expr(mode_node, aliases).strip("'\"") if mode_node else "r"
                        is_write = any(flag in mode for flag in ("w", "a", "x", "+"))
                        if is_write != writers:
                            target_nodes = []
                    elif name in {"read_text", "read_bytes", "read_json", "load_json", "glob", "rglob", "iterdir"} and writers:
                        target_nodes = []
                    elif name in {"write_text", "write_bytes"} and not writers:
                        target_nodes = []
                    for target_node in target_nodes:
                        target = _resolve_expr(target_node, aliases)
                        domains = _domain_for_text(target)
                        if domains == {"COMPATIBILITY"}:
                            unresolved_domains.add("COMPATIBILITY")
                        elif domains:
                            found.extend((domain, "Path.open" if is_path_open else name) for domain in domains)
                        elif (path_hints or any(token in (function_name or "").lower() for token in PROTECTED_SOURCE_HINTS)) and name in {"read_text", "read_bytes", "read_json", "load_json", "open"}:
                            unresolved_domains |= _domain_for_text(relative + " " + (class_name or "") + " " + (function_name or "")) or {"COMPATIBILITY"}
                for domain, sink in found:
                    candidates.add((coordinate[0], coordinate[1], domain, sink))
                for domain in unresolved_domains:
                    if name == "open" and isinstance(node.func, ast.Attribute):
                        target_expression = ast.unparse(node.func.value)
                    elif name == "open":
                        target_expression = ast.unparse(node.args[0]) if node.args else "<no-target>"
                    else:
                        target_expression = (ast.unparse(node.func.value)
                            if name in {"read_text", "read_bytes", "write_text", "write_bytes"}
                            and isinstance(node.func, ast.Attribute)
                            else ast.unparse(node.args[0]) if node.args else "<no-target>")
                    unresolved.add((coordinate[0], coordinate[1], domain, name, target_expression))
            for child in ast.iter_child_nodes(node):
                visit(child, class_name, function_name, aliases)

        visit(tree)
    return candidates, unresolved


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
            for source_record in record.get("source_coordinates", []):
                source_path = repository_root / source_record.get("path", "")
                _require(source_path.is_file(), f"{identity}: discovered source path missing: {source_path}")
                _require(source_record.get("symbol") in source_path.read_text(encoding="utf-8", errors="replace"),
                         f"{identity}: discovered source symbol missing: {source_record.get('symbol')}")
                _require(source_record.get("data_domain") in DOMAINS, f"{identity}: discovered source domain invalid")
                _require(source_record.get("sink"), f"{identity}: discovered source sink missing")
                expected_id = id_key
                _require(source_record.get(expected_id) == identity,
                         f"{identity}: discovered source owner linkage mismatch")
                _require(_inventory_source_path(source_record.get("path", "")) == _inventory_source_path(implementation.get("path", ""))
                         and source_record.get("symbol") == implementation.get("symbol"),
                         f"{identity}: discovered source is assigned to a different owner implementation")
                if family == "readers":
                    edge_id = source_record.get("read_edge_id")
                    _require(edge_id and any(edge.get("read_edge_id") == edge_id
                                             and edge.get("data_domain") == source_record.get("data_domain")
                                             for edge in record.get("read_edges", [])),
                             f"{identity}: source read edge linkage mismatch")
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
                _require(all(item.get("data_domain") in domains for item in record.get("source_coordinates", [])),
                         f"{identity}: discovered writer source domain is not classified by this owner")
            elif family == "readers":
                _require(record.get("lifecycle_status") in STATUSES,
                         f"{identity}: lifecycle_status invalid")
                edges = record.get("read_edges", [])
                _require(edges, f"{identity}: read_edges required")
                edge_domains = {edge.get("data_domain") for edge in edges}
                _require(all(item.get("data_domain") in edge_domains for item in record.get("source_coordinates", [])),
                         f"{identity}: discovered reader source has no matching mode-aware read edge")
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
    for family in ("writer_exceptions", "reader_exceptions"):
        seen_exceptions = set()
        for exception in inventory.get(family, []):
            key = _exception_key(family.removesuffix("_exceptions"), exception)
            _require(key not in seen_exceptions, f"duplicate {family} entry: {key}")
            seen_exceptions.add(key)
            _require(exception.get("reason_code") in REASON_CODES, f"{family}: reason_code invalid")
            _require(exception.get("path") and exception.get("symbol") and exception.get("domain") in DOMAINS
                     and exception.get("sink") and exception.get("target_expression"),
                     f"{family}: exact source identity required")
            _require(len(exception.get("rationale", "")) >= 8, f"{family}: rationale required")
            if exception.get("reason_code") != "NON_STORY_STORE":
                owner_key = "writer_id" if family == "writer_exceptions" else "reader_id"
                records = inventory.get("writers" if family == "writer_exceptions" else "readers", [])
                _require(exception.get(owner_key) in {row.get(owner_key) for row in records},
                         f"{family}: protected exception owner missing or unresolved")
                owner = next(row for row in records if row.get(owner_key) == exception[owner_key])
                allowed_domains = owner.get("data_domains", []) if family == "writer_exceptions" else [edge.get("data_domain") for edge in owner.get("read_edges", [])]
                _require(exception.get("domain") in allowed_domains,
                         f"{family}: protected exception owner does not classify domain")
                if family == "reader_exceptions":
                    edge_id = exception.get("read_edge_id")
                    _require(edge_id and any(edge.get("read_edge_id") == edge_id and edge.get("data_domain") == exception.get("domain") for edge in owner.get("read_edges", [])),
                             f"{family}: protected exception read edge missing")
            else:
                _require("non-story" in exception.get("rationale", "").lower()
                         or "test" in exception.get("rationale", "").lower()
                         or "operational" in exception.get("rationale", "").lower(),
                         f"{family}: NON_STORY_STORE classification rationale required")
            for evidence in exception.get("evidence", []):
                source = repository_root / evidence.get("path", "")
                _require(source.is_file(), f"{family}: evidence path missing: {source}")
                _require(evidence.get("anchor") in source.read_text(encoding="utf-8", errors="replace"),
                         f"{family}: evidence anchor missing")
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
    """List protected write owners discovered from production persistence sinks."""
    candidates, _unresolved = _protected_candidates(plugin_root, writers=True)
    return {(path, symbol) for path, symbol, _domain, _sink in candidates}


def _inventory_source_path(path):
    return Path(path).as_posix().removeprefix(".claude/plugins/zhanghui/")


def writer_coverage(inventory, plugin_root):
    declared = {(_inventory_source_path(source["path"]), source["symbol"], source["data_domain"])
                for row in inventory["writers"] for source in row.get("source_coordinates", [])}
    candidates, unresolved = _protected_candidates(plugin_root, writers=True)
    exceptions = {("writer", _inventory_source_path(row.get("path")), row.get("symbol"), row.get("domain"),
                   row.get("sink"), row.get("target_expression")) for row in inventory.get("writer_exceptions", [])}
    pending = {(path, symbol, domain) for path, symbol, domain, sink, target in unresolved
               if ("writer", path, symbol, domain, sink, target) not in exceptions}
    missing = {(path, symbol, domain) for path, symbol, domain, _sink in candidates
               if (path, symbol, domain) not in declared}
    return sorted(missing | pending)

def _exception_key(family, row):
    return (family, row.get("path"), row.get("symbol"), row.get("domain"), row.get("sink"), row.get("target_expression"))


def reader_coverage(inventory, plugin_root):
    declared = {(_inventory_source_path(source["path"]), source["symbol"], source["data_domain"])
                for row in inventory["readers"] for source in row.get("source_coordinates", [])}
    candidates, unresolved = _protected_candidates(plugin_root, writers=False)
    exceptions = {("reader", _inventory_source_path(row.get("path")), row.get("symbol"), row.get("domain"),
                   row.get("sink"), row.get("target_expression")) for row in inventory.get("reader_exceptions", [])}
    pending = {(path, symbol, domain) for path, symbol, domain, sink, target in unresolved
               if ("reader", path, symbol, domain, sink, target) not in exceptions}
    missing = {(path, symbol, domain) for path, symbol, domain, _sink in candidates
               if (path, symbol, domain) not in declared}
    return sorted(missing | pending)

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
