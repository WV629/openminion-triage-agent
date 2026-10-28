from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TriagedItem(BaseModel):
    number: int
    kind: Literal["issue", "pr"]
    title: str
    suggested_labels: list[str] = Field(default_factory=list)
    priority: Literal["P0", "P1", "P2", "P3"]
    reason: str
    url: str


class TriageReport(BaseModel):
    repo: str = ""
    summary: str = ""
    items: list[TriagedItem]
    needs_maintainer_attention: list[int] = Field(default_factory=list)
