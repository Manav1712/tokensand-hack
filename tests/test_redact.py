from skill_warden.redact import contains_secret, excerpt, redact

TOKEN = "FAKE-CANARY-TOKEN"


def test_contains_secret_ignores_values_of_three_characters_or_fewer():
    assert contains_secret("abc token", ["ab", "token"])
    assert not contains_secret("abc", ["ab", "abc"])


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
