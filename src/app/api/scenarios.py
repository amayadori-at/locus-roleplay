from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any
from app.api_validation import (
    ApiBadRequest,
    is_allowed_scenario_source_path as _is_allowed_scenario_source_path,
    query_string as _query_string,
    require_string_payload as _require_string_payload,
    validate_deletable_scenario_source_path as _validate_deletable_scenario_source_path,
    validate_id as _validate_id,
    validate_new_scenario_source_path as _validate_new_scenario_source_path,
    validate_scenario_source_path as _validate_scenario_source_path,
)
from app.images import image_asset_path, image_asset_url
from app.ids import is_locus_id
from app.loaders import list_scenarios, list_startings, load_scenario, load_starting
from app.starts import StartError, delete_start
from app.vault import FrontmatterError, Vault, parse_markdown
from app.api.common import ApiResponse, _json_response


def _scenario_summaries(vault: Vault) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for scenario_id in list_scenarios(vault):
        document = vault.load_markdown(f"rp/scenarios/{scenario_id}/scenario.md")
        metadata = dict(document.frontmatter)
        summaries.append(
            {
                "id": scenario_id,
                "name": metadata.get("name", scenario_id),
                "metadata": metadata,
                "description": document.body.strip(),
            }
        )
    return summaries


def _create_scenario_response(vault: Vault, payload: dict[str, Any]) -> dict[str, Any]:
    scenario_id = _validate_id(_require_string_payload(payload, "scenario_id"), "scenario")
    name = _require_string_payload(payload, "name")
    description = payload.get("description", "")
    if not isinstance(description, str):
        raise ApiBadRequest("description must be a string")
    scenario_dir = vault.resolve(f"rp/scenarios/{scenario_id}")
    if scenario_dir.exists():
        raise ApiBadRequest("scenario already exists")

    files = _scenario_template_files(scenario_id, name, description)
    directories = [
        "state",
        "gm",
        "characters",
        "lore",
        "memory/session_summaries",
        "memory/extracted_facts",
        "memory/unresolved_threads",
        "assets/images",
        "sessions",
        "startings",
    ]
    created_paths: list[str] = []
    try:
        scenario_dir.mkdir(parents=True)
        for directory in directories:
            (scenario_dir / directory).mkdir(parents=True, exist_ok=True)
        for relative_path, content in files.items():
            path = scenario_dir / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            created_paths.append(relative_path)
    except Exception:
        if scenario_dir.exists():
            import shutil

            shutil.rmtree(scenario_dir)
        raise

    scenario = load_scenario(vault, scenario_id)
    return {
        "scenario": {
            "id": scenario.id,
            "name": scenario.name,
            "metadata": scenario.metadata,
            "description": scenario.body.strip(),
        },
        "created": True,
        "created_files": created_paths,
    }


def _scenario_template_files(scenario_id: str, name: str, description: str) -> dict[str, str]:
    body = description.strip() or "このシナリオの説明をここに記述します。"
    return {
        "scenario.md": (
            "---\n"
            "type: scenario\n"
            f"id: {scenario_id}\n"
            f"name: {name}\n"
            "image_enabled: false\n"
            "image_mode: none\n"
            "memory_update_interval_turns: 4\n"
            "rag_scope:\n"
            "  - memory\n"
            "  - lore\n"
            "  - characters\n"
            "---\n\n"
            f"# {name}\n\n"
            f"{body}\n"
        ),
        "system_prompt.md": (
            "You are the GM for this roleplay scenario.\n"
            "Maintain consistency with the scenario, characters, lore, memory, and current state.\n"
            "Respond in Japanese unless the user explicitly asks otherwise.\n"
        ),
        "state/current.json": '{\n  "characters": {},\n  "flags": {}\n}\n',
        "startings/default.md": (
            "---\n"
            "type: starting\n"
            "id: default\n"
            "name: 通常開始\n"
            "---\n\n"
            "物語はここから始まります。\n"
        ),
    }


def _scenario_source_files(vault: Vault, scenario_id: str) -> list[dict[str, Any]]:
    load_scenario(vault, scenario_id)
    scenario_root = vault.resolve(f"rp/scenarios/{scenario_id}")
    files: list[dict[str, Any]] = []
    for path in sorted(scenario_root.rglob("*.md")):
        relative = path.relative_to(scenario_root).as_posix()
        if not _is_allowed_scenario_source_path(relative):
            continue
        files.append({"path": relative, "size": path.stat().st_size})
    return files


def _scenario_source_file(vault: Vault, scenario_id: str, source_path: str) -> dict[str, Any]:
    load_scenario(vault, scenario_id)
    safe_path = _validate_scenario_source_path(source_path)
    content = vault.read_text(f"rp/scenarios/{scenario_id}/{safe_path}")
    return {"scenario_id": scenario_id, "path": safe_path, "content": content}


