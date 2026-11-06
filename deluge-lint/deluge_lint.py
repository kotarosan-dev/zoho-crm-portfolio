"""Heuristic linter for Zoho Deluge scripts.

This is NOT a Deluge compiler or a full parser. It is a set of shallow,
high-precision checks for common mistakes in hand-written or generated
Deluge code. Every check except the structural ones (DL001-DL003, DL020)
runs on a "masked" copy of the source in which string literals and
comments are replaced by spaces (line and column positions are kept), so
text inside strings or comments never triggers a rule. DL020 looks at
string literals in the raw source but ignores those inside comments.
DL013 and DL014 are about comments themselves and use the comment
positions recorded while masking.

Rules
-----

======  =======  ====================================================
Code    Level    What it catches
======  =======  ====================================================
DL001   error    Unbalanced or mismatched ( ) { } [ ]
DL002   error    String literal not closed on the same line
DL003   error    Block comment ``/*`` without ``*/``
DL010   error    C-style ``for (...)`` loop (Deluge has only ``for each``)
DL011   error    ``while (...)`` loop (Deluge has no while loop)
DL012   error    Ternary operator ``cond ? a : b``
DL013   warning  Comment inside an ``invokeurl [ ... ]`` block
DL014   info     End-of-line comment (code followed by ``//``)
DL015   warning  Single-line ``if (...) x = y;`` without braces
DL016   warning  Call on the avoid list (getType, instanceof, isList,
                 .join, .repeat, .keySet, .compareTo, .toint)
DL020   warning  Hardcoded 18-19 digit Zoho record ID in a string
======  =======  ====================================================

Library use::

    from deluge_lint import lint
    result = lint(source)
    if result.has_errors:
        ...
    print(result.to_report())

Command line::

    python deluge_lint.py [--format text|json] <file-or-dir> [...]
    python deluge_lint.py -          # read stdin

Directories are scanned recursively for ``*.dg``. The exit code is 1 if
any error was found, 2 if a path could not be read, otherwise 0.
"""

from __future__ import annotations

import argparse
import bisect
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Literal, Optional, Tuple

__all__ = ["LintIssue", "LintResult", "lint", "main"]

Severity = Literal["error", "warning", "info"]


@dataclass
class LintIssue:
    line: int
    column: int
    severity: Severity
    code: str
    message: str

    def format(self) -> str:
        return (
            f"L{self.line}:C{self.column} {self.severity.upper()} "
            f"[{self.code}] {self.message}"
        )

    def to_dict(self) -> dict:
        return {
            "line": self.line,
            "column": self.column,
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }


@dataclass
class LintResult:
    issues: List[LintIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    @property
    def info_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "info")

    def to_report(self) -> str:
        if not self.issues:
            return "OK: no issues found."
        lines = [i.format() for i in self.issues]
        lines.append(
            f"--- {self.error_count} errors, {self.warning_count} warnings, "
            f"{self.info_count} infos ---"
        )
        return "\n".join(lines)


# ---------------------------------------------------------------------- #
# public entry
# ---------------------------------------------------------------------- #

def lint(source: str) -> LintResult:
    """Lint Deluge source text and return a LintResult."""
    masked, comments, issues = _mask(source)
    index = _LineIndex(source)

    issues.extend(_check_balanced(masked, index))
    issues.extend(_check_c_for(masked, index))
    issues.extend(_check_while(masked, index))
    issues.extend(_check_ternary(masked, index))
    issues.extend(_check_invokeurl_comments(masked, comments, index))
    issues.extend(_check_eol_comments(comments, index))
    issues.extend(_check_braceless_if(masked, index))
    issues.extend(_check_avoid_list(masked, index))
    issues.extend(_check_hardcoded_ids(source, comments, index))

    issues.sort(key=lambda i: (i.line, i.column, i.code))
    return LintResult(issues=issues)


# ---------------------------------------------------------------------- #
# helpers
# ---------------------------------------------------------------------- #

class _LineIndex:
    """Map a character offset to a 1-based (line, column)."""

    def __init__(self, source: str) -> None:
        self._starts = [0]
        for m in re.finditer("\n", source):
            self._starts.append(m.end())

    def pos(self, offset: int) -> Tuple[int, int]:
        line = bisect.bisect_right(self._starts, offset)
        return line, offset - self._starts[line - 1] + 1


@dataclass
class _Comment:
    start: int
    end: int
    kind: str  # "line" or "block"
    trailing: bool  # code precedes it on the same line


def _issue(index: _LineIndex, offset: int, severity: Severity,
           code: str, message: str) -> LintIssue:
    line, col = index.pos(offset)
    return LintIssue(line, col, severity, code, message)


# ---------------------------------------------------------------------- #
# masking scanner (string/comment-aware)
# ---------------------------------------------------------------------- #

