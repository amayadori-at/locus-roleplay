from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


class VaultError(Exception):
    """Base error for Vault access failures."""


class VaultPathError(VaultError):
    """Raised when a Vault-relative path is invalid or unsafe."""


class VaultFileError(VaultError):
    """Raised when a Vault file cannot be read or parsed."""


class FrontmatterError(VaultFileError):
    """Raised when Markdown frontmatter is malformed."""


@dataclass(frozen=True)
class MarkdownDocument:
    frontmatter: dict[str, Any]
    body: str


def vault_root_from_env(env: dict[str, str] | None = None) -> Path:
    source = env if env is not None else os.environ
    value = source.get("LOCUS_VAULT_ROOT")
    if not value:
        raise VaultPathError("LOCUS_VAULT_ROOT is not set")
    return Path(value)


class Vault:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Vault":
        return cls(vault_root_from_env(env))

    def resolve(self, relative_path: str | PurePosixPath) -> Path:
        if isinstance(relative_path, Path):
            raise VaultPathError("Vault path must be a POSIX-style relative path")

        raw_path = str(relative_path)
        if not raw_path or raw_path.strip() == "":
            raise VaultPathError("Vault path must not be empty")
        if "\\" in raw_path:
            raise VaultPathError("Vault path must not contain backslashes")

        posix_path = PurePosixPath(raw_path)
        if posix_path.is_absolute():
            raise VaultPathError("Vault path must be relative")
        if any(part in ("", ".", "..") for part in posix_path.parts):
            raise VaultPathError("Vault path contains an unsafe segment")

        resolved = (self.root / Path(*posix_path.parts)).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise VaultPathError("Vault path escapes the configured root") from exc
        return resolved

    def read_text(self, relative_path: str | PurePosixPath) -> str:
        path = self.resolve(relative_path)
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise VaultFileError(f"Failed to read Vault file: {relative_path}") from exc

    def load_json(self, relative_path: str | PurePosixPath) -> Any:
        raw = self.read_text(relative_path)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise VaultFileError(f"Invalid JSON in Vault file: {relative_path}") from exc

    def load_markdown(self, relative_path: str | PurePosixPath) -> MarkdownDocument:
        return parse_markdown(self.read_text(relative_path))


def parse_markdown(raw: str) -> MarkdownDocument:
    if not raw.startswith(("---\n", "---\r\n")) and raw != "---":
        return MarkdownDocument(frontmatter={}, body=raw)

    lines = raw.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return MarkdownDocument(frontmatter={}, body=raw)

    closing_index: int | None = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing_index = index
            break

    if closing_index is None:
        raise FrontmatterError("Markdown frontmatter is not closed")

    frontmatter_raw = "".join(lines[1:closing_index])
    body = "".join(lines[closing_index + 1 :])
    if body.startswith("\n"):
        body = body[1:]
    return MarkdownDocument(frontmatter=parse_frontmatter(frontmatter_raw), body=body)


def parse_frontmatter(raw: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_list_key: str | None = None

    for line_number, raw_line in enumerate(raw.splitlines(), start=1):
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if line.startswith("  - "):
            if current_list_key is None:
                raise FrontmatterError(f"List item without a key at frontmatter line {line_number}")
            value = _parse_scalar(line[4:].strip(), line_number)
            data[current_list_key].append(value)
            continue

        current_list_key = None
        if line.startswith((" ", "\t")):
            raise FrontmatterError(f"Unsupported indentation at frontmatter line {line_number}")
        if ":" not in line:
            raise FrontmatterError(f"Missing ':' at frontmatter line {line_number}")

        key, value_raw = line.split(":", 1)
        key = key.strip()
        if not key:
            raise FrontmatterError(f"Empty key at frontmatter line {line_number}")
        if key in data:
            raise FrontmatterError(f"Duplicate key '{key}' at frontmatter line {line_number}")

        value_raw = value_raw.strip()
        if value_raw == "":
            data[key] = []
            current_list_key = key
        else:
            data[key] = _parse_scalar(value_raw, line_number)

    return data


def _parse_scalar(value: str, line_number: int) -> Any:
    if value in ("true", "True"):
        return True
    if value in ("false", "False"):
        return False
    if value in ("null", "Null", "~"):
        return None
    if value.startswith('"') or value.endswith('"'):
        if len(value) < 2 or not value.endswith('"') or value.count('"') < 2:
            raise FrontmatterError(f"Unclosed double-quoted string at frontmatter line {line_number}")
        return value[1:-1]
    if value.startswith("'") or value.endswith("'"):
        if len(value) < 2 or not value.endswith("'") or value.count("'") < 2:
            raise FrontmatterError(f"Unclosed single-quoted string at frontmatter line {line_number}")
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value
