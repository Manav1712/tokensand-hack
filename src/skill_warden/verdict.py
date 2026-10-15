from pathlib import Path


def load_sql() -> str:
    relative = Path("schema") / "verdict.sql"
    candidates = [parent / relative for parent in Path(__file__).resolve().parents]
    candidates.append(Path.cwd() / relative)
    for path in candidates:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    raise FileNotFoundError(relative)
