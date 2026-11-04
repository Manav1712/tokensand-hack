from hypothesis import given
from hypothesis import strategies as st

from skill_warden.redact import contains_secret, excerpt, redact

TOKEN = "FAKE-CANARY-TOKEN"


def test_contains_secret_ignores_values_of_three_characters_or_fewer():
    assert contains_secret("abc token", ["ab", "token"])
    assert not contains_secret("abc", ["ab", "abc"])


def test_contains_secret_treats_four_characters_as_live():
    assert contains_secret("xxabcdxx", ["abcd"])
    assert not contains_secret("xxabcxx", ["abcd"])


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


def test_redact_keeps_secrets_of_three_characters_or_fewer():
    assert redact("abc token", ["abc", "token"]) == "abc [redacted]"


def test_redact_removes_a_secret_inside_the_placeholder():
    secret = "[red"

    assert redact(f"see {secret} here", [secret]) == "see  here"


def test_redact_removes_a_secret_rebuilt_beside_the_placeholder():
    # "[redacted]" ends in "d]". Replacing this secret leaves "d]" + "AB".
    secret = "d]AB"

    assert redact(secret + "AB", [secret]) == "AB"


def test_redact_replaces_the_longest_secret_first():
    # Reverse alphabet puts the short "SECR" first; length order must win.
    assert redact("AAAASECRET", ["SECR", "AAAASECRET"]) == "[redacted]"


def test_redact_deletes_the_longest_secret_when_the_placeholder_rebuilds_one():
    assert redact("d]ABABzzzz", ["d]AB", "zzzz"]) == "AB[redacted]"


def test_redact_deletes_the_first_rebuilt_secret_occurrence():
    assert redact("d]ABxd]ABAB", ["d]AB"]) == "xAB"


@given(
    prefix=st.text(max_size=300),
    suffix=st.text(max_size=300),
    secret=st.text(min_size=4, max_size=40),
)
def test_raw_secret_does_not_survive_redact_then_excerpt(prefix, suffix, secret):
    # §16.3 redaction, for a raw secret. Excerpt hides nothing redact left behind.
    redacted = redact(prefix + secret + suffix, [secret])

    assert secret not in redacted
    assert secret not in excerpt(redacted)
