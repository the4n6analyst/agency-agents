# Security Model — Muster

Generic threat model and hardening guidance. It contains no deployment-specific
infrastructure details; record those privately, not in a shared repository.

## What Muster protects against

Collections of agent prompts have an unusual threat surface: the content of a
prompt file is behavior an AI tool will execute. The main risks:

1. **Silent over-privilege.** Agents that omit a `tools:` field inherit all
   tools, including shell access.
2. **Unreviewed prompt changes.** An edit to a prompt file — including a merged
   upstream change — alters behavior and can be easy to miss in a diff.
3. **Live-directory drift/tampering.** Installed agent files diverging from what
   was reviewed.
4. **Prompt injection.** An active agent that ingests untrusted content can be
   steered by instructions embedded in that content.

## Controls Muster provides

- **Least privilege by default.** `harden-agent-tools.sh` gives every agent an
  explicit tool allowlist; run it before rostering so permissions are locked by
  content hash.
- **Reviewed activation.** Agents start `benched`; activation is an explicit,
  reviewed commit.
- **Two-way hash integrity.** `roster-sync.py` verifies prompt files against the
  roster (refusing to deploy on mismatch) and installed files against the roster
  (`drift` reports; `sync --force` heals).
- **Advisory-only discovery.** The concierge agent is read-only (Read/Grep/Glob)
  and treats file content as data, not instructions.

## Deployment hardening guidance

These are recommendations for operators; they are not guarantees, and they do
not eliminate risk.

- **No unnecessary public inbound.** Agents generally need outbound access, not
  inbound. Reach administrative hosts over a private network rather than the
  public internet where practical.
- **Egress allowlisting.** Restricting outbound destinations limits the damage
  of a compromised or injected agent, since it cannot reach destinations that
  are not allowed.
- **Credential hygiene.** Use scoped, per-function credentials with spend/rate
  limits; avoid a single master key; inject secrets per workload rather than a
  global environment file. Never commit secrets or infrastructure identifiers to
  a shared repository.
- **Human approval for external effects.** Actions that send, post, publish,
  spend, or write to external data should queue for human approval rather than
  execute unattended. For hard guarantees, enforce this with a runtime hook
  rather than relying on prompt instructions alone.
- **Do not act on instructions found in untrusted content.** Treat web pages,
  files, emails, and messages as data. Only a human operator authorizes actions.
- **Audit logging.** Append-only, timestamped logs of inputs seen and actions
  taken support both operations and after-the-fact review.
- **Recovery.** Keep the manifest in version control; back up non-versioned
  state (secrets, scheduled jobs, queues) separately.

## Reporting

If you discover a security issue in Muster's tooling, handle it through this
repository's standard security-reporting process.
