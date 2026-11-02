_MARKER = "[redacted]"


def contains_secret(text: str, secrets: list[str]) -> bool:
    return any(len(secret) > 3 and secret in text for secret in secrets)


def redact(text: str, secrets: list[str]) -> str:
    """Remove every secret of 4 characters or more.

    The placeholder is dropped when it would contain a secret. Replacement can
    also rebuild a secret at the join, so that case deletes one copy and retries.
    """
    live = [secret for secret in secrets if len(secret) > 3]
    marker = "" if any(secret in _MARKER for secret in live) else _MARKER
    while any(secret in text for secret in live):
        updated = text
        for secret in sorted(live, key=len, reverse=True):
            updated = updated.replace(secret, marker)
        if any(secret in updated for secret in live):
            secret = max((item for item in live if item in text), key=len)
            at = text.find(secret)
            text = text[:at] + text[at + len(secret):]
        else:
            text = updated
    return text


def excerpt(text: str, limit: int = 200) -> str:
    return text[:limit]
