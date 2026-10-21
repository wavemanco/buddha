"""One local hidden-key session for the separately approved MEAS-02 $15/120 study.

Handoff v1 fields: format, study/descriptor/review absolute paths, account_scope,
authorization {path,id,terms_sha256,budget_microusd,max_calls,scope}, source_sha256
{absolute path: digest}. The external handoff pins this script; no self-pin cycle.
No grant is created here. A key fingerprint is the only credential evidence saved.
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from buddha.__main__ import KeyInputError  # noqa: E402
from buddha.authorization import Authorization  # noqa: E402
from buddha.baseline import _read, _write  # noqa: E402
from buddha.gateway import RawHTTPTransport, _core_sources, _profiles, _spec  # noqa: E402
from buddha.provider import ModelSpec  # noqa: E402
from buddha.releases import _digest, _json, _load, _object, _root, _text  # noqa: E402

SCRIPT = Path(__file__).resolve()
OPERATOR = SCRIPT.with_name("meas02-run.py")
OPERATOR_SHA256 = "ff48850a2281bb4ded265654443730c2d43185fb0fbe45236710ee94e6eb7fb8"
FAILURES = {
    "key_terminal_required": (
        "Hidden key entry needs an interactive terminal.",
        "Use the documented command in an interactive Windows Terminal/PowerShell window "
        "with input and error output attached; do not redirect those streams.",
    ),
    "key_input_unavailable": (
        "Hidden key entry was unavailable or ended before a key was received.",
        "Use hidden entry in an interactive terminal; Ctrl+C stops it. "
        "Keep the original study and owners.",
    ),
    "key_input_invalid": (
        "The entered credential did not pass the local input check.",
        "Paste the approved key locally without surrounding spaces, then press Enter. "
        "Never paste a key into chat.",
    ),
    "key_credentials_rejected": (
        "The local credential does not match this study's approved credential requirements.",
        "Check the local key against the approved account. An existing study requires "
        "its original key; do not replace its owners or account review.",
    ),
    "live_confirmation_required": (
        "The live-run confirmations are missing.",
        "Use the documented command with --live and --confirm-project-key.",
    ),
    "invalid_options": (
        "The launch options are missing or invalid.",
        "Use the documented command and its required options.",
    ),
    "handoff_stopped": (
        "Handoff checks or execution stopped; original evidence retained.",
        "Keep the original study and saved evidence for review; "
        "this message does not authorize another run or replacement owners.",
    ),
}


class LiveHandoffError(ValueError):
    """The approved handoff cannot safely prepare or reuse its original owners."""

    def __init__(self, message, *, code="handoff_stopped"):
        self.code = code
        super().__init__(message)


def _path(value):
    path = Path(_text(value))
    if not path.is_absolute() or ".." in path.parts or path != path.resolve():
        raise LiveHandoffError("handoff requires canonical absolute local paths")
    _root(path.parent)
    return path


def _operator():
    raw = _read(OPERATOR, OPERATOR_SHA256)
    module = ModuleType("_meas02_live_operator")
    module.__file__ = str(OPERATOR)
    # Only reviewed, hash-bound first-party source is compiled; never cached pyc.
    exec(  # nosec B102
        compile(raw, str(OPERATOR), "exec"), module.__dict__
    )
    return module


def _configuration(handoff):
    record = _object(
        _load(_read(_path(str(handoff)))),
        {
            "format",
            "study",
            "descriptor",
            "review",
            "account_scope",
            "authorization",
            "source_sha256",
        },
    )
    if record["format"] != "buddha.meas02-live-handoff.v1":
        raise LiveHandoffError("unsupported live handoff")
    sources = _object(record["source_sha256"])
    if not 1 <= len(sources) <= 512:
        raise LiveHandoffError("bounded approved source inventory required")
    total = 0
    for name, digest in sources.items():
        total += len(_read(_path(name), _digest(digest)))
        if total > 256 * 1024**2:
            raise LiveHandoffError("approved source inventory exceeds its ceiling")
    if any(str(path) not in sources for path in (SCRIPT, OPERATOR)):
        raise LiveHandoffError("the local launch sources must be externally sealed")
    operator = _operator()
    controller = operator._controller()
    descriptor = _path(record["descriptor"])
    definition, inputs, _, selection, roots = controller._definition(descriptor, sources)
    package = ROOT / "buddha"
    core = [
        package / ("__init__.py" if name == "buddha" else name.split(".")[-1] + ".py")
        for name in _core_sources()
    ]
    required = [SCRIPT, OPERATOR, descriptor, *inputs, *controller._sources(), *core]
    if any(str(path.absolute()) not in sources for path in required):
        raise LiveHandoffError("approved source inventory omits an executing component")
    native = definition["native"]
    if (
        type(native["budget_microusd"]) is not int
        or native["budget_microusd"] != 15_000_000
        or type(native["max_calls"]) is not int
        or native["max_calls"] != 120
    ):
        raise LiveHandoffError("native scope differs from the approved $15/120 Luna study")
    names = _object(_object(native["profiles"], {"openai"})["openai"], {"gpt-5.6-luna"})
    name = _text(names["gpt-5.6-luna"])
    profile = _profiles(selection, roots)["openai.chat-completions.v1"]["profiles"][name]
    spec = _spec(profile["spec"])
    if spec != ModelSpec(
        "openai",
        "gpt-5.6-luna",
        1_050_000,
        128_000,
        500_000,
        1_800_000,
        "https://developers.openai.com/api/docs/pricing",
    ) or (
        profile.get("account_headers") != {}
        or profile["allow_omitted_tier"] is not True
        or profile["response_models"] != ["gpt-5.6-luna"]
        or profile["request_tiers"] != ["auto", "default"]
        or profile["response_tiers"] != ["", "default"]
    ):
        raise LiveHandoffError("profile differs from the approved Standard public-PAYG bounds")
    study, review = _path(record["study"]), _path(record["review"])
    authorization = _object(
        record["authorization"],
        {"path", "id", "terms_sha256", "budget_microusd", "max_calls", "scope"},
    )
    authority = Authorization(_path(authorization["path"]))
    observed = authority.summary()
    expected = {
        "authorization_id": _text(authorization["id"]),
        "terms_sha256": _digest(authorization["terms_sha256"]),
        "budget_microusd": 15_000_000,
        "max_calls": 120,
        "scope": _text(authorization["scope"]),
    }
    if (
        type(authorization["budget_microusd"]) is not int
        or authorization["budget_microusd"] != 15_000_000
        or type(authorization["max_calls"]) is not int
        or authorization["max_calls"] != 120
        or any(observed[key] != value for key, value in expected.items())
    ):
        raise LiveHandoffError("existing authority differs from the approved immutable terms")
    _text(record["account_scope"])
    if (
        review.is_relative_to(study)
        or authority.path.is_relative_to(study)
        or any(
            path.is_relative_to(root)
            for root in roots.values()
            for path in (study, review, authority.path)
        )
    ):
        raise LiveHandoffError(
            "review, authority and study must be outside selected component roots"
        )
    if study.exists():
        try:
            checked = controller.check_native_audit(study)
        except controller.NativeAuditError:
            # Only a separately validated original state may reach the operator's
            # durable, keyless refusal recorder. Corrupt bindings still fail here.
            with controller._exclusive(study):
                original = controller._state(study, RawHTTPTransport(allow_paid=False))["records"][
                    0
                ]
            checked = {
                "status": "stopped",
                "authorization_path": original["authorization_path"],
                "review": original["review"],
                "source_files": original["invocation"]["inputs"],
            }
        if checked["authorization_path"] != str(authority.path):
            raise LiveHandoffError("prepared study uses a different original authority")
        saved = _object(_load(_read(review)))
        if saved != checked["review"] or saved["account_scope"] != record["account_scope"]:
            raise LiveHandoffError("original account review differs; nothing is replaced")
        bindings = {item["path"]: item["sha256"] for item in checked["source_files"]}
        if any(
            bindings.get(str(path.absolute())) != sources[str(path.absolute())]
            for path in (SCRIPT, OPERATOR, descriptor, *inputs, *controller._sources())
        ):
            raise LiveHandoffError("handoff sources differ from the original owner bindings")
    else:
        if review.exists() or observed["runs"] or observed["operation_count"]:
            raise LiveHandoffError("partial preparation or prior authority use requires review")
        checked = None
    return record, operator, controller, authority, spec, checked


def launch(handoff, *, live=False, prompt_keys=False, confirm_project_key=False):
    try:
        if (
            not isinstance(handoff, Path)
            or live is not True
            or confirm_project_key is not True
            or type(prompt_keys) is not bool
        ):
            raise LiveHandoffError(
                "--live and --confirm-project-key are required before key entry",
                code="live_confirmation_required",
            )
        record, operator, controller, authority, spec, checked = _configuration(handoff)
        study = _path(record["study"])
        if checked is not None and checked["status"] == "complete":
            return operator.execute(study, live=False, prompt_keys=False)
        if checked is not None and checked["status"] == "stopped":
            return operator.execute(study, live=True, prompt_keys=False)
        from buddha.__main__ import _key_environment, _notice

        profiles = operator._Profiles([spec])
        with _key_environment(profiles, prompt_keys=prompt_keys):
            key = os.environ.get("OPENAI_API_KEY", "")
            fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()
            expected = {"openai": fingerprint} if checked is None else checked["credential_sha256"]
            try:
                operator._credentials(profiles, expected)
            except operator.OperatorError:
                raise LiveHandoffError(
                    "local credential validation stopped", code="key_credentials_rejected"
                ) from None
            # Repeat source/terms/state checks after the operator's key-entry delay.
            current = _configuration(handoff)
            if current[0] != record or (current[-1] is None) != (checked is None):
                raise LiveHandoffError("handoff state changed while entering the key")
            if checked is None:
                _notice("Preparing four original study owners; no provider calls yet.")
                review = {
                    "checked_on": datetime.now(UTC).date().isoformat(),
                    "credential_sha256": {"openai": fingerprint},
                    "account_scope": record["account_scope"],
                }
                raw = _json(review)
                if key.encode("utf-8") in raw:
                    raise LiveHandoffError(
                        "account metadata contains the credential; nothing saved"
                    )
                _write(_path(record["review"]), raw)
                controller.prepare_native_audit(
                    study,
                    descriptor=_path(record["descriptor"]),
                    authorization=authority,
                    review=review,
                )
            return operator.execute(study, live=True, prompt_keys=False)
    except KeyInputError as error:
        code = error.code
        if type(code) is not str or code not in {
            "key_terminal_required",
            "key_input_unavailable",
            "key_input_invalid",
        }:
            code = "handoff_stopped"
        raise LiveHandoffError("local key input stopped", code=code) from None
    except LiveHandoffError:
        raise
    except Exception:
        raise LiveHandoffError(
            "live handoff checks or execution stopped; original evidence retained"
        ) from None


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise LiveHandoffError("invalid handoff options", code="invalid_options")


def main(argv=None):
    try:
        parser = _Parser(description=__doc__)
        parser.add_argument("--handoff", type=Path, required=True)
        parser.add_argument("--live", action="store_true")
        parser.add_argument("--prompt-keys", action="store_true")
        parser.add_argument("--confirm-project-key", action="store_true")
        args = parser.parse_args(argv)
        result = launch(
            args.handoff.absolute(),
            live=args.live,
            prompt_keys=args.prompt_keys,
            confirm_project_key=args.confirm_project_key,
        )
        record = _operator().public_result(result)
        code = 0 if record["status"] == "complete" else 3
    except KeyboardInterrupt:
        record, code = {"status": "cancelled"}, 130
        print(
            "[meas02] Cancelled; original evidence and any outstanding holds remain.",
            file=sys.stderr,
            flush=True,
        )
    except Exception as error:
        reason = error.code if isinstance(error, LiveHandoffError) else "handoff_stopped"
        if type(reason) is not str or reason not in FAILURES:
            reason = "handoff_stopped"
        message, action = FAILURES[reason]
        record, code = {"status": "stopped", "reason_code": reason, "action": action}, 2
        print(
            f"[meas02] {reason}: {message} {action}",
            file=sys.stderr,
            flush=True,
        )
    print(json.dumps({"format": "buddha.meas02-live-launch.v1", **record}), flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
