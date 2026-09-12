# Subdivision 1.2 — Python packaging and test execution baseline

## Objective and durable status

- **Status:** `IMPLEMENTED`
- **Capability level:** `NON_FUNCTIONAL`
- **Mutation authorization:** `NONE`
- **Package version:** `0.0.0`
- **Runtime dependencies:** `[]`

This Subdivision establishes deterministic source tests and an explicit,
repeatable packaging acceptance check. It adds no Codex behavior and does not
advance the capability level.

## Validation commands

Normal unit tests require no installation or provisioned wheel:

```console
python3 -m unittest discover -s tests -v
```

Packaging validation is separately opted into:

```console
python3 -B tests/validate_packaging.py
```

The executable [packaging validator](../../../tests/validate_packaging.py) is
the canonical procedure; detailed shell instructions are intentionally not
duplicated here.

## Packaging model

The original checkout is read-only packaging input. The validator checks the
lexical `src` path before resolving it, rejects authored symlinks and
non-regular entries, and copies `pyproject.toml`, `README.md`, `LICENSE`, and
the authored `src` tree byte-for-byte into one new
`.cache/packaging-check-<unique>/project` directory. Generated `.egg-info` and
`__pycache__` entries are neither followed nor copied. The editable install
targets only the copied project, and its expected import origin is the copied
source tree.

The externally provisioned wheelhouse must be a real repository-local directory
containing exactly `setuptools-84.0.0-py3-none-any.whl`, with SHA-256
`51a52592b3b99e102b609654876bd65f19f999935166d1352678931132b0c670`.
The verified wheel is copied into the unique workspace and verified again. Pip
uses only that private candidate set with build isolation, `--no-index`, and no
runtime dependency resolution.

All packaging children share one allowlisted environment. Temporary, home,
application-data, and cache paths point inside the workspace; Python import-path
overrides are not inherited; pip configuration files are disabled. Commands use
argument lists, `shell=False`, checked results, and finite execution timeouts.
The installed probe runs with `-I -B` from the workspace `run` directory and
checks distribution name/version, Python requirement, empty requirements,
absent console and GUI entry points, guarded import behavior, and copied-source
origin. The normal SOURCE import probe remains a distinct `-S` guarded check.
On Linux/WSL, each packaging command runs in a newly owned process group; a
timeout or interrupted wait terminates and boundedly reaps that group. Native
Windows is intentionally unsupported by this command rather than receiving
weaker timeout semantics.

Only a fully successful run removes its unique workspace. Failures retain and
report that workspace. The shared wheelhouse, pre-existing workspaces, original
generated metadata, and original checkout are never cleaned or reused.

## Execution assumptions and limitations

The interpreter, standard library, preinstalled pip, and reviewed project source
are trusted development inputs. Unexpected paths, symlinks, stale artifacts,
and wrong wheels are rejected rather than followed, executed, overwritten, or
deleted. Existing prohibitions on Codex state, credentials, network behavior,
and mutation remain in force.

This validation is not an operating-system sandbox for arbitrary malicious
Python. It does not claim resistance to a compromised interpreter or kernel, or
to a hostile same-user process concurrently replacing validated files. These
limits also exclude a deliberately escaping descendant that creates a new
process group. The test loader applies scoped observation guards to the actual
parent import of the trusted validator, but this remains targeted regression
coverage rather than arbitrary-code sandboxing. These limits do not excuse
reproducible defects: review findings should identify a
concrete failure path under this execution model and distinguish current bugs
from speculative hardening.

## Acceptance evidence

The consolidated validator was run twice from the delivered working tree. Both
runs allocated distinct fresh workspaces, completed the copied-source editable
installation and installed metadata/origin checks, and removed only their owned
workspaces. The unit suite, compile check, and diff check also passed. No real
Codex RPC, state access, network resolution, or mutation was performed.

## Deferrals

Protocol research, schemas, transports, process lifecycle, Codex/Windows/WSL
integration, user-state access, networking, mutation, release automation, and
CI remain out of scope and require later reviewed work.
