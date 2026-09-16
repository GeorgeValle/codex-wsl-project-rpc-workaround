# Gated read-only `project/list` integration

## Status and scope

Phase A Cloud/offline implementation and one explicitly authorized local WSL
validation are **COMPLETE**. Subdivision 2.3 is **IMPLEMENTED**, capability is
`READ_ONLY`, mutation authorization remains `NONE`, and `GATE-002` is
`SATISFIED`. Codex Cloud did not execute or independently observe the real run;
the evidence was supplied by the human operator.

The only supported flow is Python in WSL -> an operator-selected native
Codex executable -> an owned app-server child over stdio -> `initialize` ->
`initialized` -> exactly one `project/list` page -> safe summary -> bounded
cleanup. There is no Desktop attachment, pagination, path conversion, network
transport, state inspection, mutation, general RPC API, or arbitrary argv.

## Policy boundary and authorization

The operator must separately approve BIN-002, PATH-004, the selected executable,
and one real `project/list` exercise at the reviewed commit. The
`IntegrationAuthorization` value and understanding flag are auditable
application guardrails, not cryptographic identity or provenance proof and not
an OS security boundary. The operator asserts that the path is the intended
already-installed OpenAI Codex executable; repository code validates only its
executable form. Imports and construction are inert; only `list_one_page()`
starts a process.

The executable and home are explicit absolute WSL paths. Code never searches
`PATH`, scans an installation, resolves a symlink, downloads, installs, or
falls back to Windows. This checkpoint requires a regular executable native ELF
target; launchers, scripts, and symlinks fail closed so the operator can provide
the manually reviewed concrete target. This is a scoped restriction, not a
claim about every supported Codex package format. Filename alone does not prove
provenance.

The fixed argv is `[EXACT_EXECUTABLE, "app-server", "--listen", "stdio://"]`
with `shell=False`. The child receives only explicit `HOME`, standard
`os.defpath` as `PATH`, and fixed UTF-8 locale variables. No ambient API key,
proxy, token, credential, or arbitrary `CODEX_*` value is copied.

## Wire, stream, and limits

The application-controlled writer accepts only `initialize`, parameterless
`initialized`, and `project/list`. Each request uses a fresh, unpredictable,
high-entropy string RequestId; the two IDs are unique within a run and responses
must match the exact generated ID. Tests may inject a deterministic generator.
Runtime IDs contain no user data, paths, project data, or secrets and are not
included in safe evidence. Initialize asks only for `experimentalApi=true`;
listing fixes `cursor=null`, `limit=25`, `sortKey=position`, and
`sortDirection=asc`. It never follows `nextCursor`.

Nonblocking pipes, selectors, partial writes, incremental byte buffering, and
monotonic phase deadlines handle fragmented UTF-8, partial/multiple lines, EOF,
and malformed input. Exactly one request is outstanding. Response ID type and
value must match; server requests, unrelated responses, malformed frames, and
unknown notifications fail closed. Pinned-source informational notifications
`configWarning` and `remoteControl/status/changed` may be consumed during either
bounded response phase; they never complete a request, extend a deadline,
trigger writes, or expose payloads.

Limits are: 1 MiB per stdout frame, 8 MiB stdout per session, 32 KiB retained
stderr (never rendered), 1 MiB total stderr, 32 notifications, 1 MiB aggregate
notification bytes, 10 seconds each for initialize and list, then 2 seconds
each for graceful wait, terminate wait, and kill/reap wait.

Cleanup closes stdin and owned descriptors, waits, then terminates and kills
only the exact owned `Popen` child if needed. It never enumerates processes,
kills by name/group, or touches Desktop processes. It cannot promise cleanup of
arbitrary descendants.

Ctrl+C handling is validation-runner lifecycle hardening, not a final UI
requirement: end users are not expected to use or be shown terminal cancellation
in the final interface. The temporary terminal-based Phase B validation runner
retains ownership through interrupted cleanup and finishes bounded cleanup of
only its exact child before reporting cancellation. This safeguard matters for
the large offline/manual regression suite (already well over one hundred tests,
and expected to exceed roughly 170 checks/tests as validation hardening grows),
because an orphaned owned app-server could interfere with subsequent tests,
manual validation, or the user's Codex environment.

## Pinned source provenance

Behavior is modeled at public OpenAI Codex revision
`7efa9d96fb34c3cafe108a3c870bfc33e5635772`:

