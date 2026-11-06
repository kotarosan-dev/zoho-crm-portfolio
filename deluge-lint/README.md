# deluge-lint

A lightweight linter for Zoho Deluge scripts (`.dg`).
Run it before pasting a function into the Zoho editor, in a pre-commit hook, or in CI.

- Python 3.9+, standard library only — one file, nothing to install
- Reads UTF-8 (Japanese comments are fine)
- Text or JSON output, exit code `1` when an error is found

## Usage

```bash
python deluge_lint.py my_function.dg
python deluge_lint.py functions/                  # all *.dg files, recursively
cat my_function.dg | python deluge_lint.py -      # stdin
python deluge_lint.py functions/ --format json
```

```text
examples/bad.dg:L15:C5 ERROR [DL011] Deluge has no while loop; use 'for each' over a list
--- 6 errors, 7 warnings, 1 infos in 1 files ---
```

Exit codes: `0` no errors, `1` at least one error, `2` a path could not be read.

As a library:

```python
from deluge_lint import lint

result = lint(source)
if result.has_errors:
    print(result.to_report())
```

## Rules

| Code | Level | What it catches |
| --- | --- | --- |
| DL001 | error | Unbalanced or mismatched `( ) { } [ ]` |
| DL002 | error | String literal not closed on the same line |
| DL003 | error | Block comment `/*` without `*/` |
| DL010 | error | C-style `for (...)` loop — Deluge only has `for each` |
| DL011 | error | `while (...)` loop — Deluge has no while loop |
| DL012 | error | Ternary operator `cond ? a : b` — use an if/else block |
| DL013 | warning | Comment inside an `invokeurl [ ... ]` block |
| DL014 | info | End-of-line comment (code followed by `//`) |
| DL015 | warning | Single-line `if (...) x = y;` without braces |
| DL016 | warning | Call on the avoid list: `getType(`, `instanceof`, `isList(`, `.join(`, `.repeat(`, `.keySet(`, `.compareTo(`, `.toint(` |
| DL020 | warning | Hardcoded 18–19 digit record ID in a string — prefer a lookup or a config value |

Text inside strings and comments never triggers DL010–DL016 or DL020.

## Limits

This is a set of shallow checks, not a Deluge parser.

- A clean result does not prove the script will save or run.
- DL015 only looks at a single line; a braceless `if` whose body is on the next line is not reported.
- DL013–DL016 come from mistakes seen in real projects. They are conservative house rules, not official Zoho rules.

Checked against 80 production Deluge functions: no errors were reported (10 warnings, 2 infos — mostly hardcoded IDs).

## Tests

```bash
python -m unittest discover -s tests -v
```

## License

MIT — see [LICENSE](../LICENSE).
