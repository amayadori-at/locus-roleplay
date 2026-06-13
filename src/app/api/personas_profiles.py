from __future__ import annotations

import json
from typing import Any
from app.api_validation import (
    ApiBadRequest,
    require_string_payload as _require_string_payload,
    validate_id as _validate_id,
)
from app.loaders import SECRET_PROFILE_FIELDS, LoaderError, list_personas, list_profiles, load_persona, load_profile
from app.vault import FrontmatterError, Vault, parse_markdown
from app.api.common import _atomic_write


PROFILE_EDITABLE_FIELDS: frozenset[str] = frozenset({
    "model", "temperature", "top_p", "top_k", "context_size", "max_tokens",
    "frequency_penalty", "presence_penalty", "repetition_penalty", "reasoning_effort",
})


# Fields stripped from profile API responses — never sent to the frontend.
HIDDEN_PROFILE_RESPONSE_FIELDS: frozenset[str] = frozenset({
    "api_key_env",
    "endpoint_env",
})


def _persona_summaries(vault: Vault) -> list[dict[str, str]]:
    return [{"id": persona_id, "name": load_persona(vault, persona_id).name} for persona_id in list_personas(vault)]


def _persona_detail(vault: Vault, persona_id: str) -> dict[str, Any]:
    persona = load_persona(vault, persona_id)
    content = vault.read_text(f"rp/personas/{persona_id}.md")
    return {"id": persona.id, "name": persona.name, "body": persona.body, "metadata": persona.metadata, "content": content}


def _update_persona(vault: Vault, persona_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    content = _require_string_payload(payload, "content")
    try:
        doc = parse_markdown(content)
    except FrontmatterError as exc:
        raise ApiBadRequest(f"Invalid persona frontmatter: {exc}") from exc
    metadata = doc.frontmatter
    if metadata.get("type") != "persona":
        raise ApiBadRequest("Persona content must have type: persona in frontmatter")
    if str(metadata.get("id", "")) != persona_id:
        raise ApiBadRequest(f"Persona id in frontmatter must match URL: {persona_id}")
    path = vault.resolve(f"rp/personas/{persona_id}.md")
    _atomic_write(path, content)
    return {"id": persona_id, "saved": True}


def _create_persona(vault: Vault, payload: dict[str, Any]) -> dict[str, Any]:
    persona_id = _validate_id(_require_string_payload(payload, "persona_id"), "persona")
    name = _require_string_payload(payload, "name")
    path = vault.resolve(f"rp/personas/{persona_id}.md")
    if path.exists():
        raise ApiBadRequest(f"Persona already exists: {persona_id}")
    content = f"---\ntype: persona\nid: {persona_id}\nname: {name}\n---\n\n# {name}\n\nペルソナの説明をここに記述します。\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, content)
    return {"id": persona_id, "name": name, "created": True}


def _profile_detail(vault: Vault, profile_id: str) -> dict[str, Any]:
    profile = load_profile(vault, profile_id)
    safe_data = {
        k: v for k, v in profile.data.items()
        if k not in HIDDEN_PROFILE_RESPONSE_FIELDS and k.lower() not in SECRET_PROFILE_FIELDS
    }
    return {"id": profile.id, "kind": profile.kind, "data": safe_data}


def _update_profile(vault: Vault, profile_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    extra = set(payload.keys()) - PROFILE_EDITABLE_FIELDS
    if extra:
        raise ApiBadRequest(
            f"Profile update only allows: {', '.join(sorted(PROFILE_EDITABLE_FIELDS))}. Got unexpected: {', '.join(sorted(extra))}"
        )
    lower_keys = {k.lower() for k in payload.keys()}
    suspicious = sorted(lower_keys & SECRET_PROFILE_FIELDS)
    if suspicious:
        raise ApiBadRequest(f"Profile must not contain secret fields: {', '.join(suspicious)}")
    if "model" in payload and not isinstance(payload["model"], str):
        raise ApiBadRequest("model must be a string")
    for num_field in ("temperature", "top_p", "top_k", "context_size", "max_tokens", "frequency_penalty", "presence_penalty", "repetition_penalty"):
        if num_field in payload and not isinstance(payload[num_field], (int, float)):
            raise ApiBadRequest(f"{num_field} must be a number")
    if "reasoning_effort" in payload and not isinstance(payload["reasoning_effort"], str):
        raise ApiBadRequest("reasoning_effort must be a string")
    raw = vault.load_json(f"rp/profiles/{profile_id}.json")
    if not isinstance(raw, dict):
        raise LoaderError(f"Profile is not a JSON object: {profile_id}")
    data = dict(raw)
    for field in PROFILE_EDITABLE_FIELDS:
        if field in payload:
            data[field] = payload[field]
    path = vault.resolve(f"rp/profiles/{profile_id}.json")
    _atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2))
    return {"id": profile_id, "saved": True}


def _profile_summaries(vault: Vault) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for profile_id in list_profiles(vault):
        profile = load_profile(vault, profile_id)
        data = profile.data
        summaries.append(
            {
                "id": profile.id,
                "kind": profile.kind,
                "model": data.get("model"),
                "context_size": data.get("context_size"),
                "temperature": data.get("temperature"),
                "top_p": data.get("top_p"),
                "max_tokens": data.get("max_tokens"),
            }
        )
    return summaries
