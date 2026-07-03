#!/usr/bin/env bash
#
# harden-agent-tools.sh -- Audit and enforce least-privilege tool permissions
# on agent markdown files (Claude Code subagent format with YAML frontmatter).
#
# Context: In Claude Code, an agent file that OMITS the `tools:` frontmatter
# field inherits ALL tools available to the main thread (including Bash and
# MCP tools). This script finds those silently-privileged agents and can
# inject an explicit restrictive allowlist so nothing installs with full
# inheritance by accident.
#
# Usage:
#   ./harden-agent-tools.sh audit  [REPO_DIR]
#       Report every agent file and its effective permission posture.
#
#   ./harden-agent-tools.sh apply  [REPO_DIR] [--tools "Read, Grep, Glob"] [--force]
#       Inject a default `tools:` line into every agent frontmatter that
#       lacks one. DRY RUN by default -- shows what would change.
#       Add --force to actually write. Existing `tools:` lines are never
#       modified. Use git diff afterwards to review.
#
#   ./harden-agent-tools.sh strip-bash [REPO_DIR] [--force]
#       Add `disallowedTools: Bash` to every agent frontmatter that does not
#       already declare a tools: allowlist or a disallowedTools line.
#       DRY RUN by default; --force to write.
#
# Notes:
#   - Only touches *.md files in agent division directories; skips README*,
#     CONTRIBUTING*, SECURITY*, and the integrations/, examples/, scripts/,
#     .github/ directories.
#   - Designed to run inside a git checkout: review with `git diff`,
#     revert with `git checkout -- .`
#   - No network access, no external dependencies beyond bash/grep/awk/sed.

set -euo pipefail

MODE="${1:-audit}"
REPO_DIR="${2:-.}"
DEFAULT_TOOLS="Read, Grep, Glob"
FORCE=false

# Parse remaining flags
shift $(( $# >= 2 ? 2 : $# )) || true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tools) DEFAULT_TOOLS="$2"; shift 2 ;;
    --force) FORCE=true; shift ;;
    *) echo "Unknown flag: $1" >&2; exit 1 ;;
  esac
done

cd "$REPO_DIR"

# Collect agent files: md files outside excluded paths, excluding docs.
mapfile -t AGENT_FILES < <(
  find . -type f -name "*.md" \
    -not -path "./.git/*" \
    -not -path "./integrations/*" \
    -not -path "./examples/*" \
    -not -path "./scripts/*" \
    -not -path "./.github/*" \
    -not -name "README*" \
    -not -name "CONTRIBUTING*" \
    -not -name "SECURITY*" \
    | sort
)

# has_frontmatter FILE -> 0 if file starts with --- and has a closing ---
has_frontmatter() {
  head -1 "$1" | grep -q '^---[[:space:]]*$' || return 1
  # closing delimiter must exist after line 1
  awk 'NR>1 && /^---[[:space:]]*$/ {found=1; exit} END {exit !found}' "$1"
}

# frontmatter_has KEY FILE -> 0 if key exists inside the frontmatter block
frontmatter_has() {
  local key="$1" file="$2"
  awk -v key="^${key}:" '
    NR==1 && /^---[[:space:]]*$/ {inblock=1; next}
    inblock && /^---[[:space:]]*$/ {exit}
    inblock && $0 ~ key {found=1; exit}
    END {exit !found}
  ' "$file"
}

# get_line KEY FILE -> prints the frontmatter line for KEY (first match)
get_line() {
  local key="$1" file="$2"
  awk -v key="^${key}:" '
    NR==1 && /^---[[:space:]]*$/ {inblock=1; next}
    inblock && /^---[[:space:]]*$/ {exit}
    inblock && $0 ~ key {print; exit}
  ' "$file"
}

# inject_line FILE LINE -> insert LINE just before the closing --- of frontmatter
inject_line() {
  local file="$1" line="$2" tmp
  tmp="$(mktemp)"
  awk -v ins="$line" '
    NR==1 && /^---[[:space:]]*$/ {inblock=1; print; next}
    inblock && /^---[[:space:]]*$/ && !done {print ins; done=1; inblock=0; print; next}
    {print}
  ' "$file" > "$tmp"
  mv "$tmp" "$file"
}

