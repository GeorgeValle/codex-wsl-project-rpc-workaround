# Subdivision 1.2 — Python packaging and test execution baseline

## Objective and coverage

Establish deterministic, auditable, repository-local validation of the Python
package without adding Codex behavior. Standard-library tests cover source
metadata, package discovery and structure, version consistency, absent CLI
entry points, and a controlled inert-import observation. This supplies the
packaging and test-execution prerequisite portion of GATE-001 without advancing
through that gate.

## Capability and package decisions

- **Capability level:** `NON_FUNCTIONAL`
- **Mutation authorization:** `NONE`
- **Package:** Python >=3.11, setuptools PEP 517, `src` layout
- **Names/version:** distribution `codex-wsl-rpc`, import `codex_wsl_rpc`,
  version `0.0.0`
- **Dependencies/CLI:** no runtime dependencies, test framework dependency,
  optional convenience group, or CLI

The canonical normal test command is:

```console
python3 -m unittest discover -s tests -v
```

It requires no installation, Codex, network, credentials, secrets, Windows,
WSL, or real user state.

## Packaging validation strategy

Packaging validation is separate from normal tests. It first requires Python
3.11+, standard-library prerequisites, pip, setuptools, and a usable `venv` to
be present; nothing may be installed or upgraded to repair the environment.
The exact ignored repository-local environment is
`.cache/codex-wsl-rpc-packaging-venv`. Its interpreter must execute:

```console
.cache/codex-wsl-rpc-packaging-venv/bin/python -m pip --isolated install --no-index --no-build-isolation --no-deps --editable .
```

Validation then runs from a controlled directory outside the repository root
and uses `importlib.metadata` to check the checkout import origin, distribution
name/version, `Requires-Python`, empty `Requires-Dist`, and absent
`console_scripts`. Only the exact validation paths may be removed afterward.

## Acceptance evidence and limitations

The source tests and controlled child-process import provide bounded evidence,
not proof against every possible side effect. Static source audit is required
as complementary evidence. In the recorded implementation environment, Python
and unit-test prerequisites were available but setuptools was absent from the
base interpreter and disposable venv. Consequently offline editable packaging
validation is blocked, and this Subdivision is **not complete** until that
required validation passes with already-approved local tooling.

## Deferrals and durable status

- **Status:** Implementation present; packaging validation blocked by an
  external prerequisite
- **Block 2 deferrals:** protocol research, schemas, JSON-RPC, fake or real
  transport, app-server/executable lifecycle, and every Project RPC
- **Other deferrals:** Codex/Windows/WSL integration, Codex state access,
  networking, mutation, release automation, and CI
- **Historical delivery evidence:** the implementation Pull Request for this
  Subdivision; any PR number is non-normative and GitHub remains authoritative
  for delivery state
