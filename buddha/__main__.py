"""Local CLI; model network access requires the explicit run --live option."""

import argparse
import hashlib
import http.client
import json
import re
import sys
import tempfile
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager, suppress
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

from buddha.authorization import Authorization, runtime_fingerprint
from buddha.benchmark import (
    UPSTREAM_COMMIT,
    _canonical,
    _object,
    _parse,
    import_evaluation,
    load_prompts,
    prompt_manifest,
)
from buddha.credentials import KeyInputError as KeyInputError
from buddha.credentials import getpass as getpass
from buddha.credentials import key_environment as _shared_key_environment
from buddha.credentials import os as os
from buddha.diagnostics import DiagnosticHTTPTransport, failure_summary
from buddha.evaluation import ValidationError
from buddha.history import _plain
from buddha.ledger import Ledger
from buddha.policy import Policy
from buddha.provider import Call, ModelSpec, Reply
from buddha.run import DATASETS, ReplayTransport, RunSettings, load_run, prepare_run, run_baseline


def _notice(message: str) -> None:
    # Console output must never change a paid operation's outcome.
    with suppress(OSError, ValueError):
        print(f"[buddha] {message}", file=sys.stderr, flush=True)


def _error_record(message: str, directory: Path | None) -> dict[str, object]:
    record: dict[str, object] = {"error": message}
    if directory is not None:
        diagnostic = failure_summary(directory)
        if diagnostic is not None:
            record["diagnostic"] = diagnostic
            _notice("Provider failure metadata was saved; the reservation remains held.")
    return record


def _usd(value: object) -> int:
    if (
        not isinstance(value, str)
        or len(value) > 32
        or not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,6})?", value)
    ):
        raise ValidationError("set budget_usd to an explicit decimal string")
    try:
        amount = Decimal(value)
        micros = amount * 1000000
        if (
            not amount.is_finite()
            or not 0 < micros <= 2**63 - 1
            or micros != micros.to_integral_value()
        ):
            raise ValidationError("budget must be positive USD with at most six decimal places")
        return int(micros)
    except InvalidOperation:
        raise ValidationError("invalid USD budget") from None


def _settings(path: Path, budget_override: str | None) -> RunSettings:
    raw = _object(_parse(path.read_bytes()))
    amount = raw.pop("budget_usd", None)
    if "budget_microusd" in raw:
        raise ValidationError("configuration uses budget_usd, not budget_microusd")
    raw["budget_microusd"] = _usd(budget_override if budget_override is not None else amount)
    return RunSettings.from_record(raw)


@contextmanager
def _key_environment(settings: RunSettings, *, prompt_keys: bool) -> Iterator[None]:
    """Optionally acquire missing credentials without files, echo or shell history.

    Only the trusted host runs in this process. These temporary environment values
    must never be inherited by a future generated-source executor.
    """
    with _shared_key_environment(settings, prompt_keys=prompt_keys, notice=_notice):
        yield


def _fetch(dataset: str, destination: Path) -> None:
    filename, expected = DATASETS[dataset]
    connection = http.client.HTTPSConnection("raw.githubusercontent.com", timeout=30)
    try:
        connection.request("GET", f"/novelty-bench/novelty-bench/{UPSTREAM_COMMIT}/data/{filename}")
        response = connection.getresponse()
        raw = response.read(8 * 1024 * 1024 + 1)
        if response.status != 200 or hashlib.sha256(raw).hexdigest() != expected:
            raise ValidationError("official dataset fetch failed byte verification")
    finally:
        connection.close()
    if destination.is_symlink():
        raise ValidationError("dataset destination must not be a symlink")
    if destination.exists():
        if destination.read_bytes() != raw:
            raise ValidationError("dataset destination conflicts; nothing overwritten")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(raw)
    print(json.dumps({"dataset": dataset, "sha256": expected, "upstream_commit": UPSTREAM_COMMIT}))


