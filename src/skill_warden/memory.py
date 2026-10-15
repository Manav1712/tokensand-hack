from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from skill_warden.errors import MemoryCapError

_LINE_CAP = 200
_BYTE_CAP = 25 * 1024
_RANK = {"outside": 0, "agent": 1, "user": 2}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Memory:
    def __init__(
        self,
        root: Path,
        *,
        read_text: Callable[[Path], str] | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.root = root
        self._read_text = read_text or (lambda path: path.read_text(encoding="utf-8"))
        self._clock = clock or _now

    def start_session(self) -> list[dict[str, str]]:
        return [{"title": row["title"], "origin": row["origin"]} for row in self._rows()]

    def open_note(self, note_id: str) -> str:
        row = self._row(note_id)
        return self._read_text(self.root / row["note_path"])

    def remember(self, title: str, text: str, origin: str) -> str:
        return self._write(title, text, origin)

    def rewrite(self, source_ids: list[str], title: str, text: str) -> str:
        origins = [self._row(source_id)["origin"] for source_id in source_ids]
        weakest = min(origins, key=lambda origin: _RANK[origin])
        return self._write(title, text, weakest)

    def allows_action(self, note_id: str) -> bool:
        return self._row(note_id)["origin"] in {"user", "agent"}

    def drop_index_line(self, note_id: str) -> None:
        kept = [row for row in self._rows() if row["id"] != note_id]
        self._write_index(kept)

    def search(self, query: str) -> list[str]:
        notes = self.root / "notes"
        if not notes.exists():
            return []
        found = []
        for path in sorted(notes.iterdir()):
            if path.is_file() and query in self._read_text(path):
                found.append(path.name)
        return found

    def _write(self, title: str, text: str, origin: str) -> str:
        note_id = self._new_id()
        rows = self._rows()
        rows.append(
            {
                "id": note_id,
                "title": title,
                "origin": origin,
                "written_at": self._clock(),
                "note_path": f"notes/{note_id}",
            }
        )
        rendered = _render(rows)
        if len(rows) > _LINE_CAP or len(rendered.encode("utf-8")) > _BYTE_CAP:
            raise MemoryCapError("memory cap")
        note_file = self.root / "notes" / note_id
        note_file.parent.mkdir(parents=True, exist_ok=True)
        note_file.write_text(text, encoding="utf-8")
        self._write_index(rows)
        return note_id

    def _new_id(self) -> str:
        notes = self.root / "notes"
        taken = {path.name for path in notes.iterdir()} if notes.exists() else set()
        candidate = 1
        while str(candidate) in taken:
            candidate += 1
        return str(candidate)

    def _row(self, note_id: str) -> dict[str, str]:
        for row in self._rows():
            if row["id"] == note_id:
                return row
        raise KeyError(note_id)

    def _rows(self) -> list[dict[str, str]]:
        path = self.root / "INDEX"
        if not path.exists():
            return []
        rows = []
        for line in self._read_text(path).splitlines():
            note_id, title, origin, written_at, note_path = line.split("\t")
            rows.append(
                {
                    "id": note_id,
                    "title": title,
                    "origin": origin,
                    "written_at": written_at,
                    "note_path": note_path,
                }
            )
        return rows

    def _write_index(self, rows: list[dict[str, str]]) -> None:
        (self.root / "INDEX").write_text(_render(rows), encoding="utf-8")


def _render(rows: list[dict[str, str]]) -> str:
    if not rows:
        return ""
    lines = [
        "\t".join((row["id"], row["title"], row["origin"], row["written_at"], row["note_path"]))
        for row in rows
    ]
    return "\n".join(lines) + "\n"
