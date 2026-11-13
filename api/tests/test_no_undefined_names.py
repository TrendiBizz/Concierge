"""Every module must have every global name it uses actually bound.

`inbound_email` called `email_signature.parse_signature` without importing it. Nothing failed until a
real email arrived, and then every inbound email raised NameError and the API answered 400 — an
outage invisible to the test suite and to the healthcheck, which only checks configuration.

This walks each module's syntax tree: names loaded inside functions must be bound at module level,
imported, a parameter/local, or a builtin. It is a cheap stand-in for pyflakes, which is not in the
runtime image.
"""
import ast
import builtins
import pathlib

APP = pathlib.Path(__file__).resolve().parents[1] / "app"


def _bound_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
        elif isinstance(node, (ast.comprehension,)):
            pass
    return names


def _undefined(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text())
    bound = _bound_names(tree) | set(dir(builtins)) | {"__name__", "__file__", "__doc__"}
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id not in bound:
            problems.append(f"{path.name}:{node.lineno}: {node.id}")
    return problems


def test_no_module_uses_an_undefined_global():
    problems = []
    for path in sorted(APP.glob("*.py")):
        problems.extend(_undefined(path))
    assert not problems, "names used but never bound:\n  " + "\n  ".join(problems)
