# Repository-wide agent policy

This policy applies to the entire repository. Agents MUST work within the
approved Block and Subdivision, use deny-by-default authorization, and comply
with [the pull-request contract](docs/pull-request-contract.md).

## Hard boundaries

Agents MUST NOT:

- use `sudo` or modify files outside this repository;
- access `~/.ssh`, browser profiles, browser cookies, browser password stores,
  credential stores, or unrelated environment variables or secrets;
- access or modify `~/.codex` unless a future, reviewed task explicitly
  authorizes the exact access;
- change Codex Desktop configuration;
- read Codex local SQLite state unless a future reviewed phase explicitly
  authorizes it;
- execute arbitrary shell commands or use `shell=True`;
- download or execute third-party binaries;
- add hidden network calls or telemetry;
- delete Codex Projects, delete user data, or perform destructive filesystem
  operations;
- invoke `project/create`, `project/update`, `project/move`, or
  `project/delete` without exact, reviewed authorization;
- invoke any real Codex RPC in PR1.

Repository-local, task-relevant development commands are permitted only when
their effects are understood and bounded. Agents MUST NOT broaden authorization
by inference.

## Preferred practices

Agents SHOULD prefer the Python standard library, explicit data models,
deterministic tests, fake or mock transports, small diffs, explicit errors,
documented assumptions, reversible changes, and deny-by-default authorization.

## Planning and delivery

Blocks and Subdivisions are stable roadmap identities. PR numbers are delivery
evidence and MUST NOT become stable roadmap identities. A closed, replaced,
split, or repeated PR MUST NOT invalidate the roadmap structure.

Every implementation PR MUST follow
[`docs/pull-request-contract.md`](docs/pull-request-contract.md), accurately
record executed checks, and complete the mandatory safety review.
