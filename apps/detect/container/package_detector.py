"""Package upstream execution functions without embedding sample camera defaults."""

import ast
from pathlib import Path

FUNCTIONS = {"validate_arguments", "extract_detections", "run"}
ASSIGNMENTS = {"EXIT_SUCCESS", "logger"}


def package(source: Path, destination: Path) -> None:
    """Preserve execution ASTs while omitting CLI defaults and sample connection strings."""
    tree = ast.parse(source.read_text(encoding="utf-8"))
    selected: list[ast.stmt] = []
    found: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            selected.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS:
            selected.append(node)
            found.add(node.name)
        elif isinstance(node, ast.Assign) and all(
            isinstance(target, ast.Name) and target.id in ASSIGNMENTS for target in node.targets
        ):
            selected.append(node)
            found.update(target.id for target in node.targets if isinstance(target, ast.Name))
    if found != FUNCTIONS | ASSIGNMENTS:
        raise ValueError("Detector interface changed; review the container packaging allowlist.")
    output = ast.unparse(ast.Module(body=selected, type_ignores=[])) + "\n"
    if "rtsp://" in output.lower() or "rtsps://" in output.lower():
        raise ValueError(
            "Packaged execution code contains a connection literal; review before build."
        )
    destination.write_text(output, encoding="utf-8")


if __name__ == "__main__":
    package(Path("/source/rtsp_yolo.py"), Path("/packaged/rtsp_yolo.py"))
