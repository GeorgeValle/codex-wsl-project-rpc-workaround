# Subdivision 1.1 — Repository scaffold, project context, requirements, and agent boundaries

## Objective

Establish project context, normative safety and technical requirements, agent
boundaries, minimal declarative package metadata, an inert package marker,
documentation navigation, future-test policy, and an auditable PR contract.

## Scope and gates

This Subdivision is constrained by **SAFE-003**, **PY-003**, **PATH-002**,
**NET-001**, and **MUT-001**. It remains at capability level
`NON_FUNCTIONAL`: no app-server discovery or launch, protocol transport,
Codex state access, network behavior, or Project operation is included.

## Durable status

- **Status:** Delivered for human review
- **Mutation authorization:** `NONE`
- **Acceptance evidence:** repository-local static validation, parsed package
  metadata, inert import smoke test, source compilation, and safety audit
- **Deferred:** Subdivision 1.2 establishes packaging and test execution;
  protocol research begins only in Block 2.

## Delivery evidence

- PR1 — Foundation and safety baseline

The PR reference is historical evidence only. This document and its
Block/Subdivision identity remain valid if that PR is closed, replaced, split,
or followed by additional delivery PRs.
