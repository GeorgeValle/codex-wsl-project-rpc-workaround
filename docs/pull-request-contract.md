# Pull-request documentation contract

Pull-request bodies are durable engineering records. Every implementation PR
MUST use the sections below unless a field is explicitly marked **Not
applicable** with a reason. The record must be understandable without
reconstructing context from commits or private conversations.

## Quality rules

A PR body MUST:

- explain both **what** changed and **why**;
- separate observed facts from hypotheses;
- record its execution environment, residual risk, and deferred work;
- never claim a check passed unless it was actually executed;
- record every exact RPC capability and method exercised;
- never expose secrets, secret values, or personal paths;
- avoid vague claims such as “works” or “safe” without qualification;
- treat PR numbers as historical delivery evidence only.

Blocks and Subdivisions are stable roadmap identities; PR numbers are not.
Their identity remains stable if a PR is closed, replaced, repeated, or split.

## Required PR body structure

### Block

```markdown
## Block

- Block: B1 — Foundation and Safety
- Subdivision: 1.1 — Repository scaffold, project context, requirements, and agent boundaries
```

Use the exact stable roadmap identity.

### Delivery

Include:

```markdown
## Delivery

- Role:
- Classification:
- Review mode:
- Capability level:
- Mutation authorization:
```

Use applicable controlled values:

- **Role:** `PRIMARY`, `FOLLOW_UP`, `VALIDATION`, `REPLACEMENT`
- **Classification:** `FOUNDATION`, `DOCUMENTATION`, `FEATURE`,
  `HARDENING`, `SECURITY`, `VALIDATION`, `GOVERNANCE`
- **Review mode:** `HUMAN_GATED`, `BOUNDED_AUTO_REPAIR`
- **Capability level:** `NON_FUNCTIONAL`, `MOCK_ONLY`, `READ_ONLY`,
  `MUTATING`
- **Mutation authorization:** `NONE`, `PROJECT_CREATE_ONLY`,
  `PROJECT_UPDATE_ONLY`

Mutation authorization MUST NOT be implied. It must name only an explicitly
approved capability.

### Summary

Provide concise bullets describing the delivered result.

### What

Explain concretely which files, behavior, interfaces, and documentation
changed.

### Why

Explain why the change exists, the problem it solves, and why its boundary and
approach were selected.

### Requirements / Objectives

Use this table instead of application-style User Stories unless future use
cases justify adding them:

| ID | Requirement / objective | Before | After | Evidence | Deferred |
|---|---|---|---|---|---|

### Scope

Include both headings:

```markdown
## Scope

### In scope

### Out of scope
```

Out-of-scope content is mandatory for every capability-changing PR.

### Compatibility and impact

Explicitly address each item:

- Public/internal API
- Python/package model
- Codex app-server
- Codex local state
- WSL/Windows
- Network
- Dependencies
- Breaking changes
- Migration/state changes

“No impact” is acceptable when accurate.

### Execution environment

Include selection checkboxes:

```markdown
- [ ] Codex Cloud
- [ ] Codex Desktop / WSL
- [ ] Windows native
- [ ] Manual / other
```

Then include:

| Environment / OS | Runtime / tool versions | Capabilities used | Required secrets |
|---|---|---|---|

Never expose secret values.

### Environment-specific limitations

State observed limitations, what was not exercised, and residual risk.

### Checks

| Environment | Command / audit | Result / reason / remaining risk | Pending action |
|---|---|---|---|

Use `PASS`, `FAIL`, `NOT RUN`, `NOT APPLICABLE`, or `PARTIAL`.
`PASS` is forbidden for a check that was not actually executed.

### Documentation updated

List every documentation file changed, or explain why none changed.

### Safety review

This section is mandatory. Answer `NO` or `YES — <exact justification>`:

