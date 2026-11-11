class SkillTreeError(Exception):
    pass


class NoSkillError(Exception):
    """A path does not contain a skill. The message never includes that path."""

    def __init__(self) -> None:
        super().__init__("no skill")


class BudgetError(Exception):
    pass


class MemoryCapError(Exception):
    pass


class RedactionError(Exception):
    pass


class ReaderInvalid(Exception):
    pass


class SinkError(Exception):
    pass


class JailError(Exception):
    pass
