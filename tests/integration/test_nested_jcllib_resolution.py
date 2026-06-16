"""Regression tests for nested PROC resolution across JCLLIB libraries.

The job's ``JCLLIB ORDER`` must be threaded through *every* nesting level so an
external PROC invoked from inside another PROC is found against the same library
order — including when the inner and outer PROCs live in different libraries,
and when an inline PROC invokes an external one. These tests lock that behavior
down so a refactor of ``explosion.py`` / ``proc_loader.py`` cannot silently
re-break it.
"""

import tempfile
from pathlib import Path

import pytest

from jclparser.explosion import explode_job
from jclparser.parser import parse_jcl
from jclparser.proc_loader import create_default_loader


def _write(lib: Path, name: str, body: str) -> None:
    lib.mkdir(parents=True, exist_ok=True)
    (lib / f"{name}.jcl").write_text(body)


def _programs(job) -> list[str]:
    return [s.program for s in job.steps if getattr(s, "program", None)]


@pytest.mark.integration
class TestNestedJcllibResolution:
    def test_external_outer_calls_external_inner_same_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _write(
                base / "MY.PROCLIB",
                "OUTER",
                "//OUTER PROC\n//S EXEC PROC=INNER\n//PEND\n",
            )
            _write(
                base / "MY.PROCLIB",
                "INNER",
                "//INNER PROC\n//R EXEC PGM=IEFBR14\n//PEND\n",
            )

            job = parse_jcl(
                "//J JOB\n//        JCLLIB ORDER=(MY.PROCLIB)\n//S1 EXEC PROC=OUTER\n"
            )
            loader = create_default_loader(job.procedures, base_path=base)
            exploded = explode_job(job, proc_loader=loader)

            assert _programs(exploded) == ["IEFBR14"]

    def test_inner_in_second_library_of_order(self):
        """OUTER lives in the first library, INNER only in the second."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _write(
                base / "LIBA", "OUTER", "//OUTER PROC\n//S EXEC PROC=INNER\n//PEND\n"
            )
            _write(
                base / "LIBB", "INNER", "//INNER PROC\n//R EXEC PGM=IEFBR14\n//PEND\n"
            )

            job = parse_jcl(
                "//J JOB\n//        JCLLIB ORDER=(LIBA,LIBB)\n//S1 EXEC PROC=OUTER\n"
            )
            loader = create_default_loader(job.procedures, base_path=base)
            exploded = explode_job(job, proc_loader=loader)

            assert _programs(exploded) == ["IEFBR14"]

    def test_inline_outer_calls_external_inner(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _write(
                base / "LIBB", "INNER", "//INNER PROC\n//R EXEC PGM=IEFBR14\n//PEND\n"
            )

            job = parse_jcl(
                "//J JOB\n"
                "//        JCLLIB ORDER=(LIBB)\n"
                "//OUTER PROC\n"
                "//S EXEC PROC=INNER\n"
                "//      PEND\n"
                "//S1 EXEC PROC=OUTER\n"
            )
            loader = create_default_loader(job.procedures, base_path=base)
            exploded = explode_job(job, proc_loader=loader)

            assert _programs(exploded) == ["IEFBR14"]

    def test_library_order_is_honored(self):
        """When the same PROC name exists in two libraries, the first wins."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _write(
                base / "LIBA", "SHARED", "//SHARED PROC\n//R EXEC PGM=FROM_A\n//PEND\n"
            )
            _write(
                base / "LIBB", "SHARED", "//SHARED PROC\n//R EXEC PGM=FROM_B\n//PEND\n"
            )

            job = parse_jcl(
                "//J JOB\n//        JCLLIB ORDER=(LIBA,LIBB)\n//S1 EXEC PROC=SHARED\n"
            )
            loader = create_default_loader(job.procedures, base_path=base)
            exploded = explode_job(job, proc_loader=loader)

            assert _programs(exploded) == ["FROM_A"]
