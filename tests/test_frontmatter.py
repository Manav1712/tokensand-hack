import json
from pathlib import Path

import pytest
import yaml
from hypothesis import given
from hypothesis import strategies as st

from skill_warden.frontmatter import parse_lines, read_frontmatter
from skill_warden.intake import load_skill
from skill_warden.models import Severity

_RESERVED = {"y", "n", "yes", "no", "true", "false", "on", "off", "null"}
_TOKEN = st.from_regex(r"[A-Za-z][A-Za-z0-9-]{0,12}", fullmatch=True).filter(
    lambda value: value.casefold() not in _RESERVED
)
_WORDS = (
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=1, max_size=40)
    .map(lambda value: " ".join(value.split()))
    .filter(lambda value: len(value) > 0 and value.casefold() not in _RESERVED)
)


def _ids(text: str) -> set[str]:
    return {finding.rule_id for finding in read_frontmatter(text).findings}


def _document(
    name: str,
    description: str,
    install: str | None,
    bins: list[str] | None,
    style: str,
) -> str:
    def field(value: str) -> str:
        if style == "quoted":
            return json.dumps(value)
        return value

    lines = ["---", f"name: {field(name)}"]
    if style == "block":
        lines.append("description: |")
        lines.append(f"  {description}")
    else:
        lines.append(f"description: {field(description)}")
    if install is not None or bins is not None:
        lines.append("metadata:")
        lines.append("  openclaw:")
        if install is not None:
            lines.append(f"    install: {field(install)}")
        if bins is not None:
            lines.append("    requires:")
            lines.append("      bins:")
            for item in bins:
                lines.append(f"        - {field(item)}")
    lines.extend(["---", "body"])
    return "\n".join(lines) + "\n"


def test_agreement_uses_the_frontmatter_name() -> None:
    text = """---
name: clean-date
description: Format a date.
metadata:
  openclaw:
    install: echo hello
    requires:
      bins:
        - curl
        - git
---
"""
    result = read_frontmatter(text)

    assert result.findings == ()
    assert result.name == "clean-date"


def test_literal_and_folded_blocks_agree() -> None:
    literal = "---\nname: demo\ndescription: |\n  hello\n  there\n---\n"
    folded = "---\nname: demo\ndescription: >\n  hello\n  there\n---\n"
    stripped = "---\nname: demo\ndescription: |-\n  hello\n  there\n---\n"

    assert read_frontmatter(literal).findings == ()
    assert read_frontmatter(folded).findings == ()
    assert read_frontmatter(stripped).findings == ()


def test_name_disagreement_is_a_mismatch() -> None:
    text = "---\nname: yes\ndescription: hi\n---\n"

    result = read_frontmatter(text)

    assert len(result.findings) == 1
    assert result.findings[0].rule_id == "frontmatter_mismatch"
    assert result.findings[0].severity is Severity.MEDIUM
    assert result.findings[0].file == "SKILL.md"


def test_install_disagreement_is_high() -> None:
    text = "---\nname: demo\ndescription: hi\nmetadata:\n  openclaw:\n    install: yes\n---\n"

    result = read_frontmatter(text)

    assert [item.rule_id for item in result.findings] == ["frontmatter_mismatch_install"]
    assert result.findings[0].severity is Severity.HIGH
    assert result.name == "demo"


def test_required_binary_disagreement_is_high() -> None:
    text = (
        "---\nname: demo\ndescription: hi\nmetadata:\n  openclaw:\n"
        "    requires:\n      bins:\n        - yes\n---\n"
    )

    result = read_frontmatter(text)

    assert [item.rule_id for item in result.findings] == ["frontmatter_mismatch_install"]
    assert "bins" in result.findings[0].excerpt


def test_flow_collection_in_a_compared_field_is_complex() -> None:
    text = "---\nname: [one, two]\ndescription: hi\n---\n"

    result = read_frontmatter(text)

    assert [item.rule_id for item in result.findings] == ["frontmatter_complex"]
    assert result.findings[0].severity is Severity.MEDIUM


def test_anchor_alias_and_tag_are_complex() -> None:
    anchor = "---\nname: &mark demo\ndescription: hi\n---\n"
    alias = "---\nmark: &mark demo\nname: *mark\ndescription: hi\n---\n"
    tag = "---\nname: !!str demo\ndescription: hi\n---\n"

    assert _ids(anchor) == {"frontmatter_complex"}
    assert _ids(alias) == {"frontmatter_complex"}
    assert _ids(tag) == {"frontmatter_complex"}


