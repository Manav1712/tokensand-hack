"""Inventory a skill tree without following links."""

from __future__ import annotations

import os
import stat
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from skill_warden.errors import NoSkillError, SkillTreeError
from skill_warden.frontmatter import read_frontmatter
from skill_warden.hashing import content_hash_v2
from skill_warden.models import FileEntry, Finding, Severity, SkillRecord, Source

MAX_FILES = 500
MAX_TOTAL_BYTES = 5 * 1024 * 1024
MAX_FILE_BYTES = 1 * 1024 * 1024
_SEARCH_DEPTH = 4
_EXECUTE = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
_TEXT_EXTENSIONS = frozenset(
    {".md", ".txt", ".sh", ".py", ".js", ".ts", ".json", ".yaml", ".yml", ".toml"}
)
_MACHO = (
    b"\xfe\xed\xfa\xce",
    b"\xfe\xed\xfa\xcf",
    b"\xce\xfa\xed\xfe",
    b"\xcf\xfa\xed\xfe",
    b"\xca\xfe\xba\xbe",
)
_Kind = Literal["text", "binary"]


@dataclass(frozen=True)
class Discovered:
    path: Path
    findings: tuple[Finding, ...] = ()


@dataclass(frozen=True)
class LoadedSkill:
    record: SkillRecord
    findings: tuple[Finding, ...]


@dataclass(frozen=True)
class _File:
    relpath: str
    path: Path
    size: int
    mode: int


def discover(path: Path) -> tuple[Discovered, ...]:
    """Find skill directories under ``path``. A symlink root is resolved once."""
    raw = Path(path)
    notes: list[Finding] = []
    if raw.is_symlink():
        notes.append(_finding("symlink_root", Severity.INFO, file=raw.name))
        try:
            current = raw.resolve()
        except OSError:
            raise NoSkillError() from None
    else:
        current = raw
    if _is_skill_file(current):
        return (Discovered(current.parent, tuple(notes)),)
    if not current.is_dir():
        raise NoSkillError()
    if _is_skill_dir(current):
        return (Discovered(current, tuple(notes)),)
    found: list[Path] = []
    _search(current, 0, found)
    if not found:
        raise NoSkillError()
    extra = tuple(notes)
    ordered = sorted(found, key=lambda item: item.as_posix())
    return tuple(Discovered(skill, extra) for skill in ordered)


def load_skill(
    path: Path,
    *,
    max_files: int = MAX_FILES,
    max_total_bytes: int = MAX_TOTAL_BYTES,
    max_file_bytes: int = MAX_FILE_BYTES,
) -> LoadedSkill:
    """Inventory ``path``. An error finding leaves the content hash unset."""
    root = Path(path)
    if root.is_symlink():
        try:
            root = root.resolve()
        except OSError:
            return _failed(root)
    if not root.is_dir():
        return _failed(root)
    files, relpaths, findings = _inventory(root)
    findings.extend(_cap_findings(files, max_files, max_total_bytes, max_file_bytes))
    entries: list[FileEntry] = []
    for item in sorted(files, key=lambda entry: entry.relpath):
        if item.size > max_file_bytes:
            entries.append(_entry(item, "binary"))
            continue
        kind, extra = _classify(item)
        entries.append(_entry(item, kind))
        findings.extend(extra)
    findings.extend(case_collisions(relpaths))
    name = _skill_name(root, entries, findings)
    digest = _digest(root, findings)
    record = SkillRecord(root, name, digest, 2, tuple(entries))
    return LoadedSkill(record, tuple(findings))


def _skill_name(root: Path, entries: Sequence[FileEntry], findings: list[Finding]) -> str:
    skill = next(
        (item for item in entries if item.relpath == "SKILL.md" and item.kind == "text"),
        None,
    )
    if skill is None:
        findings.append(_finding("frontmatter_invalid", Severity.INFO, file="SKILL.md"))
        return root.name
    try:
        text = (root / "SKILL.md").read_text(encoding="utf-8")
    except OSError:
        findings.append(_finding("frontmatter_invalid", Severity.INFO, file="SKILL.md"))
        return root.name
    result = read_frontmatter(text)
    findings.extend(result.findings)
    if result.name is None:
        return root.name
    return result.name


def write_normalized(
    root: Path,
    files: Sequence[FileEntry],
    dest: Path,
) -> tuple[Finding, ...]:
    """Copy text files into ``dest`` with Cf characters stripped and NFKC applied.

    The original bytes stay where they are. A non-breaking space is not a finding.
    """
    dest.mkdir(parents=True, exist_ok=True)
    dest.chmod(0o700)
    findings: list[Finding] = []
    for entry in files:
        if entry.kind != "text":
            continue
        source = root / entry.relpath
        text = source.read_text(encoding="utf-8")
        normalized, removed = _normalize_text(text)
        target = dest / entry.relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(normalized, encoding="utf-8")
        if removed:
            findings.append(
                _finding("obfuscation.unicode", Severity.MEDIUM, file=entry.relpath)
            )
    return tuple(findings)


def _normalize_text(text: str) -> tuple[str, bool]:
    kept: list[str] = []
    removed = False
    for char in text:
        if unicodedata.category(char) == "Cf":
            removed = True
            continue
        kept.append(char)
    return unicodedata.normalize("NFKC", "".join(kept)), removed


def case_collisions(relpaths: Sequence[str]) -> tuple[Finding, ...]:
    """Findings for paths that differ only by letter case."""
    groups: dict[str, list[str]] = {}
    for relpath in relpaths:
        groups.setdefault(relpath.casefold(), []).append(relpath)
    findings: list[Finding] = []
    for paths in groups.values():
        unique = sorted(set(paths))
        if len(unique) < 2:
            continue
        findings.append(
            _finding(
                "case_collision",
                Severity.HIGH,
                file=unique[0],
                excerpt=", ".join(unique),
            )
        )
    return tuple(findings)


