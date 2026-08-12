"""Reject client-authoritative monetary fields in executable order callers."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


EXECUTABLE_ROOTS = (
    Path(".github/workflows"),
    Path("postman"),
    Path("k6-tests"),
    Path("frontend/src"),
    Path("scripts"),
)
EXECUTABLE_SUFFIXES = {".yml", ".yaml", ".json", ".js", ".ts", ".tsx", ".sh", ".ps1"}
FORBIDDEN_FIELD = re.compile(
    r"(?P<quote>['\"]?)(?P<field>unitPrice|effectivePrice|price|total|discount)(?P=quote)\s*:",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    field: str


def _candidate_files(root: Path):
    for relative_root in EXECUTABLE_ROOTS:
        directory = root / relative_root
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in EXECUTABLE_SUFFIXES:
                continue
            if path.name == Path(__file__).name or ".test." in path.name or ".spec." in path.name:
                continue
            yield path


def find_violations(root: Path) -> list[Violation]:
    violations: list[Violation] = []
    for path in _candidate_files(root):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        order_lines = [index for index, line in enumerate(lines) if "/v1/orders" in line]
        seen: set[tuple[int, str]] = set()
        for order_line in order_lines:
            start = max(0, order_line - 8)
            end = min(len(lines), order_line + 9)
            for index in range(start, end):
                for match in FORBIDDEN_FIELD.finditer(lines[index]):
                    key = (index, match.group("field"))
                    if key in seen:
                        continue
                    seen.add(key)
                    violations.append(
                        Violation(
                            path=path.relative_to(root),
                            line=index + 1,
                            field=match.group("field"),
                        )
                    )
    return sorted(violations, key=lambda item: (str(item.path), item.line, item.field))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reject monetary fields in executable SmartRetailX order requests."
    )
    parser.add_argument("root", nargs="?", default=".", help="repository root")
    args = parser.parse_args(argv)
    violations = find_violations(Path(args.root).resolve())
    if violations:
        for violation in violations:
            print(f"FAIL: {violation.path}:{violation.line}: forbidden order field {violation.field}")
        return 1
    print("PASS: executable order callers send identifiers and quantities only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
