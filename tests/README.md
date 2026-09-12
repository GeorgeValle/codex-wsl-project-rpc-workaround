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
`.cache/codex-wsl-rpc-packaging-venv`. Codex Cloud setup first pre-provisions a
pinned `setuptools 84.0.0` wheel under the ignored repository-local
`.cache/codex-wsl-rpc-wheelhouse/`. That pre-task provisioning is validation
infrastructure, not a package runtime dependency. Before pip may execute build
tooling, validation must use `validate_setuptools_wheelhouse()` from
`test_foundation.py`. It first applies the repository cache-boundary checks,
then rejects a missing, non-directory, symbolic-link, or out-of-cache
wheelhouse, requires the sole setuptools distribution candidate to be
`setuptools-84.0.0-py3-none-any.whl`, and verifies its SHA-256 is
`51a52592b3b99e102b609654876bd65f19f999935166d1352678931132b0c670`.
The validator does not create or repair the externally provisioned wheelhouse.

The mandatory order is:

1. validate the repository cache boundary;
2. validate the wheelhouse boundary;
3. validate the exact, unique setuptools wheel candidate;
4. validate its SHA-256;
5. create a fresh disposable packaging venv; and
6. only then invoke pip as follows, with build isolation enabled:

```console
.cache/codex-wsl-rpc-packaging-venv/bin/python \
  -m pip \
  --isolated \
  --disable-pip-version-check \
  install \
  --no-index \
  --find-links .cache/codex-wsl-rpc-wheelhouse \
  --no-cache-dir \
  --no-deps \
  --editable .
```

Pip must not be invoked if any wheelhouse validation fails. `--find-links`
does not itself establish trust; trust comes from the boundary, symlink,
candidate, pinned-filename, and digest checks above.

After installation, validation must run outside the repository root and check
the import origin plus distribution name, version, `Requires-Python`, empty
`Requires-Dist`, and absent `console_scripts` with `importlib.metadata`.
The validation task performs no package-index resolution, runtime dependency
resolution, or automatic tooling download.

Tests are bounded and deterministic. They do not:

- require a real Codex installation (real integration must be explicit opt-in);
- access `~/.codex`;
- require credentials or secrets; or
- require network access, Windows, WSL, or real user state.

No protocol, transport, mock RPC, or functional Codex capability is tested or
provided at this `NON_FUNCTIONAL` stage.