def _mask(source: str) -> Tuple[str, List[_Comment], List[LintIssue]]:
    """Return (masked source, comments, DL002/DL003 issues).

    Strings and comments become spaces; newlines are kept so offsets,
    lines and columns of the remaining code are unchanged.
    """
    n = len(source)
    out = list(source)
    comments: List[_Comment] = []
    issues: List[LintIssue] = []
    index = _LineIndex(source)

    def blank(a: int, b: int) -> None:
        for k in range(a, b):
            if out[k] not in "\r\n":
                out[k] = " "

    has_code = False
    i = 0
    while i < n:
        ch = source[i]

        if ch == "\n":
            has_code = False
            i += 1
            continue
        if ch in " \t\r":
            i += 1
            continue

        if source.startswith("//", i):
            end = source.find("\n", i)
            if end == -1:
                end = n
            comments.append(_Comment(i, end, "line", has_code))
            blank(i, end)
            i = end
            continue

        if source.startswith("/*", i):
            end = source.find("*/", i + 2)
            if end == -1:
                issues.append(_issue(index, i, "error", "DL003",
                                     "unterminated block comment"))
                end = n
            else:
                end += 2
            comments.append(_Comment(i, end, "block", has_code))
            blank(i, end)
            i = end
            continue

        if ch == '"' or ch == "'":
            has_code = True
            j = i + 1
            closed = False
            while j < n:
                c = source[j]
                if c == "\\" and j + 1 < n and source[j + 1] != "\n":
                    j += 2
                    continue
                if c == ch:
                    closed = True
                    break
                if c == "\n":
                    break
                j += 1
            if closed:
                blank(i, j + 1)
                i = j + 1
            else:
                issues.append(_issue(index, i, "error", "DL002",
                                     f"unterminated {ch}-string literal"))
                blank(i, j)
                i = j
            continue

        has_code = True
        i += 1

    return "".join(out), comments, issues


# ---------------------------------------------------------------------- #
# checks
# ---------------------------------------------------------------------- #

_PAIRS = {")": "(", "]": "[", "}": "{"}
_OPENS = "([{"


def _check_balanced(masked: str, index: _LineIndex) -> List[LintIssue]:
    issues: List[LintIssue] = []
    stack: List[Tuple[str, int]] = []

    for off, ch in enumerate(masked):
        if ch in _OPENS:
            stack.append((ch, off))
        elif ch in _PAIRS:
            if not stack:
                issues.append(_issue(index, off, "error", "DL001",
                                     f"unmatched closing '{ch}'"))
            elif stack[-1][0] != _PAIRS[ch]:
                top_ch, top_off = stack.pop()
                tl, tc = index.pos(top_off)
                issues.append(_issue(
                    index, off, "error", "DL001",
                    f"mismatched delimiter: found '{ch}' but expected "
                    f"closer for '{top_ch}' opened at L{tl}:C{tc}",
                ))
            else:
                stack.pop()

    for ch, off in stack:
        issues.append(_issue(index, off, "error", "DL001",
                             f"unclosed '{ch}' opened here"))
    return issues


_C_FOR = re.compile(r"(?<![\w.])for\s*\(", re.IGNORECASE)


def _check_c_for(masked: str, index: _LineIndex) -> List[LintIssue]:
    return [
        _issue(index, m.start(), "error", "DL010",
               "C-style for loop is not valid Deluge; use "
               "'for each item in list'")
        for m in _C_FOR.finditer(masked)
    ]


_WHILE = re.compile(r"(?<![\w.])while\s*\(", re.IGNORECASE)


def _check_while(masked: str, index: _LineIndex) -> List[LintIssue]:
    return [
        _issue(index, m.start(), "error", "DL011",
               "Deluge has no while loop; use 'for each' over a list")
        for m in _WHILE.finditer(masked)
    ]


def _check_ternary(masked: str, index: _LineIndex) -> List[LintIssue]:
    return [
        _issue(index, m.start(), "error", "DL012",
               "ternary operator is not supported; use an if/else block")
        for m in re.finditer(r"\?", masked)
    ]


_INVOKEURL = re.compile(r"(?<![\w.])invokeurl\s*\[", re.IGNORECASE)


def _check_invokeurl_comments(masked: str, comments: List[_Comment],
                              index: _LineIndex) -> List[LintIssue]:
    issues: List[LintIssue] = []
    for m in _INVOKEURL.finditer(masked):
        open_off = m.end() - 1
        depth = 0
        end = len(masked)
        for off in range(open_off, len(masked)):
            c = masked[off]
            if c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    end = off
                    break
        for c in comments:
            if open_off < c.start < end:
                issues.append(_issue(
                    index, c.start, "warning", "DL013",
                    "comment inside an invokeurl block can break saving; "
                    "move it outside the block",
                ))
    return issues


def _check_eol_comments(comments: List[_Comment],
                        index: _LineIndex) -> List[LintIssue]:
    return [
        _issue(index, c.start, "info", "DL014",
               "end-of-line comment; put the comment on its own line")
        for c in comments
        if c.kind == "line" and c.trailing
    ]


_IF = re.compile(r"(?<![\w.])if\s*\(", re.IGNORECASE)
_ELSE_END = re.compile(r"(?<![\w.])else$", re.IGNORECASE)


