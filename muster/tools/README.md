# Agent Roster Starter Kit

Deterministic control plane for managing an agency-agents fork.
Three pieces: a manifest generator, an enforcement/drift tool, and a
read-only concierge agent for fast lookups.

Design principle: **hiring and laying off agents is a reviewed git commit,
not an LLM decision.** The roster is authority; scripts enforce it; the
concierge only reads it.

## Files

| File | Purpose |
|---|---|
| `gen-roster.py` | Scan the fork, build/refresh `roster.json` (the manifest) |
| `roster-sync.py` | Install active agents, remove benched ones, detect drift |
| `roster-concierge.md` | Read-only agent prompt for "which agent does X?" queries |

Python 3 stdlib only. No network access. No third-party dependencies.

## Quick start

```bash
# 1. Generate the roster (everything starts BENCHED -- nothing goes live
#    without an explicit decision)
./gen-roster.py /path/to/fork -o /path/to/fork/roster.json

# 2. Hire: edit roster.json, set "status": "active" (and "owner") for the
#    agents you want. Commit the change -- that commit IS the hiring record.

# 3. Deploy exactly the active set
./roster-sync.py sync roster.json /path/to/fork --force

# 4. Install the concierge (also via the roster: add it to the fork,
#    regenerate with --update, activate it, sync)
```

## Day-to-day

```bash
./roster-sync.py status roster.json          # who's active, per division
./roster-sync.py drift  roster.json FORK     # integrity check (cron/CI-able)
./roster-sync.py sync   roster.json FORK     # dry-run reconcile
./roster-sync.py sync   roster.json FORK --force
```

**Laying off:** set status to `benched`, commit, sync. The installed file is
removed. Only files this tool installed are ever touched (tracked in
`.roster-managed.json` in the agents dir); your hand-made agents are never
deleted.

**After every upstream merge:**
```bash
./gen-roster.py FORK -o roster.json --update
```
- New upstream agents appear as `benched` (never auto-active).
- Agents whose content changed get a `CONTENT CHANGED -- re-review` note and
  a new hash. Statuses/owners/notes you set are preserved.
- Removed agents are marked `retired` (kept for audit history).
- `sync` refuses to run while the repo and roster hashes disagree, so an
  upstream edit cannot reach your machines without passing through a roster
  regeneration you review and commit.

**Optional stricter policy:** if you want changed agents to be auto-benched
until re-reviewed (rather than staying active with a warning note), that is a
three-line change in `gen-roster.py` where the CONTENT CHANGED note is set --
set `e["status"] = "benched"` there.

## Integrity model

Two hash checks, both against the roster's recorded SHA-256:

1. **Repo vs roster** -- catches prompt files edited without a reviewed
   roster update (e.g. a malicious or accidental upstream change).
   `sync` hard-refuses on mismatch.
2. **Installed vs roster** -- catches tampering or staleness in the live
   agents directory. `drift` reports it (non-zero exit for cron/CI alerting);
   `sync --force` heals it by reinstalling the roster-approved version.

## Pairing with the tools hardening

Run `harden-agent-tools.sh` BEFORE generating
the roster, so the roster records the least-privilege `tools:` lines and the
hashes lock them in. Any later attempt to widen an agent's permissions then
shows up as a hash mismatch.

## Concierge usage

Once installed, ask things like:
- "Which agent handles KQL / detection engineering work?"
- "What's active in the security division?"
- "What changed since the last upstream merge?"
- "Which active agents still have INHERIT_ALL tool permissions?"

It answers from `roster.json` only, reports benched agents as
recommendations to activate (not as available), and responds to change
requests with the exact manual roster edit + sync command for a human to run.