def _check_upstream() -> None:
    connection = http.client.HTTPSConnection("api.github.com", timeout=30)
    try:
        connection.request(
            "GET",
            "/repos/novelty-bench/novelty-bench/git/ref/heads/main",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "buddha-benchmark"},
        )
        response = connection.getresponse()
        raw = response.read(65537)
        if response.status != 200 or len(raw) > 65536:
            raise ValidationError("could not verify the latest official benchmark revision")
        latest = _object(_object(_parse(raw)).get("object")).get("sha")
        if latest != UPSTREAM_COMMIT:
            raise ValidationError(
                "upstream changed; review and update the benchmark pin before a new run"
            )
    finally:
        connection.close()


def _demo(destination: Path) -> None:
    if not destination.exists():
        profiles = [
            ModelSpec("replay", model, 100000, cap, 1000000, 1000000, "offline fixture")
            for model, cap in [("generator", 4096), ("partition", 16000), ("quality", 16000)]
        ]
        settings = RunSettings(
            profiles[0],
            profiles[1],
            profiles[2],
            budget_microusd=1000000,
            max_calls=64,
            bounds_verified=False,
        )
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary) / "synthetic.jsonl"
            data.write_bytes(
                _canonical({"id": "demo-1", "prompt": "Offer a useful alternative."}) + b"\n"
            )
            prepare_run(
                destination,
                dataset_path=data,
                expected_dataset_sha256=hashlib.sha256(data.read_bytes()).hexdigest(),
                settings=settings,
                synthetic=True,
            )
    manifest, settings, _, _ = load_run(destination)
    if not manifest["synthetic"] or any(s.provider != "replay" for s in settings.profiles()):
        raise ValidationError("demo only resumes a synthetic replay run")
    summary = run_baseline(destination, transport=ReplayTransport())
    print(json.dumps({"mode": "synthetic_replay", "paid_calls": 0, "summary": asdict(summary)}))


class _SearchReplay(ReplayTransport):
    """Synthetic policy proposals; inherited judgments are deliberately constant."""

    def send(self, call: Call) -> Reply:
        body = _object(_parse(call.body_json.encode()))
        schema = _object(body.get("response_format", {})).get("json_schema", {})
        if _object(schema).get("name") == "Policy":
            self.calls += 1
            suffix = hashlib.sha256(call.body_json.encode()).hexdigest()[:16]
            policy = Policy(f"Synthetic demo policy {suffix}.", "in-context")
            return Reply(
                _canonical(policy.to_record()).decode(),
                call.spec.model,
                f"replay-{self.calls}",
                10,
                5,
                "stop",
            )
        return super().send(call)


def _search_demo(destination: Path) -> None:
    from buddha.search import SearchSpec, load_search, prepare_search, run_search

    if not destination.exists():
        profiles = [
            ModelSpec("replay", model, 100000, cap, 1000000, 1000000, "offline fixture")
            for model, cap in [("generator", 4096), ("partition", 16000), ("quality", 16000)]
        ]
        settings = RunSettings(
            profiles[0],
            profiles[1],
            profiles[2],
            budget_microusd=1000000,
            max_calls=256,
            bounds_verified=False,
        )
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary) / "synthetic.jsonl"
            data.write_bytes(
                b"".join(
                    _canonical({"id": name, "prompt": text}) + b"\n"
                    for name, text in [
                        ("dev-a", "Offer a useful alternative."),
                        ("dev-b", "Suggest another practical mechanism."),
                        ("validation-canary", "Reserved validation task."),
                        ("final-canary", "Reserved final task."),
                    ]
                )
            )
            prepare_search(
                destination,
                dataset_path=data,
                expected_dataset_sha256=hashlib.sha256(data.read_bytes()).hexdigest(),
                settings=settings,
                spec=SearchSpec(iterations=2, screen_size=2),
                splits={
                    "development": ["dev-a", "dev-b"],
                    "validation": ["validation-canary"],
                    "final": ["final-canary"],
                },
                synthetic=True,
            )
    manifest, settings, _, _ = load_search(destination)
    if not manifest["synthetic"] or any(s.provider != "replay" for s in settings.profiles()):
        raise ValidationError("search demo only resumes a synthetic replay run")
    report = run_search(destination, transport=_SearchReplay())
    print(json.dumps({"mode": "synthetic_replay", "paid_calls": 0, "report": report}))