def _scenario_startings_response(vault: Vault, scenario_id: str) -> dict[str, Any]:
    load_scenario(vault, scenario_id)
    startings = []
    for starting_id in list_startings(vault, scenario_id):
        starting = load_starting(vault, scenario_id, starting_id)
        startings.append(
            {
                "id": starting.id,
                "name": starting.name,
                "metadata": starting.metadata,
                "content": starting.body,
            }
        )
    return {"scenario_id": scenario_id, "startings": startings}


_BUSTUP_EXTENSION_ORDER: tuple[str, ...] = (".png", ".webp", ".jpg", ".jpeg", ".gif")


def _resolve_bustup_asset(vault: Vault, scenario_id: str, image_dir: str) -> tuple[str, bool]:
    """Resolve the bustup image for image_dir, trying allowed extensions in order.

    Returns (extension_with_dot, exists). When no file exists, returns (".png", False)
    so the path/URL keep the historical .png shape for backward compatibility.
    """
    for extension in _BUSTUP_EXTENSION_ORDER:
        if image_asset_path(vault, scenario_id, image_dir, "bustup", extension).is_file():
            return extension, True
    return ".png", False


def _scenario_character_bustups_response(vault: Vault, scenario_id: str) -> dict[str, Any]:
    load_scenario(vault, scenario_id)
    characters_path = vault.resolve(f"rp/scenarios/{scenario_id}/assets/characters.json")
    if not characters_path.is_file():
        return {"scenario_id": scenario_id, "characters": []}

    payload = vault.load_json(f"rp/scenarios/{scenario_id}/assets/characters.json")
    if not isinstance(payload, dict):
        raise ApiBadRequest("assets/characters.json root must be an object")

    characters: list[dict[str, Any]] = []
    for character_id, config in _character_asset_entries(payload):
        if not isinstance(character_id, str) or not is_locus_id(character_id) or not isinstance(config, dict):
            continue
        image_dir = config.get("image_dir") or _image_dir_from_base_path(config.get("image_base_path")) or character_id
        if not isinstance(image_dir, str) or not is_locus_id(image_dir):
            continue

        name = config.get("name", character_id)
        short_name = config.get("short_name", config.get("shortName", name))
        aliases = _character_aliases(character_id, config, name, short_name)
        bustup_ext, bustup_exists = _resolve_bustup_asset(vault, scenario_id, image_dir)
        characters.append(
            {
                "id": character_id,
                "name": name if isinstance(name, str) else character_id,
                "short_name": short_name if isinstance(short_name, str) else character_id,
                "aliases": aliases,
                "image_dir": image_dir,
                "bustup_path": f"{image_dir}/bustup{bustup_ext}",
                "bustup_url": image_asset_url(scenario_id, image_dir, "bustup", bustup_ext),
                "bustup_exists": bustup_exists,
            }
        )
    return {"scenario_id": scenario_id, "characters": characters}


