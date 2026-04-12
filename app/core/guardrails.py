"""Guardrail enforcement engine.

Loads all active guardrails configured on a workflow (by explicit IDs and/or
by tag), then runs the appropriate checks before the agent task is dispatched.

Prompt guardrails  — validate the incoming prompt string.
Request guardrails — validate the structured ``request`` dict against a
                     JSON Schema definition.

Raises ``fastapi.HTTPException(422)`` on the first violation encountered,
with a detail message that identifies the failing guardrail and the reason.
"""

import json
import re

import jsonschema
from fastapi import HTTPException

from app.models.guardrail import Guardrail, GuardrailType
from app.models.workflow import Workflow


async def _load_guardrails(workflow: Workflow) -> list[Guardrail]:
    """Return the union of guardrails selected by ID and by tag, deduplicated."""
    found: dict[str, Guardrail] = {}

    if workflow.guardrail_ids:
        from beanie import PydanticObjectId

        for gid in workflow.guardrail_ids:
            g = await Guardrail.get(PydanticObjectId(gid))
            if g and g.enabled:
                found[str(g.id)] = g

    if workflow.guardrail_tags:
        tag_matches = await Guardrail.find(
            {"tags": {"$in": workflow.guardrail_tags}},
            Guardrail.enabled == True,  # noqa: E712
        ).to_list()
        for g in tag_matches:
            found[str(g.id)] = g

    return list(found.values())


def _check_prompt(prompt: str, guardrail: Guardrail) -> None:
    """Validate *prompt* against a prompt guardrail's rules."""
    cfg = guardrail.prompt_config
    if cfg is None:
        return

    if cfg.min_length is not None and len(prompt) < cfg.min_length:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Guardrail '{guardrail.name}': prompt is too short "
                f"({len(prompt)} chars, minimum {cfg.min_length})."
            ),
        )

    if cfg.max_length is not None and len(prompt) > cfg.max_length:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Guardrail '{guardrail.name}': prompt is too long "
                f"({len(prompt)} chars, maximum {cfg.max_length})."
            ),
        )

    for pattern in cfg.forbidden_patterns:
        if re.search(pattern, prompt, re.IGNORECASE):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Guardrail '{guardrail.name}': prompt matches forbidden pattern '{pattern}'."
                ),
            )

    for pattern in cfg.required_patterns:
        if not re.search(pattern, prompt, re.IGNORECASE):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Guardrail '{guardrail.name}': prompt does not match "
                    f"required pattern '{pattern}'."
                ),
            )


def _check_request(request_data: dict, guardrail: Guardrail) -> None:
    """Validate *request_data* against a request guardrail's JSON Schema."""
    cfg = guardrail.request_config
    if cfg is None:
        return

    try:
        jsonschema.validate(instance=request_data, schema=cfg.json_schema)
    except jsonschema.ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Guardrail '{guardrail.name}': request validation failed — {exc.message}.",
        ) from exc
    except jsonschema.SchemaError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Guardrail '{guardrail.name}': invalid JSON Schema — {exc.message}.",
        ) from exc


async def enforce_guardrails(
    workflow: Workflow,
    prompt: str | None,
    request_data: dict | None,
) -> str:
    """Run all active guardrails for *workflow* and return the effective prompt.

    Parameters
    ----------
    workflow:
        The workflow whose guardrails are to be enforced.
    prompt:
        The raw prompt string supplied by the caller.
    request_data:
        The structured request object supplied by the caller (may be ``None``).

    Returns
    -------
    str
        The effective prompt string to pass to the agent engine.
        * For prompt-only flows this is the verbatim *prompt*.
        * For request-mode flows this is the JSON-serialised *request_data*.
        * When both are present, the request JSON is used as the prompt.

    Raises
    ------
    HTTPException(422)
        On any guardrail violation.
    HTTPException(400)
        When a required input (prompt or request) is missing.
    """
    guardrails = await _load_guardrails(workflow)

    prompt_guardrails = [g for g in guardrails if g.guardrail_type == GuardrailType.PROMPT]
    request_guardrails = [g for g in guardrails if g.guardrail_type == GuardrailType.REQUEST]

    # ── Validate presence of required inputs ─────────────────────────────────
    if prompt_guardrails and not prompt:
        raise HTTPException(
            status_code=400,
            detail="This workflow requires a 'prompt' field (enforced by prompt guardrails).",
        )

    if request_guardrails and request_data is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "This workflow requires a 'request' field (enforced by request guardrails). "
                "Provide a structured request object instead of a plain prompt."
            ),
        )

    # ── Run prompt guardrail checks ───────────────────────────────────────────
    if prompt_guardrails and prompt:
        for guardrail in prompt_guardrails:
            _check_prompt(prompt, guardrail)

    # ── Run request guardrail checks ──────────────────────────────────────────
    if request_guardrails and request_data is not None:
        for guardrail in request_guardrails:
            _check_request(request_data, guardrail)

    # ── Determine effective prompt ────────────────────────────────────────────
    if request_data is not None:
        return json.dumps(request_data, ensure_ascii=False)

    if prompt:
        return prompt

    raise HTTPException(
        status_code=400,
        detail="Either 'prompt' or 'request' must be provided.",
    )
