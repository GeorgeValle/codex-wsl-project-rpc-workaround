# Subdivision 2.3 — PR #9 Offline Validation Evidence

## Scope

This record covers **offline validation only** of the gated read-only integration
implementation for Subdivision 2.3. Validation used repository code,
deterministic fixtures, fake processes and streams, temporary repository-local
resources, and the approved packaging procedure. It did not execute or inspect
the real OpenAI Codex product.

PR #9 is historical delivery evidence, not a stable roadmap identity.

## Tested HEAD

The implementation and test HEAD validated by both canonical runs was
`aa91f1fbdede59b5cdafdd49b0990891b602a0c3`. This reachable runtime/test commit
is the parent of the documentation-only evidence commit and remains in branch
history.

## Environment

| Item | Observed value |
|---|---|
| Python | 3.12.13 |
| Git | 2.43.0 |
| Execution environment | Repository development container on Linux; offline fake-only validation |

No personal paths, credentials, or secret values were recorded.

## Capability state

- Capability: `MOCK_ONLY`
- Mutation authorization: `NONE`
- GATE-002: `UNSATISFIED`
- Real WSL validation: `NOT RUN`

## Test inventory

Discovery found **242 test cases**. Counts below are discovery counts, not an
aspirational target.

| Area | Test file(s) | Test count | Main invariants |
|---|---|---:|---|
| Foundation/import safety | `tests/test_foundation.py` | 10 | Declarative metadata, src layout, repository-local cache boundary, inert guarded import |
| Protocol envelopes | `tests/test_protocol_envelope.py` | 55 | Request/response/notification envelopes, exact ID types, JSON bounds, classification, ownership, Unicode and decode errors |
| Protocol initialization | `tests/test_protocol_initialize.py` | 5 | Client info, capability encoding, initialize params, required initialize response shape |
| Protocol Projects and list schemas | `tests/test_protocol_projects.py` | 5 | Project/root models, field bounds, list params, required `data` and required-nullable `nextCursor` |
| Mock transport | `tests/test_mock_transport.py` | 5 | In-memory framing, IDs, notifications, malformed input, response isolation |
| Mock server | `tests/test_mock_server.py` | 8 | Initialization lifecycle, `experimentalApi`, initialized notification, safe errors, mutation denial |
| Mock project/list | `tests/test_mock_project_list.py` | 16 | Sorting, null recency, pagination, signed cursors, cursor validation, snapshots and metadata |
| Mock client | `tests/test_mock_client.py` | 4 | Typed lifecycle, request IDs, server errors, exact response correlation, no retry |
| Mock safety | `tests/test_mock_safety.py` | 1 | Static denial of process, network, state, discovery, and mutation capabilities |
| Integration transport with fakes | `tests/test_integration_transport.py` | 35 | Partial I/O, fragmented UTF-8, framing, unpredictable-ID correlation, notifications, limits, deadlines, trailing output, terminal EOF, normalized OS failures and exception-safe construction |
| Integration orchestration with fakes | `tests/test_integration_client.py` | 64 | Authorization, WSL gate, executable/HOME identity, launch ownership, cancellation, unified finalization, signal-consistent cleanup, strict responses, safe evidence |
| Integration/import safety | `tests/test_integration_safety.py` | 7 | Inert imports/runner, lazy signal API lookup, explicit gate, safe categories, no real execution or mutation surface |
| Packaging/import acceptance | `tests/test_validate_packaging.py` | 27 | Controlled local artifact, inert installed imports, installed origins, mock/integration inclusion, no network/state/process side effects |
| **Total** | **13 focused test files** | **242** | **Complete deterministic offline suite** |

## Regression coverage

The inventory and test implementations were mapped to the material PR #9
invariants before deciding whether to add tests. No material gap was found, so
no count-only tests were added.

### Execution authorization

Coverage verifies explicit operator authorization, positive WSL-only gating,
the strict kernel-release marker, fail-closed unsupported platforms, inert
imports on unsupported platforms, and lazy `pthread_sigmask` resolution.

### Executable and HOME identity

Coverage verifies absolute operator-selected targets; rejection of symlinks,
non-regular files, non-ELF files, and non-directories; `O_NOFOLLOW`,
nonblocking executable validation, retained validated executable and HOME
objects, descriptor-backed execution, pathname replacement resistance,
descriptor ownership/closure through cancellation-safe caller-owned validation, and privacy-safe translation of validation
filesystem errors.

### Cancellation and process ownership