def _character_asset_entries(payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    raw_characters = payload.get("characters")
    if isinstance(raw_characters, list):
        entries: list[tuple[str, dict[str, Any]]] = []
        for item in raw_characters:
            if not isinstance(item, dict):
                continue
            character_id = item.get("id")
            if isinstance(character_id, str):
                entries.append((character_id, item))
        return sorted(entries, key=lambda entry: entry[0])

    entries = [(character_id, config) for character_id, config in payload.items() if isinstance(config, dict)]
    return sorted(entries, key=lambda entry: entry[0])


def _image_dir_from_base_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = PurePosixPath(value.strip())
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        return None
    if len(path.parts) >= 3 and path.parts[-3:-1] == ("assets", "images"):
        return path.parts[-1]
    if len(path.parts) >= 2 and path.parts[-2] == "images":
        return path.parts[-1]
    return path.name or None


def _character_aliases(character_id: str, config: dict[str, Any], name: Any, short_name: Any) -> list[str]:
    aliases = [character_id]
    for value in (name, short_name):
        if isinstance(value, str) and value.strip():
            aliases.append(value.strip())
    raw_aliases = config.get("aliases", [])
    if isinstance(raw_aliases, list):
        aliases.extend(value.strip() for value in raw_aliases if isinstance(value, str) and value.strip())

    unique: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        if alias not in seen:
            seen.add(alias)
            unique.append(alias)
    return unique


def _update_scenario_source_file(vault: Vault, scenario_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    load_scenario(vault, scenario_id)
    safe_path = _validate_scenario_source_path(payload.get("path"))
    content = payload.get("content")
    if not isinstance(content, str):
        raise ApiBadRequest("source content must be a string")
    _validate_scenario_source_content(safe_path, content)
    path = vault.resolve(f"rp/scenarios/{scenario_id}/{safe_path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    try:
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return {"scenario_id": scenario_id, "path": safe_path, "content": content, "saved": True}


def _create_scenario_source_file(vault: Vault, scenario_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    load_scenario(vault, scenario_id)
    safe_path = _validate_new_scenario_source_path(payload.get("path"))
    content = payload.get("content")
    if not isinstance(content, str):
        raise ApiBadRequest("source content must be a string")
    _validate_scenario_source_content(safe_path, content)
    path = vault.resolve(f"rp/scenarios/{scenario_id}/{safe_path}")
    if path.exists():
        raise ApiBadRequest("source file already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    try:
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return {"scenario_id": scenario_id, "path": safe_path, "content": content, "created": True}


def _validate_scenario_source_content(safe_path: str, content: str) -> None:
    parts = PurePosixPath(safe_path).parts
    if len(parts) != 2 or parts[0] != "lore":
        return
    try:
        document = parse_markdown(content)
    except FrontmatterError as exc:
        raise ApiBadRequest(f"Invalid lore frontmatter: {exc}") from exc
    keywords = document.frontmatter.get("keywords")
    if keywords is None:
        return
    if not isinstance(keywords, list):
        raise ApiBadRequest("lore keywords must be a list")
    for keyword in keywords:
        if not isinstance(keyword, str):
            raise ApiBadRequest("lore keywords must contain strings only")
        if not keyword.strip():
            raise ApiBadRequest("lore keywords must not contain empty strings")


def _delete_scenario_source_file(vault: Vault, scenario_id: str, query: dict[str, list[str]]) -> dict[str, Any]:
    load_scenario(vault, scenario_id)
    safe_path = _validate_deletable_scenario_source_path(_query_string(query, "path"))
    parts = safe_path.split("/")
    if parts[0] == "startings" and len(parts) == 2:
        starting_id = parts[1].removesuffix(".md")
        try:
            delete_start(vault, scenario_id, starting_id)
        except StartError as exc:
            raise ApiBadRequest(str(exc)) from exc
    else:
        path = vault.resolve(f"rp/scenarios/{scenario_id}/{safe_path}")
        if not path.is_file():
            raise ApiBadRequest("source file does not exist")
        path.unlink()
    return {"scenario_id": scenario_id, "path": safe_path, "deleted": True}


def _scenario_state_template(vault: Vault, scenario_id: str) -> dict[str, Any]:
    load_scenario(vault, scenario_id)
    html_path = vault.resolve(f"rp/scenarios/{scenario_id}/state/view.html")
    css_path = vault.resolve(f"rp/scenarios/{scenario_id}/state/view.css")
    has_html = html_path.is_file()
    has_css = css_path.is_file()
    if not has_html and not has_css:
        return {"scenario_id": scenario_id, "has_template": False, "html": None, "css": None, "warnings": []}

    html = html_path.read_text(encoding="utf-8") if has_html else ""
    css = css_path.read_text(encoding="utf-8") if has_css else ""
    warnings: list[str] = []
    css_errors = _state_template_css_errors(css)
    if css_errors:
        css = ""
        warnings.extend(css_errors)
    return {"scenario_id": scenario_id, "has_template": True, "html": html, "css": css, "warnings": warnings}


def _state_template_css_errors(css: str) -> list[str]:
    if not css:
        return []
    checks = [
        (r"@import\b", "State template CSS must not use @import"),
        (r"\burl\s*\(", "State template CSS must not use url()"),
        (r"position\s*:\s*fixed\b", "State template CSS must not use position: fixed"),
        (r"position\s*:\s*absolute\b", "State template CSS must not use position: absolute"),
    ]
    return [message for pattern, message in checks if re.search(pattern, css, flags=re.IGNORECASE)]


# ---------------------------------------------------------------------------
# ZIP export / import
# ---------------------------------------------------------------------------

def _scenario_export_response(vault: Vault, scenario_id: str) -> ApiResponse:
    from app.scenario_zip import export_scenario_zip
    from app.vault import VaultPathError
    try:
        zip_bytes = export_scenario_zip(vault, scenario_id)
    except VaultPathError as exc:
        return _json_response({"error": "not_found", "message": str(exc)}, status=404)
    return ApiResponse(
        status=200,
        content_type="application/zip",
        body=zip_bytes,
        headers=(("Content-Disposition", f'attachment; filename="{scenario_id}.zip"'),),
    )


def _scenario_import_response(
    vault: Vault,
    zip_bytes: bytes,
    query: dict[str, list[str]],
) -> ApiResponse:
    from app.scenario_zip import ScenarioAlreadyExistsError, ScenarioZipError, import_scenario_zip
    scenario_id = query.get("scenario_id", [""])[0].strip()
    if not scenario_id:
        raise ApiBadRequest("scenario_id query parameter is required")
    try:
        result = import_scenario_zip(vault, zip_bytes, scenario_id)
    except ScenarioAlreadyExistsError as exc:
        return _json_response({"error": "ScenarioAlreadyExistsError", "message": str(exc)}, status=409)
    except ScenarioZipError as exc:
        return _json_response({"error": "ScenarioZipError", "message": str(exc)}, status=400)
    return _json_response(result, status=201)
