# Test policy

Subdivision 1.1 intentionally adds no fake functional tests because no
functional behavior exists to exercise. Subdivision 1.2 will establish
packaging and deterministic test execution rather than expanding capability in
this foundation change.

Future tests MUST default to mocks or fakes. By default, they MUST NOT:

- require a real Codex installation (real integration must be explicit opt-in);
- access `~/.codex`;
- require credentials or secrets; or
- require network access.

Tests must remain bounded, deterministic, and consistent with the repository
safety requirements.
