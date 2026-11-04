# Fresh comparison: review preparation

The fresh comparison keeps the original review method: twelve complete Buddha
answer sets, containing up to 120 answers, selected in advance from four final
tasks and four task families. Each task supplies the starter, initial-improver
and evolved-improver sets for one of the four comparison conditions. The
selection and criteria remain fixed before any new outputs exist.

The two tracks in [REVIEW-TRACKS.md](REVIEW-TRACKS.md) still apply. The AI-evaluated
result can proceed without human availability. Human ratings can be added later
against the same frozen evidence, with their own roster, exposure disclosures,
uncertainty and conclusions. No human agreement or validation is claimed until
people actually provide ratings. The sample covers Buddha; it does not add a
human comparison against the two plain-model controls.

The [preparation recipe](conformance/prepare-fresh-review.py) reuses the existing
review, population, assessment, arithmetic and handoff validators. It adds a
review-bound version of the primary configuration. It copies the original
protocol, materials and proposed native-review route byte for byte, and changes
only the review plan's experiment and file references. The original primary
configuration and both plain-reference descriptors remain separate, unchanged
inputs. A future combined handoff must select this review-bound assessment.

The custody record gains eight references to the review materials and their
current consumers. All its other fields remain unchanged. This binds what will
be reviewed; it does **not** certify new reviewer independence, task secrecy or
absence of model prior knowledge. The static worker trace sends only the current
task to a generator and development feedback to an improver. Actual runtime
containment, opaque program behavior and prospective exposure checks still have
their own gates in [PLAN.md](PLAN.md).

Preparation creates local configuration files only. It starts no reviewers,
exports no answers, creates no packets or rating rounds, and allocates no
spending authority. Actual review records need the real completed outputs.
The earlier native model/context selection and $150 approval belong to the
interrupted original experiment; neither authorizes fresh work.

## Recorded result: November 2, 2026

The configuration completed in 10.244 seconds under a 300-second limit, with
twelve indexed files plus its result at `runs/imp01-fresh-review-20261102-v1`.
The existing full handoff checker passes with funding unallocated and no runtime
created. Four supplied checks and all eight scoped quality commands pass.
The first preparation stopped before writing output because of a set-operation
error in the recipe; that observation and its executed source remain retained.
The corrected observation has its own manifest and receipts. Hosted CI and
scientific acceptance remain separate. [Exact evidence and limits](conformance/fresh-review-delivery.json).

## Developer checks

This optional command runs the four supplied metadata checks once, from a
checkout containing this slice:

```powershell
python -m unittest discover -s tests -p test_fresh_review_preparation.py -v
```

It checks that the review selection stays fixed, rejects incorrect answer
counts and repeated families, and preserves existing custody fields. It needs
no keys or Docker, spends no API money and does not read frozen experiment
inputs. Use the current PowerShell window. Expect `Ran 4 tests` and `OK`; zero
tests means this checkout lacks the slice. Ctrl+C stops it. The direct command
has no enforced time limit; the retained supplied observation used 120 seconds.

The recipe's `--inputs` option names its reviewed file manifest; `--sha256`
binds that manifest's exact fingerprint. These are developer preparation
options, not a live-run command. They write once to a new destination, need no
keys and spend no model API money. Partial files are retained on failure. Do
not rerun a recorded preparation in place.

Only named inputs are admitted. Private programs and inherited evidence are
verified as bytes rather than interpreted. Error records retain the stage,
class and public code location without private messages or source lines.
These checks surround trusted preparation code; they are not a sandbox for
arbitrary programs. Before/after fingerprints are not an atomic host snapshot.
