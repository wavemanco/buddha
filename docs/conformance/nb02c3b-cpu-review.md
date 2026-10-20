# BENCH-02C3B: explicitly identified CPU dependency variant

This profile replaces the original Torch binary with the official
`torch==2.7.1+cpu` build. It is **not the exact upstream binary lock**. The original
72-artifact CUDA selection remains preserved and held in
[its separate record](nb02c3b-runtime-review.md). No CUDA image is enabled.
The CPU profile has been reviewed for private confined research; known security,
GNU component-notice and redistribution limitations remain explicit in
[the independent review](nb02c3b-security-review.md).

The unchanged benchmark source still comes from commit
`64a23be6b18ec1dacc298830aab276061b6e143c`, with metric version 1.1 and the actual
`--alg llm` entry point. All other original package versions remain fixed,
including the existing explicit AnyIO 4.14.2 overlay. This profile makes no model
calls and downloads no model assets.

[The official CPU index](https://download.pytorch.org/whl/cpu/torch/) points to
the actual CPython 3.13 Linux amd64 wheel on `download-r2.pytorch.org`. Its SHA256
is `84ea1f6a1d15663037d01b121d6e33bb9da3c90af8e069e5072c30f413455a57`;
its size is 175,839,558 bytes. The index's separately advertised metadata hash
was verified and then matched against the actual wheel's METADATA.

| Measured source preparation | Result |
| --- | --- |
| Target | CPython 3.13.12 / Linux amd64 / existing glibc 2.36 base |
| Exact CPU artifact selection | 57 distributions; original ROUGE source remains sealed separately |
| Compressed source artifacts | 250,669,871 bytes |
| Actual indexed notice members | 90 |
| NVIDIA / Triton dependencies | None in the actual active metadata closure |
| Other selected artifacts | Byte-identical to their held original seals |
| Installation / new image | Separately gated; not performed by these helpers |

[The CPU source-artifact inventory](nb02c3b-cpu-wheels.json) records the complete
metadata-derived graph. ROUGE's old PKG-INFO omits Requires-Dist, so the graph
explicitly uses its reviewed, hash-bound setup.py dependency list. The original
[CPU requirements](nb02c3b-cpu-requirements.txt) preserve that source selection;
they are not an approved instruction to execute a source build during installation.
The isolated derived-wheel receipt must supply the eventual wheel's new hash.

Comparing both actual Torch archives as data found the same 1,972 Python source
paths. Of these, 1,971 are byte-identical, including the CUDA availability API;
only `torch/version.py` differs. Both identify source Git revision
`e2d141dbde55c2a4370fac5165b0561b6af4798b`. The original reports
`2.7.1+cu126` / CUDA 12.6; the CPU build reports `2.7.1+cpu` / CUDA None.
This is source-comparison evidence, not binary equivalence or an observed import
result. The full official module and confined CLI still need actual differential
execution on this same CPU environment.

## Security and notices

[The CPU advisory mapping](nb02c3b-cpu-advisories.json) retains the original dated
primary findings for selected package versions. Torch `2.7.1+cpu` explicitly maps
to the public `2.7.1` source advisory set. A missing PyPI CPU-version record would
not mean that the CPU wheel has no vulnerabilities. No new Torch/Transformers major
version or unreviewed security patch is silently substituted.

[A separate supplement](nb02c3b-cpu-bundled-advisories.json) checks all sixteen
actual vendored METADATA versions in the Setuptools wheel. Its primary metadata
reports findings for jaraco.context 5.3.0 and wheel 0.45.1. This does not alter the
frozen 72-package snapshot. The controlled ROUGE extraction does not use
`jaraco.context.tarball()` or the wheel unpack CLI; installing another package
merely to perform extraction is unnecessary.

The CPU Torch wheel has actual LICENSE and NOTICE files. Its NVIDIA 2002
permissive notice is distinct from the GPU-purpose terms in the held CUDA wheels.
The actual CPU archive has no CUDA/cuDNN/NCCL libraries. It does bundle
`libgomp.so.1`; the component-to-GCC-runtime-exception notice mapping remains a
distribution provenance gap. Existing NumPy GNU runtime and Setuptools LGPL
notices remain relevant. No image publication or general commercial-license
clearance is granted.

## Offline ROUGE build

The approved recipe uses the unchanged C3A image and actual generic executor.
Only a reviewed build worker, the real channel import closure, the verified
17,400-byte source archive, Setuptools 79.0.1 wheel and hashed builder requirements
are mounted read-only. The container has no network, credentials, GPU, writable
host mount or extra capabilities. It has 512 MiB memory/swap, 128 MiB scratch,
32-process, one-CPU and 120-second limits.

The worker reads the bounded source archive as data, rejects traversal, case and
ancestor aliases, links, devices, duplicate paths and excessive sizes, then writes
files exclusively into two fresh source directories. A scratch venv uses symlinks
to the immutable base interpreter, retaining the executor's noexec scratch mount.
Only the pinned Setuptools wheel is installed there, offline and without dependency
resolution. No package setup.py runs on the host.

Both source builds use the same verified builder environment and separate source
and build directories. SOURCE_DATE_EPOCH is fixed. Python isolation (`-I`) keeps
hash randomization enabled; no effective deterministic PYTHONHASHSEED is claimed.
The required evidence is measured equality of the two wheel outputs.

The host buffers provisional frames until exit zero and owned container removal.
It checks the fixed wheel name, size, every mapped package-source byte, generated
metadata, all RECORD hashes/sizes, paths, types and timestamps before publishing.
The actual builder files are compared with their sealed original wheel and audited
through RECORD before and after both builds. Local command diagnostics are checked
after capture inside the finite-memory container; the 2 MiB diagnostic check is
not described as a preallocation limit.

Each attempt has its own ignored UUID receipt directory. Failed attempts retain
mechanical execution or failure records; they never become accepted wheels.
The first actual attempt failed because the real channel's release-module import
closure had not been staged. Its exit-1/removed-cleanup receipt is retained. The
corrected staging has a regression that imports all three real copied modules
under isolated Python. A second attempt stopped when the strict source-name
validator rejected legitimate Setuptools template names. The correction uses the
existing general portable-path validator for that separately verified builder
wheel, preserving the strict ROUGE source parser. Both failed receipts remain.

The third actual attempt succeeded: both independent builds produced
`rouge_score-0.1.2-py3-none-any.whl`, 24,987 bytes, SHA256
`bab5e3cb074d16e6e0968044d54816798caee21c69c543be381166cb8092fa0e`.
All fourteen package source files match the original archive exactly; all eighteen
wheel members have checked RECORD entries. The builder's before/after audit
matches, and the container exited zero with owned cleanup `removed`.
The receipt is under ignored
`runs/reference-linux-nb02c3b/cpu/build-results/29baee26912f452b9691bc35997f43bd/`;
the accepted wheel is in `cpu/derived-wheels/`. This is a new derived artifact,
not the original published source hash. No CUDA/Triton artifact was installed or executed.

Final local checks pass: strict 72- and 57-artifact verification, three dependency
preparation regression groups, eight build/parser/provenance/staging groups, Ruff
lint and formatting. Additional read-only mutations of the accepted wheel reject
changed package source and a changed RECORD hash; their evidence is retained under
`runs/reviews/nb02c3b-rouge-wheel-adversarial.json`. These checks establish the
bounded preparation/build result, not full evaluator import or CLI conformance.

A separate Bandit scan of the four engineering scripts reports six visible,
unsuppressed findings: two B102 uses compile the specific reviewed engineering
helper/worker bytes, avoiding adjacent-bytecode substitution; four B404/B603
findings cover subprocess imports/calls. Worker build commands run inside the
bounded offline container; the host subprocess regression imports only the three
trusted copied project modules under isolated Python with a ten-second timeout.
No downloaded package setup.py runs on the host. These reviewed engineering
findings are separate from the normal application-only security scan.

## Commands

Run from the repository folder in the same PowerShell window, using the existing
Python 3.13 development environment. Each command runs once, needs no key and spends
no model budget. `Ctrl+C` stops a foreground command. No separate window is needed.
The existing pinned official reference and sealed review records are prerequisites.

Prepare or recheck the CPU source-artifact selection, downloading only missing
verified files and copying existing verified artifacts where possible. It writes
the CPU source-selection records and ignored artifacts/notices; it does not install
them or create an image. A fresh CPU source selection uses about 251 MB compressed.

```powershell
python -B docs/conformance/nb02c3b-cpu-prepare.py prepare
```

Verify the exact 57-artifact selection, actual notices, metadata requirements and
explicit advisory mapping. This uses local files only and changes nothing.

```powershell
python -B docs/conformance/nb02c3b-cpu-prepare.py check
```

Refresh the sixteen vendored-package primary metadata snapshots and separate
supplement. This uses internet access and changes that dated supplement; new
findings need review again. It installs nothing.

```powershell
python -B docs/conformance/nb02c3b-cpu-prepare.py bundled
```

Run the offline source-parser, environment/source-drift and real isolated staging
regressions. This creates temporary test files and one short isolated Python
subprocess, then removes them. It needs no Docker engine or internet.

```powershell
python -B docs/conformance/nb02c3b-rouge-build.py self-test
```

Build ROUGE twice in the existing local C3A container image and validate/export
the result. Docker Desktop's Linux engine must be running. This starts and removes
one bounded offline container; it installs pinned build tooling only in that
container's temporary scratch space. It creates a fresh local attempt receipt and
reuses an existing derived wheel only if its bytes are identical. The command prints
the accepted wheel and new receipt paths; it never overwrites a previous receipt
or writes a tracked delivery record. A stop or failure leaves no accepted partial
wheel. A new full evaluator image is a separate step.

```powershell
python -B docs/conformance/nb02c3b-rouge-build.py build
```

## Separately installed CPU image

The private local image is
`sha256:969cbc318ec2d05502665b8ef2b4020307e4335b75e5d17584910aa51e31bf83`.
It uses the unchanged C3A Dockerfile and audit helper, the 56 verified binary
CPU-profile artifacts and the separately built ROUGE wheel. The private build
context contains exactly 62 files (250,823,483 bytes). Installation used no
network, no SSH or secret mounts, empty explicit proxy arguments and a separate
Docker client configuration containing only the installed Buildx plugin path.
The host environment passed to the builder excludes model keys and proxy values.
No image was published.

The pinned base image was already local. The first image-build attempt stopped
because the fresh client configuration could not locate the installed Buildx
plugin. A subsequent provenance-export preflight incorrectly applied selected
component hard-link rules to that installed host tool and stopped before building.
Both observations remain in the private receipts. Explicitly locating and hashing
the existing trusted host plugin fixed preparation without weakening component
rules or installing another dependency.

The successful image passed `pip check`. Fresh restricted audits, including an
independent reviewer run, produced the exact built installed manifest: **57
distributions, 24,043 tree entries, 24,033 checked RECORD files and zero unowned
site-packages files**. Its 8,799,208 bytes have SHA256
`b6b8ab4d349926577905b95b0784c622d6e443f34ea2b73625e09e72b497cf4b`.
The first audit's report export failed on a private byte field after cleanup;
the corrected public-field export and a fresh audit passed. Source, context,
command, image and installed-audit seals are retained under
`runs/reference-linux-nb02c3b/cpu-image-v1/receipts/` and in
[the environment record](nb02c3b-runtime-environment.json).

This remains a separately identified private LLM evaluator environment. The GNU
runtime notices, bundled-component notice gaps and known advisories documented
above remain applicable. It must not execute arbitrary evolved agent code.
An installed audit does not by itself close full native partition conformance.

With that exact local image already available and Docker Desktop's Linux engine
running, this optional command audits the installed files again. It runs once in
the same PowerShell window, prints a large JSON file list, removes its temporary
container and leaves the image and experiment records unchanged. It needs no
internet or API keys and spends no model budget. `Ctrl+C` stops the foreground
command and Docker attempts removal of that container.

```powershell
docker run --rm --pull=never --network=none --read-only --user=65532:65532 `
  --cap-drop=ALL --security-opt=no-new-privileges --pids-limit=32 `
  --memory=1024m --memory-swap=1024m --cpus=1 --log-driver=none `
  sha256:969cbc318ec2d05502665b8ef2b4020307e4335b75e5d17584910aa51e31bf83 `
  /opt/venv/bin/python -I -B -X pycache_prefix=/__absent_bytecode_cache /opt/runtime-prepare.py audit
```