Coverage verifies cancellation during validation and spawn/ownership handoff,
SIGINT masking and bounded acquisition, retained exact-child ownership,
truthful terminate/kill delivery state, absolute cleanup deadlines, bounded
escalation, child reaping, stdout EOF, descriptor-close failure behavior—including terminal selector close failures—and
cleanup-error precedence. Graceful cleanup additionally requires a zero child
exit status. Forced outcomes require both confirmed delivery and the matching
POSIX signal status (`-SIGTERM` or `-SIGKILL`); ordinary positive statuses and
delivery-uncertain statuses fail closed. Validation descriptors use take-before-close
release, and descriptor-release failure cannot bypass independent owned-child
cleanup.

### Transport

Coverage verifies fresh unpredictable request IDs, exact correlation and one
outstanding request, partial writes, fragmented UTF-8, multiple frames,
malformed JSON/envelopes, notification allowlisting, server-request rejection,
stdout/stderr limits, phase deadlines under continuously ready input, trailing
complete and incomplete frames, terminal stdout through EOF, and the joint
child-reaped-plus-stdout-EOF success condition. Expected selector, descriptor,
read, write, and close failures are normalized to privacy-safe transport errors,
and partially constructed transports deterministically close acquired selector
state.

### Protocol contract

Coverage verifies strict initialize and `project/list` response boundaries,
including presence of required `nextCursor` and `recencyAt` members when their
values are null. Required-nullable members are not treated as optional at the
real-integration boundary.

### Privacy and safe evidence

Coverage verifies that safe output excludes raw executable and HOME paths,
Project names/IDs/roots/metadata, raw stderr, arbitrary server diagnostics,
and arbitrary transport errors. Product-state impact, network effects, and
helper-process effects remain explicitly `NOT_ESTABLISHED` where unobserved.

## Focused test results

Every discovered focused test file was executed independently.

| Command | Result |
|---|---|
| `python3 tests/test_foundation.py` | PASS — 10 tests |
| `python3 tests/test_protocol_envelope.py` | PASS — 55 tests |
| `python3 tests/test_protocol_initialize.py` | PASS — 5 tests |
| `python3 tests/test_protocol_projects.py` | PASS — 5 tests |
| `python3 tests/test_mock_transport.py` | PASS — 5 tests |
| `python3 tests/test_mock_server.py` | PASS — 8 tests |
| `python3 tests/test_mock_project_list.py` | PASS — 16 tests |
| `python3 tests/test_mock_client.py` | PASS — 4 tests |
| `python3 tests/test_mock_safety.py` | PASS — 1 test |
| `python3 tests/test_integration_transport.py` | PASS — 35 tests |
| `python3 tests/test_integration_client.py` | PASS — 64 tests |
| `python3 tests/test_integration_safety.py` | PASS — 7 tests |
| `python3 tests/test_validate_packaging.py` | PASS — 27 tests |

## Full-suite results

Both canonical runs used the same implementation and test HEAD. No tests were
skipped, and the count and outcome were equivalent.

| Run | Tests | Passed | Failed | Errors | Skipped | Reported time |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 242 | 242 | 0 | 0 | 0 | 16.425s |
| 2 | 242 | 242 | 0 | 0 | 0 | 20.505s |

## Packaging and static checks

| Command / audit | Result |
|---|---|
| `python3 -m compileall -q src tests` | PASS |
| `python3 -B tests/validate_packaging.py` | PASS — approved local packaging procedure; installed mock and integration origins verified |
| `git diff --check` | PASS |
| `python3 tests/test_mock_safety.py` | PASS — static mock safety audit |
| `python3 tests/test_integration_safety.py` | PASS — inertness, runner gate, and forbidden-capability audit |
| Repository textual audit for process launch, real RPC, network, state access, SQLite, and mutation markers | PASS — reviewed matches are confined to the gated implementation, safety guards, fake tests, and documentation; default tests expose no real-product path |

Ordinary/default tests did not start Codex or app-server, invoke the operator
runner, perform real RPC, access `~/.codex`, inspect SQLite, use project runtime
network access, or perform Project mutation.

## Real-product boundary

- Real Codex executed: **NO**
- Real app-server executed: **NO**
- Real RPC executed: **NO**
- Operator runner executed against real product: **NO**
- Direct `~/.codex` access: **NO**
- SQLite inspection: **NO**
- Project mutation: **NO**
- Desktop configuration modification: **NO**

## Remaining validation

This document does **not** establish `READ_ONLY`. The capability remains
`MOCK_ONLY`, and GATE-002 remains `UNSATISFIED`.

Still required are explicit human authorization, local Windows/WSL real-product
validation, the exact `initialize` / `initialized` / `project/list` exercise,
sanitized evidence, and a final gate decision.

Those later steps are recorded separately in
[`pr9-real-wsl-validation.md`](pr9-real-wsl-validation.md). This section remains
the historical conclusion of the offline validation record.

## Result

`OFFLINE_VALIDATION_PASS`

All required offline checks passed twice with equivalent results. No production
defect was discovered, no material regression-coverage gap was found, and no
real-product boundary was crossed.
