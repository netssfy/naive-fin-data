from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trader_incubator.models import SkillSpec


@dataclass(frozen=True)
class SkillInvokeResult:
    raw_response: str
    skill_name: str
    input_payload: dict[str, Any]


class DeerFlowEmbeddedSkillRuntime:
    """
    Skill runtime built on deer-flow Embedded Python Client.

    This keeps AI-driven actors explicit:
    - 帅帅: creates traders via skill.md
    - 交易员: evolves strategy/program via skill.md
    """

    def __init__(self) -> None:
        self._client = self._create_client()

    @staticmethod
    def _create_client() -> Any:
        try:
            from deerflow.client import DeerFlowClient
        except Exception as exc:  # pragma: no cover - import depends on local install
            raise RuntimeError(
                "deerflow is required. Install deer-flow and configure environment first."
            ) from exc
        return DeerFlowClient()

    def invoke_skill(
        self,
        skill: SkillSpec,
        payload: dict[str, Any],
        *,
        thread_id: str | None = None,
    ) -> SkillInvokeResult:
        skill_prompt = _load_skill_prompt(skill.skill_md_path)
        request_prompt = (
            f"You are executing skill: {skill.name}\n"
            f"Skill file:\n{skill_prompt}\n\n"
            f"Task payload(JSON):\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
            "Return concise, machine-readable output."
        )
        response = self._client.chat(request_prompt, thread_id=thread_id)
        return SkillInvokeResult(
            raw_response=_extract_response_text(response),
            skill_name=skill.name,
            input_payload=payload,
        )


def _load_skill_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_response_text(response: Any) -> str:
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        for key in ("answer", "content", "text", "response"):
            value = response.get(key)
            if isinstance(value, str):
                return value
    return str(response)

