# Codex WSL Project RPC Workaround

> **Experimental and unofficial.** This project is not affiliated with or
> endorsed by OpenAI. Block 1, Subdivision 1.1 contains **no
> functional workaround** and performs no Codex RPC operations.

## Project purpose

This repository explores a possible workaround for a Codex Desktop regression
observed by a Windows + WSL user. Its long-term goal is safe, auditable
management of Codex Desktop Projects while the WSL backend remains enabled.
This repository currently establishes constraints before capabilities.

## Incident that motivated the project

In the affected environment, Codex Desktop displayed:

```text
Local app-server project migration failed
Invalid request: AbsolutePathBuf deserialized without a base path
```

The observed result was that normal local Project maintenance failed, including
creating local Projects and editing or saving existing local Projects. These
behaviors and the error text are observations from one affected environment.
Any explanation involving path conversion, migration internals, or protocol
behavior remains a hypothesis until supported by public protocol research.

## Native Windows workaround failure

As an attempted workaround, the user temporarily disabled **Run Codex in
Windows Subsystem for Linux**. In that affected environment—not necessarily in
other installations—this caused a more severe failure: Codex Desktop no longer
started successfully, and its native Windows backend failed while initializing
local SQLite state.

## Recovery history

Recovery required neither reinstalling Codex Desktop nor deleting `.codex`.
The setting in the following file:

```text
C:\Users\<WINDOWS_USER>\.codex\config.toml
```

had become:

```toml
runCodexInWindowsSubsystemForLinux = false
```

Restoring it to:

```toml
runCodexInWindowsSubsystemForLinux = true
```

allowed Codex Desktop to start successfully again using WSL. This is incident
and recovery history, not a procedure automated by this project. Project code
MUST NOT automate this configuration change.

## WSL-first requirement

Because of that incident, this project deliberately keeps the WSL backend
enabled. A future workaround MUST NOT depend on switching Codex Desktop to its
native Windows backend.

## Proposed technical direction

Future, separately reviewed work intends to investigate public OpenAI Codex
information, public Codex source and protocol definitions, Codex app-server,
and experimental Project-management RPC functionality exposed by app-server.
The objective is to manage Projects without relying on the broken Desktop
Project registration path.

Potential future operations are read-only Project listing, controlled Project
creation, and controlled Project update. **None of these features exists at the
current `NON_FUNCTIONAL` capability level.**

## Staged progression

1. Foundation and safety
2. Packaging and deterministic tests
3. Public protocol research
4. Mock protocol modeling
5. Read-only Project inspection
6. Controlled Project creation
7. Controlled Project update
8. Hardening and diagnostics

Destructive operations are not part of the currently approved roadmap. See the
[stable roadmap](docs/roadmap/README.md) for Blocks and Subdivisions.

## Core design principles

- Safety first and deny-by-default capabilities
- Auditability through explicit behavior and documented evidence
- Small, reviewed, reversible changes
- Minimal dependencies and a Python standard-library preference
- Mock-first protocol development
- No hidden network behavior or telemetry
- No secrets or credential access
- No third-party binary downloads
- No user-specific paths in committed code or documentation (placeholders such
  as `<WINDOWS_USER>` are used instead)

The durable technical rules are in
[`projects-requirements.md`](projects-requirements.md), and coding agents are
bound by [`AGENTS.md`](AGENTS.md).
