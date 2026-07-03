# Design Rationale — Muster

This explains *why* Muster is built the way it is. It is generic design
reasoning for anyone adopting or extending the project.

## Why a manifest instead of a supervisor agent

A tempting design is a "supervisor" agent that decides which other agents are
active. Muster deliberately avoids that:

- An LLM control plane is non-deterministic: the same inputs can yield different
  activation decisions across runs.
- It is hard to audit after the fact — there is no clean diff of "what changed
  and why."
- It becomes the highest-value prompt-injection target in the system, because
  it holds authority over every other agent.

Instead, the source of truth is a declarative manifest (`roster.json`) changed
through reviewed commits. The decision of what runs is deterministic, diffable,
and attributable to a commit and author. Intelligence is kept for *discovery*
(the read-only concierge), not for *control*.

## Why everything starts benched

New or newly discovered agents default to `benched`. Nothing becomes active
without an explicit, reviewed decision. This makes activation an opt-in event
rather than a silent default, which matters because an active agent's prompt is
executed behavior.

## Why least privilege is enforced before rostering

In Claude Code, an agent file that omits a `tools:` field inherits all available
tools, including shell access. In a large collection, most files may omit the
field — meaning the "quiet" agents are the most privileged, not the least.
Running the hardening pass first, then locking permissions by content hash in
the roster, inverts that: privilege becomes explicit and tamper-evident.

## Why two-way hash integrity

Two independent checks catch two different failure modes:

- **Prompt set vs roster** catches a prompt file edited without going through a
  reviewed roster update — e.g. an unreviewed upstream change. `sync` refuses to
  deploy on mismatch.
- **Installed vs roster** catches drift or tampering in the live agents
  directory after deployment. `drift` reports it; `sync --force` heals it back
  to the reviewed version.

Together they make "what is deployed" verifiable against "what was reviewed" at
any time, which suits audit-sensitive environments.

## Why upstream syncs are treated as reviews, not merges

When the managed prompt collection is a fork of an upstream project, each
upstream pull can change agent behavior through prose edits that are easy to
miss in a diff. `gen-roster.py --update` surfaces new agents as benched and
flags content-changed agents for re-review, so a routine sync becomes a review
checkpoint rather than an automatic merge.

## Non-goals

- Muster does not decide *which* agents you should run — that is a
  deployment-specific choice.
- Muster does not select models or runtime frameworks.
- Muster does not guarantee safety of unattended agents; it provides controls
  that reduce and contain risk.