def test_duplicate_key_is_not_a_silent_pick() -> None:
    text = "---\nname: one\nname: two\ndescription: hi\n---\n"

    result = read_frontmatter(text)

    assert [item.rule_id for item in result.findings] == ["frontmatter_complex"]
    assert result.name == "two"


def test_uncompared_flow_is_ignored() -> None:
    text = "---\nname: demo\ndescription: hi\nextra: [1, 2]\n---\n"

    assert read_frontmatter(text).findings == ()


def test_python_object_tag_never_builds_an_object(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("yaml.load")

    monkeypatch.setattr(yaml, "load", refuse)
    text = "---\nname: !!python/object/apply:os.system ['echo pwned']\ndescription: hi\n---\n"

    result = read_frontmatter(text)

    assert [item.rule_id for item in result.findings] == ["frontmatter_unparseable"]
    assert result.findings[0].severity is Severity.HIGH
    assert result.name is None


def test_unresolved_alias_is_unparseable() -> None:
    text = "---\nname: *missing\ndescription: hi\n---\n"

    result = read_frontmatter(text)

    assert [item.rule_id for item in result.findings] == ["frontmatter_unparseable"]
    assert result.findings[0].severity is Severity.HIGH
    assert result.name is None


def test_missing_frontmatter_is_invalid() -> None:
    result = read_frontmatter("# no frontmatter\nhello\n")

    assert [item.rule_id for item in result.findings] == ["frontmatter_invalid"]
    assert result.findings[0].severity is Severity.INFO
    assert result.name is None


def test_missing_description_is_invalid() -> None:
    result = read_frontmatter("---\nname: demo\n---\n")

    assert [item.rule_id for item in result.findings] == ["frontmatter_invalid"]
    assert result.name == "demo"


def test_whitespace_only_difference_agrees() -> None:
    text = '---\nname: "demo"\ndescription: "hello   world"\n---\n'

    result = read_frontmatter(text)

    assert result.findings == ()
    assert result.name == "demo"


def test_load_skill_uses_the_frontmatter_name(tmp_path: Path) -> None:
    skill = tmp_path / "folder"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: date-helper\ndescription: Format a date.\n---\nhello\n",
        encoding="utf-8",
    )

    loaded = load_skill(skill)

    assert loaded.record.name == "date-helper"
    assert loaded.findings == ()


def test_load_skill_falls_back_to_the_directory_name(tmp_path: Path) -> None:
    skill = tmp_path / "folder"
    skill.mkdir()
    (skill / "SKILL.md").write_text("hello\n", encoding="utf-8")

    loaded = load_skill(skill)

    assert loaded.record.name == "folder"
    assert [item.rule_id for item in loaded.findings] == ["frontmatter_invalid"]


@given(
    name=_TOKEN,
    description=_WORDS,
    install=st.one_of(st.none(), _TOKEN),
    bins=st.one_of(st.none(), st.lists(_TOKEN, max_size=3)),
    style=st.sampled_from(["plain", "quoted", "block"]),
)
def test_subset_readings_agree(
    name: str,
    description: str,
    install: str | None,
    bins: list[str] | None,
    style: str,
) -> None:
    result = read_frontmatter(_document(name, description, install, bins, style))

    assert result.findings == ()
    assert result.name == name


@given(name=_TOKEN, other=_TOKEN, kind=st.sampled_from(["duplicate", "flow", "anchor", "alias"]))
def test_generated_complex_fields_are_not_silent(name: str, other: str, kind: str) -> None:
    if kind == "duplicate":
        body = f"name: {name}\nname: {other}\ndescription: hi\n"
    elif kind == "flow":
        body = f"name: [{name}, {other}]\ndescription: hi\n"
    elif kind == "anchor":
        body = f"name: &mark {name}\ndescription: hi\n"
    else:
        body = f"mark: &mark {name}\nname: *mark\ndescription: hi\n"
    result = read_frontmatter(f"---\n{body}---\n")

    assert {item.rule_id for item in result.findings} & {
        "frontmatter_complex",
        "frontmatter_mismatch",
        "frontmatter_mismatch_install",
    }


@given(st.text(max_size=200))
def test_line_parser_never_raises(text: str) -> None:
    result = parse_lines(text)
    assert result.error is None or isinstance(result.error, str)


@given(st.text(max_size=300))
def test_read_frontmatter_never_raises(text: str) -> None:
    result = read_frontmatter(text)
    assert isinstance(result.findings, tuple)
