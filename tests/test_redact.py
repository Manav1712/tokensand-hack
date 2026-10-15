from skill_warden.redact import excerpt, redact

TOKEN = "FAKE-CANARY-TOKEN"


def test_redact_removes_secret():
    text = f"prefix {TOKEN} suffix"

    assert TOKEN not in redact(text, [TOKEN])


def test_excerpt_caps_length():
    assert len(excerpt("x" * 500)) == 200


def test_excerpt_redacts_before_cut():
    text = ("x" * 190) + TOKEN

    result = excerpt(redact(text, [TOKEN]), 200)

    assert TOKEN not in result
    assert "FAKE" not in result
    assert len(result) <= 200
