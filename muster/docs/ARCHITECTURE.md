# Architecture — Muster

This document describes Muster's design. It contains design reasoning, not a
record of verified production behavior; behavior in any given environment should
be verified there.

## Purpose

Organize, monitor, and control a large set of AI agent-prompt files with an
emphasis on determinism and auditability: you can always see which agents are
active, what they may do, and when that changed.

## Two planes

**Control plane (deterministic).** The source of truth is a single manifest,
`control-plane/roster.json`. It records every agent's id, division, description,
tool permissions, content hash, status (`active`/`benched`/`retired`), owner,
and review date. Changing what is deployed = editing this file in a reviewed
commit. No LLM makes control decisions.

**Query plane (advisory).** A read-only concierge agent
(`agents/roster-concierge.md`) answers "which agent handles X", "what is active
in <division>", "what changed". It reads the roster only and cannot install,
edit, or activate anything.

**Rationale.** Separating a deterministic control plane from an advisory query
plane keeps every deployment decision diffable and auditable, and keeps the one
component with real authority (the manifest plus scripts) free of
non-deterministic model behavior. See `DESIGN-RATIONALE.md`.

## Enforcement flow

```
  agent-prompt collection (division folders of .md files)
        │  update / pull
        ▼
  gen-roster.py --update ──► roster.json  (new agents benched; changes flagged)
        │  human review + commit  (this commit IS the hire/fire record)
        ▼
  roster-sync.py sync ──► installs ONLY active agents to the agents dir
        │
        ▼
  roster-sync.py drift  (cron) ──► reports prompt-side or install-side hash drift
```

Two SHA-256 checks, both against the hash recorded in the roster:
1. **Prompt set vs roster** — catches prompt files changed without a reviewed
   roster update. `sync` refuses to run on mismatch.
2. **Installed vs roster** — catches drift/tampering in the live agents dir.
   `drift` reports (non-zero exit for cron/CI); `sync --force` heals.

## Hardening dependency

`tools/harden-agent-tools.sh` should be run on the prompt set **before** roster
generation, so the roster records least-privilege `tools:` lines and locks them
by hash. Any later attempt to widen a permission then shows as a hash mismatch.

## Deployment considerations (guidance, not prescriptions)

- A headless host is a natural fit; the tooling is cron-friendly and needs no
  inbound network.
- Agents typically need **outbound** access (model API, task endpoints), not
  **inbound**. Expose no public inbound unless a specific function requires it.
- Any agent action with external effect (sending, posting, spending, writing to
  external data) should queue for human approval rather than execute unattended.
- These controls reduce and contain risk; they do not eliminate it. Unattended
  agent systems carry residual risk (including prompt injection from untrusted
  content) that hardening mitigates but does not remove.

## Not prescribed here

- Which agents to activate for a given deployment.
- Model or runtime-framework selection.
- Repository layout relative to the managed prompt collection.
