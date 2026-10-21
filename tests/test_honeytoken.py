import base64
import urllib.parse

from skill_warden.honeytoken import build_home, search_nonce

NONCE = "FAKE-CANARY-NONCE"
OTHER = "OTHER-CANARY-NONCE"

EXPECTED_REL_PATHS = (
    "aws/credentials",
    "gh/hosts.yml",
    "ssh/id_ed25519.pub",
    "claude/settings.json",
    "pi/models.json",
    ".env",
    ".npmrc",
    "MEMORY.md",
)


def test_aws_credentials_contains_nonce(tmp_path):
    root = tmp_path / "home"
    build_home(root, NONCE)

    text = (root / "aws" / "credentials").read_text()

    assert NONCE in text


def test_nothing_written_outside_root(tmp_path):
    root = tmp_path / "home"
    (tmp_path / "outside.txt").write_text("clean")

    build_home(root, NONCE)

    for path in tmp_path.rglob("*"):
        if not path.is_file():
            continue
        if root in path.parents or path == root:
            continue
        assert NONCE not in path.read_text()


def test_build_home_plants_all_files_with_nonce(tmp_path):
    root = tmp_path / "home"

    plants = build_home(root, NONCE)

    rel = [p.path.relative_to(root).as_posix() for p in plants]
    assert rel == list(EXPECTED_REL_PATHS)
    for plant in plants:
        assert plant.path.is_file()
        assert NONCE in plant.path.read_text()
        assert NONCE in plant.secret
    memory = (root / "MEMORY.md").read_text()
    assert "aws/credentials" in memory


def test_search_nonce_finds_base64(tmp_path):
    encoded = base64.b64encode(NONCE.encode()).decode()
    blobs = {"body": encoded}

    assert search_nonce(blobs, NONCE) == ["body"]


def test_search_nonce_ignores_different_nonce_base64():
    encoded = base64.b64encode(OTHER.encode()).decode()
    blobs = {"body": encoded}

    assert search_nonce(blobs, NONCE) == []


def test_search_nonce_finds_hex():
    blobs = {"dns": NONCE.encode().hex()}

    assert search_nonce(blobs, NONCE) == ["dns"]


def test_search_nonce_finds_url_encoded():
    blobs = {"http": urllib.parse.quote(NONCE, safe="")}

    assert search_nonce(blobs, NONCE) == ["http"]
