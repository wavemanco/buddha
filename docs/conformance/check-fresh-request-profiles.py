"""Check pinned profiles with synthetic requests only; no transport or paid authority."""

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).absolute().parents[2]
RUNS = ROOT.parents[1]
PROFILE = RUNS / "imp01-fresh-primary-20261102-v2/components/host/profiles.json"
PROFILE_SHA = "a582e97b86e3d651b1c7c6a6aa296adb370c8f7c33dde8f36edc2a9702878a31"
PLAIN = RUNS / "imp01-fresh-plain-20261102-v1"
PINS = {
    "regenerate": (
        "4c603dd6ddb133cc4241b3edb72e5bb4562b12a9fef1f790eabe4f558a83ca8c",
        "09b2f58a4ff6398c60c7d17abb015540912bea6bf1bdb26e1fcd761833ecad10",
    ),
    "in-context": (
        "793261f71ef752e2f01c0902b3f67eedb8b4a604b2515868481b5c6c4149074f",
        "6877f4803a4e3a429e88f40530a7d5ac77334bf62e9dcbfb0747cb126df30acd",
    ),
}
FIXTURE = ROOT / "tests/fixtures/native_judges.json"
FIXTURE_SHA = "d4ca7e838e9d769abb44e5215c81aca52bfda4a99a9c5a2fff4722fc46d0da99"
HELPER = RUNS / "reviews/fresh-primary-preparation/docs/conformance/prepare-fresh-primary.py"
HELPER_SHA = "a362fe4b5e2ed3d2eb44f7cfee09b04d0cc9726ac7b2c14fc542269f7770bbb2"


def external_guard(event, _args):
    if event.startswith(("socket.", "subprocess.", "sqlite3.connect")) or event in {
        "os.system",
        "os.exec",
        "os.spawn",
        "os.posix_spawn",
    }:
        raise RuntimeError("diagnostic_external_operation_denied")


