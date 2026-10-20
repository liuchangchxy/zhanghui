#!/usr/bin/env bash
# install-plugin.sh - Canonical Zhanghui plugin installation and update tool.
#
# Connects Claude Code directly to the authoritative repository marketplace manifest,
# ensuring the active plugin is loaded directly from the canonical repository tree
# (.claude/plugins/zhanghui/) without stale intermediate copies or partial whitelist drift.
#
# Usage:
#   bin/install-plugin.sh          # Register marketplace and install/enable zhanghui
#   bin/install-plugin.sh --check  # Verify the active installation loads the canonical repo
#                                  #   exit 0 = verified, 1 = wrong source, 3 = SKIPPED (no claude CLI)
#   bin/install-plugin.sh --digest # Print the canonical source tree digest
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CANONICAL_PLUGIN="${REPO_ROOT}/.claude/plugins/zhanghui"

if [ ! -d "${CANONICAL_PLUGIN}" ]; then
    echo "ERROR: Canonical plugin source not found at ${CANONICAL_PLUGIN}" >&2
    exit 1
fi

# Source digest of the canonical plugin tree. Version strings cannot distinguish two
# different trees that both call themselves 6.5.0 — which is exactly how a stale cache copy
# was loaded while `--check` reported success. The digest is what makes the check able to
# answer "is the *code* I am about to rely on actually the code in this repo?".
source_digest() {
    ( cd "${CANONICAL_PLUGIN}" && find . -type f \
        ! -path './6.4.0/*' ! -name '*.pyc' ! -path '*/__pycache__/*' -print0 \
        | LC_ALL=C sort -z | xargs -0 shasum -a 256 2>/dev/null | shasum -a 256 | cut -d' ' -f1 )
}

if [ "${1:-}" = "--check" ]; then
    echo "Verifying active Claude Code plugin installation for zhanghui..."
    if ! command -v claude >/dev/null 2>&1; then
        # NOT a pass. This path verifies nothing, and the previous `exit 0` let callers read
        # "skipped" as "verified". Report SKIPPED and fail so the caller has to decide.
        echo "SKIPPED: 'claude' CLI not in PATH — no live check was performed." >&2
        echo "         Install the Claude Code CLI, or re-run without --check." >&2
        exit 3
    fi
    LIST_OUT="$(claude plugin list 2>&1 || true)"
    if ! echo "${LIST_OUT}" | grep -qE "Read[[:space:]]*from:[[:space:]]*${CANONICAL_PLUGIN}"; then
        echo "ERROR: Active plugin is NOT pointing to canonical repo!" >&2
        echo "Current claude plugin list:" >&2
        echo "${LIST_OUT}" >&2
        echo "" >&2
        echo "Fix: bin/install-plugin.sh   (re-register the marketplace and reinstall)" >&2
        exit 1
    fi
    echo "✓ Active plugin 'zhanghui@zhanghui' is read directly from canonical repo: ${CANONICAL_PLUGIN}"
    echo "  canonical source digest: $(source_digest)"
    VERSION_OUT="$(claude plugin list 2>&1 | grep -iE 'zhanghui' || true)"
    echo "  reported entry: ${VERSION_OUT:-<none>}"
    echo ""
    echo "NOTE: a matching version string is NOT evidence of a matching source tree."
    echo "      The 'Read from' path above is the load source; compare the digest against"
    echo "      'bin/install-plugin.sh --digest' if you need to prove the bytes."
    exit 0
fi

if [ "${1:-}" = "--digest" ]; then
    echo "canonical plugin tree: ${CANONICAL_PLUGIN}"
    echo "digest: $(source_digest)"
    exit 0
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
