# Public app-server Project protocol research

## Purpose and boundary

This is the canonical, documentation-only protocol reference for Block 2,
Subdivision 2.1. It describes enough of the public Codex app-server surface to
support a later mock-modeling decision, centered on `project/list`. It is not a
client, executable schema, compatibility promise, or authorization to start
Codex, access state, or invoke an RPC.

Capability remains `NON_FUNCTIONAL`; mutation authorization remains `NONE`.
`project/create` and `project/update` are recorded only as future contract
boundaries. No method in this document was invoked during research.

## Delivery 2 executable schema policy

Delivery 2 adds pure value codecs only; it does not add a transport, dispatch,
state machine, or real integration. Schema decoding validates the complete JSON
tree, ignores valid unknown members, and keeps handler normalization out of the
models.

Initialization omission rules follow the pinned serde shapes: `ClientInfo.title`
encodes as a string or explicit null; absent or null
`InitializeParams.capabilities` is omitted. `experimentalApi` and
`requestAttestation` always encode a boolean, while false
`mcpServerOpenaiFormElicitation` and absent `extensions` are omitted.
`optOutNotificationMethods` encodes an explicit null when absent.

Project/list schema options (`cursor`, `limit`, `sortKey`, and `sortDirection`)
all encode explicit null when absent. `Project.recencyAt` and
`ProjectListResponse.nextCursor` likewise encode explicit null. Limits retain
their schema values; defaulting, clamping, sorting, pagination, and cursor
semantics are handler concerns deferred beyond this delivery.

For `ProjectRoot.path`, this is a limited **LOCAL MODEL POLICY for Delivery 2**:
the codec accepts clearly absolute POSIX, Windows-drive, and UNC wire spellings
without filesystem access or normalization. Exact cross-platform
`AbsolutePathBuf` behavior remains **NOT_ESTABLISHED**. Timestamp units for
`createdAt` and `updatedAt` also remain **NOT_ESTABLISHED**; `recencyAt` is Unix
seconds as established by the pinned source.

## Selected upstream reference and method

