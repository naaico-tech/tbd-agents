"""Guardrail enforcement engine.

Loads all active guardrails configured on a workflow (by explicit IDs and/or
by tag), then runs the appropriate checks before the agent task is dispatched.

Prompt guardrails  — validate the incoming prompt string.
Request guardrails — validate the structured ``request`` dict against a
                     JSON Schema definition.
Output guardrails  — validate the agent's response after execution (PII
                     detection, format enforcement, regex patterns).

Prompt and request guardrails raise ``fastapi.HTTPException(422)`` on the
first violation encountered, with a detail message that identifies the
failing guardrail and the reason.  Output guardrails return a list of
violation strings to the caller (the agent engine) which logs and publishes
them rather than raising.
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


# ── Common PII patterns ─────────────────────────────────────────────────────

_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "email address",
        re.compile(
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            re.IGNORECASE,
        ),
    ),
    (
        "phone number",
        re.compile(
            r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
        ),
    ),
    (
        "SSN",
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    ),
]


def _check_output(output: str, guardrail: Guardrail) -> str | None:
    """Validate *output* against an output guardrail's rules.

    Returns a violation message string on failure, or ``None`` if clean.
    """
    cfg = guardrail.output_config
    if cfg is None:
        return None

    if cfg.max_length is not None and len(output) > cfg.max_length:
        return (
            f"Guardrail '{guardrail.name}': output is too long "
            f"({len(output)} chars, maximum {cfg.max_length})."
        )

    for pattern in cfg.forbidden_patterns:
        if re.search(pattern, output, re.IGNORECASE):
            return (
                f"Guardrail '{guardrail.name}': output matches forbidden pattern '{pattern}'."
            )

    for pattern in cfg.required_patterns:
        if not re.search(pattern, output, re.IGNORECASE):
            return (
                f"Guardrail '{guardrail.name}': output does not match "
                f"required pattern '{pattern}'."
            )

    if cfg.must_be_valid_json:
        try:
            json.loads(output)
        except (json.JSONDecodeError, TypeError):
            return f"Guardrail '{guardrail.name}': output is not valid JSON."

    if cfg.pii_detection:
        for pii_label, pii_re in _PII_PATTERNS:
            if pii_re.search(output):
                return (
                    f"Guardrail '{guardrail.name}': output appears to contain "
                    f"PII ({pii_label})."
                )

    return None


async def enforce_output_guardrails(
    workflow: "Workflow",
    output: str,
) -> list[str]:
    """Run all active output guardrails for *workflow* against the agent response.

    Returns a list of violation messages (empty if all checks pass).
    """
    guardrails = await _load_guardrails(workflow)
    output_guardrails = [g for g in guardrails if g.guardrail_type == GuardrailType.OUTPUT]

    violations: list[str] = []
    for guardrail in output_guardrails:
        result = _check_output(output, guardrail)
        if result:
            violations.append(result)

    return violations


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