- CLI app-server selection and listen option: [`codex-cli/src/main.rs`, `AppServer`](https://github.com/openai/codex/blob/7efa9d96fb34c3cafe108a3c870bfc33e5635772/codex-rs/cli/src/main.rs) and [`app-server/src/main.rs`](https://github.com/openai/codex/blob/7efa9d96fb34c3cafe108a3c870bfc33e5635772/codex-rs/app-server/src/main.rs).
- Stdio line framing: [`app-server-transport/src/transport/stdio.rs`](https://github.com/openai/codex/blob/7efa9d96fb34c3cafe108a3c870bfc33e5635772/codex-rs/app-server-transport/src/transport/stdio.rs).
- Initialize state and errors: [`initialize_processor.rs`, `initialize`](https://github.com/openai/codex/blob/7efa9d96fb34c3cafe108a3c870bfc33e5635772/codex-rs/app-server/src/request_processors/initialize_processor.rs) and [`message_processor.rs`](https://github.com/openai/codex/blob/7efa9d96fb34c3cafe108a3c870bfc33e5635772/codex-rs/app-server/src/message_processor.rs).
- Experimental `project/list` registration, dispatch and errors: [`protocol/common.rs`](https://github.com/openai/codex/blob/7efa9d96fb34c3cafe108a3c870bfc33e5635772/codex-rs/app-server-protocol/src/protocol/common.rs), [`request_processors/projects.rs`, `project_list`](https://github.com/openai/codex/blob/7efa9d96fb34c3cafe108a3c870bfc33e5635772/codex-rs/app-server/src/request_processors/projects.rs), and [`error_code.rs`](https://github.com/openai/codex/blob/7efa9d96fb34c3cafe108a3c870bfc33e5635772/codex-rs/app-server-protocol/src/error_code.rs).
- Allowed notification definitions: [`protocol/common.rs`, server notification definitions](https://github.com/openai/codex/blob/7efa9d96fb34c3cafe108a3c870bfc33e5635772/codex-rs/app-server-protocol/src/protocol/common.rs). Payloads are intentionally discarded.

The protocol reference is pinned to that source revision. The selected product
identity is operator-confirmed but unverified by repository code; its version is
unobserved, and installed binary-to-pinned-source mapping, installed-build
compatibility, and Desktop-store equivalence remain `NOT_ESTABLISHED`.

An error code of `-32601` is reported only as `project/list unavailable or
unsupported`. This intentionally privacy-safe category can mean that the method
is not registered, the feature or Project capability is unavailable, the store
is unavailable in the selected runtime context, or another method-not-found
style condition. Raw server error messages and data are not used or exposed.

## Privacy and evidence

Decoded Projects exist transiently in memory and are not persisted or logged.
Output allowlists the protocol-reference SHA, UTC timestamp, operator-confirmed
but code-unverified target provenance, `NOT_ESTABLISHED` target-revision mapping,
unobserved target version,
platform strings, lifecycle booleans, sanitized Codex-home category, page
count, `has_more`, root representation categories, cleanup outcome, and
explicit negative mutation/state-inspection/Desktop-comparison facts. Product
state impact, network effects, and helper-process effects are each reported as
`NOT_ESTABLISHED` until real validation can establish them. It never
includes Project names/IDs, roots, metadata, cursor, raw Codex home, stderr,
credentials, executable path, or server error text/data.

The validated operator workflow was:

```console
python3 tools/run_read_only_project_list.py \
  --i-understand-this-starts-codex \
  --codex-executable /<REVIEWED>/<CODEX_NATIVE_EXECUTABLE> \
  --home /home/<USER>
```

Safe evidence must record the protocol-reference SHA, UTC time,
operator-confirmed/code-unverified provenance category, unobserved version,
`NOT_ESTABLISHED` installed-binary-to-source mapping, safe runner JSON, exact
`project/list` authorization, and
whether product/network/helper effects were observed—never raw Projects or
paths.

## Demonstrated capability and Desktop comparison

One approved Windows 11 / WSL2 / Ubuntu 24.04.4 LTS exercise used the runner's
own app-server child and the exact flow `initialize`, `initialized`, and
`project/list`. Initialization and listing succeeded, a valid empty page was
returned with `has_more=false`, and cleanup was graceful. No mutation was
attempted and repository code did not directly inspect Codex state.

The already-open Desktop UI displayed multiple Projects in the same tested
context. The independently launched app-server result therefore has the
classification `DIVERGENCE_OBSERVED`. This does not diagnose the cause or prove
separate stores, different homes or authentication, a migration or sync defect,
or that `project/list` is broken. Desktop correspondence remains unestablished.

## Remaining limitations

- Product network effects, helper-process effects, and product-state impact are
  `NOT_ESTABLISHED`.
- Installed executable mapping to the pinned source SHA and target version are
  `NOT_ESTABLISHED` / unobserved.
- Filesystem-side-effect-free startup, universal behavior across versions,
  path-adaptation correctness, mutation safety, and create/update behavior are
  not established.
- The validation establishes one read-only context only; it is not a universal
  Desktop workaround.

### Corrective-runtime validation status

The authorized real WSL observation is tied to repository HEAD
`f9f61486339029f3743db02b5ba03c4d06d627fe`. A later corrective runtime/test
HEAD, `10296e539a0fa3b3f785141e26e7798e681b623e`, is offline-validated but has
not been re-exercised against the real product. Real WSL revalidation of the
corrected executable runtime remains pending; the prior observation remains
historical evidence and is not attributed to the newer HEAD.
