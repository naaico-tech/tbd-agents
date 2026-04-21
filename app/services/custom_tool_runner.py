"""Sandboxed execution engine for user-supplied Python tool functions.

Design decisions
----------------
* Tools run in a **subprocess** using the same Python interpreter so they
  share the project's virtualenv (unrestricted imports).
* Both ``sync`` and ``async`` functions are supported.  The wrapper script
  calls ``asyncio.run()`` for async functions detected with
  ``inspect.iscoroutinefunction``.
* A configurable timeout (default 30 s) cancels runaway tools.
* stdout carries the JSON-serialised return value; stderr carries errors.
* Non-JSON-serialisable return values are wrapped as ``{"result": str(value)}``.
* Schema inference uses ``inspect.signature`` to produce a JSON Schema from
  type annotations.  Unannotated parameters get ``{"type": "string"}`` as a
  safe default.
"""

import asyncio
import json
import logging
import sys
import textwrap
from typing import Any

logger = logging.getLogger(__name__)

# Seconds before a tool call is forcibly terminated
CUSTOM_TOOL_TIMEOUT_SECONDS = 30

# Python → JSON Schema type map
_PY_TYPE_TO_JSON: dict[str, str] = {
    "str": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "list": "array",
    "dict": "object",
    "None": "null",
}


def _py_annotation_to_json_type(annotation: Any) -> str:
    """Convert a Python type annotation to a JSON Schema type string."""
    if annotation is None:
        return "string"
    name = getattr(annotation, "__name__", str(annotation))
    return _PY_TYPE_TO_JSON.get(name, "string")


# ── Schema inference ──────────────────────────────────────────────────────────


async def infer_schema(source_code: str, func_name: str) -> dict:
    """Inspect *source_code* to produce a JSON Schema for *func_name*.

    This runs in a subprocess so that importing arbitrary user code cannot
    pollute the main process's state.
    """
    script = textwrap.dedent(f"""
        import inspect, json, sys, types

        _src = {json.dumps(source_code)}
        _name = {json.dumps(func_name)}

        _mod = types.ModuleType("_tool_mod")
        exec(compile(_src, "<custom_tool>", "exec"), _mod.__dict__)

        fn = getattr(_mod, _name, None)
        if fn is None:
            raise ValueError(f"Function '{{_name}}' not found in source")

        sig = inspect.signature(fn)
        props = {{}}
        required = []
        for pname, param in sig.parameters.items():
            ann = param.annotation
            ann_name = ann.__name__ if hasattr(ann, "__name__") else str(ann) if ann is not inspect.Parameter.empty else None
            type_map = {{"str": "string", "int": "integer", "float": "number",
                         "bool": "boolean", "list": "array", "dict": "object"}}
            json_type = type_map.get(ann_name, "string") if ann_name else "string"
            props[pname] = {{"type": json_type}}
            if param.default is inspect.Parameter.empty:
                required.append(pname)

        schema = {{"type": "object", "properties": props}}
        if required:
            schema["required"] = required

        print(json.dumps(schema))
    """)

    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=CUSTOM_TOOL_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        proc.kill()
        return {"type": "object", "properties": {}}

    if proc.returncode != 0:
        logger.warning("Schema inference failed: %s", stderr.decode()[:500])
        return {"type": "object", "properties": {}}

    try:
        return json.loads(stdout.decode())
    except json.JSONDecodeError:
        return {"type": "object", "properties": {}}


# ── Validation ────────────────────────────────────────────────────────────────


async def validate_tool(source_code: str, func_name: str) -> dict:
    """Validate *source_code* and return ``{valid, inferred_schema, error}``.

    Runs a subprocess that compiles and introspects the code without calling
    the function, so no side-effects occur.
    """
    script = textwrap.dedent(f"""
        import inspect, json, sys, types

        _src = {json.dumps(source_code)}
        _name = {json.dumps(func_name)}
        try:
            _mod = types.ModuleType("_tool_mod")
            exec(compile(_src, "<custom_tool>", "exec"), _mod.__dict__)
            fn = getattr(_mod, _name, None)
            if fn is None:
                raise ValueError(f"Function '{{_name}}' not found in source")
            if not callable(fn):
                raise TypeError(f"'{{_name}}' is not callable")

            sig = inspect.signature(fn)
            props = {{}}
            required = []
            for pname, param in sig.parameters.items():
                ann = param.annotation
                ann_name = ann.__name__ if hasattr(ann, "__name__") else str(ann) if ann is not inspect.Parameter.empty else None
                type_map = {{"str": "string", "int": "integer", "float": "number",
                             "bool": "boolean", "list": "array", "dict": "object"}}
                json_type = type_map.get(ann_name, "string") if ann_name else "string"
                props[pname] = {{"type": json_type}}
                if param.default is inspect.Parameter.empty:
                    required.append(pname)

            schema = {{"type": "object", "properties": props}}
            if required:
                schema["required"] = required

            print(json.dumps({{"valid": True, "inferred_schema": schema}}))
        except Exception as exc:
            print(json.dumps({{"valid": False, "error": str(exc)}}))
    """)

    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=CUSTOM_TOOL_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        proc.kill()
        return {"valid": False, "error": "Validation timed out"}

    raw = stdout.decode().strip()
    if not raw:
        err = stderr.decode()[:500] or "Unknown error during validation"
        return {"valid": False, "error": err}

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"valid": False, "error": "Unexpected validation output"}


# ── Execution ────────────────────────────────────────────────────────────────


async def run_tool(source_code: str, func_name: str, arguments: dict) -> str:
    """Execute *func_name* from *source_code* with *arguments*.

    Returns the JSON-encoded result string (ready to use as a tool message).
    Both sync and async functions are supported.
    """
    args_json = json.dumps(arguments)

    # The runner script is eval-safe: source_code + func_name are embedded
    # via json.dumps which escapes all special characters.
    script = textwrap.dedent(f"""
        import asyncio, inspect, json, sys, types

        _src = {json.dumps(source_code)}
        _name = {json.dumps(func_name)}
        _args = {args_json}

        _mod = types.ModuleType("_tool_mod")
        exec(compile(_src, "<custom_tool>", "exec"), _mod.__dict__)

        fn = getattr(_mod, _name, None)
        if fn is None:
            raise ValueError(f"Function '{{_name}}' not found")

        if inspect.iscoroutinefunction(fn):
            result = asyncio.run(fn(**_args))
        else:
            result = fn(**_args)

        if isinstance(result, (dict, list)):
            print(json.dumps(result))
        else:
            print(json.dumps({{"result": str(result) if result is not None else ""}}))
    """)

    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=CUSTOM_TOOL_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        proc.kill()
        logger.warning("Custom tool '%s' timed out after %ds", func_name, CUSTOM_TOOL_TIMEOUT_SECONDS)
        return json.dumps({"error": f"Tool '{func_name}' timed out after {CUSTOM_TOOL_TIMEOUT_SECONDS}s"})

    if proc.returncode != 0:
        err = stderr.decode()[:500]
        logger.warning("Custom tool '%s' exited with code %d: %s", func_name, proc.returncode, err)
        return json.dumps({"error": err or f"Tool '{func_name}' failed with exit code {proc.returncode}"})

    raw = stdout.decode().strip()
    if not raw:
        return json.dumps({"result": ""})

    # Validate the output is JSON; fall back to wrapping plain text
    try:
        json.loads(raw)
        return raw
    except json.JSONDecodeError:
        return json.dumps({"result": raw})
