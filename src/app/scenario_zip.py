from __future__ import annotations

import io
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from app.ids import is_locus_id
from app.images import ALLOWED_IMAGE_EXTENSIONS
from app.loaders import load_scenario
from app.memory_summarizer import mark_rag_index_stale
from app.vault import Vault, VaultError, VaultPathError


_ALLOWED_TEXT_EXTENSIONS: frozenset[str] = frozenset({
    ".md", ".json", ".yaml", ".html", ".css",
})
_ALLOWED_EXTENSIONS: frozenset[str] = _ALLOWED_TEXT_EXTENSIONS | frozenset(ALLOWED_IMAGE_EXTENSIONS)

_EXCLUDE_TOP_DIRS: frozenset[str] = frozenset({"sessions", "memory", "_cache"})

_MAX_ZIP_BYTES = 200 * 1024 * 1024   # 200 MB
_MAX_FILE_BYTES = 50 * 1024 * 1024   # 50 MB


class ScenarioZipError(VaultError):
    """Raised when a ZIP export or import operation fails."""


class ScenarioAlreadyExistsError(ScenarioZipError):
    """Raised when the target scenario_id already exists in the vault."""


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_scenario_zip(vault: Vault, scenario_id: str) -> bytes:
    """Build and return a ZIP archive of a scenario directory.

    Excludes sessions/, memory/, and _cache/. Only allows image files with
    permitted extensions under assets/images/.
    """
    scenario_dir = vault.resolve(f"rp/scenarios/{scenario_id}")
    if not scenario_dir.is_dir():
        raise VaultPathError(f"Scenario not found: {scenario_id}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for abs_path in sorted(scenario_dir.rglob("*")):
            if not abs_path.is_file():
                continue

            rel = abs_path.relative_to(scenario_dir)
            top = rel.parts[0] if rel.parts else ""

            if top in _EXCLUDE_TOP_DIRS:
                continue

            ext = abs_path.suffix.lower()

            # Under assets/images/ allow only image extensions
            if len(rel.parts) >= 2 and rel.parts[0] == "assets" and rel.parts[1] == "images":
                if ext not in ALLOWED_IMAGE_EXTENSIONS:
                    continue
            else:
                # Outside assets/images/ allow only text extensions
                if ext not in _ALLOWED_TEXT_EXTENSIONS:
                    continue

            zf.write(abs_path, arcname=rel.as_posix())

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def import_scenario_zip(vault: Vault, zip_bytes: bytes, scenario_id: str) -> dict[str, Any]:
    """Extract a ZIP archive into the vault as a new scenario.

    Validates every entry for path traversal, extension allowlist, symlinks,
    and file size. Raises ScenarioZipError or VaultPathError on any failure.
    """
    if not is_locus_id(scenario_id):
        raise ScenarioZipError(f"Invalid scenario_id: {scenario_id}")

    if len(zip_bytes) > _MAX_ZIP_BYTES:
        raise ScenarioZipError(
            f"ZIP is too large ({len(zip_bytes)} bytes, limit {_MAX_ZIP_BYTES})"
        )

    scenario_dir = vault.resolve(f"rp/scenarios/{scenario_id}")
    if scenario_dir.exists():
        raise ScenarioAlreadyExistsError(f"Scenario already exists: {scenario_id}")

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as exc:
        raise ScenarioZipError("Invalid ZIP file") from exc

    with zf:
        _validate_zip_entries(zf)
        imported_files = _extract_to_vault(zf, scenario_id, scenario_dir)

    mark_rag_index_stale(vault, scenario_id, [])

    scenario = load_scenario(vault, scenario_id)
    return {
        "scenario": {
            "id": scenario.id,
            "name": scenario.name,
            "metadata": scenario.metadata,
        },
        "imported": True,
        "imported_files": imported_files,
    }


def _validate_zip_entries(zf: zipfile.ZipFile) -> None:
    has_scenario_md = False
    for info in zf.infolist():
        name = info.filename

        if info.is_dir():
            continue

        if name == "scenario.md" or name.endswith("/scenario.md"):
            # Accept only the top-level scenario.md
            if "/" not in name:
                has_scenario_md = True

        _check_entry_path(name)

        if _is_zip_symlink(info):
            raise ScenarioZipError(f"ZIP contains a symlink entry: {name}")

        if info.file_size > _MAX_FILE_BYTES:
            raise ScenarioZipError(
                f"Entry too large: {name} ({info.file_size} bytes, limit {_MAX_FILE_BYTES})"
            )

    if not has_scenario_md:
        raise ScenarioZipError("ZIP does not contain scenario.md")


def _is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    # Unix external attributes: upper 16 bits are the file mode.
    # 0xA000 is the symlink bit mask (S_IFLNK).
    unix_attrs = info.external_attr >> 16
    return bool(unix_attrs) and (unix_attrs & 0xF000) == 0xA000


def _check_entry_path(name: str) -> None:
    if not name or name.startswith("/"):
        raise ScenarioZipError(f"Invalid ZIP entry path: {name!r}")

    try:
        posix = PurePosixPath(name)
    except Exception as exc:
        raise ScenarioZipError(f"Invalid ZIP entry path: {name!r}") from exc

    for part in posix.parts:
        if part in ("", ".", ".."):
            raise ScenarioZipError(f"ZIP entry contains unsafe path segment: {name!r}")

    ext = posix.suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise ScenarioZipError(f"ZIP entry has disallowed extension: {name!r}")


def _extract_to_vault(
    zf: zipfile.ZipFile,
    scenario_id: str,
    scenario_dir: Path,
) -> list[str]:
    """Extract ZIP into vault and return list of extracted file paths (scenario-relative)."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="locus_zip_import_"))
    extracted: list[str] = []
    try:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            dest = tmp_dir / Path(*PurePosixPath(name).parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(name))
            extracted.append(name)

        _patch_scenario_id(tmp_dir / "scenario.md", scenario_id)
        _ensure_runtime_dirs(tmp_dir)
        shutil.move(str(tmp_dir), str(scenario_dir))
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    return extracted


def _patch_scenario_id(scenario_md: Path, scenario_id: str) -> None:
    """Rewrite the id field in scenario.md frontmatter to match the target scenario_id."""
    if not scenario_md.is_file():
        return
    import re as _re
    text = scenario_md.read_text(encoding="utf-8")
    patched = _re.sub(r"(?m)^id:\s*.+$", f"id: {scenario_id}", text, count=1)
    scenario_md.write_text(patched, encoding="utf-8")


def _ensure_runtime_dirs(base: Path) -> None:
    for rel in (
        "sessions",
        "memory/session_summaries",
        "memory/extracted_facts",
        "memory/unresolved_threads",
    ):
        (base / rel).mkdir(parents=True, exist_ok=True)
