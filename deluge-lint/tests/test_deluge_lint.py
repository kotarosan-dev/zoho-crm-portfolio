import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from deluge_lint import lint  # noqa: E402

SCRIPT = ROOT / "deluge_lint.py"


def codes(source):
    return [i.code for i in lint(source).issues]


class RuleTestCase(unittest.TestCase):
    def assertFires(self, code, source):
        self.assertIn(code, codes(source), source)

    def assertQuiet(self, code, source):
        self.assertNotIn(code, codes(source), source)


class TestDL001(RuleTestCase):
    def test_fires_unclosed(self):
        self.assertFires("DL001", "if (a == 1\n{\n}\n")

    def test_fires_unmatched_close(self):
        self.assertFires("DL001", "x = 1;\n}\n")

    def test_fires_mismatched(self):
        self.assertFires("DL001", "x = (1];\n")

    def test_quiet_balanced(self):
        self.assertQuiet("DL001", "if (a == 1)\n{\n    x = [1, 2];\n}\n")

    def test_quiet_in_string_and_comment(self):
        self.assertQuiet("DL001", 'x = "(((";\n')
        self.assertQuiet("DL001", "// ))) {{{\n/* ] [ */\n")


class TestDL002(RuleTestCase):
    def test_fires(self):
        self.assertFires("DL002", 'x = "abc;\ny = 1;\n')

    def test_quiet_closed(self):
        self.assertQuiet("DL002", 'x = "abc";\n')

    def test_quiet_apostrophe_in_comment(self):
        self.assertQuiet("DL002", "// it's fine\n")

    def test_quiet_escaped_quote(self):
        self.assertQuiet("DL002", 'x = "say \\"hi\\"";\n')

    def test_quiet_other_quote_inside_string(self):
        self.assertQuiet("DL002", "x = \"it's\";\n")


class TestDL003(RuleTestCase):
    def test_fires(self):
        self.assertFires("DL003", "x = 1;\n/* never closed\n")

    def test_quiet_closed(self):
        self.assertQuiet("DL003", "/* closed\nacross lines */\nx = 1;\n")

    def test_quiet_inside_string_and_line_comment(self):
        self.assertQuiet("DL003", 'x = "/* not a comment";\n')
        self.assertQuiet("DL003", "// /* not a block\n")


class TestDL010(RuleTestCase):
    def test_fires(self):
        self.assertFires("DL010", "for (int i = 0; i < 3; i++)\n{\n}\n")
        self.assertFires("DL010", "for(int i = 0; i < 3; i++)\n{\n}\n")

    def test_quiet_for_each(self):
        self.assertQuiet("DL010", "for each item in items\n{\n}\n")

    def test_quiet_in_string_and_comment(self):
        self.assertQuiet("DL010", 'x = "for (int i = 0;;)";\n')
        self.assertQuiet("DL010", "// for (int i = 0;;)\n")
        self.assertQuiet("DL010", "/* for (int i = 0;;) */\n")

    def test_quiet_identifier_suffix(self):
        self.assertQuiet("DL010", "x = platfor(1);\n")


class TestDL011(RuleTestCase):
    def test_fires(self):
        self.assertFires("DL011", "while (a < 3)\n{\n}\n")
        self.assertFires("DL011", "while(a < 3)\n{\n}\n")

    def test_quiet_in_string_and_comment(self):
        self.assertQuiet("DL011", 'x = "while (true)";\n')
        self.assertQuiet("DL011", "// while (true)\n")
        self.assertQuiet("DL011", "/* while (true) */\n")

    def test_quiet_identifier_suffix(self):
        self.assertQuiet("DL011", "x = meanwhile(1);\n")


class TestDL012(RuleTestCase):
    def test_fires(self):
        self.assertFires("DL012", 'x = a > 1 ? "y" : "n";\n')

    def test_quiet_if_else(self):
        self.assertQuiet("DL012", "if (a > 1)\n{\n    x = 1;\n}\n")

    def test_quiet_question_mark_in_string(self):
        self.assertQuiet("DL012", 'u = "https://example.com/a?b=1&c=2";\n')

    def test_quiet_question_mark_in_comment(self):
        self.assertQuiet("DL012", "// why?\n/* really? */\n")


