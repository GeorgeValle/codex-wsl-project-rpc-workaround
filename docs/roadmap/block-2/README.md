# Block 2 — Protocol Understanding and Read-Only Access

Block 2 moves from public research toward a possible, separately reviewed,
read-only experiment. It does not authorize access merely because a public
wire contract exists.

| Subdivision | Objective | Status |
|---|---|---|
| [2.1](subdivision-2.1-protocol-research.md) | Public Codex app-server protocol research | IMPLEMENTED |
| 2.2 | Mock protocol transport and schemas | IMPLEMENTED — Deliveries 1–3 and the incident-evidence documentation follow-up are implemented |
| 2.3 | Read-only real `project/list` integration | FUTURE — requires review and resolved integration gates |

Capability progression remains governed by `GATE-001` through `GATE-003` in
the [requirements](../../../projects-requirements.md). Completion of one
Subdivision does not automatically authorize the next. Delivery 1 established
the envelope/codec foundation, Delivery 2 added
initialization and Project/list schemas, and Delivery 3 adds the deterministic
in-memory transport/server/client and fake `project/list` behavior. The
incident-evidence documentation follow-up is merged history.

Subdivision 2.2 is `IMPLEMENTED`; capability is `MOCK_ONLY`; mutation
authorization is `NONE`; and technical `GATE-001` is `SATISFIED`. The gate is
technical evidence: packaging and deterministic tests are established, safety
rules are tested, and the fake protocol operates without Codex, secrets, user
state, or network. Code Review, Security Review, and human approval remain
separate acceptance/merge controls rather than intrinsic gate conditions.

Subdivision 2.3 remains `FUTURE`, separately reviewed, and limited to read-only
real `project/list`. Delivery 3 invokes no real RPC and authorizes no real state
access or mutation.
