# Test policy

Run the canonical normal test suite from the repository root:

```console
python3 -m unittest discover -s tests -v
```

Normal tests require no package installation. They parse `pyproject.toml`,
check the `src` package structure and version, reject configured CLI entry
points, and import the package in a fresh child Python process. The import probe
uses the current interpreter, an explicit absolute `src` path, bytecode
suppression, repository-local temporary work and HOME-like directories, a
small environment allowlist, captured output, artifact inspection, and guards
for selected network, process, shell, and SQLite primitives.

This evidence demonstrates the tested metadata and that the current import did
not invoke those selected primitives or leave artifacts in the controlled
directories. It does not prove the absence of every conceivable side effect,
and it is not a Codex integration test. Static source review complements the
targeted runtime guards rather than globally patching filesystem operations.

Editable installation is a separate packaging-validation step, not a
prerequisite for normal tests. It uses the exact ignored repository-local venv
`.cache/codex-wsl-rpc-packaging-venv`, pre-existing pip and setuptools, and:

```console
.cache/codex-wsl-rpc-packaging-venv/bin/python -m pip --isolated install --no-index --no-build-isolation --no-deps --editable .
```

After installation, validation must run outside the repository root and check
the import origin plus distribution name, version, `Requires-Python`, empty
`Requires-Dist`, and absent `console_scripts` with `importlib.metadata`.
Packaging tooling must not be installed or upgraded to make this check pass.

Tests are bounded and deterministic. They do not:

- require a real Codex installation (real integration must be explicit opt-in);
- access `~/.codex`;
- require credentials or secrets; or
- require network access, Windows, WSL, or real user state.

No protocol, transport, mock RPC, or functional Codex capability is tested or
provided at this `NON_FUNCTIONAL` stage.
