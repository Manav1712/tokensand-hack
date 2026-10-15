def redact(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if len(secret) <= 3:
            continue
        text = text.replace(secret, "[redacted]")
    return text


def excerpt(text: str, limit: int = 200) -> str:
    return text[:limit]
