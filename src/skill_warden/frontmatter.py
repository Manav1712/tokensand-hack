"""Read SKILL.md frontmatter with YAML and with a line parser, then compare."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

import yaml

from skill_warden.models import Finding, Severity, Source

_NAME = "name"
_DESCRIPTION = "description"
_INSTALL = "metadata.openclaw.install"
_BINS = "metadata.openclaw.requires.bins"
_MISSING = object()
_BLOCK = {"|", "|-", "|+", ">", ">-", ">+"}


@dataclass(frozen=True)
class LineResult:
    """A line-parser result. ``error`` is set instead of raising."""

    value: object
    complex_paths: frozenset[str] = frozenset()
    duplicate_paths: frozenset[str] = frozenset()
    error: str | None = None


@dataclass(frozen=True)
class Frontmatter:
    name: str | None
    findings: tuple[Finding, ...]


def parse_lines(text: str) -> LineResult:
    """Parse the plain subset of YAML. Never raises."""
    try:
        return _Parser(text).parse()
    except Exception as exc:  # noqa: BLE001
        return LineResult(None, error=type(exc).__name__)


def read_frontmatter(text: str) -> Frontmatter:
    """Compare the two readings of ``text``. Never raises."""
    try:
        return _read(text)
    except Exception:  # noqa: BLE001
        return Frontmatter(None, (_finding("frontmatter_unparseable", Severity.HIGH, "yaml"),))


def _read(text: str) -> Frontmatter:
    block = _front_block(text)
    if block is None:
        return Frontmatter(None, (_finding("frontmatter_invalid", Severity.INFO, "frontmatter"),))
    try:
        loaded = yaml.safe_load(block)
    except yaml.YAMLError:
        return Frontmatter(None, (_finding("frontmatter_unparseable", Severity.HIGH, "yaml"),))
    if not isinstance(loaded, dict):
        return Frontmatter(None, (_finding("frontmatter_invalid", Severity.INFO, "frontmatter"),))
    parsed = parse_lines(block)
    if parsed.error is not None or not isinstance(parsed.value, dict):
        return Frontmatter(
            _yaml_name(loaded),
            (_finding("frontmatter_complex", Severity.MEDIUM, "document"),),
        )
    return _compare(loaded, parsed)


def _compare(loaded: dict[object, object], parsed: LineResult) -> Frontmatter:
    complex_fields: list[str] = []
    mismatched: list[str] = []
    install_mismatch: list[str] = []
    missing: list[str] = []
    line_value = parsed.value if isinstance(parsed.value, dict) else {}
    for path, label, required in (
        (_NAME, "name", True),
        (_DESCRIPTION, "description", True),
        (_INSTALL, "install", False),
        (_BINS, "bins", False),
    ):
        if _blocked(path, parsed):
            complex_fields.append(label)
            continue
        yaml_value = _dig(loaded, path)
        other = _dig(line_value, path)
        if required:
            _compare_required(yaml_value, other, label, mismatched, missing)
        else:
            _compare_optional(yaml_value, other, label, install_mismatch)
    findings: list[Finding] = []
    if complex_fields:
        findings.append(
            _finding("frontmatter_complex", Severity.MEDIUM, ", ".join(complex_fields))
        )
    if mismatched:
        findings.append(
            _finding("frontmatter_mismatch", Severity.MEDIUM, ", ".join(mismatched))
        )
    if install_mismatch:
        findings.append(
            _finding(
                "frontmatter_mismatch_install",
                Severity.HIGH,
                ", ".join(install_mismatch),
            )
        )
    if missing:
        findings.append(_finding("frontmatter_invalid", Severity.INFO, ", ".join(missing)))
    return Frontmatter(_yaml_name(loaded), tuple(findings))


def _compare_required(
    yaml_value: object,
    other: object,
    label: str,
    mismatched: list[str],
    missing: list[str],
) -> None:
    if _blank(yaml_value) and _blank(other):
        missing.append(label)
        return
    if _scalar(yaml_value) != _scalar(other):
        mismatched.append(label)


def _compare_optional(
    yaml_value: object,
    other: object,
    label: str,
    mismatched: list[str],
) -> None:
    if yaml_value is _MISSING and other is _MISSING:
        return
    if label == "bins":
        if _bins(yaml_value) != _bins(other):
            mismatched.append(label)
        return
    if _scalar(yaml_value) != _scalar(other):
        mismatched.append(label)


def _front_block(text: str) -> str | None:
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() in {"---", "..."}:
            return "\n".join(lines[1:index]) + "\n"
    return None


def _blocked(path: str, parsed: LineResult) -> bool:
    return _covers(path, parsed.complex_paths) or _covers(path, parsed.duplicate_paths)


def _covers(path: str, flagged: frozenset[str]) -> bool:
    parts = path.split(".")
    for index in range(1, len(parts) + 1):
        if ".".join(parts[:index]) in flagged:
            return True
    return False


def _dig(value: object, path: str) -> object:
    current = value
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            return _MISSING
        current = current[key]
    return current


def _blank(value: object) -> bool:
    if value is _MISSING or value is None:
        return True
    return isinstance(value, str) and _collapse(value) == ""


def _scalar(value: object) -> str | None:
    if value is _MISSING or value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return _collapse(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    return None


def _bins(value: object) -> tuple[str, ...] | None:
    if value is _MISSING:
        return None
    if not isinstance(value, list):
        return None
    items: list[str] = []
    for item in value:
        text = _scalar(item)
        if text is None:
            return None
        items.append(text)
    return tuple(items)


def _collapse(value: str) -> str:
    return " ".join(value.split())


def _yaml_name(loaded: object) -> str | None:
    if not isinstance(loaded, dict):
        return None
    raw = loaded.get("name")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _finding(rule_id: str, severity: Severity, excerpt: str) -> Finding:
    return Finding(Source.INTAKE, rule_id, severity, file="SKILL.md", excerpt=excerpt)


class _Parser:
    def __init__(self, text: str) -> None:
        self.lines = [(len(raw) - len(raw.lstrip(" ")), raw.lstrip(" ")) for raw in text.splitlines()]
        self.index = 0
        self.complex: set[str] = set()
        self.duplicates: set[str] = set()

    def parse(self) -> LineResult:
        value = self._parse_block(0, "")
        return LineResult(value, frozenset(self.complex), frozenset(self.duplicates))

    def _parse_block(self, indent: int, path: str) -> object:
        while self.index < len(self.lines) and self.lines[self.index][1] == "":
            self.index += 1
        if self.index >= len(self.lines):
            return {}
        content = self.lines[self.index][1]
        if content.startswith("- ") or content == "-":
            return self._parse_seq(indent, path)
        return self._parse_map(indent, path)

    def _parse_map(self, indent: int, path: str) -> dict[str, object]:
        result: dict[str, object] = {}
        while self.index < len(self.lines):
            ind, content = self.lines[self.index]
            if content == "" or content.startswith("#"):
                self.index += 1
                continue
            if "\t" in content:
                self.complex.add(path or "document")
                self.index += 1
                continue
            if ind < indent:
                break
            if ind > indent or content.startswith("-"):
                self.complex.add(path or "document")
                self.index += 1
                continue
            key, raw_value = _split_key(content)
            if key is None:
                self.complex.add(path or "document")
                self.index += 1
                continue
            full = f"{path}.{key}" if path else key
            if key in result:
                self.duplicates.add(full)
            self.index += 1
            result[key] = self._value(indent, full, raw_value)
        return result

    def _value(self, indent: int, path: str, raw_value: str | None) -> object:
        if raw_value is None:
            if self.index < len(self.lines) and _next_content_indent(self.lines, self.index) > indent:
                child = _next_content_indent(self.lines, self.index)
                return self._parse_block(child, path)
            return None
        if raw_value in _BLOCK:
            return self._block(indent, raw_value)
        if _unsupported(raw_value):
            self.complex.add(path)
            return None
        return _plain(raw_value)

    def _parse_seq(self, indent: int, path: str) -> list[object]:
        items: list[object] = []
        while self.index < len(self.lines):
            ind, content = self.lines[self.index]
            if content == "" or content.startswith("#"):
                self.index += 1
                continue
            if ind < indent:
                break
            if ind > indent or not (content.startswith("- ") or content == "-"):
                self.complex.add(path or "document")
                self.index += 1
                continue
            item = content[1:].strip()
            self.index += 1
            if item == "":
                if self.index < len(self.lines) and self.lines[self.index][0] > indent:
                    items.append(self._parse_block(self.lines[self.index][0], path))
                else:
                    items.append(None)
                continue
            if _unsupported(item):
                self.complex.add(path or "document")
                items.append(None)
                continue
            items.append(_plain(item))
        return items

    def _block(self, indent: int, style: str) -> str:
        chunks: list[str] = []
        block_indent: int | None = None
        while self.index < len(self.lines):
            ind, content = self.lines[self.index]
            if content == "":
                chunks.append("")
                self.index += 1
                continue
            if block_indent is None:
                if ind <= indent:
                    break
                block_indent = ind
            elif ind < block_indent:
                break
            chunks.append(content)
            self.index += 1
        while chunks and chunks[-1] == "":
            chunks.pop()
        if style.startswith(">"):
            body = _fold(chunks)
        else:
            body = "\n".join(chunks)
        if style.endswith("-"):
            return body
        if body and not body.endswith("\n"):
            return body + "\n"
        return body


def _next_content_indent(lines: Sequence[tuple[int, str]], index: int) -> int:
    for ind, content in lines[index:]:
        if content == "" or content.startswith("#"):
            continue
        return ind
    return -1


def _split_key(content: str) -> tuple[str | None, str | None]:
    if ":" not in content or content.startswith(("-", "!", "&", "*", "[", "{", "'", '"', "|", ">")):
        return None, None
    key, rest = content.split(":", 1)
    key = key.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", key):
        return None, None
    rest = _strip_comment(rest.strip())
    if rest == "":
        return key, None
    return key, rest


def _unsupported(value: str) -> bool:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return False
    if text.startswith(("!", "&", "*", "[", "{", "|", ">", "'", '"')):
        return True
    return re.search(r"(^|\s)[&*!]", text) is not None


def _strip_comment(value: str) -> str:
    if value.startswith(("'", '"')):
        return value
    if " #" in value:
        return value.split(" #", 1)[0].rstrip()
    return value


def _plain(value: str) -> str:
    text = _strip_comment(value.strip())
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        inner = text[1:-1]
        if text[0] == '"':
            return _decode_double(inner)
        return inner.replace("''", "'")
    return text


def _decode_double(inner: str) -> str:
    chars: list[str] = []
    index = 0
    while index < len(inner):
        if inner[index] != "\\":
            chars.append(inner[index])
            index += 1
            continue
        if index + 1 >= len(inner):
            chars.append("\\")
            break
        code = inner[index + 1]
        chars.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(code, code))
        index += 2
    return "".join(chars)


def _fold(chunks: Sequence[str]) -> str:
    parts: list[str] = []
    for chunk in chunks:
        if chunk == "":
            if parts and parts[-1] != "\n":
                parts.append("\n")
            continue
        if parts and parts[-1] != "\n":
            parts.append(" ")
        parts.append(chunk)
    return "".join(parts)
