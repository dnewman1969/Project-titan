"""Team templates from game packages (M6.T6)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

REPO_ROOT = Path(__file__).resolve().parents[3]
GAMES_DIR = REPO_ROOT / "games"


class TeamAgentTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str
    persona_slug: str
    is_director: bool = False
    tick_interval_ms: int = Field(default=10_000, ge=2000)
    event_subscriptions: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)


class TeamTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    purpose: str
    template_slug: str | None = None
    agents: list[TeamAgentTemplate]


def load_team_template(game_slug: str, *, path: Path | None = None) -> TeamTemplate:
    yaml_path = path or (GAMES_DIR / game_slug / "teams" / "default.yaml")
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = f"{yaml_path}: expected mapping"
        raise TypeError(msg)
    return TeamTemplate.model_validate(data)


def template_to_roster(template: TeamTemplate) -> list[dict[str, Any]]:
    return [agent.model_dump() for agent in template.agents]
