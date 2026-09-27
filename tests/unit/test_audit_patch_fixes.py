"""Regression tests for the AUDIT.md patch-release batch (C1-C6, H1, H2, H5, M3).

Each class pins one finding: untrusted JCL must not read outside the PROCLIB
base or blow up expansion, in-stream data must end only at a real delimiter,
and pathological input must surface as a JCL error rather than a crash.
"""

import json
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10 only
    import tomli as tomllib

import pytest

import jclparser
from jclparser import JCLStructureError, JCLSyntaxError, parse_jcl, validate_jcl
from jclparser.errors import UndefinedSymbolError
from jclparser.explosion import SymbolScope, explode_job, substitute_symbols
from jclparser.include_loader import DictMemberLoader, resolve_includes
from jclparser.proc_loader import JCLLIBProcedureLoader

REPO_ROOT = Path(__file__).resolve().parents[2]

PROC = "//EVIL     PROC\n//S1       EXEC PGM=STOLEN\n//         PEND\n"


@pytest.mark.unit
class TestJcllibOrderContainment:
    """C1: a JCLLIB library must stay inside the loader's base path."""

    @pytest.fixture
    def layout(self, tmp_path):
        base = tmp_path / "base"
        (base / "SYS1.PROCLIB").mkdir(parents=True)
        (base / "SYS1.PROCLIB" / "GOOD.jcl").write_text(
            "//GOOD     PROC\n//S1       EXEC PGM=OK\n//         PEND\n"
        )
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "EVIL.jcl").write_text(PROC)
        return base, outside

    def test_library_inside_base_loads(self, layout):
        base, _ = layout
        loader = JCLLIBProcedureLoader(base_path=base)
        assert loader.load_procedure("GOOD", ["SYS1.PROCLIB"]) is not None

    def test_relative_escape_rejected(self, layout):
        base, _ = layout
        loader = JCLLIBProcedureLoader(base_path=base)
        assert loader.load_procedure("EVIL", ["../outside"]) is None

    def test_absolute_library_rejected(self, layout):
        base, outside = layout
        loader = JCLLIBProcedureLoader(base_path=base)
        assert loader.load_procedure("EVIL", [str(outside)]) is None

    def test_symlinked_library_inside_base_still_loads(self, layout):
        base, outside = layout
        link = base / "LINKED.PROCLIB"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            pytest.skip("symlinks unavailable")
        loader = JCLLIBProcedureLoader(base_path=base)
        assert loader.load_procedure("EVIL", ["LINKED.PROCLIB"]) is not None


@pytest.mark.unit
class TestIncludeExpansionBounds:
    """C2: recursive INCLUDEs are not re-expanded; total output is capped."""

    def test_recursive_member_left_intact(self):
        loader = DictMemberLoader(
            {"SELF": "//X EXEC PGM=A\n// INCLUDE MEMBER=SELF\n// INCLUDE MEMBER=SELF\n"}
        )
        result = resolve_includes("// INCLUDE MEMBER=SELF\n", loader)
        assert result.count("//X EXEC PGM=A") == 1
        assert result.count("INCLUDE MEMBER=SELF") == 2

    def test_indirect_recursion_left_intact(self):
        loader = DictMemberLoader(
            {"A": "// INCLUDE MEMBER=B\n", "B": "//Y EXEC PGM=B\n// INCLUDE MEMBER=A\n"}
        )
        result = resolve_includes("// INCLUDE MEMBER=A\n", loader)
        assert result.count("//Y EXEC PGM=B") == 1

    def test_same_member_twice_is_not_recursion(self):
        loader = DictMemberLoader({"M": "//Z EXEC PGM=Z\n"})
        src = "// INCLUDE MEMBER=M\n// INCLUDE MEMBER=M\n"
        assert resolve_includes(src, loader).count("//Z EXEC PGM=Z") == 2

    def test_fan_out_over_distinct_members_is_capped(self):
        # M0 includes M1 four times, M1 includes M2 four times ... (no cycle).
        members = {f"M{i}": f"// INCLUDE MEMBER=M{i + 1}\n" * 4 for i in range(7)}
        members["M7"] = "//S EXEC PGM=X\n"
        loader = DictMemberLoader(members)
        with pytest.raises(JCLStructureError, match="INCLUDE expansion exceeds"):
            resolve_includes("// INCLUDE MEMBER=M0\n", loader, max_lines=10_000)


@pytest.mark.unit
class TestSymbolExpansionBounds:
    """C3: a self-referencing symbol is a cycle; fan-out is capped."""

    def test_self_reference_left_as_written(self):
        scope = SymbolScope(set_symbols={"A": "&A&A&A&A&A&A"})
        # The unresolved trailing ``&A`` gets its delimiting period, as before.
        assert substitute_symbols("X&A", scope) == "X&A&A&A&A&A&A."

    def test_nested_reference_still_resolves(self):
        scope = SymbolScope(set_symbols={"HLQ": "&USER", "USER": "IBMUSER"})
        assert substitute_symbols("&HLQ..DATA", scope) == "IBMUSER.DATA"

    def test_fan_out_over_distinct_symbols_is_capped(self):
        symbols = {f"S{i}": f"&S{i + 1}" * 20 for i in range(7)}
        symbols["S7"] = "X" * 20
        with pytest.raises(JCLStructureError, match="expands to more than"):
            substitute_symbols("&S0", SymbolScope(set_symbols=symbols))

    def test_self_referencing_proc_default_is_fast(self):
        jcl = (
            "//J        JOB (A),'B'\n"
            "//P        PROC A='&A&A&A&A&A'\n"
            "//S        EXEC PGM=X\n"
            "//DD1      DD DSN=&A,DISP=SHR\n"
            "//         PEND\n"
            "//RUN      EXEC P\n"
        )
        exploded = explode_job(parse_jcl(jcl))
        dsn = exploded.steps[0].dd_statements[0].dataset_name
        assert len(dsn) < 100


