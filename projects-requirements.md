# Project requirements

## Purpose

This is the durable normative technical requirements document, not a Python
dependency file. It governs progression from an inert foundation toward a
possible WSL-first Project-management workaround.

## Supported environment

- **ENV-001:** The primary target MUST be Codex Desktop on Windows with its WSL
  backend enabled.
- **ENV-002:** Platform-specific behavior MUST be documented and MUST NOT be
  generalized from one observed environment without evidence.

## WSL-first requirement

- **WSL-001:** The workaround MUST keep the WSL backend enabled and MUST NOT
  require a native Windows backend fallback.
- **WSL-002:** Project code MUST NOT modify Codex Desktop configuration.

## Python baseline

- **PY-001:** Supported Python versions MUST be 3.11 or newer.
- **PY-002:** Packaging MUST use the `src` layout and declarative PEP 517
  metadata.
- **PY-003:** Importing the top-level package MUST perform no I/O or state
  discovery.

## Dependency policy

- **DEP-001:** Runtime dependencies MUST remain empty until a reviewed change
  demonstrates that the standard library is insufficient.
- **DEP-002:** Tooling MUST NOT be installed automatically.
- **DEP-003:** New dependencies require necessity, provenance, and risk review.

## Protocol research provenance

- **RPC-001:** Protocol claims MUST cite public OpenAI documentation or public
  Codex source/protocol definitions and distinguish facts from hypotheses.
- **RPC-002:** Protocol models MUST be developed against mocks before real
  integration.
- **RPC-003:** Every real RPC exercise MUST record the exact method and
  capability authorization.

## Safety requirements

- **SAFE-001:** Capabilities MUST be denied by default and enabled only by an
  explicitly reviewed scope.
- **SAFE-002:** Code MUST NOT delete Projects, user data, or perform destructive
  filesystem operations.
- **SAFE-003:** Block 1, Subdivision 1.1 MUST remain `NON_FUNCTIONAL`: no
  app-server process handling, real RPC invocation, network behavior, Codex
  state access, configuration modification, or mutation.
- **SAFE-004:** Changes SHOULD be small, auditable, and reversible.

## Secrets policy

- **SECRET-001:** Code and default tests MUST NOT require or access secrets,
  credentials, credential stores, or browser data.
- **SECRET-002:** Secret values MUST never be committed or recorded in reports.

## Binary policy

- **BIN-001:** Project code and development procedures MUST NOT download or
  execute third-party binaries.

## Path and privacy policy

- **PATH-001:** Committed code and documentation MUST NOT contain personal or
  user-specific paths; documented examples MUST use placeholders.
- **PATH-002:** Project code and default tests MUST NOT access `~/.codex`.
- **PATH-003:** Access to Codex SQLite state requires a future, explicit,
  reviewed authorization.

## Network policy

- **NET-001:** Project code MUST NOT make hidden network calls or emit
  telemetry.
- **NET-002:** Tests MUST require no network access by default.
- **NET-003:** Any future network behavior MUST be explicit, documented,
  bounded, and separately reviewed.

## Testing principles

- **TEST-001:** Tests MUST be deterministic and use mocks or fakes by default.
- **TEST-002:** Tests MUST NOT require a real Codex installation, credentials,
  network access, or user state unless separately marked and explicitly opted
  into.
- **TEST-003:** A check MUST NOT be reported as passing unless it was executed.

## Mutation authorization policy

- **MUT-001:** Mutation authorization MUST be `NONE` unless an approved
  capability-changing task names an exact allowed method.
- **MUT-002:** Authorization for `project/create` MUST NOT imply authorization
  for `project/update`, or vice versa.
- **MUT-003:** `project/move`, `project/delete`, and destructive operations
  are outside the approved roadmap.

## Development Blocks

1. **Block 1 — Foundation and Safety:** repository policy, packaging, and test
   execution baseline.
2. **Block 2 — Protocol Understanding and Read-Only Access:** public research,
   mock modeling, then gated read-only integration.
3. **Block 3 — Controlled Project Mutation:** separately authorized creation
   and update.
4. **Block 4 — Hardening:** validation, recovery, diagnostics, and ergonomics.

Subdivisions and current status are maintained in the
[roadmap](docs/roadmap/README.md).

## Progression gates

- **GATE-001 — NON_FUNCTIONAL to MOCK_ONLY:** packaging and deterministic test
  execution are established; safety rules are tested; no real Codex state is
  needed.
- **GATE-002 — MOCK_ONLY to READ_ONLY:** public protocol provenance is
  documented, schemas and fake transport are validated, exact read methods are
  reviewed, and failure behavior is deny-by-default.
- **GATE-003 — READ_ONLY to MUTATING:** read-only integration is demonstrated;
  input, path, authorization, recovery, and audit controls are reviewed; the
  exact mutation method receives human approval.

## Capability-level acceptance criteria

| Capability | Acceptance criteria |
|---|---|
| NON_FUNCTIONAL | Import is inert; no transport, process, state, network, or mutation behavior exists. |
| MOCK_ONLY | Deterministic fake transport and schemas pass without Codex, secrets, user state, or network access. |
| READ_ONLY | Exact read method is documented and authorized; no mutation is reachable; local-state and environment impact are reported. |
| MUTATING | Only the named method is authorized; inputs and paths are validated; dry-run or equivalent safeguards, recovery, and audit evidence are reviewed. |

Advancement through any gate requires a reviewed implementation PR and does
not follow automatically from completing the previous stage.
