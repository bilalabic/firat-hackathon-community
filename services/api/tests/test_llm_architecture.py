"""Application data never reaches an LLM (D-22, D-23): import-closure check.

Roots: every module under `fhc_api/community` and `fhc_api/admin_bot`, plus every module whose
source (SQL included) mentions `community_applications` or `team_applications`. The transitive
closure of their imports (absolute, relative, parent packages, and string literals naming an
`fhc_api.*` module, e.g. for `importlib.import_module`) must not contain `fhc_api.llm` or
`fhc_api.importing` (which calls the LLM).
"""

import ast
import re
from collections import deque
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "fhc_api"
ROOT_PACKAGES = ("fhc_api.community", "fhc_api.admin_bot")
APPLICATION_TABLES = ("community_applications", "team_applications")
FORBIDDEN = ("fhc_api.llm", "fhc_api.importing")
_MODULE_LITERAL_RE = re.compile(r"fhc_api(?:\.[A-Za-z_]\w*)+")


def module_name(path: Path, src: Path = SRC) -> str:
    parts = list(path.relative_to(src).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(["fhc_api", *parts])


def index_modules(src: Path = SRC) -> dict[str, Path]:
    return {module_name(path, src): path for path in sorted(src.rglob("*.py"))}


def referenced_names(source: str, module: str, is_package: bool) -> set[str]:
    """Dotted names a module imports or names in string literals (not yet resolved)."""
    package = module.split(".") if is_package else module.split(".")[:-1]
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = package[: len(package) - node.level + 1] if node.level else []
            target = ".".join([*base, *([node.module] if node.module else [])])
            names.add(target)
            names.update(f"{target}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            names.update(_MODULE_LITERAL_RE.findall(node.value))
    return names


def resolve(name: str, modules: dict[str, Path]) -> set[str]:
    """Known modules a dotted name loads: the name (or its longest module prefix, for
    `from a.b import attr`) and every parent package."""
    parts = name.split(".")
    return {".".join(parts[:i]) for i in range(1, len(parts) + 1)} & modules.keys()


def import_closure(roots: set[str], modules: dict[str, Path]) -> dict[str, str | None]:
    """Every module reachable from `roots`, mapped to the module that first imported it."""
    parent: dict[str, str | None] = dict.fromkeys(roots)
    queue = deque(sorted(roots))
    while queue:
        current = queue.popleft()
        path = modules[current]
        source = path.read_text(encoding="utf-8")
        for name in referenced_names(source, current, path.name == "__init__.py"):
            for target in resolve(name, modules):
                if target not in parent:
                    parent[target] = current
                    queue.append(target)
    return parent


def chain(module: str, parent: dict[str, str | None]) -> str:
    links = [module]
    while (previous := parent[links[-1]]) is not None:
        links.append(previous)
    return " <- ".join(links)


def application_roots(modules: dict[str, Path]) -> set[str]:
    roots = {m for m in modules if m.startswith(tuple(f"{p}." for p in ROOT_PACKAGES))}
    roots |= {m for m in modules if m in ROOT_PACKAGES}
    roots |= {
        name
        for name, path in modules.items()
        if any(table in path.read_text(encoding="utf-8") for table in APPLICATION_TABLES)
    }
    return roots


def _forbidden(module: str) -> bool:
    return any(module == f or module.startswith(f"{f}.") for f in FORBIDDEN)


def test_application_code_never_reaches_the_llm() -> None:
    modules = index_modules()
    roots = application_roots(modules)
    assert {"fhc_api.community.service", "fhc_api.admin_bot.handlers"} <= roots
    closure = import_closure(roots, modules)
    leaks = sorted(chain(m, closure) for m in closure if _forbidden(m))
    assert not leaks, "application code reaches the LLM:\n" + "\n".join(leaks)


def test_scanner_follows_every_import_form(tmp_path: Path) -> None:
    src = tmp_path / "fhc_api"
    files = {
        "__init__.py": "",
        "community/__init__.py": "",
        "community/a.py": "from . import b\n",
        "community/b.py": "from ..common import c\n",
        "common/__init__.py": "",
        "common/c.py": "import importlib\nimportlib.import_module('fhc_api.llm.openai')\n",
        "llm/__init__.py": "",
        "llm/openai.py": "",
        "other.py": "from fhc_api.llm import openai\n",
    }
    for relative, text in files.items():
        (src / relative).parent.mkdir(parents=True, exist_ok=True)
        (src / relative).write_text(text, encoding="utf-8")
    modules = index_modules(src)

    closure = import_closure({"fhc_api.community.a"}, modules)

    assert "fhc_api.llm.openai" in closure
    assert chain("fhc_api.llm.openai", closure).endswith(
        "fhc_api.common.c <- fhc_api.community.b <- fhc_api.community.a"
    )
    assert "fhc_api.other" not in closure
    assert resolve("fhc_api.llm.openai.OpenAIProvider", modules) == {
        "fhc_api",
        "fhc_api.llm",
        "fhc_api.llm.openai",
    }