def _check_braceless_if(masked: str, index: _LineIndex) -> List[LintIssue]:
    issues: List[LintIssue] = []
    for m in _IF.finditer(masked):
        prefix = masked[:m.start()].rstrip()
        # Only statement-level ifs: skip the built-in if(cond, a, b)
        # expression form, as in "x = if(a, 1, 2);".
        if prefix and prefix[-1] not in "{};" and not _ELSE_END.search(prefix):
            continue

        depth = 0
        close = -1
        for off in range(m.end() - 1, len(masked)):
            c = masked[off]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    close = off
                    break
        if close == -1:
            continue

        line_end = masked.find("\n", close)
        if line_end == -1:
            line_end = len(masked)
        rest = masked[close + 1:line_end].strip()
        if rest and not rest.startswith("{"):
            issues.append(_issue(
                index, m.start(), "warning", "DL015",
                "single-line 'if' without braces; wrap the body in { }",
            ))
    return issues


# (display name, regex, hint)
_AVOID: List[Tuple[str, "re.Pattern[str]", Optional[str]]] = [
    ("getType(", re.compile(r"(?<![\w])getType\s*\("), None),
    ("instanceof", re.compile(r"(?<![\w])instanceof(?![\w])"), None),
    ("isList(", re.compile(r"(?<![\w])isList\s*\("), None),
    (".join(", re.compile(r"\.\s*join\s*\("), 'toString(",")'),
    (".repeat(", re.compile(r"\.\s*repeat\s*\("), None),
    (".keySet(", re.compile(r"\.\s*keySet\s*\("), "keys()"),
    (".compareTo(", re.compile(r"\.\s*compareTo\s*\("), None),
    (".toint(", re.compile(r"\.\s*toint\s*\(", re.IGNORECASE), "toLong()"),
]


def _check_avoid_list(masked: str, index: _LineIndex) -> List[LintIssue]:
    issues: List[LintIssue] = []
    for name, pattern, hint in _AVOID:
        for m in pattern.finditer(masked):
            msg = (f"'{name}' is on the avoid list "
                   "(not a reliable Deluge built-in)")
            if hint:
                msg += f"; try {hint}"
            issues.append(_issue(index, m.start(), "warning", "DL016", msg))
    return issues


# Zoho record IDs are 18-19 digit numeric strings. Warn when one appears
# as a hardcoded string literal; prefer a lookup or a config value.
_HARDCODED_ID = re.compile(r'(["\'])(\d{18,19})\1')


def _check_hardcoded_ids(source: str, comments: List[_Comment],
                         index: _LineIndex) -> List[LintIssue]:
    return [
        _issue(index, m.start(), "warning", "DL020",
               f"hardcoded Zoho-looking ID {m.group(2)!r}; "
               "consider a lookup or a config value")
        for m in _HARDCODED_ID.finditer(source)
        if not any(c.start <= m.start() < c.end for c in comments)
    ]


# ---------------------------------------------------------------------- #
# command line
# ---------------------------------------------------------------------- #

def _collect(paths: Iterable[str]) -> Tuple[List[Tuple[str, Optional[Path]]],
                                            List[str]]:
    targets: List[Tuple[str, Optional[Path]]] = []
    problems: List[str] = []
    for raw in paths:
        if raw == "-":
            targets.append(("<stdin>", None))
            continue
        p = Path(raw)
        if p.is_dir():
            found = sorted(p.rglob("*.dg"))
            targets.extend((str(f), f) for f in found)
        elif p.is_file():
            targets.append((str(p), p))
        else:
            problems.append(f"{raw}: no such file or directory")
    return targets, problems


def _read(path: Optional[Path]) -> str:
    if path is None:
        data = sys.stdin.buffer.read()
    else:
        data = path.read_bytes()
    return data.decode("utf-8-sig")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="deluge_lint",
        description="Heuristic linter for Zoho Deluge scripts.",
    )
    parser.add_argument("paths", nargs="+",
                        help="files or directories (searched for *.dg); "
                             "'-' reads stdin")
    parser.add_argument("--format", choices=("text", "json"), default="text",
                        help="output format (default: text)")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    targets, problems = _collect(args.paths)
    results: List[Tuple[str, LintResult]] = []
    for label, path in targets:
        try:
            source = _read(path)
        except (OSError, UnicodeDecodeError) as exc:
            problems.append(f"{label}: cannot read as UTF-8: {exc}")
            continue
        results.append((label, lint(source)))

    errors = sum(r.error_count for _, r in results)
    warnings = sum(r.warning_count for _, r in results)
    infos = sum(r.info_count for _, r in results)

    if args.format == "json":
        payload = {
            "files": [
                {"path": label,
                 "issues": [i.to_dict() for i in r.issues]}
                for label, r in results
            ],
            "summary": {
                "files": len(results),
                "errors": errors,
                "warnings": warnings,
                "infos": infos,
            },
            "problems": problems,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for label, r in results:
            for i in r.issues:
                print(f"{label}:L{i.line}:C{i.column} "
                      f"{i.severity.upper()} [{i.code}] {i.message}")
        print(f"--- {errors} errors, {warnings} warnings, {infos} infos "
              f"in {len(results)} files ---")

    for msg in problems:
        print(f"error: {msg}", file=sys.stderr)

    if errors:
        return 1
    if problems:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
