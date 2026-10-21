# SRC-01: separate Python runtime prerequisite

This is the runtime-only part of SRC-01. It does not enable the production
execution of generated agents, a model channel, source mutation or evolutionary
search. The existing fixed-seed generation route and `buddha.executor` are unchanged.
The [living plan](PLAN.md) retains the remaining SRC-01 gate.

The local Linux amd64 image is
`sha256:757f5ffd3125ae10a83a7fb7eed05afe5e047442e4063d21bf995c03db1d0f04`.
It uses the same already installed, immutable CPython 3.13.12
[base](conformance/src01-runtime.Dockerfile) as the earlier confined runtime.
No dependency is downloaded or installed. A new venv uses `--without-pip`;
the active container filesystem has empty system and venv site-packages,
no pip launchers or bundled ensurepip wheels, and no adjacent Python bytecode.
Its Python dependency set consists of the standard library and its extensions.
The Debian OS libraries and utilities remain present; this is not a shell-free
image or an assertion that arbitrary Python is safe by itself.

The [environment record](conformance/src01-runtime-environment.json) binds the
image ID/configuration, recipe/helper bytes, interpreter and installed inventory.
The inventory measures 1,120 base-tree and 16 venv entries. Its 144,159 bytes hash
to `3da67017216e00138f3ba69dad28ec9214ece8a504920bf3720801e57c22b782`.
The audit hashes source, extension and executable files, checks known symlinks
and every conventional Python interpreter alias, and rejects physical package
artifacts/customization hooks even when isolated imports would overlook them.
A fresh read-only audit must equal the manifest created during the build.

## Actual checks and limits

The [delivery record](conformance/src01-runtime-delivery.json) preserves the
actual new-image observations. The original byte-sealed eleven-case executor
harness is reused with explicitly selected environment/output paths. These are
new executions, not a relabeling of old evidence: both role boundaries, stale
bytecode, IPv4/IPv6/TCP/UDP/DNS/HTTP network attempts, scratch space/noexec, CPU,
descendant timeout, stdout/stderr bounds, memory and process limits are exercised.
All owned containers are removed; an independent canary stays alive until its
own controlled release.

Ten physical-audit tests also run inside the new Linux image without skips.
Two literal `/agent/candidate.py` variants process one sanitized task and return
different expected outputs. They are compiled/executed only in containers;
this is a controlled runtime fixture, not a parent-authored mutation or the
future production candidate interface. No evaluator, split/final dataset, host
home, Docker socket, API key or paid authority is supplied to those fixtures.
The future candidate worker and narrow host-owned model channel still need
independent source, replay, quota and accounting checks before SRC-01 closes.

Docker's local daemon, CLI and host/kernel remain trusted. The tests do not
establish resistance to every kernel/container exploit or every resource attack.
The wall limit stops the owned container; existing synchronous host callback
finalization can extend return time. Docker control output is trusted metadata
with a post-capture size check. The image retains the already reviewed base's
OS/GNU/LGPL notice scope; see [the prior base-license findings](conformance/nb02c3-runtime.md#license-findings-before-local-use).
This local image has not been published/distributed. There is no claim of an
all-permissive OS, a whole-OS vulnerability audit or legal clearance.

## Reproduce on the Windows Docker Desktop host

Use the repository folder in PowerShell, with Docker Desktop's Linux engine
running. Python 3.13, the pinned base image and the existing Docker buildx plugin
must already be installed locally. These commands make no API calls, use no keys
or paid allocation and perform no image pull. A missing base fails the build.
Use a new unused build folder and output filename for each attempt so old proof
is retained. Both helper CLIs accept relative paths from this folder.

Create the ignored local working folder, if needed. This runs once and only
creates the folder; it does not spend money or change an experiment.

```powershell
New-Item -ItemType Directory -Force runs | Out-Null
```

Build a separate local image and save its source context, build logs, actual
configuration, fresh inventory and environment record in a new folder. This
runs once in the same window and uses local disk space. Build steps have network
access disabled and a clean Docker client configuration. Ctrl+C requests a stop;
interruption can leave local build cache or an image.

```powershell
python docs/conformance/src01-runtime-probe.py build --directory runs/src01-runtime-rebuild-1
```

Run the complete confinement checks and literal-source fixtures against that
new image, then save a new proof. This runs once in the same window; no separate
window is needed. Ctrl+C stops the foreground probe and the executor attempts
owned-container cleanup. Failure evidence and build files remain for review.

```powershell
python docs/conformance/src01-runtime-probe.py probe --environment runs/src01-runtime-rebuild-1/environment.json --out runs/src01-runtime-rebuild-proof-1.json
```

The new environment/proof is a new measurement. A rebuild may have a different
image identity; review and record it before using it in any execution contract.
It does not update the frozen image record, existing agents, grants or owners.
