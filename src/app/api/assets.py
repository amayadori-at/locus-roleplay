from __future__ import annotations

from app.api_validation import validate_id as _validate_id
from app.images import ALLOWED_IMAGE_EXTENSIONS, ImageMarkerError, image_asset_path
from app.vault import Vault
from app.api.common import ApiResponse, _json_response


def _image_response(vault: Vault, scenario_id: str, character_id: str, filename: str) -> ApiResponse:
    scenario_id = _validate_id(scenario_id, "scenario")
    dot_pos = filename.rfind(".")
    if dot_pos < 0:
        raise ImageMarkerError(f"Invalid image filename: {filename}")
    extension = filename[dot_pos:]
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ImageMarkerError(f"Invalid image filename: {filename}")
    situation_id = filename[:dot_pos]
    path = image_asset_path(vault, scenario_id, character_id, situation_id, extension)
    if not path.is_file():
        return _json_response({"error": "not_found", "message": "Image asset not found"}, status=404)
    return ApiResponse(
        status=200,
        content_type=ALLOWED_IMAGE_EXTENSIONS[extension],
        body=path.read_bytes(),
        last_modified=path.stat().st_mtime,
    )
