# Block 2 — Protocol Understanding and Read-Only Access

Block 2 moves from public research toward a possible, separately reviewed,
read-only experiment. It does not authorize access merely because a public
wire contract exists.

| Subdivision | Objective | Status |
|---|---|---|
| [2.1](subdivision-2.1-protocol-research.md) | Public Codex app-server protocol research | IMPLEMENTED |
| 2.2 | Mock protocol transport and schemas | IMPLEMENTED — Deliveries 1–3 and the incident-evidence documentation follow-up are implemented |
| Governance prerequisite for 2.3 | Bounded product-under-test execution policy | IMPLEMENTED — policy clarification only; no real execution or RPC |
| 2.3 | Read-only real `project/list` integration | IMPLEMENTED — offline implementation and one authorized local WSL validation COMPLETE; capability READ_ONLY; mutation authorization NONE; GATE-002 SATISFIED |

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

The governance prerequisite between Subdivisions 2.2 and 2.3 distinguishes
uncontrolled third-party binary execution from future, separately reviewed,
explicitly opted-in execution of an already-installed OpenAI Codex/app-server
in WSL solely as the product under test. It requires an operator-selected
absolute executable path, fixed reviewed arguments, `shell=False`, bounded
owned-child cleanup, and continued application of the RPC, state, network, and
mutation policies. It permits neither generic command execution nor a
Windows-native or automatically selected substitute.

This governance delivery performs and authorizes no real RPC, does not start a
real product process, and does not change the `MOCK_ONLY` capability or `NONE`
mutation authorization. `GATE-002` remains `UNSATISFIED`; the policy
clarification alone does not establish `READ_ONLY` capability.

Subdivision 2.3 is `IMPLEMENTED`. PR #9 is historical delivery evidence for the
offline implementation and one explicitly authorized local WSL validation of
`initialize`, the `initialized` notification, and `project/list`. Public
protocol provenance, validated schemas and fake transport, deny-by-default
failure behavior, clean Code Review and Security Review, and the successful real
read-only exercise satisfy the current `GATE-002` and `READ_ONLY` criteria.

Capability is `READ_ONLY`, `GATE-002` is `SATISFIED`, and mutation authorization
remains `NONE`. The independently launched app-server returned an empty page
while Desktop displayed multiple Projects; the cause and Desktop correspondence
remain `NOT_ESTABLISHED`. Block 3 remains separately human-gated. Network
transport and all Project mutation remain unauthorized.
