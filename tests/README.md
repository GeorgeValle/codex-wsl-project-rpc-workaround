# Test policy

The normal, deterministic unit suite is:

```console
python3 -m unittest discover -s tests -v
```

It requires neither package installation nor the externally provisioned build
wheel. It validates source metadata and structure, statically reads the version,
and runs the package only in a guarded, bounded child process.

The separate, opt-in packaging acceptance check is:

```console
python3 -B tests/validate_packaging.py
```

[`validate_packaging.py`](validate_packaging.py) is the executable and
authoritative procedure. It validates the repository-local `.cache` boundary
and the externally provisioned pinned setuptools wheel, creates one unique
workspace beneath `.cache`, copies the current packaging inputs into it, and
performs a build-isolated editable install of that copy. Pip uses only a private
copy of the approved wheel with package-index access disabled. Installation
metadata and package origin are checked from the workspace's `run` directory.

The packaging check removes only its owned workspace after complete success.
On failure it reports and retains that workspace for inspection. It never
reuses or cleans an old fixed packaging venv, and it never creates or removes
editable-build metadata in the original source tree.

Both commands are development validation. They provide no Codex integration,
transport, RPC, network, state, or mutation capability.
