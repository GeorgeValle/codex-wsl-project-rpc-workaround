# Block 2 — Protocol Understanding and Read-Only Access

Block 2 moves from public research toward a possible, separately reviewed,
read-only experiment. It does not authorize access merely because a public
wire contract exists.

| Subdivision | Objective | Status |
|---|---|---|
| [2.1](subdivision-2.1-protocol-research.md) | Public Codex app-server protocol research | IMPLEMENTED |
| 2.2 | Mock protocol transport and schemas | IN PROGRESS — Delivery 1 merged; Delivery 2 implemented by this PR; Delivery 3 pending approval |
| 2.3 | Read-only real `project/list` integration | FUTURE — requires review and resolved integration gates |

Capability progression remains governed by `GATE-001` through `GATE-003` in
the [requirements](../../../projects-requirements.md). Completion of one
Subdivision does not automatically authorize the next. In particular, this
Delivery 2 remains `NON_FUNCTIONAL` with mutation authorization `NONE` and
leaves `GATE-001` unsatisfied. It adds schemas but no mock or real transport and
invokes no RPC; Subdivision 2.2 is not complete.
