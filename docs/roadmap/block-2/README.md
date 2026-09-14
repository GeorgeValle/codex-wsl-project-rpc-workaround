# Block 2 — Protocol Understanding and Read-Only Access

Block 2 moves from public research toward a possible, separately reviewed,
read-only experiment. It does not authorize access merely because a public
wire contract exists.

| Subdivision | Objective | Status |
|---|---|---|
| [2.1](subdivision-2.1-protocol-research.md) | Public Codex app-server protocol research | IMPLEMENTED |
| 2.2 | Mock protocol transport and schemas | IN PROGRESS — Delivery 1 merged; Delivery 2 merged; [incident-evidence documentation follow-up](../../incidents/windows-wsl-projects-41463.md) is this delivery; Delivery 3 pending separate human approval |
| 2.3 | Read-only real `project/list` integration | FUTURE — requires review and resolved integration gates |

Capability progression remains governed by `GATE-001` through `GATE-003` in
the [requirements](../../../projects-requirements.md). Completion of one
Subdivision does not automatically authorize the next. In particular, this
documentation follow-up remains `NON_FUNCTIONAL` with mutation authorization
`NONE` and leaves `GATE-001` unsatisfied. Delivery 1 established
the envelope/codec foundation, and Delivery 2 added initialization and
Project/list schemas; both are merged. This follow-up adds public incident
evidence only. Delivery 3—fake transport/server/client and `project/list`
behavior—remains pending separate human approval. No mock or real transport is
added and no RPC is invoked; Subdivision 2.2 is not complete.
