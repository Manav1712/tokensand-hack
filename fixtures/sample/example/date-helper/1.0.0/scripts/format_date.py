from datetime import date


def format_date(value: date) -> str:
    return value.strftime("%Y-%m-%d")
