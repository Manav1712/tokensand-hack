"""Only policy.py may construct a Verdict. Tests may still build values."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "skill_warden"

_MODELS = "skill_warden.models"


def _dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        if base is None:
            return None
        return f"{base}.{node.attr}"
    return None


def _is_models(node: ast.AST, models_exprs: set[str]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in models_exprs
    dotted = _dotted(node)
    return dotted in models_exprs or dotted == _MODELS


def _is_verdict_expr(node: ast.AST, verdict_names: set[str], models_exprs: set[str]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in verdict_names
    if isinstance(node, ast.Attribute) and node.attr == "Verdict":
        return _is_models(node.value, models_exprs)
    return False


def _import_bindings(tree: ast.AST) -> tuple[set[str], set[str]]:
    verdict_names: set[str] = set()
    models_exprs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            from_models = node.module == _MODELS or (node.level == 1 and node.module == "models")
            if from_models:
                for alias in node.names:
                    bound = alias.asname or alias.name
                    if alias.name in {"Verdict", "*"}:
                        verdict_names.add("Verdict" if alias.name == "*" else bound)
            if node.module == "skill_warden" and node.level == 0:
                for alias in node.names:
                    if alias.name == "models":
                        models_exprs.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == _MODELS:
                    models_exprs.add(alias.asname or alias.name)
    return verdict_names, models_exprs


def _propagate_aliases(
    tree: ast.AST, verdict_names: set[str], models_exprs: set[str]
) -> None:
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            targets: list[ast.expr]
            value: ast.expr
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if not isinstance(target, ast.Name):
                    continue
                targets = [target]
                value = node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if node.value is None:
                    continue
                targets = [node.target]
                value = node.value
            else:
                continue
            name = targets[0].id
            if name not in verdict_names and _is_verdict_expr(value, verdict_names, models_exprs):
                verdict_names.add(name)
                changed = True
            if name not in models_exprs and _is_models(value, models_exprs):
                models_exprs.add(name)
                changed = True


def verdict_constructions(source: str) -> list[int]:
    """Line numbers of calls that build skill_warden.models.Verdict."""
    tree = ast.parse(source)
    verdict_names, models_exprs = _import_bindings(tree)
    _propagate_aliases(tree, verdict_names, models_exprs)
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_verdict_expr(
            node.func, verdict_names, models_exprs
        ):
            lines.append(node.lineno)
    return sorted(lines)


def test_imported_call_is_a_construction():
    source = "from skill_warden.models import Verdict\nVerdict('BLOCK', 'x')\n"

    assert verdict_constructions(source) == [2]


def test_import_alias_is_a_construction():
    source = "from skill_warden.models import Verdict as V\nV('ALLOW', 'clean')\n"

    assert verdict_constructions(source) == [2]


def test_qualified_call_is_a_construction():
    source = "import skill_warden.models\nskill_warden.models.Verdict('ASK', 'medium_only')\n"

    assert verdict_constructions(source) == [2]


def test_isinstance_and_class_are_not_constructions():
    source = (
        "from skill_warden.models import Verdict\n"
        "class Box:\n"
        "    verdict: Verdict\n"
        "    def check(self) -> bool:\n"
        "        return isinstance(self.verdict, Verdict)\n"
    )

    assert verdict_constructions(source) == []


def test_policy_constructs_verdict():
    assert verdict_constructions((SRC / "policy.py").read_text(encoding="utf-8"))


def test_only_policy_constructs_verdict():
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if path.name == "policy.py":
            continue
        lines = verdict_constructions(path.read_text(encoding="utf-8"))
        if lines:
            relative = path.relative_to(ROOT).as_posix()
            offenders.append(f"{relative}: {', '.join(str(line) for line in lines)}")

    assert offenders == []
