# Subdivision 2.1 — Public Codex app-server protocol research

## Objective and durable status

- **Status:** `IMPLEMENTED`
- **Role:** `PRIMARY`
- **Classification:** `DOCUMENTATION`
- **Review mode:** `HUMAN_GATED`
- **Capability level:** `NON_FUNCTIONAL`
- **Mutation authorization:** `NONE`
- **Selected public-source revision:**
  `7efa9d96fb34c3cafe108a3c870bfc33e5635772`

The objective was to establish a reconstructable public-source contract for a
future mock-first Project client without running Codex or accessing Codex
state. The canonical result is the
[technical reference](../../protocol/app-server-projects.md).

## Research scope and acceptance evidence

Research covered envelopes, initialization, experimental gating, stdio,
Unix-socket and WebSocket framing, and the narrowly relevant Project methods.
The pinned OpenAI source defines and dispatches `project/list`, `project/read`,
`project/create`, and `project/update`; its handlers and upstream tests provide
revision-specific behavior evidence. Public documentation endpoints were also
retried, with the access limitation recorded in the technical reference.

The delivery is accepted as research-complete because one revision is pinned,
material claims are classified and traceable, unknown Desktop/WSL applicability
is not promoted to fact, and readiness is evaluated component by component.
No executable schema, fixture, transport, process integration, state access, or
RPC invocation was added.

## Findings by evidence class

### `CONFIRMED_IN_PUBLIC_SOURCE`

- The revision's envelope deliberately omits the JSON-RPC 2.0 `jsonrpc` member;
  request IDs are strings or signed 64-bit integers.
- Clients initialize with required `clientInfo.name` and `clientInfo.version`,
  optional nullable `title`, and optional capabilities. Project methods require
  per-connection `experimentalApi: true` after initialization.
- `project/list` is registered, read-only with respect to Project records, and
  supports cursor pagination plus position or recency sorting.
- The default transport is newline-delimited JSON over stdio. Unix-domain
  sockets carry WebSocket frames; TCP WebSocket is also present; `off` disables
  the listener.

### `HYPOTHESIS`

- Stdio is the smallest useful transport abstraction for mock modeling because
  its framing is deterministic and has no listener/authentication surface.
- A path-context mismatch may be relevant to the motivating
  `AbsolutePathBuf deserialized without a base path` observation, but the public
  evidence does not establish that cause.

### `NOT_ESTABLISHED`

- A standalone app-server started in WSL reaches the same Project records as
  Codex Desktop with its WSL backend enabled.
- The pinned revision maps to any particular installed Desktop build.
- Listing Projects is free of process-startup, migration, logging, cache, or
  other filesystem side effects.
- Windows, WSL UNC, and Linux path forms are converted between environments by
  app-server.

## Requirements / objectives mapping

| IDs | Applicability and evidence |
|---|---|
| `ENV-001`, `ENV-002`, `WSL-001`, `WSL-002` | Target and uncertainty are documented; no platform behavior or configuration change was introduced. |
| `RPC-001` | Material protocol facts cite pinned public OpenAI source and are separated from hypotheses and unknowns. |
| `RPC-002`, `GATE-001`, `GATE-002`, `GATE-003` | Mock-first progression is preserved; this delivery does not cross a capability gate. |
| `RPC-003`, `MUT-001`, `MUT-002`, `MUT-003` | No RPC was exercised; authorization remains `NONE`; excluded mutations remain excluded. |
| `SAFE-001`, `SAFE-002`, `SAFE-004` | Documentation-only, deny-by-default, small and reversible scope. |
| `SECRET-001`, `SECRET-002`, `BIN-001` | No secret or third-party binary was required, accessed, downloaded, or executed. |
| `PATH-001`, `PATH-002`, `PATH-003` | Only placeholder paths are documented; neither `~/.codex` nor SQLite was accessed. |
| `NET-001`, `NET-002`, `NET-003` | No runtime network behavior was added; bounded public HTTP research is disclosed, not embedded in code or tests. |
| `TEST-003` | Only actually executed checks are reported in the delivery record. |

No normative requirements gap was found, so
[`projects-requirements.md`](../../../projects-requirements.md) is unchanged.

## Model-readiness decision

| Component | Decision | Constraint |
|---|---|---|
| Wire envelope model | `READY_FOR_2_2` | Pin fixtures to the selected SHA; omit `jsonrpc`. |
| Request ID model | `READY_FOR_2_2` | Model string and signed 64-bit integer IDs. |
| Error model | `READY_FOR_2_2` | Model code, message, and optional data. |
| Initialization model | `READY_FOR_2_2` | Enforce first initialization and required client fields. |
| Experimental capability/gating model | `READY_FOR_2_2` | Model the per-connection opt-in and rejection path. |
| Candidate transport framing model | `READY_FOR_2_2` | Model stdio only; do not imply Desktop connectivity. |
| Project identity model | `READY_FOR_2_2` | Treat Project IDs and roots as distinct from threads/repositories. |
| `project/list` model | `READY_FOR_2_2` | Registration is confirmed only for the pinned revision and enabled gate. |
| Create contract reference | `READY_FOR_2_2` | Reference-only; mutation remains unauthorized. |
| Update contract reference | `READY_FOR_2_2` | Reference-only; mutation remains unauthorized. |
| Desktop Project-store equivalence | `NOT_ESTABLISHED` | Must not be encoded in mocks. |
| Installed-build compatibility | `NOT_ESTABLISHED` | Requires a public mapping or later controlled observation. |
| Real WSL integration | `INTEGRATION_ONLY` | Requires separate Subdivision 2.3 authorization and safety review. |

**Research delivery:** `COMPLETE`.

**Evidence for proposed Subdivision 2.2 modeling:** sufficient for the rows
marked `READY_FOR_2_2`; not sufficient for Desktop-store equivalence,
installed-build compatibility, or real integration.

## Integration blockers, deferrals, and next-step gate

Subdivision 2.2 must not silently encode unverified path conversion, installed
method exposure, or Desktop-store equivalence. It may build deterministic
models and fake transport only after human approval. Real process discovery,
launching or attachment, RPCs, state-root inspection, Desktop/WSL integration,
and every mutation are explicitly deferred. Subdivision 2.3 remains blocked on
a reviewed way to establish process/store context without broad state access.