def _review_command(args: argparse.Namespace) -> int:
    from buddha.source_review import SourceReviewError
    from buddha.source_review_handoff import collect_source_reviews, export_source_review

    stage = "export" if args.command == "source-review-export" else "collection"
    try:
        _notice("Checking saved evaluation and writing review files. Reading can take time.")
        common = {
            "kind": args.kind,
            "expected_report_sha256": args.report_sha256,
            "plan": args.plan,
            "expected_plan_sha256": args.plan_sha256,
            "output": args.out,
        }
        if stage == "export":
            result = export_source_review(
                args.run,
                **common,
                reviewers=[{"id": identifier, "type": kind} for identifier, kind in args.reviewer],
            )
        else:
            result = collect_source_reviews(
                args.run,
                **common,
                round_plan=args.round_plan,
                expected_round_plan_sha256=args.round_plan_sha256,
                submissions=[
                    {
                        "reviewer_id": identifier,
                        "path": str(Path(path).absolute()),
                        "sha256": digest,
                    }
                    for identifier, path, digest in args.submission
                ],
            )
        print(json.dumps(result))
        return 0 if result["status"] == "complete" else 3
    except (OSError, ValueError) as error:
        reason = str(error) if isinstance(error, SourceReviewError) else f"review {stage} refused"
        status, code = "refused", 2
    except KeyboardInterrupt:
        reason, status, code = f"review {stage} interrupted", "interrupted", 130
    _notice(f"Review {stage} stopped; original files and unfinished output are retained.")
    print(
        json.dumps(
            {
                "format": f"buddha.source-review-{stage}.v1",
                "status": "stopped",
                "stage": stage,
                "reason": status,
                "error": reason,
                "output": str(args.out),
            }
        )
    )
    return code


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    review_export = commands.add_parser(
        "source-review-export", help="write checked reviewer files and a private round offline"
    )
    review_inspect = commands.add_parser(
        "source-review-inspect", help="save a private comparison of supplied review forms offline"
    )
    for command in (review_export, review_inspect):
        command.add_argument("--run", type=Path, required=True)
        command.add_argument("--kind", choices=("final", "improver", "transfer"), required=True)
        command.add_argument("--report-sha256", required=True)
        command.add_argument("--plan", type=Path, required=True)
        command.add_argument("--plan-sha256", required=True)
        command.add_argument("--out", type=Path, required=True)
    review_export.add_argument(
        "--reviewer", nargs=2, action="append", required=True, metavar=("ID", "TYPE")
    )
    review_inspect.add_argument("--round-plan", type=Path, required=True)
    review_inspect.add_argument("--round-plan-sha256", required=True)
    review_inspect.add_argument(
        "--submission", nargs=3, action="append", default=[], metavar=("ID", "PATH", "SHA256")
    )
    continuation_source = commands.add_parser(
        "continuation-source", help="verify original receipt slots and saved science offline"
    )
    continuation_prepare = commands.add_parser(
        "continuation-prepare", help="freeze and bind a linked continuation without model calls"
    )
    for command in (continuation_source, continuation_prepare):
        command.add_argument("--source", type=Path, required=True)
        command.add_argument("--manifest-sha256", required=True)
        command.add_argument("--ledger-sha256", required=True)
        command.add_argument("--archive", type=Path, required=True)
        command.add_argument("--archive-sha256", required=True)
    continuation_prepare.add_argument("--authorization", type=Path, required=True)
    continuation_prepare.add_argument("--out", type=Path, required=True)
    authorization_create = commands.add_parser(
        "authorization-create", help="create one explicit shared dollar/call authorization offline"
    )
    authorization_create.add_argument("--out", type=Path, required=True)
    authorization_create.add_argument("--budget-usd", required=True)
    authorization_create.add_argument("--max-calls", type=int, required=True)
    authorization_create.add_argument("--scope", required=True)
    authorization_import = commands.add_parser(
        "authorization-import",
        help="adopt sealed historical costs and liability without model calls",
    )
    authorization_import.add_argument("--authorization", type=Path, required=True)
    authorization_import.add_argument("--run", type=Path, required=True)
    authorization_import.add_argument("--manifest-sha256", required=True)
    authorization_import.add_argument("--ledger-sha256", required=True)
    authorization_bind = commands.add_parser(
        "authorization-bind", help="bind an empty prepared run to existing shared authorization"
    )
    authorization_bind.add_argument("--authorization", type=Path, required=True)
    authorization_bind.add_argument("--run", type=Path, required=True)
    authorization_inspect = commands.add_parser(
        "authorization-inspect", help="read shared accounting without keys, writes or model calls"
    )
    authorization_inspect.add_argument("--authorization", type=Path, required=True)
    authorization_deactivate = commands.add_parser(
        "authorization-deactivate", help="permanently deactivate a bound run without model calls"
    )
    authorization_deactivate.add_argument("--authorization", type=Path, required=True)
    authorization_deactivate.add_argument("--run-id", required=True)
    authorization_deactivate.add_argument("--reason", required=True)
    commands.add_parser(
        "check-upstream", help="verify this build still matches current upstream HEAD"
    )
    demo = commands.add_parser("demo", help="run or resume a credential-free synthetic example")
    demo.add_argument("--out", type=Path, required=True)
    search_demo = commands.add_parser("search-demo", help="run or resume synthetic policy search")
    search_demo.add_argument("--out", type=Path, required=True)
    search_prepare = commands.add_parser(
        "search-prepare", help="freeze a bounded development search"
    )
    search_prepare.add_argument("--dataset", choices=DATASETS, required=True)
    search_prepare.add_argument("--data", type=Path, required=True)
    search_prepare.add_argument("--config", type=Path, required=True)
    search_prepare.add_argument("--budget-usd")
    search_prepare.add_argument("--screen-size", type=int, default=1)
    search_prepare.add_argument("--iterations", type=int, default=1)
    search_prepare.add_argument("--max-active", type=int, default=8)
    search_prepare.add_argument("--seed", type=int, default=7)
    search_prepare.add_argument(
        "--method", choices=["archive", "latest", "uninformed"], default="archive"
    )
    search_prepare.add_argument("--out", type=Path, required=True)
    search_run = commands.add_parser(
        "search-run", help="execute or resume one frozen policy search"
    )
    search_run.add_argument("--run", type=Path, required=True)
    search_run.add_argument("--live", action="store_true")
    search_run.add_argument("--prompt-keys", action="store_true")
    search_run.add_argument("--authorization", type=Path)
    search_inspect = commands.add_parser(
        "search-inspect", help="reconstruct search offline from receipts"
    )
    search_inspect.add_argument("--run", type=Path, required=True)
    search_verify = commands.add_parser(
        "search-verify",
        help="check explicitly sealed search evidence without writes or model calls",
    )
    search_verify.add_argument("--run", type=Path, required=True)
    search_verify.add_argument("--evidence", type=Path, required=True)
    doctor = commands.add_parser(
        "doctor", help="observe saved work and locks without writes or calls"
    )
    doctor.add_argument("--run", type=Path, required=True)
    doctor.add_argument("--authorization", type=Path)
    watch = commands.add_parser("watch", help="observe an existing run without keys or API calls")
    watch.add_argument("--run", type=Path, required=True)
    watch.add_argument("--authorization", type=Path)
    fetch = commands.add_parser(
        "fetch", help="fetch hash-verified pinned v1.1 prompts; no model calls"
    )
    fetch.add_argument("--dataset", choices=DATASETS, required=True)
    fetch.add_argument("--out", type=Path, required=True)
    prepare = commands.add_parser("prepare", help="freeze a development baseline without API calls")
    prepare.add_argument("--dataset", choices=DATASETS, required=True)
    prepare.add_argument("--data", type=Path, required=True)
    prepare.add_argument("--config", type=Path, required=True)
    prepare.add_argument("--budget-usd", help="explicit USD decimal override for the configuration")
    prepare.add_argument(
        "--limit", type=int, help="development pilot: first N source rows, recorded exactly"
    )
    prepare.add_argument("--out", type=Path, required=True)
    run = commands.add_parser("run", help="execute/resume the frozen baseline")
    run.add_argument("--run", type=Path, required=True)
    run.add_argument(
        "--live", action="store_true", help="allow model API spending under the frozen cap"
    )
    run.add_argument(
        "--prompt-keys", action="store_true", help="enter missing API keys without echo or files"
    )
    run.add_argument("--authorization", type=Path)
    for name in ["inspect", "verify"]:
        command = commands.add_parser(
            name, help="inspect the ledger or verify all exported artifacts offline"
        )
        command.add_argument("--run", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command in {"source-review-export", "source-review-inspect"}:
        return _review_command(args)
    try:
        authorization = None
        if args.command in {"run", "search-run"}:
            if args.live and args.authorization is None:
                raise ValidationError("--live requires an existing --authorization database")
            if args.authorization is not None:
                authorization = Authorization(args.authorization)
                bound_ledger = authorization.for_run(args.run)
                if args.live:
                    bound_ledger.authorize_dispatch()
        if args.command == "continuation-source":
            from buddha.continuation import read_source

            source = read_source(
                args.source,
                manifest_sha256=args.manifest_sha256,
                ledger_sha256=args.ledger_sha256,
                archived_runtime_zip=args.archive,
                archived_runtime_sha256=args.archive_sha256,
            )
            print(
                json.dumps(
                    {
                        "status": "verified_source",
                        "model_calls": 0,
                        "source_run_id": source.history.run_id,
                        "source_manifest_sha256": source.history.manifest_sha256,
                        "source_ledger_sha256": source.history.ledger_sha256,
                        "completed_receipts": len(source.completed),
                        "inherited_microusd": sum(
                            item.actual_microusd or 0 for item in source.completed
                        ),
                        "unknown_operation_id": source.unknown.operation_id,
                        "unknown_hold_microusd": source.unknown.reserve_microusd,
                        "claim": "source verified; no continuation prepared or spending allocated",
                    }
                )
            )
        elif args.command == "continuation-prepare":
            from buddha.continuation import prepare_continuation
            from buddha.search import load_search

            target = prepare_continuation(
                args.out,
                source=args.source,
                source_manifest_sha256=args.manifest_sha256,
                source_ledger_sha256=args.ledger_sha256,
                authorization=Authorization(args.authorization),
                archived_runtime_zip=args.archive,
                archived_runtime_sha256=args.archive_sha256,
            )
            manifest, settings, _, _ = load_search(target)
            print(
                json.dumps(
                    {
                        "status": "prepared",
                        "run": str(target),
                        "run_id": manifest["run_id"],
                        "model_calls": 0,
                        "inherited_replies": 9,
                        "budget_microusd": settings.budget_microusd,
                        "max_calls": settings.max_calls,
                    }
                )
            )
        elif args.command == "authorization-create":
            budget = _usd(args.budget_usd)
            if not args.scope.strip():
                raise ValidationError("authorization scope must be nonblank")
            created = Authorization.create(
                args.out,
                authorization_id=uuid.uuid4().hex,
                budget_microusd=budget,
                max_calls=args.max_calls,
                scope=args.scope,
            )
            print(json.dumps(created.summary()))
        elif args.command == "authorization-import":
            adopted = Authorization(args.authorization)
            adopted.import_history(
                args.run,
                manifest_sha256=args.manifest_sha256,
                ledger_sha256=args.ledger_sha256,
            )
            print(json.dumps(adopted.summary()))
        elif args.command == "authorization-bind":
            bound = Authorization(args.authorization)
            _plain(args.run.absolute())
            record = _object(_parse((args.run / "manifest.json").read_bytes()))
            if record.get("format") == "buddha.policy-search.v1":
                from buddha.search import load_search

                load_search(args.run)
            elif record.get("format") == "buddha.baseline.v1":
                manifest, settings, _, _ = load_run(args.run)
                path = args.run / "operations.sqlite3"
                try:
                    _plain(path.absolute())
                except FileNotFoundError:
                    Ledger(
                        path,
                        run_id=str(manifest["run_id"]),
                        manifest_sha256=hashlib.sha256(_canonical(manifest)).hexdigest(),
                        budget_microusd=settings.budget_microusd,
                        max_calls=settings.max_calls,
                    )
            else:
                raise ValidationError("unsupported run manifest")
            bound.bind_run(args.run, runtime_sha256=runtime_fingerprint())
            print(json.dumps(bound.summary()))
        elif args.command == "authorization-inspect":
            print(json.dumps(Authorization(args.authorization).summary()))
        elif args.command == "authorization-deactivate":
            deactivated = Authorization(args.authorization)
            deactivated.deactivate(args.run_id, args.reason)
            print(json.dumps(deactivated.summary()))
        elif args.command == "check-upstream":
            _check_upstream()
            print(json.dumps({"latest_matches": True, "upstream_commit": UPSTREAM_COMMIT}))
        elif args.command == "demo":
            _demo(args.out)
        elif args.command == "search-demo":
            _search_demo(args.out)
        elif args.command == "search-verify":
            from buddha.search_evidence import MAX_MANIFEST_BYTES, _absolute, _read
            from buddha.search_verify import verify_search

            declaration = _object(
                _parse(_read(_absolute(str(args.evidence.absolute())), MAX_MANIFEST_BYTES))
            )
            verification = verify_search(args.run, evidence=declaration)
            print(json.dumps(verification.to_record()))
            return 0 if verification.status == "verified" else 3
        elif args.command == "doctor":
            from buddha.doctor import observe

            observation = observe(args.run, authorization=args.authorization)
            print(json.dumps(observation))
            return (
                0 if observation["status"] == "observed" and not observation["needs_review"] else 3
            )
        elif args.command == "watch":
            from buddha.progress import watch_run

            prepared = False
            for name in ("manifest.json", "context.json"):
                path = args.run.absolute() / name
                try:
                    _plain(path)
                    prepared |= path.is_file()
                except FileNotFoundError:
                    continue
            if not prepared:
                raise ValidationError("watch requires an existing prepared run")
            watched = (
                watch_run(args.run)
                if args.authorization is None
                else watch_run(args.run, authorization=args.authorization)
            )
            print(json.dumps(watched))
            return 0 if watched.get("status") == "complete" else 2
        elif args.command == "search-prepare":
            from buddha.search import SearchSpec, prepare_search

            settings = _settings(args.config, args.budget_usd)
            spec = SearchSpec(
                iterations=args.iterations,
                max_active=args.max_active,
                seed=args.seed,
                method=args.method,
                screen_size=args.screen_size,
            )
            _check_upstream()
            prepare_search(
                args.out,
                dataset_path=args.data,
                expected_dataset_sha256=DATASETS[args.dataset][1],
                settings=settings,
                spec=spec,
            )
            print(
                json.dumps(
                    {
                        "status": "prepared",
                        "model_calls": 0,
                        "budget_microusd": settings.budget_microusd,
                    }
                )
            )
        elif args.command in {"search-run", "search-inspect"}:
            from buddha.progress import Progress
            from buddha.search import inspect_search, load_search, run_search

            if args.command == "search-inspect":
                print(json.dumps(inspect_search(args.run)))
            else:
                if args.prompt_keys and not args.live:
                    raise ValidationError("--prompt-keys requires --live")
                manifest, settings, _, _ = load_search(args.run)
                if manifest["format"] == "buddha.policy-search-continuation.v1":
                    if authorization is None:
                        raise ValidationError("linked execution requires --authorization")
                    _notice(
                        "Reusing 9 inherited replies. Progress counts new API operations; "
                        "the original unknown request remains held."
                    )
                if args.live:
                    settings.permit_live()
                transport = (
                    DiagnosticHTTPTransport(args.run, allow_paid=True)
                    if args.live
                    else _SearchReplay()
                )
                with _key_environment(settings, prompt_keys=args.prompt_keys):
                    _notice("Starting policy search. Provider calls can take time.")
                    with Progress(args.run):
                        report = run_search(
                            args.run,
                            transport=transport,
                            allow_paid=args.live,
                            authorization=authorization,
                        )
                print(
                    json.dumps(
                        {"mode": "live" if args.live else "synthetic_replay", "report": report}
                    )
                )
        elif args.command == "fetch":
            _fetch(args.dataset, args.out)
        elif args.command == "prepare":
            settings = _settings(args.config, args.budget_usd)
            _check_upstream()
            expected = DATASETS[args.dataset][1]
            prompts = load_prompts(args.data, expected_sha256=expected)
            if args.limit is not None and not 1 <= args.limit <= len(prompts):
                raise ValidationError("pilot limit must be within the dataset size")
            ids = [p.id for p in prompts[: args.limit]] if args.limit is not None else None
            prepare_run(
                args.out,
                dataset_path=args.data,
                expected_dataset_sha256=expected,
                settings=settings,
                prompt_ids=ids,
            )
            print(json.dumps({"status": "prepared", "model_calls": 0}))
        else:
            manifest, settings, prompts, protocol = load_run(args.run)
            if args.command == "run":
                from buddha.progress import Progress

                if args.prompt_keys and not args.live:
                    raise ValidationError("--prompt-keys requires --live")
                if args.live:
                    settings.permit_live()
                baseline_transport = (
                    DiagnosticHTTPTransport(args.run, allow_paid=True)
                    if args.live
                    else ReplayTransport()
                )
                with _key_environment(settings, prompt_keys=args.prompt_keys):
                    _notice("Starting baseline evaluation. Provider calls can take time.")
                    with Progress(args.run):
                        result = run_baseline(
                            args.run,
                            transport=baseline_transport,
                            allow_paid=args.live,
                            authorization=authorization,
                        )
                print(
                    json.dumps(
                        {
                            "mode": "live" if args.live else "synthetic_replay",
                            "summary": asdict(result),
                        }
                    )
                )
            elif args.command == "verify":
                result, _ = import_evaluation(
                    args.run / "evaluation",
                    protocol=protocol,
                    expected_prompt_hashes=prompt_manifest(prompts),
                )
                print(
                    json.dumps(
                        {
                            "verified": True,
                            "synthetic": manifest["synthetic"],
                            "summary": asdict(result),
                        }
                    )
                )
            else:
                info: dict[str, object] = {
                    "metric_version": protocol.metric_version,
                    "synthetic": manifest["synthetic"],
                    "prompt_count": len(prompts),
                    "budget_microusd": settings.budget_microusd,
                    "max_calls": settings.max_calls,
                    "reservation_per_call_microusd": {
                        role: spec.reserve_microusd()
                        for role, spec in zip(
                            ("generation", "partition", "quality"), settings.profiles(), strict=True
                        )
                    },
                }
                path = args.run / "operations.sqlite3"
                if path.exists():
                    ledger = Ledger(
                        path,
                        run_id=str(manifest["run_id"]),
                        manifest_sha256=hashlib.sha256(_canonical(manifest)).hexdigest(),
                        budget_microusd=settings.budget_microusd,
                        max_calls=settings.max_calls,
                    )
                    info["ledger"] = ledger.totals()
                print(json.dumps(info))
        return 0
    except ValidationError as error:
        _notice("Stopped. See the error JSON; no automatic retry was made.")
        directory = args.run if args.command in {"run", "search-run"} else None
        print(json.dumps(_error_record(str(error), directory)))
        return 2
    except (OSError, ValueError):
        _notice("Stopped. See the error JSON; no automatic retry was made.")
        print(json.dumps({"error": "filesystem or public-data network operation failed"}))
        return 2
    except KeyboardInterrupt:
        _notice("Interrupted. Any uncertain provider requests retain their reservations.")
        directory = args.run if args.command in {"run", "search-run"} else None
        print(
            json.dumps(
                _error_record(
                    "interrupted; keep the run directory for review before resuming", directory
                )
            )
        )
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
