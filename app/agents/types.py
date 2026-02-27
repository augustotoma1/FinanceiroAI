"""
Core types for AI Employee orchestration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AgentAction:
    """One audited action performed by an AI employee role."""

    agent: str
    action: str
    status: str = "ok"
    details: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OrchestrationResult:
    """Structured output for one orchestration run."""

    success: bool
    mode: str
    dry_run: bool
    started_at: str
    finished_at: str
    actions: List[AgentAction] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["actions"] = [action.to_dict() for action in self.actions]
        return payload
