# BENCH-02C3: minimal Linux runtime preparation

This prepares the actual installed environment for the complete official LLM
scoring and summary modules. It is an offline engineering step: no model calls,
API keys, or paid allocation are involved. It does not close BENCH-02C3 or certify
the worker, host channel, CLI hooks, cancellation, generation, or confinement.

The source is the unchanged official checkout at commit
`64a23be6b18ec1dacc298830aab276061b6e143c`, whose `pyproject.toml` requires
Python `>=3.11`. The active image uses CPython 3.13.12 on Linux amd64. Its base is
the immutable platform manifest
`python@sha256:3121f8b0804aa3698ab750d9a39ea4a42657a385c9b133722b915e55c51551a6`.
[The environment record](nb02c3-runtime-environment.json) contains the final
local image identity, exact configuration, helper and installed-manifest hashes,
provenance, evidence hashes, and limits.

The 28-package set derives from
[the original reference requirements](nb02-reference-requirements.txt), changing
only AnyIO 4.10.0 to 4.14.2. The original requirements and research environment
remain intact. Both SDK requirements accept this version. The explicit security
overlay addresses the maintainers' [TLS advisory](https://github.com/agronholm/anyio/security/advisories/GHSA-82r6-8w77-94w6)
and [subprocess advisory](https://github.com/agronholm/anyio/security/advisories/GHSA-5p39-cfhj-2xmp).
Import success and dependency compatibility do not establish behavioral parity;
the patched environment needs the native differential checks in the composed
C3 work.

## What was measured

The final image installs verified Linux wheels offline, without pip in the
active venv. Installation uses hashes and no dependency resolution. `pip check`
found no broken requirements. A requirement-set `pip-audit` found no known
vulnerabilities; this is not an OS vulnerability assessment or a future guarantee.

The installed-file audit checks all 6,546 installed RECORD entries for file
existence, SHA256, declared size, and venv containment, then inventories the
actual venv tree (6,556 entries). It rejects unowned site-packages files.
The fresh, read-only audit produced the same manifest bytes as the image build.
All wheel license and notice files remain installed.
Actual read-only override-mount probes also confirmed rejection of a changed
installed `six.py` and an extra unowned site-packages file.

Actual imports of `src.score`, `src.summarize`, `src.judge`, and
`src.evaluation_io` succeeded under a nonroot, read-only, network-disabled
container with 512 MiB memory, one CPU, 32 processes, no capabilities, and a
bounded temporary filesystem. All 2,652 imported module origins were recorded;
no module came from the base image's site-packages. Imports did not change the
installed tree. This is the LLM score/summary closure, not the reward-model,
partition, ROUGE, Torch, vLLM, or whole-project dependency set.

The measurements are retained under `runs/reviews/nb02c3-runtime-*.json`.
[The wheel record](nb02c3-runtime-wheels.json) records source URLs, upstream-lock
or overlay hashes, metadata, and the 30 actual wheel license/notice file hashes.
The environment record seals the larger local evidence rather than pretending
the wheelhouse is an installed environment.

## Installed audit API and origin rules

The fixed interpreter is `/opt/venv/bin/python`. Load the verified stdlib-only
helper `/opt/runtime-prepare.py` by its fixed filepath and call
`collect_audit()`. It returns a dictionary with format
`buddha.review.nb02c3-installed-runtime.v1`; failed RECORD or tree checks raise
an error. The `audit` CLI prints the same dictionary as JSON.

`inventory` maps relative paths to `{sha256, bytes}` for regular files.
Symlinks have `{symlink, target_is_directory}` and, for file targets,
`target_sha256`. `bin/python*` resolve to the base image's
`/usr/local/bin/python3.13`; `lib64` points to `lib`. The target details are
part of the evidence. A flat file-hash map does not account for these links.
`distributions` records each package's name, version, and checked RECORD files.

The stdlib at `/usr/local/lib/python3.13` belongs to the immutable base image,
not the venv inventory. `/usr/local/lib/python3.13/site-packages` is excluded
from valid imported dependency origins. Python's namespace packages have
no file origin: the observed ones are `src`, `anthropic._decoders`, and
`anthropic.lib._parse`, with explicit measured search paths. The observed
fileless generated modules are `_cython_3_1_0`, `_cython_3_1_3`,
`cython_runtime`, and `six.moves`. The Cython modules appeared during pandas
import; `six.moves` uses the installed `six._SixMetaPathImporter`. These require
explicit image-specific treatment, not blanket acceptance of unknown origins.
The worker bootstrap's `__main__` identity needs its own source binding.

The host must verify the actual launched immutable image identity. The worker
must independently verify the helper, installed inventory, selected official
and runner sources, and imported origins before requests and at completion.
This document supplies measurements; those execution guards belong to C3.
The internally stored RECORD is not an independent trust anchor: comparing the
measured tree with the owner's frozen expected inventory is still required.

## License findings before local use

The actual NumPy Linux wheel contains GPL-3.0-with-GCC-exception notices for
bundled `libgfortran` and LGPL-2.1-or-later notices for bundled `libquadmath`.
Certifi uses MPL-2.0. Tqdm's license metadata is `MPL-2.0 AND MIT`, with
component-specific terms in its LICENCE file. The Debian base contains GNU/LGPL
tools and libraries; 97 `/usr/share/doc/*/copyright` files were inventoried.
A text marker is not a legal classification of every file containing it.

These were flagged before the local isolated build. Notices are retained.
This work does not authorize publishing or distributing the image or make a
commercial-license assessment. No HyperAgents code or dependencies are used.

Ruff passes for the preparation helper. A separate Bandit scan reports B404
for importing subprocess, B603 for the pip argument-vector subprocess, and B310
for `urlopen`. These remain visible, unsuppressed findings: the subprocess uses
the host interpreter without a shell, and the URL is a fixed HTTPS PyPI address
whose overlay wheel hash is independently fixed. The image and helper have not
been changed to hide these findings. The normal application scan does not
include documentation helpers.

## Reproduce preparation

Run these from the repository folder in the same PowerShell window, with Docker
Desktop's Linux engine running and Python 3.13 available. The pinned official
checkout must already exist under
`runs/references/noveltybench-conformance/64a23be6b18ec1dacc298830aab276061b6e143c`.
Each command runs once, uses local disk space, and makes no paid model calls.
Use Ctrl+C to stop a foreground command. A rebuild creates a new image identity;
record and review it instead of reusing the old identity silently.

Download and verify the exact Linux wheels, extract their notices, and produce
the derived requirements and wheel record. This needs internet access and
does not install them into your normal Python environment.

```powershell
python docs/conformance/nb02c3-runtime-prepare.py download
```

Copy the reviewed recipe into its separate local build folder and restrict the
files available to Docker's builder. This changes only the ignored build folder.

```powershell
Copy-Item docs/conformance/nb02c3-runtime-prepare.py runs/reference-linux-nb02c3/runtime-prepare.py
Copy-Item docs/conformance/nb02c3-runtime.Dockerfile runs/reference-linux-nb02c3/Dockerfile
@'
*
!Dockerfile
!requirements.txt
!runtime-prepare.py
!wheelhouse.json
!wheels/
!wheels/*.whl
'@ | Set-Content -Encoding ascii runs/reference-linux-nb02c3/.dockerignore
```

Fetch the exact official base image. This uses internet access and local disk.

```powershell
docker pull --platform linux/amd64 python@sha256:3121f8b0804aa3698ab750d9a39ea4a42657a385c9b133722b915e55c51551a6
```

Build the isolated image from the verified wheels without network access during
installation. Empty proxy arguments prevent Docker's proxy configuration from
being added to the build. The image includes its installed-file manifest.

```powershell
docker build --network=none --platform=linux/amd64 --progress=plain `
  --tag=buddha-nb-runtime:nb02c3-sdk-v1 `
  --iidfile=runs/reference-linux-nb02c3/image-id.txt `
  --build-arg=HTTP_PROXY= --build-arg=HTTPS_PROXY= --build-arg=ALL_PROXY= --build-arg=NO_PROXY= `
  --build-arg=http_proxy= --build-arg=https_proxy= --build-arg=all_proxy= --build-arg=no_proxy= `
  runs/reference-linux-nb02c3
```

Optionally audit the actual installed files again. It starts one temporary
read-only container, prints a large JSON manifest, then exits and removes that
container. The image remains. It needs no internet or keys and changes no run.
Use the frozen image digest from the environment record, rather than relying
on a mutable tag, when integrating it into a recorded execution.

```powershell
docker run --rm --pull=never --network=none --read-only --user=65532:65532 `
  --cap-drop=ALL --security-opt=no-new-privileges --pids-limit=32 `
  --memory=512m --memory-swap=512m --cpus=1 --log-driver=none `
  sha256:d9476e5c6baf21ba4e70709b96100bdc7fe30637e59a377432690088c8dc77c1 `
  /opt/venv/bin/python -I -B /opt/runtime-prepare.py audit
```

The environment record labels the local image with `buddha-nb-runtime@` before
its SHA256. The suffix is the actual local Docker image ID, not a published
registry manifest digest. Pass `sha256:...` directly, as above; no image has
been published to a registry.
