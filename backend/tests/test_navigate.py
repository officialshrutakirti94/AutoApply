from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.agents.nodes.navigate import _matches_target_roles, open_apply
from tests.helpers import button, observation


def test_short_role_tokens_match_search_cards():
    assert _matches_target_roles("AI Engineer at Acme", ["AI"])
    assert _matches_target_roles("ML Researcher at Acme", ["ML Engineer"])


def test_search_results_open_a_card_when_no_card_label_matches_roles():
    state = {
        "observation": observation(
            run_id=str(uuid.uuid4()),
            page_type="search_results",
            elements=[
                button("b1", "Backend Developer Intern at ThinkNovaa"),
                button("b2", "ML Researcher at Acme"),
            ],
        ),
        "notes": [],
    }

    result = open_apply(state, SimpleNamespace(target_roles=["AI Engineer"]))

    assert result["status"] == "continue"
    assert result["actions"][0]["type"] == "click"
    assert result["actions"][0]["ref"] == "b1"