def main():
    if not __debug__:
        raise RuntimeError("diagnostic_requires_assertions")
    sys.dont_write_bytecode = True
    sys.addaudithook(external_guard)
    assert hashlib.sha256(HELPER.read_bytes()).hexdigest() == HELPER_SHA
    spec = importlib.util.spec_from_file_location("pinned_preparation_helpers", HELPER)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)  # Pinned definitions only; never preparation/main.
    sys.path.insert(0, str(ROOT))
    from agents import frozen_seed
    from buddha import gateway, reference

    assert all(
        Path(module.__file__).absolute().parent.parent == ROOT
        for module in (frozen_seed, gateway, reference)
    )
    constructors = {
        str(Path(module.__file__).absolute()): helper.sha(Path(module.__file__).read_bytes())
        for module in (frozen_seed, gateway, reference)
    }
    pins = {PROFILE: PROFILE_SHA, FIXTURE: FIXTURE_SHA}
    for mode, values in PINS.items():
        pins.update(
            {
                PLAIN / mode / name: pin
                for name, pin in zip(("generation.json", "baseline.json"), values, strict=True)
            }
        )
    raw = {path: helper.read_pinned(path, pin) for path, pin in pins.items()}
    profiles = gateway._profile_file(json.loads(raw[PROFILE]))["profiles"]
    fixture = json.loads(raw[FIXTURE])
    accepted, denied = [], []

    def accept(route, body, capability, profile_id):
        gateway._request_spec(
            gateway.GatewayCall(
                capability, profile_id, "synthetic." + route, 0, helper.canonical(body)
            ),
            profiles[profile_id],
        )
        accepted.append(
            {
                "route": route,
                "model": body["model"],
                "body_sha256": helper.sha(helper.canonical(body)),
                "profile": profile_id,
            }
        )

    def reject(route, body, capability, profile_id, changes):
        for label, field, value in changes:
            changed = copy.deepcopy(body)
            if value is None:
                del changed[field]
            else:
                changed[field] = value
            try:
                gateway._request_spec(
                    gateway.GatewayCall(
                        capability, profile_id, "synthetic.mutant", 0, helper.canonical(changed)
                    ),
                    profiles[profile_id],
                )
            except gateway.GatewayError:
                denied.append(route + ":" + label)
            else:
                raise AssertionError("mutant_was_accepted:" + route + ":" + label)

    task = {"id": "synthetic-task", "prompt": "Write one useful original answer.", "count": 10}
    history = ["Synthetic prior answer A", "", "Synthetic prior answer C"]
    baselines = []
    for mode in PINS:
        recipe_path = PLAIN / mode / "generation.json"
        recipe, baseline = (
            json.loads(raw[PLAIN / mode / name]) for name in ("generation.json", "baseline.json")
        )
        assert (
            recipe["format"] == "buddha.frozen-generation.v1" and recipe["entrypoint"] == "seed.py"
        )
        assert baseline["format"] == "buddha.native-baseline.v1"
        assert (
            Path(baseline["generation"]["descriptor"]) == recipe_path
            and baseline["tasks"] == recipe["tasks"]
        )
        selected = recipe["profile"]
        assert selected == {"capability": "openai.chat-completions.v1", "profile_id": "seed"}
        for name in ("generation", "native"):
            section = baseline[name]
            assert Path(section["roots"]["host"]) == PROFILE.parent
            assert section["selection"]["components"]["host"] == {"profiles.json": PROFILE_SHA}
            assert section["selection"]["capabilities"][selected["capability"]] == "profiles.json"
        assert baseline["generation"]["selection"]["components"]["agent"] == {
            "seed.py": constructors[str(Path(frozen_seed.__file__).absolute())]
        }
        assert (
            constructors[str(Path(frozen_seed.__file__).absolute())]
            == "2b87bfe0d3c97ee45db2d45260985ffe0234eca93967f4689fb7c59f82603921"
        )
        baselines.append(baseline)
        config = recipe["config"]
        assert config == {
            "provider": "openai",
            "model": "gpt-5.6-luna",
            "max_output_tokens": 4096,
            "instructions": "",
            "sampling": mode,
        }
        first, later = (
            json.loads(frozen_seed.request(config, task, previous)) for previous in ([], history)
        )
        assert first["messages"] == [{"role": "user", "content": task["prompt"]}]
        assert later["reasoning_effort"] == "low" and later["max_completion_tokens"] == 4096
        assert (
            first == later
            if mode == "regenerate"
            else [row["content"] for row in later["messages"] if row["role"] == "assistant"]
            == history
        )
        if mode == "in-context":
            assert len(later["messages"]) == 7 and later["messages"][-1] == {
                "role": "user",
                "content": "Can you generate a different answer?",
            }
        for label, body in (("first", first), ("later", later)):
            accept(mode + "." + label, body, selected["capability"], "seed")
        reject(
            mode,
            later,
            selected["capability"],
            "seed",
            [
                ("effort", "reasoning_effort", "high"),
                ("cap", "max_completion_tokens", 2048),
                ("model", "model", "synthetic-other-model"),
                ("temperature", "temperature", 0.4),
                ("omit_effort", "reasoning_effort", None),
                ("omit_cap", "max_completion_tokens", None),
            ],
        )
    for kind, fallback, index, profile_id in (
        ("Partition", False, 0, "grouping"),
        ("Score", False, 1, "quality"),
        ("Score", True, 1, "fallback"),
    ):
        expected = copy.deepcopy(fixture["captured_bodies"][index]["body"])
        if fallback:
            expected["model"] = "claude-sonnet-5"
        body = reference.judge_body(kind, expected["messages"][-1]["content"], fallback=fallback)
        assert body == expected
        provider = "openai" if kind == "Partition" else "anthropic"
        capability = (
            "openai.chat-completions.v1" if provider == "openai" else "anthropic.messages.v1"
        )
        assert all(
            row["native"]["profiles"][provider][body["model"]] == profile_id
            and row["native"]["selection"]["capabilities"][capability] == "profiles.json"
            for row in baselines
        )
        accept(profile_id, body, capability, profile_id)
        changes = [("model", "model", "synthetic-other-model"), ("temperature", "temperature", 0.4)]
        if kind == "Partition":
            assert not {"reasoning_effort", "max_tokens", "max_completion_tokens"}.intersection(
                body
            )
            changes += [
                ("effort", "reasoning_effort", "low"),
                ("cap", "max_completion_tokens", 4096),
                ("omit_format", "response_format", None),
            ]
        else:
            assert body["max_tokens"] == 16000 and body["output_config"]["effort"] == "high"
            changes += [
                ("effort", "output_config", body["output_config"] | {"effort": "low"}),
                ("cap", "max_tokens", 15999),
                ("omit_thinking", "thinking", None),
            ]
        reject(profile_id, body, capability, profile_id, changes)
    proposal = profiles["proposal"]
    assert "reasoning_effort" not in proposal["request_settings"]["required"]
    assert all(helper.read_pinned(path, pin) == raw[path] for path, pin in pins.items())
    print(
        json.dumps(
            {
                "format": "buddha.fresh-request-profile-check.v1",
                "status": "pass",
                "input_sha256": {str(path): pin for path, pin in pins.items()},
                "constructor_source_sha256": constructors,
                "accepted_synthetic_requests": accepted,
                "rejected_mutants": denied,
                "proposal_profile": {
                    "model": proposal["spec"]["model"],
                    "max_output_tokens": proposal["spec"]["max_output_tokens"],
                    "reasoning_effort_required": None,
                    "authoring_request_emitted_or_checked": False,
                },
                "provider_calls": 0,
                "scope": (
                    "Pinned profile/synthetic-body compatibility only; no P/C execution, "
                    "installed SDK/fallback trigger/account/price/runtime/custody "
                    "or live-clearance claim."
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
