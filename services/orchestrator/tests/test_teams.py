from __future__ import annotations

from titan_orchestrator.teams import load_team_template, template_to_roster


def test_ksp_default_team_template() -> None:
    template = load_team_template("ksp")
    roster = template_to_roster(template)
    assert any(agent["role"] == "director" for agent in roster)
    assert template.template_slug == "ksp.default"