case "$MODE" in

  audit)
    n_total=0; n_declared=0; n_inherit=0; n_nofm=0
    declared_list=(); inherit_list=(); nofm_list=()
    for f in "${AGENT_FILES[@]}"; do
      (( ++n_total ))
      if ! has_frontmatter "$f"; then
        (( ++n_nofm )); nofm_list+=("$f")
        continue
      fi
      if frontmatter_has "tools" "$f"; then
        (( ++n_declared )); declared_list+=("$f|$(get_line tools "$f")")
      elif frontmatter_has "disallowedTools" "$f"; then
        (( ++n_declared )); declared_list+=("$f|$(get_line disallowedTools "$f")")
      else
        (( ++n_inherit )); inherit_list+=("$f")
      fi
    done

    echo "=============================================================="
    echo " AGENT TOOL-PERMISSION AUDIT"
    echo " Repo: $(pwd)"
    echo "=============================================================="
    echo ""
    echo " Total agent files scanned : $n_total"
    echo " Explicit tools/disallowed : $n_declared  (restricted -- OK)"
    echo " NO tools field (INHERITS ALL TOOLS incl. Bash) : $n_inherit"
    echo " No frontmatter at all     : $n_nofm"
    echo ""
    if (( n_declared > 0 )); then
      echo "--- Explicitly declared (verify these are what you want) ---"
      for e in "${declared_list[@]}"; do
        printf "  %-70s %s\n" "${e%%|*}" "${e#*|}"
      done
      echo ""
    fi
    if (( n_inherit > 0 )); then
      echo "--- FULL-INHERITANCE agents (highest risk, fix these) ---"
      printf "  %s\n" "${inherit_list[@]}"
      echo ""
    fi
    if (( n_nofm > 0 )); then
      echo "--- Files without frontmatter (inspect manually) ---"
      printf "  %s\n" "${nofm_list[@]}"
      echo ""
    fi
    echo "Next step:"
    echo "  ./harden-agent-tools.sh apply . --tools \"Read, Grep, Glob\" --force"
    ;;

  apply)
    changed=0; skipped=0
    echo "Injecting: tools: $DEFAULT_TOOLS"
    $FORCE || echo "(DRY RUN -- add --force to write)"
    echo ""
    for f in "${AGENT_FILES[@]}"; do
      has_frontmatter "$f" || { echo "SKIP (no frontmatter): $f"; (( ++skipped )); continue; }
      if frontmatter_has "tools" "$f"; then
        (( ++skipped )); continue
      fi
      if $FORCE; then
        inject_line "$f" "tools: $DEFAULT_TOOLS"
        echo "WROTE: $f"
      else
        echo "WOULD WRITE: $f"
      fi
      (( ++changed ))
    done
    echo ""
    if $FORCE; then echo "Files changed: $changed | left as-is: $skipped"; else echo "Files that would change: $changed | left as-is: $skipped"; fi
    $FORCE && echo "Review with: git diff    Revert with: git checkout -- ."
    ;;

  strip-bash)
    changed=0; skipped=0
    echo "Injecting: disallowedTools: Bash"
    $FORCE || echo "(DRY RUN -- add --force to write)"
    echo ""
    for f in "${AGENT_FILES[@]}"; do
      has_frontmatter "$f" || { (( ++skipped )); continue; }
      if frontmatter_has "tools" "$f" || frontmatter_has "disallowedTools" "$f"; then
        (( ++skipped )); continue
      fi
      if $FORCE; then
        inject_line "$f" "disallowedTools: Bash"
        echo "WROTE: $f"
      else
        echo "WOULD WRITE: $f"
      fi
      (( ++changed ))
    done
    echo ""
    if $FORCE; then echo "Files changed: $changed | left as-is: $skipped"; else echo "Files that would change: $changed | left as-is: $skipped"; fi
    $FORCE && echo "Review with: git diff    Revert with: git checkout -- ."
    ;;

  *)
    echo "Unknown mode: $MODE (use: audit | apply | strip-bash)" >&2
    exit 1
    ;;
esac
