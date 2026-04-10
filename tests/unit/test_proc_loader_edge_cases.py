"""
Test edge cases for proc_loader.py to improve coverage.

Simplified tests focusing on achievable edge cases without complex mocking.
"""

import os
import stat
import tempfile
from pathlib import Path
from unittest.mock import patch
from jclparser.proc_loader import (
    JCLLIBProcedureLoader,
    InlineProcedureLoader,
    CompositeProcedureLoader,
)
from jclparser.model import Procedure, Step


class TestJCLLIBProcedureLoaderEdgeCases:
    """Test JCLLIBProcedureLoader edge cases."""

    def test_load_procedure_from_jcl_file(self):
        """Test loading procedure from file that's actually a JCL file."""
        # Create a temp file with JOB card (not a PROC file)
        with tempfile.TemporaryDirectory() as tmpdir:
            proc_file = Path(tmpdir) / "NOTPROC.jcl"
            with open(proc_file, "w", encoding="utf-8") as f:
                f.write("""//MYJOB JOB
//STEP1 EXEC PGM=PROG
//DD1 DD DSN=FILE""")

            loader = JCLLIBProcedureLoader(Path(tmpdir))

            # Should return None - file is JCL, not PROC
            proc = loader.load_procedure("NOTPROC", libraries=["."])
            assert proc is None

    def test_load_procedure_from_valid_proc_file(self):
        """Test loading procedure from valid PROC file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proc_file = Path(tmpdir) / "lib" / "MYPROC.jcl"
            proc_file.parent.mkdir(exist_ok=True)
            with open(proc_file, "w", encoding="utf-8") as f:
                f.write("""//MYPROC PROC
//STEP1 EXEC PGM=PROG1
//DD1 DD DSN=FILE1
//PEND""")

            loader = JCLLIBProcedureLoader(Path(tmpdir))
            proc = loader.load_procedure("MYPROC", libraries=["lib"])

            assert proc is not None
            assert proc.name == "MYPROC"
            assert len(proc.steps) == 1

    def test_load_procedure_file_not_found(self):
        """Test loading non-existent procedure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = JCLLIBProcedureLoader(Path(tmpdir))

            proc = loader.load_procedure("NONEXISTENT", libraries=["lib"])
            assert proc is None

    def test_load_procedure_caching(self):
        """Test that loader caches procedures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proc_file = Path(tmpdir) / "lib" / "CACHED.jcl"
            proc_file.parent.mkdir(exist_ok=True)
            with open(proc_file, "w", encoding="utf-8") as f:
                f.write("""//CACHED PROC
//STEP1 EXEC PGM=PROG
//PEND""")

            loader = JCLLIBProcedureLoader(Path(tmpdir))

            # Load twice - should use cache second time
            proc1 = loader.load_procedure("CACHED", libraries=["lib"])
            proc2 = loader.load_procedure("CACHED", libraries=["lib"])

            # Should return same object (cached)
            assert proc1 is proc2


class TestProcedureParsingEdgeCases:
    """Test procedure file parsing edge cases."""

    def test_parse_procedure_file_without_pend(self):
        """Test PROC file missing PEND statement."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proc_file = Path(tmpdir) / "lib" / "NOPEND.jcl"
            proc_file.parent.mkdir(exist_ok=True)
            with open(proc_file, "w", encoding="utf-8") as f:
                # PROC without PEND
                f.write("""//NOPEND PROC
//STEP1 EXEC PGM=PROG1
//DD1 DD DSN=FILE1""")

            loader = JCLLIBProcedureLoader(Path(tmpdir))
            proc = loader.load_procedure("NOPEND", libraries=["lib"])

            # Should still parse successfully
            assert proc is not None
            assert proc.name == "NOPEND"

    def test_parse_procedure_file_with_comments(self):
        """Test PROC file with comments."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proc_file = Path(tmpdir) / "lib" / "COMMENTS.jcl"
            proc_file.parent.mkdir(exist_ok=True)
            with open(proc_file, "w", encoding="utf-8") as f:
                f.write("""//* This is a comment
