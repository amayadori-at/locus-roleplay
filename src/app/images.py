from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.loaders import Scenario
from app.vault import Vault, VaultError


MARKER_PATTERN = re.compile(r"\[\[image:\s*([^\]]+?)\s*\]\]")
IMAGE_PATH_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+\.png$")
MissingImageBehavior = Literal["fallback_normal", "hide", "show_warning"]


class ImageMarkerError(VaultError):
    """Raised when an image marker is unsafe or invalid."""


@dataclass(frozen=True)
class TextSegment:
    type: Literal["text"]
    content: str


@dataclass(frozen=True)
class ImageSegment:
    type: Literal["image"]
    path: str
    url: str
    character_id: str
    situation_id: str
    exists: bool = True
    warning: str | None = None


Segment = TextSegment | ImageSegment


def validate_image_marker_path(marker_path: str) -> tuple[str, str]:
    candidate = marker_path.strip()
    if not IMAGE_PATH_PATTERN.fullmatch(candidate):
        raise ImageMarkerError(f"Invalid image marker path: {marker_path}")
    character_id, filename = candidate.split("/", 1)
    situation_id = filename.removesuffix(".png")
    return character_id, situation_id


def parse_image_markers(
    text: str,
    *,
    scenario: Scenario,
    vault: Vault | None = None,
    missing_behavior: MissingImageBehavior | None = None,
) -> list[Segment]:
    if scenario.metadata.get("image_enabled") is not True:
        return [TextSegment(type="text", content=text)] if text else []

    behavior = _missing_behavior(scenario, missing_behavior)
    segments: list[Segment] = []
    cursor = 0
    for match in MARKER_PATTERN.finditer(text):
        if match.start() > cursor:
            segments.append(TextSegment(type="text", content=text[cursor : match.start()]))

        marker_path = match.group(1)
        character_id, situation_id = validate_image_marker_path(marker_path)
        image_segment = _resolve_image_segment(
            scenario=scenario,
            vault=vault,
            character_id=character_id,
            situation_id=situation_id,
            behavior=behavior,
        )
        if image_segment is not None:
            segments.append(image_segment)
        cursor = match.end()

    if cursor < len(text):
        segments.append(TextSegment(type="text", content=text[cursor:]))
    return [segment for segment in segments if not (segment.type == "text" and segment.content == "")]


def image_asset_path(vault: Vault, scenario_id: str, character_id: str, situation_id: str) -> Path:
    validate_image_marker_path(f"{character_id}/{situation_id}.png")
    return vault.resolve(f"rp/scenarios/{scenario_id}/assets/images/{character_id}/{situation_id}.png")


def image_asset_url(scenario_id: str, character_id: str, situation_id: str) -> str:
    validate_image_marker_path(f"{character_id}/{situation_id}.png")
    return f"/api/assets/images/{scenario_id}/{character_id}/{situation_id}.png"


def _resolve_image_segment(
    *,
    scenario: Scenario,
    vault: Vault | None,
    character_id: str,
    situation_id: str,
    behavior: MissingImageBehavior,
) -> ImageSegment | None:
    resolved_character_id = character_id
    resolved_situation_id = situation_id
    exists = True
    warning: str | None = None

    if vault is not None:
        requested = image_asset_path(vault, scenario.id, character_id, situation_id)
        if not requested.is_file():
            exists = False
            if behavior == "fallback_normal" and situation_id != "normal":
                fallback = image_asset_path(vault, scenario.id, character_id, "normal")
                if fallback.is_file():
                    resolved_situation_id = "normal"
                    exists = True
            if not exists and behavior == "hide":
                return None
            if not exists and behavior == "fallback_normal":
                return None
            if not exists and behavior == "show_warning":
                warning = f"Missing image asset: {character_id}/{situation_id}.png"

    return ImageSegment(
        type="image",
        path=f"{resolved_character_id}/{resolved_situation_id}.png",
        url=image_asset_url(scenario.id, resolved_character_id, resolved_situation_id),
        character_id=resolved_character_id,
        situation_id=resolved_situation_id,
        exists=exists,
        warning=warning,
    )


def _missing_behavior(scenario: Scenario, override: MissingImageBehavior | None) -> MissingImageBehavior:
    if override is not None:
        return override
    value = scenario.metadata.get("missing_image_behavior", "fallback_normal")
    if value in ("fallback_normal", "hide", "show_warning"):
        return value
    return "fallback_normal"
