#!/usr/bin/env python3
"""
gen-roster.py -- Generate/refresh roster.json: the deterministic control-plane
manifest for an agency-agents fork.

Scans agent markdown files, extracts division / name / description / tool
permissions from YAML frontmatter, computes a SHA-256 content hash per agent,
and writes a single roster.json that acts as the source of truth for which
agents exist and which are active.

Statuses:
  active   -- installed by roster-sync
  benched  -- known, reviewed, but not installed ("laid off")
  retired  -- file no longer exists upstream; kept for audit history

Behavior:
  - First run: every discovered agent is created as "benched" (nothing goes
    live without an explicit, reviewable decision to activate it).
  - --update: re-scan and merge. Preserves status/owner/notes for existing
    agents, updates hash/description if the file changed (and flags it),
    adds new agents as "benched", marks vanished agents "retired".

Usage:
  ./gen-roster.py REPO_DIR [-o roster.json] [--update]

No network access. Requires only Python 3 stdlib.
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

EXCLUDE_DIRS = {".git", ".github", "integrations", "examples", "scripts"}
# Case-sensitive on purpose: repo doc files are UPPERCASE (README.md,
# SECURITY.md); agent files are lowercase (security-architect.md).
EXCLUDE_NAMES = re.compile(r"^(README|CONTRIBUTING|SECURITY)")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def parse_frontmatter(text: str) -> dict:
    """Minimal single-level YAML frontmatter parser (key: value lines only).
    Nested structures (e.g. services:) are skipped intentionally."""
    fm = {}
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return fm
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip().strip('"').strip("'")
            if val:  # skip keys opening nested blocks
                fm[key] = val
    return fm


def discover_agents(repo: Path):
    for p in sorted(repo.rglob("*.md")):
        rel = p.relative_to(repo)
        if rel.parts[0] in EXCLUDE_DIRS:
            continue
        if EXCLUDE_NAMES.match(p.name):
            continue
        yield p


def build_entry(repo: Path, p: Path) -> dict:
    rel = p.relative_to(repo)
    text = p.read_text(encoding="utf-8", errors="replace")
    fm = parse_frontmatter(text)
    division = rel.parts[0] if len(rel.parts) > 1 else "root"
    tools = fm.get("tools", "")
    disallowed = fm.get("disallowedTools", "")
    if tools:
        effective = tools
    elif disallowed:
        effective = f"ALL EXCEPT: {disallowed}"
    else:
        effective = "INHERIT_ALL (no tools field -- full inheritance)"
    return {
        "id": str(rel.with_suffix("")).replace("/", ":"),
        "name": fm.get("name", p.stem),
        "division": division,
        "path": str(rel),
        "description": fm.get("description", "(no frontmatter description)"),
        "tools": effective,
        "sha256": sha256_file(p),
        "status": "benched",
        "owner": "",
        "notes": "",
        "added": date.today().isoformat(),
        "last_reviewed": "",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", help="Path to the agents repo/fork")
    ap.add_argument("-o", "--output", default="roster.json")
    ap.add_argument("--update", action="store_true",
                    help="Merge with existing roster, preserving decisions")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    out = Path(args.output)

    scanned = {}
    for p in discover_agents(repo):
        e = build_entry(repo, p)
        scanned[e["id"]] = e

    changed, new, retired = [], [], []

    if args.update and out.exists():
        existing = {e["id"]: e for e in json.loads(out.read_text())["agents"]}
        merged = {}
        for aid, e in scanned.items():
            if aid in existing:
                old = existing[aid]
                # preserve human decisions
                for k in ("status", "owner", "notes", "added", "last_reviewed"):
                    e[k] = old.get(k, e[k])
                if old.get("sha256") != e["sha256"]:
                    changed.append(aid)
                    e["notes"] = (e["notes"] + " | " if e["notes"] else "") + \
                        f"CONTENT CHANGED on {date.today().isoformat()} -- re-review"
            else:
                new.append(aid)
            merged[aid] = e
        for aid, old in existing.items():
            if aid not in scanned and old.get("status") != "retired":
                old["status"] = "retired"
                old["notes"] = (old.get("notes", "") + " | " if old.get("notes") else "") + \
                    f"file removed upstream, retired {date.today().isoformat()}"
                retired.append(aid)
                merged[aid] = old
            elif aid not in scanned:
                merged[aid] = old
        roster_agents = merged
    else:
        roster_agents = scanned
        new = list(scanned)

    counts = {}
    for e in roster_agents.values():
        counts[e["status"]] = counts.get(e["status"], 0) + 1

    doc = {
        "schema": 1,
        "generated": date.today().isoformat(),
        "repo": str(repo),
        "summary": counts,
        "agents": sorted(roster_agents.values(), key=lambda e: (e["division"], e["id"])),
    }
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Roster written: {out}  ({len(roster_agents)} agents)")
    print(f"  Status counts: {counts}")
    if new:
        print(f"  New (benched by default): {len(new)}")
    if changed:
        print(f"  CONTENT CHANGED since last roster (re-review these): {len(changed)}")
        for aid in changed:
            print(f"    - {aid}")
    if retired:
        print(f"  Retired (removed upstream): {len(retired)}")
        for aid in retired:
            print(f"    - {aid}")


if __name__ == "__main__":
    sys.exit(main())
