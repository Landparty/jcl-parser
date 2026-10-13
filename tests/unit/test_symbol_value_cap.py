"""Regression tests for #70: chained SET symbols must not expand without bound.

``SET A2='&A1&A1'``, ``SET A3='&A2&A2'`` ... doubles at each step; 30 such
SETs used to allocate gigabytes. Every substitution path now stops at
``utils.MAX_SYMBOL_VALUE_LENGTH``: lenient parsing leaves the value
unresolved with a warning, strict parsing raises.
"""

import time

import pytest

from jclparser import JCLStructureError, JCLSyntaxError, parse_jcl
from jclparser._model_factories import _resolve_set_value
from jclparser.explosion import SymbolScope, explode_job, substitute_symbols
from jclparser.utils import MAX_SYMBOL_VALUE_LENGTH


def _doubling_sets(count: int) -> str:
    return (
        "//J JOB\n// SET A1='XXXXXXXXXX'\n"
        + "".join(f"// SET A{i + 1}='&A{i}&A{i}'\n" for i in range(1, count))
        + f"//S EXEC PGM=X,PARM='&A{count}'\n"
    )


def _overflow_warnings(warnings: list[str]) -> list[str]:
    return [w for w in warnings if f"{MAX_SYMBOL_VALUE_LENGTH:,}" in w]


@pytest.mark.unit
class TestParseJclCap:
    def test_thirty_doubling_sets_finish_quickly_and_warn(self):
        start = time.perf_counter()
        job = parse_jcl(_doubling_sets(30), strict_mode=False)
        assert time.perf_counter() - start < 2
        # 10 * 2**13 = 81,920 characters: A14 is the first to overflow and is
        # kept as written.
        assert job.set_statements["A14"] == "&A13&A13"
        assert len(job.set_statements["A13"]) <= MAX_SYMBOL_VALUE_LENGTH + 2
        # The reference that cannot be expanded stays as written.
        assert "&A30" in str(job.steps[0].parameters["PARM"])
        warnings = _overflow_warnings(job.warnings)
        assert any("&A14" in w and "left unresolved" in w for w in warnings)
        assert any("Step S" in w for w in warnings)

    def test_value_below_cap_still_resolves(self):
        job = parse_jcl(_doubling_sets(13), strict_mode=False)
        assert len(str(job.steps[0].parameters["PARM"])) >= 10 * 2**12
        assert not _overflow_warnings(job.warnings)

    def test_strict_mode_raises(self):
        with pytest.raises(JCLSyntaxError, match="A14"):
            parse_jcl(_doubling_sets(30), strict_mode=True)

    def test_forward_reference_chain_overflows_in_post_parse_pass(self):
        # Defined in reverse, every SET is a forward reference while parsing,
        # so only resolve_set_symbols() sees the chain.
        sets = "".join(f"// SET A{i + 1}='&A{i}&A{i}'\n" for i in range(29, 0, -1))
        src = "//J JOB\n" + sets + "// SET A1='XXXXXXXXXX'\n//S EXEC PGM=X,PARM=&A30\n"
        start = time.perf_counter()
        job = parse_jcl(src, strict_mode=False)
        assert time.perf_counter() - start < 2
        assert job.steps[0].parameters["PARM"] == "&A30"
        assert any("SET symbol(s)" in w for w in _overflow_warnings(job.warnings))
        with pytest.raises(JCLSyntaxError, match="expand to more than"):
            parse_jcl(src, strict_mode=True)


@pytest.mark.unit
class TestExplodeJobCap:
    def test_thirty_doubling_sets_explode_quickly_and_warn(self):
        start = time.perf_counter()
        exploded = explode_job(parse_jcl(_doubling_sets(30), strict_mode=False))
        assert time.perf_counter() - start < 2
        assert "&A30" in str(exploded.steps[0].parameters["PARM"])
        assert _overflow_warnings(exploded.warnings)

    def test_strict_symbols_raise(self):
        job = parse_jcl(_doubling_sets(30), strict_mode=False)
        with pytest.raises(JCLStructureError, match="expand to more than"):
            explode_job(job, strict_symbols=True)

    def test_chained_proc_symbolic_defaults(self):
        # Four-way fan-out reaches the cap within the nesting depth limit.
        defaults = ",".join(
            ["B1='XXXXXXXXXX'"]
            + [f"B{i + 1}='&B{i}&B{i}&B{i}&B{i}'" for i in range(1, 10)]
        )
        # One PROC statement carrying 30 defaults, written as continuations.
        first, *rest = defaults.split(",")
        proc_lines = [f"//P PROC {first},"] + [f"//         {d}," for d in rest[:-1]]
        proc_lines.append(f"//         {rest[-1]}")
        src = (
            "//J JOB\n"
            + "\n".join(proc_lines)
            + "\n//S EXEC PGM=X,PARM='&B10'\n//  PEND\n//RUN EXEC P\n"
        )
        start = time.perf_counter()
        exploded = explode_job(parse_jcl(src, strict_mode=False))
        assert time.perf_counter() - start < 2
        assert "&B10" in str(exploded.steps[0].parameters["PARM"])
        assert _overflow_warnings(exploded.warnings)


@pytest.mark.unit
class TestHelpers:
    def test_resolve_set_value_without_sink_returns_raw(self):
        big = "X" * (MAX_SYMBOL_VALUE_LENGTH // 2 + 1)
        assert _resolve_set_value("&A&A", {"A": big}) == "&A&A"

    def test_resolve_set_value_strict_raises(self):
        big = "X" * (MAX_SYMBOL_VALUE_LENGTH // 2 + 1)
        with pytest.raises(JCLSyntaxError, match="&B"):
            _resolve_set_value("&A&A", {"A": big}, symbol="B", strict=True)

    def test_substitute_symbols_without_sink_returns_raw(self):
        scope = SymbolScope(set_symbols={"A": "X" * (MAX_SYMBOL_VALUE_LENGTH + 1)})
        assert substitute_symbols("&A", scope) == "&A"