class TestDL013(RuleTestCase):
    BLOCK = (
        "r = invokeurl\n[\n"
        '    url: "https://www.zohoapis.com/crm/v8/Leads"\n'
        "{comment}"
        "    type: GET\n"
        '    connection: "zoho_crm"\n'
        "];\n"
    )

    def block(self, comment):
        return self.BLOCK.replace("{comment}", comment)

    def test_fires_line_comment(self):
        self.assertFires("DL013", self.block("    // note\n"))

    def test_fires_block_comment(self):
        self.assertFires("DL013", self.block("    /* note */\n"))

    def test_quiet_comment_outside(self):
        self.assertQuiet(
            "DL013", "// before\n" + self.block("") + "// after\n")

    def test_quiet_slashes_in_url_string(self):
        self.assertQuiet("DL013", self.block(""))

    def test_quiet_comment_text_in_string_inside_block(self):
        self.assertQuiet("DL013", self.block('    parameters: "// x"\n'))

    def test_case_insensitive_keyword(self):
        src = self.block("    // note\n").replace("invokeurl", "invokeUrl")
        self.assertFires("DL013", src)


class TestDL014(RuleTestCase):
    def test_fires(self):
        self.assertFires("DL014", "x = 1; // note\n")

    def test_fires_after_string(self):
        self.assertFires("DL014", 'info "a"; // note\n')

    def test_severity_is_info(self):
        issues = lint("x = 1; // note\n").issues
        self.assertEqual([i.severity for i in issues], ["info"])

    def test_quiet_full_line_comment(self):
        self.assertQuiet("DL014", "// note\n    // indented note\n")

    def test_quiet_slashes_inside_string(self):
        self.assertQuiet("DL014", 'u = "https://example.com";\n')

    def test_quiet_block_comment_then_line_comment(self):
        self.assertQuiet("DL014", "/* a */ // b\n")

    def test_quiet_comment_in_block_comment(self):
        self.assertQuiet("DL014", "/*\n x = 1; // not a comment\n*/\n")


class TestDL015(RuleTestCase):
    def test_fires(self):
        self.assertFires("DL015", "if (a == 1) b = 2;\n")

    def test_fires_else_if(self):
        self.assertFires(
            "DL015", "if (a == 1)\n{\n}\nelse if (a == 2) b = 3;\n")

    def test_quiet_braces_same_line(self):
        self.assertQuiet("DL015", "if (a == 1) { b = 2; }\n")

    def test_quiet_braces_next_line(self):
        self.assertQuiet("DL015", "if (a == 1)\n{\n    b = 2;\n}\n")

    def test_quiet_nested_parens_condition(self):
        self.assertQuiet(
            "DL015", "if ((a == 1) && (b == 2))\n{\n    c = 1;\n}\n")

    def test_quiet_if_function_expression(self):
        self.assertQuiet("DL015", 'x = if(a == 1, "y", "n");\n')

    def test_quiet_in_string_and_comment(self):
        self.assertQuiet("DL015", 'x = "if (a == 1) b = 2;";\n')
        self.assertQuiet("DL015", "// if (a == 1) b = 2;\n")
        self.assertQuiet("DL015", "/* if (a == 1) b = 2; */\n")


class TestDL016(RuleTestCase):
    CASES = [
        "x = y.getType();",
        "x = getType(y);",
        "x = y instanceof Map;",
        "x = isList(y);",
        'x = y.join(",");',
        'x = y.repeat(2);',
        "x = y.keySet();",
        "x = y.compareTo(z);",
        "x = y.toint();",
    ]

    def test_fires_each(self):
        for case in self.CASES:
            with self.subTest(case=case):
                self.assertFires("DL016", case + "\n")

    def test_toint_case_insensitive(self):
        self.assertFires("DL016", "x = y.toInt();\n")
        self.assertFires("DL016", "x = y.TOINT();\n")

    def test_quiet_in_string(self):
        for case in self.CASES:
            with self.subTest(case=case):
                src = 'x = "' + case.replace('"', "'") + '";\n'
                self.assertQuiet("DL016", src)

    def test_quiet_in_comment(self):
        for case in self.CASES:
            with self.subTest(case=case):
                self.assertQuiet("DL016", "// " + case + "\n")
                self.assertQuiet("DL016", "/* " + case + " */\n")

    def test_quiet_supported_builtins(self):
        self.assertQuiet("DL016", "x = y.keys();\nz = w.toLong();\n")

    def test_quiet_similar_names(self):
        self.assertQuiet("DL016", "x = isListing(y);\nz = myinstanceof;\n")

    def test_message_and_hints(self):
        msgs = {i.message for i in lint('x = y.keySet();\n').issues}
        self.assertEqual(
            msgs,
            {"'.keySet(' is on the avoid list "
             "(not a reliable Deluge built-in); try keys()"},
        )
        join_msg = lint('x = y.join(",");\n').issues[0].message
        self.assertIn('toString(",")', join_msg)
        toint_msg = lint("x = y.toint();\n").issues[0].message
        self.assertIn("toLong()", toint_msg)
        other = lint("x = y.repeat(2);\n").issues[0].message
        self.assertEqual(
            other,
            "'.repeat(' is on the avoid list "
            "(not a reliable Deluge built-in)",
        )