def _search(directory: Path, depth: int, found: list[Path]) -> None:
    if depth >= _SEARCH_DEPTH:
        return
    try:
        children = sorted(directory.iterdir(), key=lambda item: item.name)
    except OSError:
        return
    for child in children:
        try:
            linked = child.is_symlink()
            is_dir = child.is_dir()
        except OSError:
            continue
        if linked or not is_dir:
            continue
        if _is_skill_dir(child):
            found.append(child)
            continue
        _search(child, depth + 1, found)


def _is_skill_file(path: Path) -> bool:
    try:
        return path.is_file() and path.name == "SKILL.md"
    except OSError:
        return False


def _is_skill_dir(directory: Path) -> bool:
    marker = directory / "SKILL.md"
    try:
        return marker.is_symlink() or marker.is_file()
    except OSError:
        return False


def _inventory(root: Path) -> tuple[list[_File], list[str], list[Finding]]:
    files: list[_File] = []
    relpaths: list[str] = []
    findings: list[Finding] = []

    def onerror(error: OSError) -> None:
        relpath = _relative(root, error.filename)
        findings.append(_finding("unreadable", Severity.ERROR, file=relpath))
        if relpath:
            relpaths.append(relpath)

    for dirpath, dirnames, filenames in os.walk(root, onerror=onerror):
        directory = Path(dirpath)
        kept: list[str] = []
        for name in dirnames:
            path = directory / name
            relpath = _relative(root, path)
            if path.is_symlink():
                findings.append(_finding("symlink", Severity.ERROR, file=relpath))
                relpaths.append(relpath)
                continue
            kept.append(name)
        dirnames[:] = kept
        for name in filenames:
            path = directory / name
            relpath = _relative(root, path)
            relpaths.append(relpath)
            if path.is_symlink():
                findings.append(_finding("symlink", Severity.ERROR, file=relpath))
                continue
            try:
                info = path.lstat()
            except OSError:
                findings.append(_finding("unreadable", Severity.ERROR, file=relpath))
                continue
            if not stat.S_ISREG(info.st_mode):
                findings.append(_finding("unreadable", Severity.ERROR, file=relpath))
                continue
            files.append(_File(relpath, path, info.st_size, info.st_mode))
    return files, relpaths, findings


def _cap_findings(
    files: Sequence[_File],
    max_files: int,
    max_total_bytes: int,
    max_file_bytes: int,
) -> list[Finding]:
    findings: list[Finding] = []
    if len(files) > max_files:
        findings.append(
            _finding("too_large", Severity.ERROR, excerpt=f"file count cap is {max_files}")
        )
    total = sum(item.size for item in files)
    if total > max_total_bytes:
        findings.append(
            _finding(
                "too_large",
                Severity.ERROR,
                excerpt=f"total size cap is {max_total_bytes} bytes",
            )
        )
    oversized = sorted(item.relpath for item in files if item.size > max_file_bytes)
    if oversized:
        findings.append(
            _finding(
                "too_large",
                Severity.ERROR,
                file=oversized[0],
                excerpt=f"file size cap is {max_file_bytes} bytes",
            )
        )
    return findings


def _classify(item: _File) -> tuple[_Kind, tuple[Finding, ...]]:
    try:
        data = item.path.read_bytes()
    except OSError:
        return "binary", (_finding("unreadable", Severity.ERROR, file=item.relpath),)
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return "binary", _binary_findings(item, data)
    return "text", ()


def _binary_findings(item: _File, data: bytes) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    if PurePosixPath(item.relpath).suffix.lower() in _TEXT_EXTENSIONS:
        findings.append(_finding("undecodable_text", Severity.MEDIUM, file=item.relpath))
    if _opaque(item, data):
        findings.append(_finding("opaque_binary", Severity.MEDIUM, file=item.relpath))
    elif not findings:
        findings.append(_finding("binary_file", Severity.INFO, file=item.relpath))
    return tuple(findings)


def _opaque(item: _File, data: bytes) -> bool:
    return bool(item.mode & _EXECUTE or item.relpath.startswith("scripts/") or _magic(data))


def _magic(data: bytes) -> bool:
    if data.startswith((b"\x7fELF", b"MZ", b"\x00asm")):
        return True
    return data.startswith(_MACHO)


def _digest(root: Path, findings: list[Finding]) -> str | None:
    if any(finding.severity is Severity.ERROR for finding in findings):
        return None
    try:
        return content_hash_v2(root)
    except SkillTreeError:
        findings.append(_finding("unreadable", Severity.ERROR))
        return None


def _entry(item: _File, kind: _Kind) -> FileEntry:
    return FileEntry(item.relpath, item.size, kind, bool(item.mode & _EXECUTE))


def _failed(path: Path) -> LoadedSkill:
    record = SkillRecord(path, path.name, None, 2, ())
    return LoadedSkill(record, (_finding("unreadable", Severity.ERROR),))


def _relative(root: Path, raw: object) -> str:
    if isinstance(raw, bytes):
        candidate = Path(os.fsdecode(raw))
    elif isinstance(raw, Path):
        candidate = raw
    elif isinstance(raw, str):
        candidate = Path(raw)
    else:
        return ""
    try:
        relative = candidate.relative_to(root)
    except ValueError:
        return ""
    text = relative.as_posix()
    if text == ".":
        return ""
    return text


def _finding(
    rule_id: str,
    severity: Severity,
    *,
    file: str = "",
    excerpt: str = "",
) -> Finding:
    return Finding(Source.INTAKE, rule_id, severity, file=file, excerpt=excerpt)