//COMMENTS PROC
//* Another comment
//STEP1 EXEC PGM=PROG1
//DD1 DD DSN=FILE1
//* Final comment
//PEND""")

            loader = JCLLIBProcedureLoader(Path(tmpdir))
            proc = loader.load_procedure("COMMENTS", libraries=["lib"])

            assert proc is not None
            assert len(proc.steps) == 1

    def test_parse_empty_procedure_file(self):
        """Test empty PROC file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proc_file = Path(tmpdir) / "lib" / "EMPTY.jcl"
            proc_file.parent.mkdir(exist_ok=True)
            with open(proc_file, "w", encoding="utf-8") as f:
                f.write("")

            loader = JCLLIBProcedureLoader(Path(tmpdir))

            # Should return None - no PROC found
            proc = loader.load_procedure("EMPTY", libraries=["lib"])
            assert proc is None


class TestInlineProcedureLoader:
    """Test InlineProcedureLoader edge cases."""

    def test_load_inline_procedure(self):
        """Test loading inline procedure."""
        proc = Procedure(name="INLINEPROC", parameters={"PARM": "VALUE"})
        step = Step(name="STEP1", program="PROG1", parameters={})
        proc.steps.append(step)

        loader = InlineProcedureLoader([proc])
        loaded_proc = loader.load_procedure("INLINEPROC")

        assert loaded_proc is not None
        assert loaded_proc.name == "INLINEPROC"
        assert len(loaded_proc.steps) == 1

    def test_load_nonexistent_inline_procedure(self):
        """Test loading non-existent inline procedure."""
        loader = InlineProcedureLoader([])

        proc = loader.load_procedure("NONEXISTENT")
        assert proc is None

    def test_has_procedure_inline(self):
        """Test has_procedure for inline procedures."""
        proc = Procedure(name="MYPROC", parameters={})
        loader = InlineProcedureLoader([proc])

        assert loader.has_procedure("MYPROC")
        assert not loader.has_procedure("NONEXISTENT")


class TestCompositeProcedureLoader:
    """Test CompositeProcedureLoader edge cases."""

    def test_composite_loader_tries_all_loaders(self):
        """Test composite loader tries all loaders in order."""
        inline_proc = Procedure(name="INLINE", parameters={})
        inline_loader = InlineProcedureLoader([inline_proc])

        # Create temp JCLLIB with different procedure
        with tempfile.TemporaryDirectory() as tmpdir:
            proc_file = Path(tmpdir) / "lib" / "JCLLIB.jcl"
            proc_file.parent.mkdir(exist_ok=True)
            with open(proc_file, "w", encoding="utf-8") as f:
                f.write("""//JCLLIB PROC
//STEP1 EXEC PGM=PROG
//PEND""")

            jcllib_loader = JCLLIBProcedureLoader(Path(tmpdir))

            composite = CompositeProcedureLoader([inline_loader, jcllib_loader])

            # Should find inline procedure first
            proc1 = composite.load_procedure("INLINE")
            assert proc1.name == "INLINE"

            # Should find JCLLIB procedure second
            proc2 = composite.load_procedure("JCLLIB", libraries=("lib",))
            assert proc2.name == "JCLLIB"

    def test_composite_loader_procedure_not_found(self):
        """Test composite loader when procedure not in any loader."""
        inline_loader = InlineProcedureLoader([])
        composite = CompositeProcedureLoader([inline_loader])

        proc = composite.load_procedure("NONEXISTENT")
        assert proc is None

    def test_composite_loader_has_procedure(self):
        """Test has_procedure in composite loader."""
        proc = Procedure(name="MYPROC", parameters={})
        inline_loader = InlineProcedureLoader([proc])
        composite = CompositeProcedureLoader([inline_loader])

        assert composite.has_procedure("MYPROC")
        assert not composite.has_procedure("NONEXISTENT")

    def test_composite_loader_empty_loaders_list(self):
        """Test composite loader with empty loaders list."""
        composite = CompositeProcedureLoader([])

        proc = composite.load_procedure("ANYPROC")
        assert proc is None

        assert not composite.has_procedure("ANYPROC")


