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

Packaging validation is separate from normal tests. Before the validation task
starts, Codex Cloud setup pre-provisions the pinned `setuptools 84.0.0` wheel
under `.cache/codex-wsl-rpc-wheelhouse/`. This environment provisioning is not
part of the package runtime dependency model. The task validates that the
wheelhouse is repository-local and then creates the exact ignored,
repository-local environment `.cache/codex-wsl-rpc-packaging-venv`.

Wheelhouse validation is a mandatory precondition to executing pip. In order,
the task must validate the repository cache boundary, reject a missing,
non-directory, symbolic-link, or out-of-cache wheelhouse, require exactly the
pinned setuptools wheel `setuptools-84.0.0-py3-none-any.whl` as its sole
filesystem entry, reject that entry unless it is a non-symlink regular file,
and verify SHA-256
`51a52592b3b99e102b609654876bd65f19f999935166d1352678931132b0c670`.
Only after those checks pass may validation use
`repository_disposable_dir()` to boundary-check and create the exact
non-symlink directory `.cache/codex-wsl-rpc-packaging-tmp`. It exports
`TMPDIR`, `TEMP`, and `TMP` to that validated absolute path before creating the
fresh disposable venv, invoking pip, or validating installed metadata. Before
venv creation, `prepare_disposable_directory()` validates the exact venv path.
A stale directory is removed only with explicit opt-in after symlink, type,
and exact cache-parent validation; symlinked, non-directory, and out-of-cache
paths fail closed. Creation occurs only after the path is confirmed absent.
The editable install is:

```console
TMPDIR="$PACKAGING_TMP" \
TEMP="$PACKAGING_TMP" \
TMP="$PACKAGING_TMP" \
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

The validation fails closed without invoking pip, downloading a replacement,
modifying the wheelhouse, or deleting unexpected files. `--find-links` alone
does not make a wheelhouse trusted: trust is established by repository-local
path validation, symlink rejection, exact candidate validation, the pinned
filename, and SHA-256 verification. Pip retains build isolation and obtains
build tooling only from that validated local wheelhouse. Consistent with
DEP-002, pip may install that explicitly approved tooling into its ephemeral
isolated build environment; uncontrolled or package-index-resolved tooling
installation remains prohibited.

Validation then runs from a controlled directory outside the repository root
and uses `importlib.metadata` to check the checkout import origin, distribution
name/version, `Requires-Python`, empty `Requires-Dist`, and absent
`console_scripts`, while the same temporary-directory variables remain set.
The required order is cache validation, wheelhouse validation, exact wheel and
digest validation, packaging-temp validation/creation, temporary-variable
export, exact stale-venv validation and removal, confirmation that the venv
path is absent, clean venv creation, editable install, metadata validation,
and exact cleanup. The validation performs no package-index or runtime
dependency resolution and no automatic tooling download. Only the exact
disposable venv and packaging-temp directory may be removed afterward, after
each exact path is revalidated as repository-local and non-symlinked. The
cache directory and provisioned wheelhouse remain.

## Acceptance evidence and limitations

The source tests and controlled child-process import provide bounded evidence,
not proof against every possible side effect. Static source audit is required
as complementary evidence. In the recorded validation environment, the fresh
Python 3.12 venv did not need setuptools preinstalled: pip build isolation
successfully obtained `setuptools 84.0.0` from the provisioned local wheelhouse
with `--no-index`, and the editable install and installed metadata checks
passed. Environment provisioning occurred before the task; packaging
validation itself used the local wheelhouse only.

## Deferrals and durable status

- **Status:** `IMPLEMENTED`
- **Block 2 deferrals:** protocol research, schemas, JSON-RPC, fake or real
  transport, app-server/executable lifecycle, and every Project RPC
- **Other deferrals:** Codex/Windows/WSL integration, Codex state access,
  networking, mutation, release automation, and CI
- **Historical delivery evidence:** the implementation Pull Request for this
  Subdivision; any PR number is non-normative and GitHub remains authoritative
  for delivery state
