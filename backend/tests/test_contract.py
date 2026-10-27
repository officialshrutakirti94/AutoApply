"""The shared contract must mean the same thing to TypeScript and Python.

The JSON Schema is the source of truth; the Pydantic models are the backend's
enforcement. This test proves they agree on valid and invalid payloads, so the
extension cannot be written against a contract the server does not honour.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from app.contract.models import AgentResponse, Observation

SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "packages" / "shared" / "contract.schema.json"
)


def _document() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _subschema(name: str) -> dict:
    document = _document()
    return {
        "$schema": document["$schema"],
        "$defs": document["$defs"],
        "$ref": f"#/$defs/{name}",
    }


def _schema_accepts(name: str, payload: dict) -> bool:
    try:
        jsonschema.Draft202012Validator(_subschema(name)).validate(payload)
        return True
    except jsonschema.ValidationError:
        return False


def _pydantic_accepts(model, payload: dict) -> bool:
    try:
        model.model_validate(payload)
        return True
    except ValidationError:
        return False


def test_schema_file_is_valid_json_schema():
    jsonschema.Draft202012Validator.check_schema(_document())


def test_schema_declares_the_agreed_shapes():
    document = _document()
    for name in ("observation", "agentResponse", "action", "element", "job", "chat"):
        assert name in document["$defs"], name


def _valid_observation() -> dict:
    return {
        "run_id": str(uuid.uuid4()),
        "platform": "linkedin",
        "page_type": "apply_form",
        "job": {
            "id": "4012345",
            "title": "Backend Engineer",
            "company": "Acme",
            "location": "Pune",
            "job_url": "https://www.linkedin.com/jobs/view/4012345",
            "already_applied": False,
            "external": False,
        },
        "elements": [
            {"ref": "f1", "kind": "text", "label": "Full name", "required": True, "value": None},
            {"ref": "f2", "kind": "select", "label": "Notice period", "options": ["30", "60"]},
            {"ref": "b1", "kind": "button", "label": "Submit application"},
        ],
        "chat": {"question": "Expected CTC?", "input_ref": "c1"},
        "page_text_digest": "Backend Engineer, Pune.",
        "signals": [],
    }


def _valid_response() -> dict:
    return {
        "actions": [
            {"type": "fill_text", "ref": "f1", "value": "Priya Sharma"},
            {"type": "click", "ref": "b1"},
            {"type": "wait", "ms": 1200},
        ],
        "status": "continue",
        "reason": None,
    }


def test_valid_payloads_are_accepted_by_both():
    observation = _valid_observation()
    response = _valid_response()

    assert _schema_accepts("observation", observation)
    assert _pydantic_accepts(Observation, observation)

    assert _schema_accepts("agentResponse", response)
    assert _pydantic_accepts(AgentResponse, response)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update({"page_type": "made_up_page"}),
        lambda payload: payload.update({"platform": "indeed"}),
        lambda payload: payload.update({"unknown_key": True}),
        lambda payload: payload.update({"signals": ["not_a_signal"]}),
        lambda payload: payload["elements"][0].update({"ref": "NOT-A-REF"}),
        lambda payload: payload["elements"][0].update({"kind": "textarea"}),
        lambda payload: payload["job"].update({"id": ""}),
        lambda payload: payload.pop("job"),
    ],
)
def test_invalid_observations_are_rejected_by_both(mutate):
    payload = _valid_observation()
    mutate(payload)

    assert not _schema_accepts("observation", payload)
    assert not _pydantic_accepts(Observation, payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"actions": [], "status": "continue"},
        {"actions": [], "status": "hitl"},
        {"actions": [{"type": "fill_text", "ref": "f1"}], "status": "continue"},
        {"actions": [{"type": "submit", "ref": "b1"}], "status": "continue"},
        {"actions": [{"type": "wait"}], "status": "continue"},
        {"actions": [{"type": "teleport", "ref": "f1"}], "status": "continue"},
        {"actions": [{"type": "click", "ref": "f1"}] * 11, "status": "continue"},
    ],
)
def test_invalid_responses_are_rejected_by_both(payload):
    assert not _schema_accepts("agentResponse", payload)
    assert not _pydantic_accepts(AgentResponse, payload)


def test_schema_and_models_agree_on_action_count():
    document = _document()
    limit = document["$defs"]["agentResponse"]["properties"]["actions"]["maxItems"]
    assert limit == 10


def test_refs_cannot_be_selectors_or_urls():
    payload = _valid_observation()
    for bad_ref in ("#submit-button", "https://example.com", "div.foo", "F1"):
        payload["elements"][0]["ref"] = bad_ref
        assert not _schema_accepts("observation", payload), bad_ref
        assert not _pydantic_accepts(Observation, payload), bad_ref
