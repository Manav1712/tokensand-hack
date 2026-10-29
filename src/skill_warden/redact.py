def contains_secret(text: str, secrets: list[str]) -> bool:
    return any(len(secret) > 3 and secret in text for secret in secrets)


def redact(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if len(secret) <= 3:
            continue
        text = text.replace(secret, "[redacted]")
    return text


def excerpt(text: str, limit: int = 200) -> str:
    return text[:limit]