```text
Files outside repository accessed:
~/.codex accessed:
Codex Desktop configuration modified:
Real app-server RPCs invoked:
RPC methods invoked:
Mutation RPCs invoked:
Network behavior added to project code:
Third-party binaries downloaded/executed:
Secrets accessed:
User-specific paths committed:
```

For any RPC usage, list exact method names. For secrets, state only whether
they were required or accessed—never disclose values.

### Risks / Notes

Record known risks, uncertainties, assumptions, and residual concerns.

### Next

Name the next Block/Subdivision or state explicitly that progression requires
human approval.

## Complete concise example: foundation baseline

```markdown
## Block

- Block: B1 — Foundation and Safety
- Subdivision: 1.1 — Repository scaffold, project context, requirements, and agent boundaries

## Delivery

- Role: PRIMARY
- Classification: FOUNDATION
- Review mode: HUMAN_GATED
- Capability level: NON_FUNCTIONAL
- Mutation authorization: NONE

## Summary

- Establishes project context, safety requirements, roadmap, and agent policy.
- Adds minimal package metadata and an inert package marker.

## What

Replaced the minimal overview and added normative requirements, documentation
indexes, roadmap records, PR governance, test policy, and inert Python scaffold.

## Why

The project needs auditable constraints before protocol or Codex capabilities.
The narrow foundation avoids interacting with user state while later work is
researched and reviewed.

## Requirements / Objectives

| ID | Requirement / objective | Before | After | Evidence | Deferred |
|---|---|---|---|---|---|
| SAFE-003 | Non-functional foundation | Not documented | Explicitly enforced | Policy and static audit | All RPC capability |
| PY-003 | Inert package import | No package | Marker-only import | Import smoke test | Test execution baseline |

## Scope

### In scope

Documentation, policies, declarative metadata, inert source, and test-tree
policy.

### Out of scope

RPCs, process handling, network behavior, Codex state, a CLI, dependencies,
functional tests, and mutation.

## Compatibility and impact

- Public/internal API: Version marker only; no functional API.
- Python/package model: Adds Python >=3.11, PEP 517, setuptools, and src layout.
- Codex app-server: No impact.
- Codex local state: No access or changes.
- WSL/Windows: Documents WSL-first target; no runtime behavior.
- Network: No behavior added.
- Dependencies: No runtime dependencies.
- Breaking changes: None.
- Migration/state changes: None.

## Execution environment

- [ ] Codex Cloud
- [ ] Codex Desktop / WSL
- [ ] Windows native
- [x] Manual / other

| Environment / OS | Runtime / tool versions | Capabilities used | Required secrets |
|---|---|---|---|
| Repository development container | Python 3.11+, Git | Local static checks only | None |

## Environment-specific limitations

No real Codex installation, Desktop environment, app-server, Windows backend,
or WSL integration was exercised. Functional behavior remains unvalidated and
deliberately absent.

## Checks

| Environment | Command / audit | Result / reason / remaining risk | Pending action |
|---|---|---|---|
| Development container | `git diff --check` | PASS | None |
| Development container | Parse `pyproject.toml` with `tomllib` | PASS | None |
| Development container | Isolated inert import | PASS | None |
| Development container | Compile `src` | PASS | None |
| Development container | Repository-local prohibited-code audit | PASS; static audit only | Reassess with each capability change |

## Documentation updated

`README.md`, `AGENTS.md`, `projects-requirements.md`, `docs/README.md`,
roadmap records, PR contract, and `tests/README.md`.

## Safety review

Files outside repository accessed: NO
~/.codex accessed: NO
Codex Desktop configuration modified: NO
Real app-server RPCs invoked: NO
RPC methods invoked: NO
Mutation RPCs invoked: NO
Network behavior added to project code: NO
Third-party binaries downloaded/executed: NO
Secrets accessed: NO
User-specific paths committed: NO

## Risks / Notes

The reported incident represents one affected environment. Protocol causes
remain hypotheses pending sourced research.

## Next

Subdivision 1.2 requires human approval before packaging and test execution
work begins.
```