- **Repository:** <https://github.com/openai/codex>
- **Selected revision:**
  [`7efa9d96fb34c3cafe108a3c870bfc33e5635772`](https://github.com/openai/codex/tree/7efa9d96fb34c3cafe108a3c870bfc33e5635772)
- **Access date:** 2026-09-13
- **Revision rule:** all source/type/handler/test claims below refer to this
  single SHA. Links use that SHA rather than a moving branch.

The GitHub commit API returned that exact revision, making the planning-approved
candidate available and suitable. Public OpenAI source at that revision contains
the Project types, method registry, dispatch handlers, transport implementation,
and relevant tests. Generated types and schemas are revision-specific artifacts;
future mocks must remain pinned to this revision until a reviewed update.

The official developer-documentation endpoint redirected from
`https://developers.openai.com/codex/app-server/` to
`https://developers.openai.com/codex/app-server`, after which retrieval failed
with HTTP proxy `403` (`CONNECT tunnel failed`).
`https://learn.chatgpt.com/docs/app-server` also returned HTTP `403`. Therefore
this reference does **not** claim those pages were read. It relies on pinned
public OpenAI source where sufficient and leaves other points unknown.

## Evidence classification

- `CONFIRMED_IN_PUBLIC_SOURCE`: the pinned public OpenAI revision directly
  defines, registers, handles, or tests the claim.
- `HYPOTHESIS`: a plausible modeling or incident explanation not proven by the
  selected evidence.
- `NOT_ESTABLISHED`: proportionate public research did not establish the claim.

These labels classify material claims, not every explanatory sentence.

## App-server role and lifecycle

**`CONFIRMED_IN_PUBLIC_SOURCE`.** The protocol declares `ClientRequest` values
sent to app-server and server responses/notifications sent back to clients. The
binary selects one of stdio, Unix socket, TCP WebSocket, or disabled transport.
This establishes a client/server interface, not that an independently started
server shares context with any Desktop-owned process.

The first request on a connection must be `initialize`. All other typed requests
are rejected with invalid-request code `-32600` and message `Not initialized`;
a second initialization is rejected with `-32600` and `Already initialized`.
After a successful response, connection-specific initialization notifications
may be emitted. The protocol also defines an `initialized` client notification,
but the selected message processor logs client notifications rather than using
that notification as a second lifecycle gate. A minimal model should therefore
model the request/response order and should not invent a required handshake step.

Starting or attaching to an app-server was outside this research authorization.

## Wire envelopes

The pinned source explicitly says it does **not** implement true JSON-RPC 2.0
because it neither sends nor expects `"jsonrpc": "2.0"`. Names in source retain
`JSONRPC*` terminology, but the precise wire shapes are:

| Kind | Required members | Optional member | Meaning |
|---|---|---|---|
| Request | `id`, `method` | `params`, `trace` | Expects a response. |
| Successful response | `id`, `result` | none defined | Correlates by the same request ID. |
| Error response | `id`, `error` | `error.data` | `error` requires signed integer `code` and string `message`. |
| Notification | `method` | `params` | Has no ID and expects no response. |

The request `trace` is an optional W3C trace context. A `RequestId` is an
untagged string or signed 64-bit integer; `null` is not a declared ID variant.
The generic error constants include invalid request `-32600`, method not found
`-32601`, invalid params `-32602`, internal error `-32603`, and overloaded
`-32001`. Only errors tied to Project/lifecycle behavior below should be encoded
as Project expectations; the existence of a generic code does not prove every
handler produces it.

**Model consequence (`CONFIRMED_IN_PUBLIC_SOURCE`):** omit `jsonrpc`; accept
only string/integer IDs; keep `error.data` optional; do not treat notifications
as responses.

## Initialization and capability negotiation

`InitializeParams` requires `clientInfo` and permits an optional `capabilities`
object. `ClientInfo` fields are:

| Wire field | Type | Presence |
|---|---|---|
| `name` | string | required; handler also requires a valid HTTP-header value |
| `title` | string or null | optional on input; serialized as null when absent in the typed value |
| `version` | string | required |

When `capabilities` is absent, its booleans default false. Relevant capability
fields are `experimentalApi` (boolean, default false), `requestAttestation`
(boolean, default false), `mcpServerOpenaiFormElicitation` (boolean, default
false), optional nullable `optOutNotificationMethods`, and optional nullable
`extensions`. Only `experimentalApi` is needed for the Project surface.

`InitializeResponse` requires `userAgent`, `codexHome` (the absolute server
`$CODEX_HOME` path), `platformFamily`, and `platformOs`. Its disclosure confirms
that state-root and execution platform belong to the running server context; it
does not establish Desktop/WSL equivalence.

## Experimental API model

**`CONFIRMED_IN_PUBLIC_SOURCE`.** Every Project request in the method registry—
including list, read, create, update, import, move, and delete—is annotated
experimental. Dispatch checks the request's experimental reason after checking
initialization. If the connection did not negotiate `experimentalApi: true`, it
returns invalid request (`-32600`) with the generated message that the named
experimental API is disabled. Upstream tests directly verify this mechanism for
experimental methods.

The selected implementation has a typed registry entry and dispatch arm for
the relevant methods; the gate is conditional at request handling rather than
conditional removal of those registry variants. This revision-specific detail
does not establish registration in a different binary.

> type exists != method registered != experimental gate enabled != installed
> Desktop supports it

No public mapping between the selected SHA and an installed Desktop build was
found. Availability in every Desktop build is `NOT_ESTABLISHED`.

## Relevant transports

| Transport | `CONFIRMED_IN_PUBLIC_SOURCE` framing and lifecycle | Applicability / unknowns |
|---|---|---|
| stdio (default `stdio://`) | One JSON object per input line; one serialized object plus newline per output. One unauthenticated connection uses stdin/stdout. EOF closes it; Unix shutdown code also handles SIGTERM with a bounded process deadline. | Best candidate for 2.2 framing. It would require process ownership in a real experiment; Desktop attachment and startup side effects are unknown. |
| Unix socket (`unix://` or `unix://PATH`) | Binds a validated private Unix-domain socket path and performs a WebSocket upgrade over the stream; each text frame carries one serialized object. An empty path derives a control socket under resolved `CODEX_HOME`. | Potentially relevant to local attachment, but discovering/using a Desktop-associated socket and its ownership is not authorized or established. Socket creation/removal is itself filesystem behavior. |
| TCP WebSocket (`ws://IP:PORT`) | Binds the given address; each text frame carries one object; binary frames are dropped. Loopback may be unauthenticated. Non-loopback without configured capability-token or signed-bearer-token auth is refused; requests with an `Origin` header are rejected. | Adds listener/authentication/network surface unnecessary for initial mocks. Desktop use and WSL reachability are unknown. |
| disabled (`off`) | Parses as an explicit no-listener mode. | Useful only to understand that transport exposure can be disabled. |

**Provisional modeling recommendation (`HYPOTHESIS`):** Subdivision 2.2 should
model newline-delimited stdio framing because it is the smallest deterministic
surface. This is a modeling choice only—not a decision that a WSL process can
reach Desktop Projects. Unix-socket and WebSocket models should be deferred
until an integration need is separately reviewed.

## Project terminology and identity

At this revision, a `Project` contains:

| Field | Type / meaning established by source |
|---|---|
| `id` | string Project identifier |
| `name` | string |
| `roots` | array of `ProjectRoot`, each with absolute `path` |
| `metadata` | string-to-string map |
| `position` | signed 64-bit integer |
| `createdAt`, `updatedAt` | signed 64-bit integers |
| `recencyAt` | signed 64-bit Unix seconds or null; newest non-archived member-thread recency |

The public types can associate a thread with a nullable Project ID and calculate
Project recency from member threads. They do not make a Project synonymous with
a thread, working directory, repository, or cloud environment. This document
keeps those concepts distinct. `thread/list` is not a substitute for
`project/list`.

## Project method matrix

| Method | Params / response | Exposure | Project-record effect | Roadmap treatment |
|---|---|---|---|---|
| `project/list` | `ProjectListParams` / `ProjectListResponse` | Registered and experimental | Reads Project records | Primary future read target |
| `project/read` | `ProjectReadParams` / `ProjectReadResponse` | Registered and experimental | Reads one Project | Confirmed surface, not required as substitute |
| `project/create` | `ProjectCreateParams` / `ProjectCreateResponse` | Registered and experimental | May create a Project | Block 3 reference only; unauthorized here |
| `project/update` | `ProjectUpdateParams` / `ProjectUpdateResponse` | Registered and experimental | May mutate a Project | Block 3 reference only; unauthorized here |

The registry also confirms `project/import`, `project/move`, and
`project/delete`. Import, move, and delete are outside the approved roadmap;
they are not future implementation targets and are not documented as callable
examples. In particular, move and delete remain excluded by `MUT-003`.

### `project/list` contract

All parameter fields are optional and nullable in the generated TypeScript
surface:

| Field | Type | Behavior |
|---|---|---|
| `cursor` | string or null | Opaque continuation cursor; malformed cursors produce invalid params (`-32602`). |
| `limit` | unsigned 32-bit integer or null | Defaults to 25; handler clamps to the inclusive range 1–100. |
| `sortKey` | `position`, `recencyAt`, or null | Defaults to `position`; recency sorting puts empty Projects last. |
| `sortDirection` | `asc`, `desc`, or null | Requires `sortKey`; defaults to ascending for position and descending for recency. |

The response requires `data` (an array of Projects) and `nextCursor` (string or
null). The registry serializes list as a global shared read of the Project
store. The handler performs no Project-record mutation, but that statement is
not a claim of zero process or filesystem side effects.

Concrete failures confirmed in the handler/tests include:

- `-32600` before initialization or without the experimental opt-in;
- `-32602` when `sortDirection` is supplied without `sortKey` or a cursor is
  invalid;
- `-32601` with an unavailable-without-SQLite-state message when the selected
  thread store does not support Projects;
- `-32603` for other internal Project-store failures.

**Exact readiness:** `project/list` is `READY_FOR_2_2` as a pinned mock model,
including gate, params, response and known failure branches. Actual exposure in
an installed build and the backing store reached from WSL are not established.

### `project/read` confirmation

`ProjectReadParams` requires `projectId`; the response requires `project`. A
missing Project becomes invalid params (`-32602`). It is included because the
selected registry and handler establish the actual wire method, not because of
naming symmetry. It is not needed to replace `project/list`.

### Future create/update contract boundaries

`project/create` requires `name`, `roots`, and `idempotencyKey`; `metadata` is
optional and nullable. Its response requires `project`. The handler trims and
rejects an empty name, requires a nonblank idempotency key no longer than 512
bytes, validates roots as absolute and rejects logical or canonically resolved
duplicates. The store supplies replay behavior for an idempotency key, and a
new creation emits `project/changed`. These facts do not authorize mutation.

`project/update` requires `projectId`; `name`, `roots`, and `metadata` are each
optional and nullable. Omission means no update for that field in the handler;
because an `Option<map>` represents metadata, the wire contract does not expose
a distinct value for “set metadata to null.” A missing Project produces
`-32602`; changed records emit `project/changed`. No idempotency field is
defined for update. These facts do not authorize mutation.

## Path semantics relevant to the incident

**`CONFIRMED_IN_PUBLIC_SOURCE`.** `ProjectRoot.path` uses `AbsolutePathBuf`.
Create/update validation calls `from_absolute_path_checked`; relative roots are
invalid. The transport selector can resolve a supplied Unix-socket path relative
to the current directory, but that is a transport-path rule, not a Project-root
conversion rule. The initialize response exposes the server's absolute
`codexHome`.

The selected evidence does not define cross-context conversion among examples
such as:

```text
C:\Users\<WINDOWS_USER>\project
\\wsl.localhost\<DISTRO>\home\<USER>\project
/home/<USER>/project
```

Serialization carries a path value; the Project handler validates it in the
server process's path semantics and may canonicalize it only for duplicate
detection. Responsibility for translating Windows, WSL UNC, and Linux paths is
`NOT_ESTABLISHED`.

The observed incident text—`AbsolutePathBuf deserialized without a base path`—
remains an observation. A Windows/WSL conversion cause is a `HYPOTHESIS`; the
public source reviewed here does not prove that causal link.

## Desktop/WSL applicability: highest-priority question

**Question:** Does a future app-server client reach the same Project records
used by Codex Desktop with the WSL backend enabled?

**Result: `NOT_ESTABLISHED`.** The public source shows that:

- standalone startup selects a transport and loads a server configuration;
- `InitializeResponse.codexHome` identifies the running server's state root and
  reports its platform;
- the Project handler uses the process-scoped thread store and returns
  method-not-found when Projects are unavailable without SQLite state;
- connection origin distinguishes stdio, in-process, WebSocket, and remote
  control contexts.

It does not establish that a separately launched WSL app-server uses the same
configuration, state root, process ownership, or persistent Project store as
the Desktop-associated app-server. Common method names prove no equivalence.

A future, separately authorized real integration must verify: which process
Desktop owns or connects to; that process's reported platform and `codexHome`;
which endpoint is intended for attachment; whether its Project store contains
the Desktop-visible records; and whether Windows/WSL path values round-trip.
That investigation must minimize state access and must not inspect local SQLite
or `~/.codex` without exact reviewed authorization.

## Read-only method versus lifecycle side effects

`project/list` is a shared-read store operation and does not mutate Project
records in its handler (`CONFIRMED_IN_PUBLIC_SOURCE`). Separately, server
startup constructs process-scoped stores; Unix-socket mode creates a socket;
the initialize handler sets connection state and can set process-global client
metadata; configuration warnings and analytics hooks exist. Tests use temporary
`codexHome` directories and SQLite feature setup.

Whether a normal standalone or Desktop-associated startup performs migrations,
logs, cache writes, or other persistent changes in the motivating environment
is `NOT_ESTABLISHED`. Therefore this reference does not call `project/list`
“filesystem-write-free” or treat a read RPC as proof of a side-effect-free
process lifecycle.

## Version and compatibility limitations

This contract is a snapshot of public source at the selected SHA, accessed
2026-09-13. Project APIs are experimental and may change. Schema/type presence
is version-specific; no installed Desktop version was inspected, and no public
mapping from an installed build to this SHA was established. Installed-build
compatibility is `NOT_ESTABLISHED`; an invented compatibility matrix would be
misleading.

## Model-readiness handoff

| Component | State | Evidence boundary for 2.2 |
|---|---|---|
| Wire envelope model | `READY_FOR_2_2` | Exact pinned structs; no `jsonrpc` member. |
| Request ID model | `READY_FOR_2_2` | String or signed 64-bit integer. |
| Error model | `READY_FOR_2_2` | Exact envelope and relevant concrete codes. |
| Initialization model | `READY_FOR_2_2` | Required fields, ordering, duplicate rejection. |
| Experimental capability/gating model | `READY_FOR_2_2` | Per-connection boolean and rejection path. |
| Candidate transport framing model | `READY_FOR_2_2` | Stdio newline framing only. |
| Project identity model | `READY_FOR_2_2` | Exact Project/ProjectRoot snapshot; preserve distinctions. |
| `project/list` model | `READY_FOR_2_2` | Exact registry, fields, defaults and known failures. |
| Create contract reference | `READY_FOR_2_2` | Reference-only; never make callable under current authorization. |
| Update contract reference | `READY_FOR_2_2` | Reference-only; never make callable under current authorization. |
| Desktop Project-store equivalence | `NOT_ESTABLISHED` | Must not be asserted by mocks. |
| Installed-build compatibility | `NOT_ESTABLISHED` | Requires public mapping or controlled future evidence. |
| Real WSL integration | `INTEGRATION_ONLY` | Not part of 2.2; requires separately reviewed 2.3. |

**Research delivery:** `COMPLETE`.

**Enough evidence for proposed Subdivision 2.2 modeling:** yes, only for the
`READY_FOR_2_2` rows. Desktop store equivalence and installed-build support are
not ready; real integration is not authorized. Mocks must not silently encode
those unknowns, unverified path conversion, or method exposure in other builds.

## Delivery 3 mock implementation

The `codex_wsl_rpc.mock` package is a synthetic, synchronous development aid.
Its JSON-line `str` boundary and immutable fixture store are local mock choices;
they are not a real stdio stream, the Codex Project store, Desktop state, or a
model of Desktop synchronization. The fake store is always available (and may
be empty), so the pinned upstream unavailable-store branch is intentionally
unreachable. Trusted-development static regression guards help prevent unsafe
imports and operations, but are not OS-level security containment.

The handler behavior is compatible specifically with pinned revision
`7efa9d96fb34c3cafe108a3c870bfc33e5635772`: position ordering uses position
then ID; recency ordering always places non-null recency before null recency and
uses ID as the tie-breaker; direction applies to values and IDs. Limits default
to 25 and clamp to 1–100. Stateless keyset cursors use legacy
`<position>|<uuid>` for ascending position and
`v1|<key>|<direction>|<value>|<uuid>` otherwise. Cursor parsing enforces the
128-character limit, exact components, canonical integers, matching order, and
canonical lowercase hyphenated UUIDs. Position anchors accept the complete
signed-64-bit domain, including negative positions, and reject values outside
that domain.

`Project` remains a wire schema and intentionally accepts broader ID strings.
Only the fake store requires canonical UUID fixture IDs so cursor generation
cannot fail during pagination; that is a mock store/handler constraint, not a
schema change. Fixture roots preserve POSIX, Windows drive, `wsl.localhost`, and
`wsl$` spellings and ordering exactly. Paths are data: the mock performs no
translation, normalization, canonicalization, or existence check.

The pinned `message_processor.rs` `process_notification` and
`process_client_notification` symbols only log client notifications. Therefore
an `initialized` notification before or after initialization is accepted with
no response and no state change; it cannot initialize the connection or enable
`experimentalApi`. The pinned `error_code.rs` establishes generic
method-not-found code `-32601`, but no exact generic message at this mock's
dispatch boundary was established. The deterministic text `Method not found`
is consequently **mock-local**, not claimed as upstream-exact.

### GATE-001 technical validation matrix

| Condition | Evidence |
|---|---|
| packaging established | Packaging validator explicitly imports both `codex_wsl_rpc` and `codex_wsl_rpc.mock` from its installed copied-source environment and verifies both module origins. |
| deterministic test execution established | The complete standard-library unittest suite passes with fixed fixtures and sequential IDs. |
| safety rules tested | Mock safety tests and static audits pass as trusted-development regression guards. |
| no real Codex state needed | Runtime contains no Desktop, `~/.codex`, or SQLite access. |
| fake transport + schemas pass | Transport, server, client, and Project/list tests pass. |
| no Codex needed | Runtime contains no process launch or executable discovery. |
| no secrets/user state | Tests use synthetic placeholder fixtures only. |
| no network | Runtime and tests contain no network operation. |

**Technical GATE-001 status: `SATISFIED`.** This evidence makes the
`MOCK_ONLY` transition technically eligible. Acceptance and merge remain
human-gated and require clean Code Review, clean Security Review, and final
human approval; those process controls are not intrinsic GATE-001 rows.

## Open questions and explicit non-goals

The Phase A integration consumes only the pinned server notifications
`configWarning` and `remoteControl/status/changed`, with bounded counts/bytes
and discarded payloads. This narrow handling does not establish that either
notification will occur in an installed build.

Open integration questions are the Desktop-owned endpoint/process, selected
state root, installed-build mapping, startup writes, and cross-platform path
round-tripping. They constrain Subdivision 2.3 but do not block completion of
this proportionate public research.

Executable mock models, transports, and fixtures were deferred during protocol
research but are now delivered by Delivery 3. That delivery is limited to the
`codex_wsl_rpc.mock` client/test-support package, its synthetic in-memory
JSON-line transport and fixture store, the fake app-server lifecycle, and
deterministic mock `project/list` behavior.

Phase A delivers a gated, offline-tested stdio integration path for
`initialize`, `initialized`, and one `project/list` page. One explicitly
authorized local WSL validation subsequently exercised that exact path
successfully; capability is therefore `READ_ONLY` and GATE-002 is `SATISFIED`.
The returned empty page diverged from the non-empty Desktop-visible Project
list, and the cause remains `NOT_ESTABLISHED`. Unix socket or WebSocket/TCP
transport and attachment to a Desktop-owned app-server remain explicit
non-goals. Access to
`~/.codex`, SQLite, Desktop configuration or state, and Windows/WSL path
adaptation also remains deferred, as do Desktop sidebar/store equivalence
claims. Mutation authorization remains `NONE`:
Project mutation and `project/create`, `project/update`, `project/import`,
`project/move`, and `project/delete` are explicit non-goals.

## Sources and provenance ledger

Every source below is public OpenAI source at the selected SHA and was accessed
2026-09-13.

| Classification | Claim | Pinned source (file / symbol) | Establishes | Does not establish |
|---|---|---|---|---|
| `CONFIRMED_IN_PUBLIC_SOURCE` | Envelope and ID shapes omit `jsonrpc`. | [`rpc.rs`](https://github.com/openai/codex/blob/7efa9d96fb34c3cafe108a3c870bfc33e5635772/codex-rs/app-server-protocol/src/rpc.rs), `RequestId`, `JSONRPC*` | Exact serialization structs and explicit non-2.0 note. | Compatibility with other revisions/builds. |
| `CONFIRMED_IN_PUBLIC_SOURCE` | Initialization fields and response context. | [`v1.rs`](https://github.com/openai/codex/blob/7efa9d96fb34c3cafe108a3c870bfc33e5635772/codex-rs/app-server-protocol/src/protocol/v1.rs), `InitializeParams`, `InitializeCapabilities`, `InitializeResponse`; [`initialize_processor.rs`](https://github.com/openai/codex/blob/7efa9d96fb34c3cafe108a3c870bfc33e5635772/codex-rs/app-server/src/request_processors/initialize_processor.rs), `initialize` | Required fields, defaults, duplicate behavior, returned server context. | Desktop/store equivalence or absence of startup side effects. |
| `CONFIRMED_IN_PUBLIC_SOURCE` | Project wire types and optionality. | [`project.rs`](https://github.com/openai/codex/blob/7efa9d96fb34c3cafe108a3c870bfc33e5635772/codex-rs/app-server-protocol/src/protocol/v2/project.rs), Project structs | Exact revision-specific request/response fields. | Method exposure by itself. |
| `CONFIRMED_IN_PUBLIC_SOURCE` | Project wire names are registered and experimental. | [`common.rs`](https://github.com/openai/codex/blob/7efa9d96fb34c3cafe108a3c870bfc33e5635772/codex-rs/app-server-protocol/src/protocol/common.rs), `client_request_definitions!` entries | Names, request/response pairing, experimental annotations, serialization scopes. | Installed Desktop registration. |
| `CONFIRMED_IN_PUBLIC_SOURCE` | Experimental and initialization gates precede dispatch. | [`message_processor.rs`](https://github.com/openai/codex/blob/7efa9d96fb34c3cafe108a3c870bfc33e5635772/codex-rs/app-server/src/message_processor.rs), `dispatch_initialized_client_request`; [`experimental_api.rs`](https://github.com/openai/codex/blob/7efa9d96fb34c3cafe108a3c870bfc33e5635772/codex-rs/app-server/tests/suite/v2/experimental_api.rs) | Per-connection enforcement and rejection behavior. | Universal support in released clients. |
| `CONFIRMED_IN_PUBLIC_SOURCE` | List defaults, validation, errors, and create/update boundaries. | [`projects.rs`](https://github.com/openai/codex/blob/7efa9d96fb34c3cafe108a3c870bfc33e5635772/codex-rs/app-server/src/request_processors/projects.rs), `project_list`, `project_create`, `project_update`; [`projects` tests](https://github.com/openai/codex/blob/7efa9d96fb34c3cafe108a3c870bfc33e5635772/codex-rs/app-server/tests/suite/v2/projects.rs) | Handler semantics and selected test-observed errors. | Behavior of another state backend/build. |
| `CONFIRMED_IN_PUBLIC_SOURCE` | Supported transport modes and framing. | [`transport/mod.rs`](https://github.com/openai/codex/blob/7efa9d96fb34c3cafe108a3c870bfc33e5635772/codex-rs/app-server-transport/src/transport/mod.rs), `AppServerTransport`; [`stdio.rs`](https://github.com/openai/codex/blob/7efa9d96fb34c3cafe108a3c870bfc33e5635772/codex-rs/app-server-transport/src/transport/stdio.rs); [`unix_socket.rs`](https://github.com/openai/codex/blob/7efa9d96fb34c3cafe108a3c870bfc33e5635772/codex-rs/app-server-transport/src/transport/unix_socket.rs); [`websocket.rs`](https://github.com/openai/codex/blob/7efa9d96fb34c3cafe108a3c870bfc33e5635772/codex-rs/app-server-transport/src/transport/websocket.rs) | Mode parsing, line/text-frame boundaries, listener behavior. | Which transport Desktop uses or exposes. |
| `HYPOTHESIS` | Stdio is the narrowest 2.2 model. | Synthesis of pinned transport sources above. | A reviewable modeling recommendation. | Real Desktop integration choice. |
| `NOT_ESTABLISHED` | Standalone WSL and Desktop Project stores are equivalent. | No public source found that maps process/state contexts. | The evidence gap. | Equivalence. |
| `NOT_ESTABLISHED` | Installed Desktop matches the selected SHA. | Public commit availability only. | Revision provenance. | Build-to-SHA mapping. |
| `NOT_ESTABLISHED` | Cross-platform path conversion caused the incident. | Project path types and validation only. | Absolute-path requirement. | Causation or conversion responsibility. |
