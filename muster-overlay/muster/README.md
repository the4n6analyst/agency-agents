# Muster

**A deterministic, auditable control plane for AI agent-prompt rosters.**

Muster manages a large collection of AI agent-prompt files (such as the
`agency-agents` project) the way you'd manage personnel: every agent is a line
in a reviewed manifest with a status, an owner, tool permissions, and a content
hash. Turning an agent on or off is a reviewed commit — not a runtime decision
made by a model.

## Why

Collections of agent prompts share an unusual property: the "product" is
instructions that AI tools will obey. A change to a prompt file is a change to
behavior, and an agent that omits a `tools:` field inherits every available tool
(including shell access). Muster makes the active set explicit, least-privilege
by default, and diffable, so you can see — and review — exactly which agents are
live and what they can do.

## Design in one line

Hiring or laying off an agent is a **reviewed commit** that changes its `status`
in `roster.json`. Deterministic scripts enforce the manifest; a read-only
"concierge" agent answers "which agent does what" but cannot act.

## Layout

```
muster/
├── README.md                 this file
├── LICENSE                   MIT
├── docs/
│   ├── ARCHITECTURE.md       two-plane design + enforcement flow
│   ├── DESIGN-RATIONALE.md   why a manifest instead of a supervisor agent
│   └── SECURITY.md           threat model + hardening guidance
├── control-plane/
│   └── roster.json           source of truth: every agent + status
├── tools/
│   ├── harden-agent-tools.sh enforce least-privilege tool permissions
│   ├── gen-roster.py         build/refresh roster.json from the prompt set
│   ├── roster-sync.py        install active agents; detect drift
│   └── README.md             kit usage details
└── agents/
    └── roster-concierge.md   read-only "which agent does what" advisor
```

Python 3 standard library only. No third-party dependencies. No network access.

## Quick start

Assume `AGENTS_DIR` is the directory holding your agent-prompt files (the
division folders). Run tool commands from the repo root.

```bash
# 0. (recommended) enforce least-privilege tool permissions on the prompt set
muster/tools/harden-agent-tools.sh apply "$AGENTS_DIR" --tools "Read, Grep, Glob" --force

# 1. build the roster (every agent starts BENCHED — nothing is active until
#    explicitly hired via a reviewed commit)
muster/tools/gen-roster.py "$AGENTS_DIR" -o muster/control-plane/roster.json
#    after upstream changes:
muster/tools/gen-roster.py "$AGENTS_DIR" -o muster/control-plane/roster.json --update

# 2. hire: edit muster/control-plane/roster.json -> set "status": "active"
#    (and "owner"), then commit. That commit IS the hiring record.

# 3. deploy exactly the active set
muster/tools/roster-sync.py sync muster/control-plane/roster.json "$AGENTS_DIR" --force

# 4. monitor (cron-friendly; non-zero exit signals drift)
muster/tools/roster-sync.py drift  muster/control-plane/roster.json "$AGENTS_DIR"
muster/tools/roster-sync.py status muster/control-plane/roster.json
```

## Integrity model

Two SHA-256 checks, both against the hash recorded in the roster:

1. **Prompt set vs roster** — catches prompt files edited without a reviewed
   roster update. `sync` refuses to run on mismatch.
2. **Installed vs roster** — catches drift/tampering in the live agents
   directory. `drift` reports (non-zero exit for cron/CI); `sync --force` heals.

## Relationship to the agent-prompt collection

Muster does not vendor the prompt collection it manages. Place them together in
whatever way suits you (same repo, git submodule, or sibling checkout). The
tools take the prompt-set path as an argument. The bundled `roster.json` is an
example generated against a public agent-prompt set; regenerate it against your
own with `gen-roster.py`.

## License

MIT. See `LICENSE`. Muster is a management layer; the agent-prompt collections
it manages carry their own licenses — check and comply with those separately.
