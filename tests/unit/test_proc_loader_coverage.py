"""
Coverage-focused tests for ``jclparser.proc_loader``.

Targets the previously-uncovered ``DictProcedureLoader`` and the
``list_all_procedures`` discovery helper on ``JCLLIBProcedureLoader``.
"""

import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

from jclparser.proc_loader import (
    DictProcedureLoader,
    JCLLIBProcedureLoader,
)

PROC_CONTENT = """//MYPROC PROC
//STEP1 EXEC PGM=IEFBR14
// PEND
"""

JOB_CONTENT = """//MYJOB JOB
//STEP1 EXEC PGM=IEFBR14
"""


class TestDictProcedureLoader:
    """Tests for the in-memory dict-backed procedure loader."""

    def test_loads_and_marks_external(self):
        loader = DictProcedureLoader({"MYPROC": PROC_CONTENT})
        proc = loader.load_procedure("MYPROC")
        assert proc is not None
        assert proc.name.upper() == "MYPROC"
        assert proc.is_external is True

    def test_case_insensitive_lookup(self):
        loader = DictProcedureLoader({"MyProc": PROC_CONTENT})
        assert loader.load_procedure("myproc") is not None

    def test_result_is_cached(self):
        loader = DictProcedureLoader({"MYPROC": PROC_CONTENT})
        first = loader.load_procedure("MYPROC")
        second = loader.load_procedure("MYPROC")
        assert first is second

    def test_empty_name_returns_none(self):
        loader = DictProcedureLoader({"MYPROC": PROC_CONTENT})
        assert loader.load_procedure("") is None

    def test_unknown_name_returns_none(self):
        loader = DictProcedureLoader({"MYPROC": PROC_CONTENT})
        assert loader.load_procedure("OTHER") is None

    def test_job_file_content_rejected(self):
        # Content with a JOB card is a job stream, not a PROC.
        loader = DictProcedureLoader({"MYJOB": JOB_CONTENT})
        assert loader.load_procedure("MYJOB") is None

    def test_unparseable_content_returns_none(self):
        loader = DictProcedureLoader({"X": "not really jcl at all"})
        assert loader.load_procedure("X") is None

    def test_content_without_proc_card_wrapped_from_steps(self):
        # No PROC/PEND card but the content has executable steps: the loader
        # synthesises a Procedure under the requested name from those steps.
        loader = DictProcedureLoader({"WRAPME": "//S EXEC PGM=IEFBR14\n"})
        proc = loader.load_procedure("WRAPME")
        assert proc is not None
        assert proc.name == "WRAPME"
        assert proc.is_external is True
        assert [s.name for s in proc.steps] == ["S"]

    def test_has_procedure(self):
        loader = DictProcedureLoader({"MYPROC": PROC_CONTENT})
        assert loader.has_procedure("MYPROC") is True
        assert loader.has_procedure("MISSING") is False

    def test_parse_failure_is_logged(self, caplog):
        # A genuine parse failure should be surfaced via a warning log rather
        # than swallowed silently, while still returning None to callers.
        loader = DictProcedureLoader({"X": PROC_CONTENT})
        with (
            caplog.at_level(logging.WARNING, logger="jclparser.proc_loader"),
            patch("jclparser.parser.parse_jcl", side_effect=ValueError("boom")),
        ):
            assert loader.load_procedure("X") is None
        assert any(
            "Failed to parse in-memory procedure" in r.message and "boom" in r.message
            for r in caplog.records
        )


class TestExternalLoadLogging:
    """The external file loader logs (rather than swallows) load failures."""

    def test_parse_procedure_file_failure_is_logged(self, caplog):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            lib = base / "LIB"
            lib.mkdir()
            (lib / "BROKEN.jcl").write_text(PROC_CONTENT)

            loader = JCLLIBProcedureLoader(base_path=base)
            with (
                caplog.at_level(logging.WARNING, logger="jclparser.proc_loader"),
                patch("builtins.open", side_effect=OSError("disk error")),
            ):
                assert loader.load_procedure("BROKEN", ["LIB"]) is None
        assert any(
            "Failed to load procedure" in r.message and "disk error" in r.message
            for r in caplog.records
        )


class TestListAllProcedures:
    """Tests for JCLLIBProcedureLoader.list_all_procedures discovery."""

    def test_missing_base_path_returns_empty(self, tmp_path: Path):
        loader = JCLLIBProcedureLoader(tmp_path / "does-not-exist")
        assert loader.list_all_procedures() == {}

    def test_discovers_procs_by_library(self, tmp_path: Path):
        lib = tmp_path / "SYS1.PROCLIB"
        lib.mkdir()
        (lib / "ALPHA.jcl").write_text(PROC_CONTENT)
        (lib / "BETA").write_text(PROC_CONTENT)  # no suffix -> still a PROC
        (lib / "notes.txt").write_text("ignored")  # other suffix -> skipped
        (lib / "subdir").mkdir()  # nested dir -> skipped (not a file)

        loader = JCLLIBProcedureLoader(tmp_path)
        result = loader.list_all_procedures()

        assert result == {"SYS1.PROCLIB": ["ALPHA", "BETA"]}

    def test_empty_library_dir_excluded(self, tmp_path: Path):
        # A library directory with no PROC files should not appear in the result.
        (tmp_path / "EMPTY.LIB").mkdir()
        loader = JCLLIBProcedureLoader(tmp_path)
        assert loader.list_all_procedures() == {}

    def test_files_at_base_path_root_ignored(self, tmp_path: Path):
        # Only immediate subdirectories are scanned as libraries.
        (tmp_path / "loose.jcl").write_text(PROC_CONTENT)
        loader = JCLLIBProcedureLoader(tmp_path)
        assert loader.list_all_procedures() == {}
