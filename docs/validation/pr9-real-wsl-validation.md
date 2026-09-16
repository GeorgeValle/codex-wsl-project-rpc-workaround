# Subdivision 2.3 — PR #9 Real WSL Validation Evidence

## Scope

This record captures one explicitly authorized real-product, read-only
validation performed by a human operator in a local Windows/WSL environment.
Codex Cloud did not execute or independently observe the run. PR #9 is
historical delivery evidence, not a stable roadmap identity.

## Tested repository HEAD

`f9f61486339029f3743db02b5ba03c4d06d627fe`

## Environment

- Windows 11 host
- WSL2
- Ubuntu 24.04.4 LTS
- Python 3.12.3
- Operator-confirmed Codex Desktop WSL executable (ELF 64-bit, x86-64,
  regular executable file)

No personal path, username, Project data, credential, token, raw stderr, or raw
Codex state is recorded. The separately installed pnpm Codex CLI was not used.

## Authorization

The operator explicitly authorized one execution of
`tools/run_read_only_project_list.py` with the real-execution acknowledgement,
the operator-selected executable, and the operator's WSL home. The runner
started and owned a separate app-server process; it did not attach to, modify,
terminate, or control the Desktop-owned app-server.

The authorized protocol flow was limited to:

1. `initialize`
2. `initialized` notification
3. `project/list`

Mutation authorization remained `NONE`. No other RPC was intentionally invoked
by repository code.

## Result

| Evidence field | Sanitized observation |
|---|---|
| Observed UTC timestamp | `2026-09-16T03:33:02.099070+00:00` |
| Cleanup outcome | `graceful` |
| Initialize attempted / succeeded | `true` / `true` |
| Initialized sent | `true` |
| Project list attempted / succeeded | `true` / `true` |
| Returned page count | `0` |
| Has more | `false` |
| Root representation categories | `[]` |
| Platform family / OS | `unix` / `linux` |
| Codex-home category | `posix_absolute` |
| Mutation attempted | `false` |
| Direct state inspection | `false` |
| Network effects | `NOT_ESTABLISHED` |
| Helper-process effects | `NOT_ESTABLISHED` |
| Product-state impact | `NOT_ESTABLISHED` |
| Target provenance | `operator_confirmed_openai_codex_unverified_by_repository` |
| Target revision mapping | `NOT_ESTABLISHED` |
| Target version | `unobserved` |
| Protocol reference SHA | `7efa9d96fb34c3cafe108a3c870bfc33e5635772` |

## Desktop comparison

- Independently launched app-server: `project/list` **SUCCESS**, returned page
  count `0`, `has_more=false`.
- Desktop: multiple Projects visible by manual operator observation.
- Classification: `DIVERGENCE_OBSERVED`.

This establishes only that the independently launched app-server's successful
result did not correspond to the non-empty Project list visible in Desktop in
this tested context. The cause is `NOT_ESTABLISHED`.

## What this establishes

- The selected real WSL Codex product process started successfully.
- `initialize` succeeded and the `initialized` notification was sent.
- Real `project/list` succeeded and returned a valid empty page.
- No Project mutation was attempted.
- Repository code did not directly inspect Codex state.
- Cleanup completed gracefully.
- The independent app-server result diverged from the non-empty Desktop-visible
  Project list in this tested context.

## What this does NOT establish

- Physical store identity or Desktop/app-server store equivalence.
- The reason for the divergence.
- Installed-binary mapping to the pinned source SHA or the target version.
- Filesystem-side-effect-free startup.
- Absence of product network effects or helper-process effects.
- Universal behavior across Codex versions.
- Path-adaptation correctness.
- Mutation safety or create/update behavior.

It also does not establish a particular migration failure, synchronization bug,
authentication difference, `codexHome` difference, Desktop defect, or storage
mechanism.

## Gate decision

The current `GATE-002` requires documented public protocol provenance,
validated schemas and fake transport, reviewed exact read methods, and
deny-by-default failure behavior. The `READ_ONLY` criteria additionally require
the exact read method to be documented and authorized, no reachable mutation,
and reporting of local-state and environment impact.

Previously merged protocol provenance, validated schemas and fake transport,
the 232-test offline validation, clean Code Review and Security Review, and this
authorized successful real WSL exercise satisfy those conditions. Desktop-list
equivalence is not a normative `GATE-002` condition and the observed divergence
does not negate the successful RPC.

- Capability: `READ_ONLY`
- GATE-002: `SATISFIED`
- Mutation authorization: `NONE`
- Subdivision 2.3: `IMPLEMENTED`

Block 3 remains separately human-gated.

## Corrective-runtime revalidation status

This real-product observation remains historical evidence for the exact tested
repository HEAD `f9f61486339029f3743db02b5ba03c4d06d627fe`. The later corrective
runtime/test HEAD `10296e539a0fa3b3f785141e26e7798e681b623e` closes terminal transport-close
and validation-descriptor ownership gaps and has received deterministic offline
validation only. It has **not** been re-exercised against the real product; real
WSL revalidation of that corrected executable runtime remains pending.

The existing `READ_ONLY` / `GATE-002: SATISFIED` record describes the approved
capability and its historical evidence. It must not be read as a claim that the
later corrective runtime HEAD received the earlier real run.