class TestDL020(RuleTestCase):
    def test_fires(self):
        self.assertFires("DL020", 'id = "123456789012345678";\n')
        self.assertFires("DL020", "id = '1234567890123456789';\n")

    def test_quiet_short_number(self):
        self.assertQuiet("DL020", 'id = "12345678901234567";\n')

    def test_quiet_unquoted(self):
        self.assertQuiet("DL020", "id = 123456789012345678;\n")

    def test_quiet_in_comments(self):
        self.assertQuiet("DL020", '// id = "123456789012345678"\nx = 1;\n')
        self.assertQuiet("DL020", '/* id = "1234567890123456789" */\nx = 1;\n')


class TestPositions(unittest.TestCase):
    def test_line_and_column(self):
        issues = lint("x = 1;\n    while (a)\n").issues
        w = [i for i in issues if i.code == "DL011"][0]
        self.assertEqual((w.line, w.column), (2, 5))

    def test_masking_keeps_columns_after_string(self):
        issues = lint('x = "ab"; y = a ? 1 : 2;\n').issues
        t = [i for i in issues if i.code == "DL012"][0]
        self.assertEqual((t.line, t.column), (1, 17))


class TestCli(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def run_cli(self, *args, stdin=None):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args],
            input=stdin,
            capture_output=True,
            cwd=str(self.dir),
        )

    def write(self, name, text):
        p = self.dir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def test_exit_0_on_clean_file(self):
        p = self.write("ok.dg", "x = 1;\n")
        r = self.run_cli(str(p))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_exit_0_on_warnings_only(self):
        p = self.write("warn.dg", 'x = y.keySet();\n')
        r = self.run_cli(str(p))
        self.assertEqual(r.returncode, 0)
        self.assertIn("[DL016]", r.stdout.decode("utf-8"))

    def test_exit_1_on_error(self):
        p = self.write("bad.dg", "while (a)\n{\n}\n")
        r = self.run_cli(str(p))
        self.assertEqual(r.returncode, 1)
        out = r.stdout.decode("utf-8")
        self.assertIn(f"{p}:L1:C1 ERROR [DL011]", out)
        self.assertIn("--- 1 errors, 0 warnings, 0 infos in 1 files ---", out)

    def test_directory_scan_is_recursive_and_dg_only(self):
        self.write("a/b/deep.dg", "while (a)\n{\n}\n")
        self.write("a/ignored.txt", "while (a)\n{\n}\n")
        r = self.run_cli("a", "--format", "json")
        data = json.loads(r.stdout.decode("utf-8"))
        self.assertEqual(len(data["files"]), 1)
        self.assertTrue(data["files"][0]["path"].endswith("deep.dg"))
        self.assertEqual(r.returncode, 1)

    def test_stdin(self):
        r = self.run_cli("-", stdin=b"x = a ? 1 : 2;\n")
        self.assertEqual(r.returncode, 1)
        self.assertIn("<stdin>:L1:C7 ERROR [DL012]", r.stdout.decode("utf-8"))

    def test_json_format(self):
        p = self.write("bad.dg", 'x = 1; // c\nwhile (a)\n{\n}\n')
        r = self.run_cli(str(p), "--format", "json")
        data = json.loads(r.stdout.decode("utf-8"))
        self.assertEqual(data["summary"]["errors"], 1)
        self.assertEqual(data["summary"]["infos"], 1)
        issues = data["files"][0]["issues"]
        self.assertEqual([i["code"] for i in issues], ["DL014", "DL011"])
        self.assertEqual(
            set(issues[0]), {"line", "column", "severity", "code", "message"})
        self.assertEqual(r.returncode, 1)

    def test_japanese_comments_utf8(self):
        p = self.write("jp.dg", "// 日本語のコメント\nx = \"テスト?\";\n")
        r = self.run_cli(str(p))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_missing_path_exit_2(self):
        r = self.run_cli("does_not_exist.dg")
        self.assertEqual(r.returncode, 2)

    def test_examples(self):
        good = self.run_cli(str(ROOT / "examples" / "good.dg"),
                            "--format", "json")
        gd = json.loads(good.stdout.decode("utf-8"))
        self.assertEqual(good.returncode, 0)
        self.assertEqual(gd["summary"]["errors"], 0)
        self.assertEqual(gd["summary"]["warnings"], 0)
        bad = self.run_cli(str(ROOT / "examples" / "bad.dg"),
                           "--format", "json")
        bd = json.loads(bad.stdout.decode("utf-8"))
        self.assertEqual(bad.returncode, 1)
        found = {i["code"] for i in bd["files"][0]["issues"]}
        self.assertTrue(
            {"DL001", "DL002", "DL003", "DL010", "DL011", "DL012", "DL013",
             "DL014", "DL015", "DL016", "DL020"} <= found, found)


if __name__ == "__main__":
    unittest.main()