@pytest.mark.unit
class TestQuotedDelimiter:
    """C4: ``DLM='$)'`` must not swallow the rest of the job."""

    def test_rest_of_job_parsed(self):
        jcl = (
            "//J        JOB (A),'B'\n"
            "//S1       EXEC PGM=IEBGENER\n"
            "//SYSUT1   DD *,DLM='$)'\n"
            "DATA1\n"
            "$)\n"
            "//SYSUT2   DD DSN=A.B,DISP=SHR\n"
            "//S2       EXEC PGM=IEFBR14\n"
        )
        job = parse_jcl(jcl)
        assert [s.name for s in job.steps] == ["S1", "S2"]
        assert [d.name for d in job.steps[0].dd_statements] == ["SYSUT1", "SYSUT2"]
        assert job.steps[0].dd_statements[0].inline_data == "DATA1"


@pytest.mark.unit
class TestIndentedDelimiterIsData:
    """C5: only a delimiter in columns 1-2 ends in-stream data."""

    def test_indented_comment_is_data(self):
        jcl = (
            "//J        JOB (A),'B'\n"
            "//S1       EXEC PGM=IKJEFT01\n"
            "//SYSTSIN  DD *\n"
            "  /* comment */\n"
            "  RUN PROG\n"
            "/*\n"
            "//S2       EXEC PGM=IEFBR14\n"
        )
        job = parse_jcl(jcl)
        s1 = job.steps[0]
        assert [d.name for d in s1.dd_statements] == ["SYSTSIN"]
        assert s1.dd_statements[0].inline_data == "  /* comment */\n  RUN PROG"
        assert [s.name for s in job.steps] == ["S1", "S2"]

    def test_indented_custom_delimiter_is_data(self):
        jcl = (
            "//J        JOB (A),'B'\n"
            "//S1       EXEC PGM=IEBGENER\n"
            "//SYSUT1   DD DATA,DLM=$$\n"
            "  $$X\n"
            "$$\n"
            "//S2       EXEC PGM=IEFBR14\n"
        )
        job = parse_jcl(jcl)
        assert job.steps[0].dd_statements[0].inline_data == "  $$X"
        assert [s.name for s in job.steps] == ["S1", "S2"]


@pytest.mark.unit
class TestDeeplyNestedCondition:
    """C6: nesting past the recursion limit is unparseable, not a crash."""

    @pytest.fixture
    def jcl(self):
        depth = sys.getrecursionlimit()
        condition = "(" * depth + "RC EQ 0" + ")" * depth
        chunks = [condition[i : i + 50] for i in range(0, len(condition), 50)]
        lines = ["//J        JOB (A),'B'", "//S1       EXEC PGM=X"]
        lines.append(f"//T        IF {chunks[0]}")
        lines += [f"//            {chunk}" for chunk in chunks[1:]]
        lines += ["//            THEN", "//S2       EXEC PGM=Y", "//         ENDIF"]
        return "\n".join(lines) + "\n"

    def test_parse_jcl_keeps_raw_condition(self, jcl):
        job = parse_jcl(jcl)
        block = job.conditionals[0]
        assert block.condition
        assert block.condition_ast is None

    def test_validate_jcl_does_not_raise(self, jcl):
        validate_jcl(jcl)


@pytest.mark.unit
class TestNonStringDelimiter:
    """M3: ``DLM=(AB)`` is a syntax error, not an AttributeError."""

    def test_list_dlm_raises_syntax_error(self):
        jcl = (
            "//J        JOB (A),'B'\n"
            "//S1       EXEC PGM=X\n"
            "//IN       DD *,DLM=(AB)\n"
            "DATA\n"
            "AB\n"
        )
        with pytest.raises(JCLSyntaxError, match="DLM="):
            parse_jcl(jcl)


@pytest.mark.unit
class TestStrictSymbolsOnPlainSteps:
    """H5: strict_symbols covers EXEC parameters of non-PROC steps too."""

    JCL = "//J        JOB (A),'B'\n//S1       EXEC PGM=X,PARM='&NOPE'\n"

    def test_strict_raises(self):
        with pytest.raises(UndefinedSymbolError):
            explode_job(parse_jcl(self.JCL), strict_symbols=True)

    def test_lenient_warns(self):
        exploded = explode_job(parse_jcl(self.JCL))
        assert any("&NOPE" in w for w in exploded.warnings)


@pytest.mark.unit
class TestPackageMetadata:
    """H1/H2: version matches the release; the contract's imports work."""

    def test_version_matches_pyproject(self):
        pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
        assert jclparser.__version__ == pyproject["project"]["version"]

    def test_release_please_bumps_init(self):
        config = json.loads((REPO_ROOT / "release-please-config.json").read_text())
        assert "jclparser/__init__.py" in config["packages"]["."]["extra-files"]

    def test_contract_exception_imports(self):
        from jclparser import (  # noqa: F401
            JCLParseError,
            JCLStructureError,
            JCLSyntaxError,
            JCLValidationError,
        )

        assert issubclass(JCLSyntaxError, JCLParseError)
        assert "JCLParseError" in jclparser.__all__
