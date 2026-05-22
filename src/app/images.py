from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.loaders import Scenario
from app.vault import Vault, VaultError


MARKER_PATTERN = re.compile(r"\[\[image:\s*([^\]]+?)\s*\]\]")
_ALLOWED_IMG_EXTS = "png|jpg|jpeg|webp|gif"
IMAGE_PATH_PATTERN = re.compile(rf"^[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+\.(?:{_ALLOWED_IMG_EXTS})$")
ALLOWED_IMAGE_EXTENSIONS: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
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


def validate_image_marker_path(marker_path: str) -> tuple[str, str, str]:
    """Return (character_id, situation_id, extension) where extension includes the dot."""
    candidate = marker_path.strip()
    if not IMAGE_PATH_PATTERN.fullmatch(candidate):
        raise ImageMarkerError(f"Invalid image marker path: {marker_path}")
    character_id, filename = candidate.split("/", 1)
    dot_pos = filename.rfind(".")
    situation_id = filename[:dot_pos]
    extension = filename[dot_pos:]
    return character_id, situation_id, extension


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
        character_id, situation_id, extension = validate_image_marker_path(marker_path)
        image_segment = _resolve_image_segment(
            scenario=scenario,
            vault=vault,
            character_id=character_id,
            situation_id=situation_id,
            extension=extension,
            behavior=behavior,
        )
        if image_segment is not None:
            segments.append(image_segment)
        cursor = match.end()

    if cursor < len(text):
        segments.append(TextSegment(type="text", content=text[cursor:]))
    return [segment for segment in segments if not (segment.type == "text" and segment.content == "")]


def image_asset_path(
    vault: Vault,
    scenario_id: str,
    character_id: str,
    situation_id: str,
    extension: str = ".png",
) -> Path:
    validate_image_marker_path(f"{character_id}/{situation_id}{extension}")
    return vault.resolve(
        f"rp/scenarios/{scenario_id}/assets/images/{character_id}/{situation_id}{extension}"
    )


def image_asset_url(
    scenario_id: str,
    character_id: str,
    situation_id: str,
    extension: str = ".png",
) -> str:
    validate_image_marker_path(f"{character_id}/{situation_id}{extension}")
    return f"/api/assets/images/{scenario_id}/{character_id}/{situation_id}{extension}"


def _resolve_image_segment(
    *,
    scenario: Scenario,
    vault: Vault | None,
    character_id: str,
    situation_id: str,
    extension: str,
    behavior: MissingImageBehavior,
) -> ImageSegment | None:
    resolved_character_id = character_id
    resolved_situation_id = situation_id
    exists = True
    warning: str | None = None

    if vault is not None:
        requested = image_asset_path(vault, scenario.id, character_id, situation_id, extension)
        if not requested.is_file():
            exists = False
            if behavior == "fallback_normal" and situation_id != "normal":
                fallback = image_asset_path(vault, scenario.id, character_id, "normal", extension)
                if fallback.is_file():
                    resolved_situation_id = "normal"
                    exists = True
            if not exists and behavior == "hide":
                return None
            if not exists and behavior == "fallback_normal":
                return None
            if not exists and behavior == "show_warning":
                warning = f"Missing image asset: {character_id}/{situation_id}{extension}"

    return ImageSegment(
        type="image",
        path=f"{resolved_character_id}/{resolved_situation_id}{extension}",
        url=image_asset_url(scenario.id, resolved_character_id, resolved_situation_id, extension),
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
