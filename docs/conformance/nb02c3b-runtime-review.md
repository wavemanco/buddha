# BENCH-02C3B: held original partition dependency record

The original locked Linux dependency closure has been downloaded and inspected,
but **installation and image creation are held**. Actual NVIDIA license terms
restrict CUDA/cuDNN/cuSPARSELt use to applications running on NVIDIA GPUs. This
project's confined evaluator has no GPU. Keeping these files for review does not
authorize running or redistributing them. A separately identified official Torch
CPU build is being investigated; it must not overwrite this record or be described
as the original upstream binary lock.

No model calls, credentials, model assets, host-package installation or new Docker
image were involved. All existing `nb02c3-*` records and the C3A image remain intact.
This is dependency preparation, not a full partition-conformance result.

The immutable official reference is commit
`64a23be6b18ec1dacc298830aab276061b6e143c`. Its Python requirement is `>=3.11`.
Selection targets CPython 3.13.12, Linux amd64, and the existing glibc 2.36 base.
The helper verifies the actual upstream lock/project and sealed C3A requirements
and wheel record before deriving anything. It uses the already pinned development
tool `packaging==26.0`; application dependencies do not change.

The four unconditional partition imports—Torch 2.7.1, Transformers 4.56.1,
SacreBLEU 2.5.1 and ROUGE 0.1.2—have a 51-distribution Linux closure. Combining
that with C3A gives 72 distributions: 44 additions and seven reused dependencies.
Only the previously declared AnyIO 4.10.0 → 4.14.2 security overlay remains.
No other version or binary source is replaced in this held profile.

| Observed preparation | Result |
| --- | --- |
| Exact locked/overlay artifacts | 71 wheels and one original ROUGE source archive |
| Actual compressed bytes | 3,059,502,998, including the 17,400-byte source archive |
| Additional wheel bytes relative to C3A | 3,023,784,651 |
| Actual indexed license/notice members | 104 |
| Primary metadata snapshots | 72/72; response bodies retained with SHA256 and byte counts |
| Target dependency and Python constraints | All available active METADATA requirements compatible |
| Installation / active image | Not enabled |

[The artifact record](nb02c3b-runtime-wheels.json) contains exact artifact URLs,
sizes/hashes, selected lock edges, metadata requirements and notice inventories.
[The requirements](nb02c3b-runtime-requirements.txt) reproduce that source selection.
The ROUGE entry still names the original source hash: these are **not** approved
installation instructions. Its source archive has old metadata without
`Requires-Dist`; its dependencies come from the sealed lock and inspected
`setup.py`, pending a separately sealed wheel build.

Artifacts and extracted notices are under ignored
`runs/reference-linux-nb02c3b/artifacts/` and `licenses/`. Complete primary metadata
responses are under its `metadata/` folder. The subsequently approved isolated
ROUGE build belongs to the [separate CPU variant](nb02c3b-cpu-review.md), with
its own derived-wheel receipt. It does not overwrite this source selection.

## Actual notices and unresolved restrictions

All fourteen NVIDIA artifacts contain actual license members. Twelve identify
proprietary software; NCCL and NVTX carry separate terms. The GPU-purpose
restriction is an actual-text finding, rather than an inference from a package
classifier. [The independent security/license review](nb02c3b-security-review.md)
records the applicability assessment and release gate.

NumPy physically bundles GNU runtime libraries already flagged for C3A.
Setuptools vendors LGPL-3.0 autocommand. Torch's omnibus license includes LGPL/GPL
third-party notices whose binary reachability has not been established here.
The manifest's GNU/MPL/proprietary booleans are text-search indicators for review,
not a legal classification of every matching file. Preserve notices and resolve
distribution obligations separately; no image publication is authorized.

Four sealed artifacts contain no separately named license/notice file discoverable
by the helper: jiter (already present in C3A), ROUGE's source archive, tokenizers
and Triton. This absence is explicit. ROUGE source files have Apache-2.0 headers
and its metadata declares the Apache classifier; the missing standalone file is
not silently replaced with a new download or an invented notice.

## Security and execution limits

[The dated advisory snapshot](nb02c3b-runtime-advisories.json) records primary PyPI
responses for all 72 exact versions. Nine have advisory entries: filelock,
fsspec, lxml, NLTK, Requests, setuptools, Torch, Transformers and urllib3. This
preflight does not establish an installed, operating-system or ELF-library audit,
and advisory absence is not a future guarantee. Version-update candidates are
not automatically approved compatibility fixes.

The unchanged official CLI uses `--version 1.1 --alg llm`. Its selected call path
does not invoke model/checkpoint loading, classifier downloads, BERTScore assets,
XML parsing or fsspec reference templates. Torch import and
`torch.cuda.is_available()` do execute; import-time filelock/cache/native-library
behavior still needs actual confined measurement. There is no blanket advisory
waiver. The CLI has no fallback flag; separately configured source-stage fallback
checks must be labeled separately.

Full partition import and CLI execution remain unmeasured in this held
environment. Static inspection also predicts relative-placeholder origins for
`torch.ops` / `torch.classes`; the actual worker audit must measure and narrowly
attribute generated modules rather than permit arbitrary unknown origins.

## Preparation commands

Run from the repository folder in the same PowerShell window using the existing
Python 3.13 development environment. The pinned official reference must already
exist at its documented `runs/references/noveltybench-conformance/` path.
Every command runs once, needs no API key and spends no model budget. No separate
window is needed. `Ctrl+C` stops a foreground command. `-B` prevents Python from
writing bytecode cache files.

Refresh the 72 primary package-metadata snapshots. This uses the internet and
writes the dated advisory record plus ignored raw responses; a changed snapshot
needs review again. It neither downloads models nor installs packages.

```powershell
python -B docs/conformance/nb02c3b-runtime-prepare.py metadata
```

Download and hash-check the exact held artifacts, inspect their metadata, extract
notices and regenerate the two source-selection records. This uses about 3.06 GB
of local compressed-artifact space plus extracted notices. Verified files already
present are reused; an incomplete `.part` download is overwritten on retry.
This command does not install or execute these packages.

```powershell
python -B docs/conformance/nb02c3b-runtime-prepare.py download
```

Check the frozen source seals, exact requirements, full artifact/notice record,
actual local file hashes, retained metadata responses and dependency constraints.
This needs the prepared local files, uses no internet and changes nothing.

```powershell
python -B docs/conformance/nb02c3b-runtime-prepare.py check
```

Run the small offline regression checks. They exercise changed source/artifact
hashes, disallowed origins, changed requirements, missing dependencies, and actual
Linux nvJitLink versus incompatible Windows wheel tags. They create and remove
temporary test files, without altering the frozen reference or artifact records.

```powershell
python -B docs/conformance/nb02c3b-runtime-prepare.py self-test
```

All modes accept optional `--directory PATH` to use a different prepared artifact
folder. Source seals and the repository's review records remain fixed; changing
this path does not authorize a different dependency selection or installation.
