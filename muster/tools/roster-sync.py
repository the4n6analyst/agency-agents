#!/usr/bin/env python3
"""
roster-sync.py -- Deterministic enforcement for roster.json.

Installs ONLY agents marked "active" in the roster into the target agents
directory (default: ~/.claude/agents), removes managed agents that are no
longer active, and verifies SHA-256 hashes in both directions:

  1. Repo integrity : repo file hash vs roster hash
                      (catches edits that bypassed roster review)
  2. Install integrity: installed file hash vs roster hash
                      (catches tampering/drift in the live agents dir)

Modes:
  sync   -- reconcile install dir with roster (DRY RUN unless --force)
  drift  -- report-only integrity check, no changes ever
  status -- one-line-per-agent roster overview

Only files this tool installed are ever touched: it keeps a manifest
(.roster-managed.json) in the target dir and will not delete files it does
not manage.

Usage:
  ./roster-sync.py sync   ROSTER REPO_DIR [--dest ~/.claude/agents] [--force]
  ./roster-sync.py drift  ROSTER REPO_DIR [--dest ~/.claude/agents]
  ./roster-sync.py status ROSTER

No network access. Python 3 stdlib only.
"""

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

MANAGED = ".roster-managed.json"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def load_roster(path: Path) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {e["id"]: e for e in doc["agents"]}


def dest_name(agent: dict) -> str:
    # flat install: division prefix keeps names unique and greppable
    return agent["id"].replace(":", "--") + ".md"


def load_managed(dest: Path) -> dict:
    f = dest / MANAGED
    if f.exists():
        return json.loads(f.read_text())
    return {}


def save_managed(dest: Path, managed: dict):
    (dest / MANAGED).write_text(json.dumps(managed, indent=2) + "\n")


def check_repo_integrity(agents: dict, repo: Path):
    """Return list of (id, problem) for repo-side hash mismatches."""
    problems = []
    for aid, a in agents.items():
        if a["status"] == "retired":
            continue
        src = repo / a["path"]
        if not src.exists():
            problems.append((aid, "MISSING in repo (roster not updated?)"))
            continue
        if sha256_file(src) != a["sha256"]:
            problems.append((aid, "HASH MISMATCH repo vs roster -- "
                                  "file edited without roster review"))
    return problems


def cmd_status(agents):
    by_div = {}
    for a in agents.values():
        by_div.setdefault(a["division"], []).append(a)
    for div in sorted(by_div):
        print(f"\n[{div}]")
        for a in sorted(by_div[div], key=lambda x: x["id"]):
            flag = {"active": "●", "benched": "○", "retired": "✗"}.get(a["status"], "?")
            print(f"  {flag} {a['status']:<8} {a['name']:<42} tools: {a['tools'][:60]}")
    total = {}
    for a in agents.values():
        total[a["status"]] = total.get(a["status"], 0) + 1
    print(f"\nTotals: {total}")


def cmd_drift(agents, repo: Path, dest: Path):
    rc = 0
    print("== Repo integrity (repo file vs roster hash) ==")
    probs = check_repo_integrity(agents, repo)
    if probs:
        rc = 1
        for aid, msg in probs:
            print(f"  DRIFT  {aid}: {msg}")
    else:
        print("  OK -- all non-retired roster entries match repo contents")

    print("\n== Install integrity (installed files vs roster hash) ==")
    managed = load_managed(dest)
    active = {aid: a for aid, a in agents.items() if a["status"] == "active"}
    any_prob = False
    for aid, a in active.items():
        f = dest / dest_name(a)
        if not f.exists():
            print(f"  DRIFT  {aid}: active in roster but NOT installed")
            any_prob = True
        elif sha256_file(f) != a["sha256"]:
            print(f"  DRIFT  {aid}: installed file hash differs from roster "
                  f"-- possible tampering or stale install")
            any_prob = True
    for name in list(managed):
        aid = managed[name]
        if aid not in active:
            f = dest / name
            if f.exists():
                print(f"  DRIFT  {aid}: installed but no longer active in roster")
                any_prob = True
    if not any_prob:
        print("  OK -- installed set matches roster exactly")
    else:
        rc = 1
    print("\nExit code:", rc, "(non-zero = drift found; suitable for cron/CI)")
    return rc


def cmd_sync(agents, repo: Path, dest: Path, force: bool):
    # Refuse to install anything if repo integrity is broken.
    probs = check_repo_integrity(agents, repo)
    if probs:
        print("REFUSING TO SYNC -- repo/roster integrity problems "
              "(fix or regenerate roster with --update, review, then retry):")
        for aid, msg in probs:
            print(f"  {aid}: {msg}")
        return 2

    dest.mkdir(parents=True, exist_ok=True)
    managed = load_managed(dest)
    active = {aid: a for aid, a in agents.items() if a["status"] == "active"}

    installs, removals = [], []
    for aid, a in active.items():
        f = dest / dest_name(a)
        if not f.exists() or sha256_file(f) != a["sha256"]:
            installs.append(a)
    for name, aid in list(managed.items()):
        if aid not in active:
            removals.append(name)

    if not force:
        print("(DRY RUN -- add --force to apply)\n")
    print(f"Active in roster: {len(active)} | to install/update: "
          f"{len(installs)} | to remove: {len(removals)}")
    for a in installs:
        print(f"  + {dest_name(a)}")
        if force:
            shutil.copy2(repo / a["path"], dest / dest_name(a))
            managed[dest_name(a)] = a["id"]
    for name in removals:
        print(f"  - {name}")
        if force:
            f = dest / name
            if f.exists():
                f.unlink()
            managed.pop(name, None)
    if force:
        # register anything active that was already correct
        for aid, a in active.items():
            managed[dest_name(a)] = aid
        save_managed(dest, managed)
        print(f"\nApplied. Managed manifest updated: {dest / MANAGED}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["sync", "drift", "status"])
    ap.add_argument("roster")
    ap.add_argument("repo", nargs="?", default=".")
    ap.add_argument("--dest", default=str(Path.home() / ".claude" / "agents"))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    agents = load_roster(Path(args.roster))
    repo = Path(args.repo).resolve()
    dest = Path(args.dest).expanduser()

    if args.mode == "status":
        return cmd_status(agents)
    if args.mode == "drift":
        return cmd_drift(agents, repo, dest)
    return cmd_sync(agents, repo, dest, args.force)


if __name__ == "__main__":
    sys.exit(main())