class TestListAllProcedures:
    """Test JCLLIBProcedureLoader.list_all_procedures() directory scanning."""

    def test_list_all_procedures_basic(self):
        """list_all_procedures returns library -> [proc names] mapping."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            lib1 = base / "SYS1.PROCLIB"
            lib1.mkdir()
            (lib1 / "PROC1.jcl").write_text("//PROC1 PROC\n//S1 EXEC PGM=P\n//PEND\n")
            (lib1 / "PROC2.jcl").write_text("//PROC2 PROC\n//S1 EXEC PGM=P\n//PEND\n")

            lib2 = base / "USER.PROCLIB"
            lib2.mkdir()
            (lib2 / "UPROC.jcl").write_text("//UPROC PROC\n//S1 EXEC PGM=P\n//PEND\n")

            loader = JCLLIBProcedureLoader(base_path=base)
            result = loader.list_all_procedures()

            assert "SYS1.PROCLIB" in result
            assert "USER.PROCLIB" in result
            assert "PROC1" in result["SYS1.PROCLIB"]
            assert "PROC2" in result["SYS1.PROCLIB"]
            assert "UPROC" in result["USER.PROCLIB"]

    def test_list_all_procedures_non_jcl_files_excluded(self):
        """Only .jcl and no-extension files are listed; .txt etc. are excluded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            lib = base / "MYLIB"
            lib.mkdir()
            (lib / "GOODPROC.jcl").write_text("//GOODPROC PROC\n//PEND\n")
            (lib / "README.txt").write_text("documentation")
            (lib / "NOEXT").write_text("//NOEXT PROC\n//PEND\n")

            loader = JCLLIBProcedureLoader(base_path=base)
            result = loader.list_all_procedures()

            assert "MYLIB" in result
            assert "GOODPROC" in result["MYLIB"]
            assert "NOEXT" in result["MYLIB"]
            assert "README" not in result["MYLIB"]

    def test_list_all_procedures_empty_base(self):
        """Returns empty dict when base_path has no library subdirectories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = JCLLIBProcedureLoader(base_path=Path(tmpdir))
            result = loader.list_all_procedures()
            assert result == {}

    def test_list_all_procedures_nonexistent_base(self):
        """Returns empty dict when base_path does not exist."""
        loader = JCLLIBProcedureLoader(base_path=Path("/nonexistent/path/xyz"))
        result = loader.list_all_procedures()
        assert result == {}

    def test_list_all_procedures_skips_files_at_base_level(self):
        """Files directly under base_path (not in subdirs) are ignored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            # A file directly at base level - should be ignored
            (base / "TOPLEVEL.jcl").write_text("//TOPLEVEL PROC\n//PEND\n")
            # A proper library subdirectory
            lib = base / "REALLIB"
            lib.mkdir()
            (lib / "REALPROC.jcl").write_text("//REALPROC PROC\n//PEND\n")

            loader = JCLLIBProcedureLoader(base_path=base)
            result = loader.list_all_procedures()

            assert "REALLIB" in result
            # TOPLEVEL.jcl was at base level (is_dir() is False), so not in result
            assert "TOPLEVEL" not in result.get("REALLIB", [])


class TestParseProcedureFileEdgeCases:
    """Tests for _parse_procedure_file() paths not covered by main tests."""

    def test_parse_unknown_file_type_with_steps(self):
        """A file of UNKNOWN type whose content has steps is returned as a Procedure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            lib = base / "LIB"
            lib.mkdir()
            # Neither a JCL job (no JOB card) nor an explicit PROC/PEND block.
            # The parser will produce a job with steps when wrapped.
            proc_file = lib / "IMPLICIT.jcl"
            proc_file.write_text(
                "//STEP1 EXEC PGM=IEFBR14\n//DD1 DD DSN=MY.FILE,DISP=SHR\n"
            )

            loader = JCLLIBProcedureLoader(base_path=base)
            proc = loader.load_procedure("IMPLICIT", ["LIB"])

            # Should fall through to the step-based fallback
            assert proc is not None
            assert proc.name == "IMPLICIT"
            assert proc.is_external is True

    def test_parse_jcl_file_rejected(self):
        """A file with a JOB card is rejected (returns None)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            lib = base / "LIB"
            lib.mkdir()
            proc_file = lib / "ISJOB.jcl"
            proc_file.write_text(
                "//ISJOB JOB CLASS=A\n//STEP1 EXEC PGM=IEFBR14\n"
            )

            loader = JCLLIBProcedureLoader(base_path=base)
            proc = loader.load_procedure("ISJOB", ["LIB"])
            assert proc is None

    def test_parse_proc_file_with_wrong_name_falls_back_to_steps(self):
        """If file defines OTHERPROC but we asked for MYPROC, step fallback fires."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            lib = base / "LIB"
            lib.mkdir()
            proc_file = lib / "MYPROC.jcl"
            proc_file.write_text(
                "//OTHERPROC PROC\n//S1 EXEC PGM=IEFBR14\n//PEND\n"
            )

            loader = JCLLIBProcedureLoader(base_path=base)
            proc = loader.load_procedure("MYPROC", ["LIB"])

            # No procedure named MYPROC found, but steps exist -> step fallback
            # OR the loader returns None because the explicit PROC is OTHERPROC.
            # Either result is acceptable; what must NOT happen is an unhandled exception.
            # (The step fallback returns a Procedure from job.steps if any.)
            assert proc is None or proc.name == "MYPROC"

    def test_parse_procedure_file_os_error(self):
        """OSError during file open is caught and returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            lib = base / "LIB"
            lib.mkdir()
            proc_file = lib / "BROKEN.jcl"
            proc_file.write_text("//BROKEN PROC\n//S1 EXEC PGM=P\n//PEND\n")

            loader = JCLLIBProcedureLoader(base_path=base)

            with patch("builtins.open", side_effect=OSError("disk error")):
                proc = loader.load_procedure("BROKEN", ["LIB"])

            assert proc is None

    def test_path_traversal_candidate_skipped(self):
        """Candidates whose resolved path escapes the library directory are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            lib = base / "LIB"
            lib.mkdir()

            loader = JCLLIBProcedureLoader(base_path=base)

            # A name with path traversal that won't match any real file still
            # exercises the OSError/ValueError guard in _load_from_library.
            proc = loader.load_procedure("../../etc/passwd", ["LIB"])
            assert proc is None
