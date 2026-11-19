#!/usr/bin/env python3
"""Test AI prompts against local or cloud Ollama.

Usage:
    python scripts/prompt_tester.py PRM-001
    python scripts/prompt_tester.py PRM-001 --dry-run
    python scripts/prompt_tester.py PRM-002 --context path/to/context.yaml
"""

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import yaml  # noqa: E402

from shared.config import load  # noqa: E402
from shared.ia_service import (  # noqa: E402
    analyze,
    load_prompt,
    render_prompt,
)

_CONTEXTS_PATH = _ROOT / "tests" / "fixtures" / "prompt_contexts.yaml"

PROMPT_PATH: dict[str, str] = {
    "PRM-001": "initial_evaluation/compatibility",
    "PRM-002": "processing/diagnostic",
    "PRM-003": "processing/strategic_extraction",
    "PRM-004": "processing/application_design",
    "PRM-005": "processing/inputs",
}

# La ruta `evaluation` se retiró con el rediseño del Módulo 3 (D76/D79): el
# prompt de compatibilidad sigue vigente como instrucción del chat, pero ya no
# se envía a un modelo desde el sistema. Para la prueba se usa la ruta cloud
# declarada, que es una configuración existente y reporta sus fallos.
PURPOSE: dict[str, str] = {
    "PRM-001": "processing",
    "PRM-002": "processing",
    "PRM-003": "processing",
    "PRM-004": "processing",
    "PRM-005": "processing",
}

VARS_BY_PROMPT: dict[str, list[str]] = {
    "PRM-001": ["oferta", "perfil"],
    "PRM-002": ["oferta"],
    "PRM-003": ["oferta", "perfil", "diagnostico"],
    "PRM-004": ["oferta", "perfil", "diagnostico", "analisis"],
    "PRM-005": ["oferta", "perfil", "diagnostico", "analisis", "puntuaciones"],
}

VARIABLE_MAPPING: dict[str, str] = {
    "oferta": "oferta_ejemplo",
    "perfil": "perfil_ejemplo",
    "diagnostico": "diagnostico_ejemplo",
    "analisis": "analisis_ejemplo",
    "puntuaciones": "puntuaciones_ejemplo",
}


def _load_context(path: Path) -> dict[str, object]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _build_context(
    raw_data: dict[str, object], prompt_id: str
) -> dict[str, str]:
    required_vars = VARS_BY_PROMPT.get(prompt_id, [])
    context: dict[str, str] = {}
    for prompt_var in required_vars:
        fixture_key = VARIABLE_MAPPING.get(prompt_var, prompt_var)
        value = raw_data.get(fixture_key)
        if value is None:
            print(
                f"  [WARNING] Variable '{prompt_var}' not found in context",
                file=sys.stderr,
            )
            context[prompt_var] = ""
        else:
            context[prompt_var] = json.dumps(value, ensure_ascii=False)
    return context


def _prompt_name(prompt_id: str) -> str:
    path = PROMPT_PATH.get(prompt_id)
    if path:
        return path
    return prompt_id


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test AI prompts with Ollama (local or cloud)"
    )
    parser.add_argument(
        "prompt_id",
        help="Prompt ID: PRM-001 .. PRM-005, or path like 'initial_evaluation/compatibility'",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show the rendered prompt without sending to model",
    )
    parser.add_argument(
        "--context",
        default=None,
        help="Alternative path to the YAML context file",
    )
    args = parser.parse_args()

    prompt_id = args.prompt_id.upper() if args.prompt_id.startswith("PRM") else args.prompt_id
    prompt_path = _prompt_name(prompt_id)
    purpose = PURPOSE.get(prompt_id, "processing")

    contexts_path = Path(args.context) if args.context else _CONTEXTS_PATH
    if not contexts_path.exists():
        print(f"Error: context file not found: {contexts_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Prompt:     {prompt_id} → {prompt_path}")
    print(f"Purpose:  {purpose}")
    print(f"Context:   {contexts_path}")

    raw_data = _load_context(contexts_path)
    context = _build_context(raw_data, prompt_id)
    print(f"Variables:  {', '.join(context.keys())}")

    try:
        template = load_prompt(prompt_path)
    except Exception as e:
        print(f"Error loading prompt: {e}", file=sys.stderr)
        sys.exit(1)

    rendered_prompt = render_prompt(template, context)

    print(f"\n{'='*70}")
    print("RENDERED PROMPT:")
    print(f"{'='*70}")
    print(rendered_prompt)
    print(f"{'='*70}")

    if args.dry_run:
        print("\nDry-run mode: not sent to model.")
        return

    routing = load().get("ai_routing", {})
    provider = routing.get(purpose, "local")
    print(f"\nSending to {provider}...")
    try:
        result = analyze(prompt_path, context, purpose=purpose)
        print(f"\n{'='*70}")
        print("MODEL RESPONSE:")
        print(f"{'='*70}")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print(f"{'='*70}")
    except Exception as e:
        print(f"\nModel error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
