#!/usr/bin/env bash
# install-plugin.sh - Canonical Zhanghui plugin installation and update tool.
#
# Connects Claude Code directly to the authoritative repository marketplace manifest,
# ensuring the active plugin is loaded directly from the canonical repository tree
# (.claude/plugins/zhanghui/) without stale intermediate copies or partial whitelist drift.
#
# Usage:
#   bin/install-plugin.sh          # Register marketplace and install/enable zhanghui
#   bin/install-plugin.sh --check  # Verify active installation points to canonical repo
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CANONICAL_PLUGIN="${REPO_ROOT}/.claude/plugins/zhanghui"

if [ ! -d "${CANONICAL_PLUGIN}" ]; then
    echo "ERROR: Canonical plugin source not found at ${CANONICAL_PLUGIN}" >&2
    exit 1
fi

if [ "${1:-}" = "--check" ]; then
    echo "Verifying active Claude Code plugin installation for zhanghui..."
    if ! command -v claude >/dev/null 2>&1; then
        echo "WARN: 'claude' CLI not in PATH; skipping live check."
        exit 0
    fi
    LIST_OUT="$(claude plugin list 2>&1 || true)"
    if echo "${LIST_OUT}" | grep -qE "Read[[:space:]]*from:[[:space:]]*${CANONICAL_PLUGIN}"; then
        echo "✓ Active plugin 'zhanghui@zhanghui' is read directly from canonical repo: ${CANONICAL_PLUGIN}"
        exit 0
    else
        echo "ERROR: Active plugin is NOT pointing to canonical repo!" >&2
        echo "Current claude plugin list:" >&2
        echo "${LIST_OUT}" >&2
        exit 1
    fi
fi

echo "=== Zhanghui Plugin Installation / Sync ==="
echo "Canonical repo root:   ${REPO_ROOT}"
echo "Canonical plugin tree: ${CANONICAL_PLUGIN}"
echo ""

if ! command -v claude >/dev/null 2>&1; then
    echo "ERROR: 'claude' CLI not found in PATH." >&2
    exit 1
fi

# 1. Clean legacy marketplace registration if it exists
LEGACY_MKT="webnovel-chang-marketplace"
if claude plugin marketplace 2>&1 | grep -q "${LEGACY_MKT}"; then
    echo "Removing legacy marketplace '${LEGACY_MKT}'..."
    claude plugin marketplace remove "${LEGACY_MKT}" || true
fi

# 2. Register local repo as marketplace 'zhanghui'
echo "Registering repo root as marketplace 'zhanghui'..."
claude plugin marketplace remove zhanghui 2>/dev/null || true
claude plugin marketplace add "${REPO_ROOT}"

# 3. Install / enable zhanghui@zhanghui
echo "Installing zhanghui@zhanghui from local marketplace..."
claude plugin install zhanghui@zhanghui
claude plugin enable zhanghui@zhanghui || true

echo ""
echo "Verifying installation:"
claude plugin list

echo ""
echo "✓ Installation complete! Claude Code reads directly from canonical repo."
