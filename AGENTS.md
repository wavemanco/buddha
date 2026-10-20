# Project planning context

Follow the user's host engineering instructions. Before substantial work, read [docs/PLAN.md](docs/PLAN.md): it is the single living roadmap for scope, status, dependencies and the next slice. [docs/DESIGN.md](docs/DESIGN.md) remains the technical/scientific contract; dated reports and run artifacts remain evidence.

When new findings or completed work change the roadmap, update the relevant stable item, gate, evidence link and revision log in `docs/PLAN.md`. Preserve original objectives and frozen experiment history. Do not create competing plans or treat historical next-step sections as current scheduling authority.

The user's standing implementation instruction is to continue through the plan, pausing only when a live run or a user decision is required. After each small slice, relay a summary here, commit it and create its own PR; then continue authorized independent work. This supersedes the earlier default to stop after every slice. Keep unreviewed dependent PRs stacked rather than silently merging them.

Document every user-facing command in the relevant project guide, including optional commands. Put a short, plain-English explanation beside it, written for someone with basic CLI/PowerShell skills. Explain what it does and, where relevant, whether it spends money or changes anything, runs once or keeps running, needs a separate window, and how to stop it. Keep this crisp; avoid unexplained jargon.
