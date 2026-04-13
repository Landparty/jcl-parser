"""
Tests targeting security-critical path-traversal protections in
jclparser/proc_loader.py.

Covers:
- list_procedures(): symlink pointing outside lib dir is skipped (line 148)
- list_procedures(): OSError during resolve() is caught (lines 151-153)
- list_procedures(): lib dir with no valid procs yields no entry (line 156->142)
- _load_from_library(): path-traversal candidate is skipped (lines 197-198)
- _load_from_library(): OSError during resolve() is caught (lines 197-198)
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jclparser.proc_loader import JCLLIBProcedureLoader


class TestListProceduresPathTraversal:
    """list_procedures skips entries that escape the library directory."""

    def test_symlink_outside_lib_dir_is_skipped(self, tmp_path):
        # Secret file lives OUTSIDE the base directory tree
        outside = tmp_path / "outside"
        outside.mkdir()
        secret = outside / "secret.jcl"
        secret.write_text("//SECRET PROC\n//PEND")

        # Library directory inside base
        lib_dir = tmp_path / "base" / "MYLIB"
        lib_dir.mkdir(parents=True)

        # Symlink inside lib_dir pointing to the outside file
        link = lib_dir / "ESCAPE.jcl"
        link.symlink_to(secret)

        loader = JCLLIBProcedureLoader(tmp_path / "base")
        procs = loader.list_all_procedures()

        # "ESCAPE" must not appear — it was rejected by the traversal guard
        mylib_procs = procs.get("MYLIB", [])
        assert "ESCAPE" not in mylib_procs

    def test_lib_dir_with_no_valid_procs_has_no_entry(self, tmp_path):
        """A library subdirectory containing only non-JCL files is omitted."""
        lib_dir = tmp_path / "EMPTYLIB"
        lib_dir.mkdir()
        # Create a file with an extension that is not .jcl
        (lib_dir / "README.txt").write_text("not a proc")

        loader = JCLLIBProcedureLoader(tmp_path)
        procs = loader.list_all_procedures()
        assert "EMPTYLIB" not in procs

    def test_valid_proc_appears_in_listing(self, tmp_path):
        lib_dir = tmp_path / "SYS1.PROCLIB"
        lib_dir.mkdir()
        proc_file = lib_dir / "MYPROC.jcl"
        proc_file.write_text("//MYPROC PROC\n//S1 EXEC PGM=IEFBR14\n//      PEND\n")

        loader = JCLLIBProcedureLoader(tmp_path)
        procs = loader.list_all_procedures()
        assert "MYPROC" in procs.get("SYS1.PROCLIB", [])

    def test_oserror_during_resolve_in_list_is_caught(self, tmp_path):
        """OSError raised by Path.resolve() inside list_procedures is swallowed."""
        lib_dir = tmp_path / "MYLIB"
        lib_dir.mkdir()
        proc_file = lib_dir / "MYPROC.jcl"
        proc_file.write_text("//MYPROC PROC\n//PEND\n")

        loader = JCLLIBProcedureLoader(tmp_path)

        original_resolve = Path.resolve

        def patched_resolve(self, **kwargs):
            if self.name == "MYPROC.jcl":
                raise OSError("simulated resolve failure")
            return original_resolve(self, **kwargs)

        with patch.object(Path, "resolve", patched_resolve):
            # Should not raise
            procs = loader.list_all_procedures()
        # MYPROC is skipped due to the OSError, so it should not appear
        assert "MYPROC" not in procs.get("MYLIB", [])


class TestLoadFromLibraryPathTraversal:
    """_load_from_library skips candidates outside the library directory."""

    def test_path_traversal_name_is_blocked(self, tmp_path):
        """A proc name containing '..' is rejected by is_relative_to guard."""
        lib_dir = tmp_path / "MYLIB"
        lib_dir.mkdir()
        # A sensitive file one level above the library directory
        sensitive = tmp_path / "SENSITIVE.jcl"
        sensitive.write_text("//SENSITIVE PROC\n//PEND\n")

        loader = JCLLIBProcedureLoader(tmp_path)
        # Even if the caller passes a name that would escape the library,
        # the resolved path must stay within MYLIB — it won't.
        result = loader.load_procedure("../SENSITIVE", libraries=["MYLIB"])
        assert result is None

    def test_oserror_during_resolve_in_load_is_caught(self, tmp_path):
        """OSError raised by Path.resolve() inside _load_from_library is swallowed."""
        lib_dir = tmp_path / "MYLIB"
        lib_dir.mkdir()
        proc_file = lib_dir / "MYPROC.jcl"
        proc_file.write_text("//MYPROC PROC\n//S1 EXEC PGM=IEFBR14\n//      PEND\n")

        loader = JCLLIBProcedureLoader(tmp_path)

        original_resolve = Path.resolve

        call_count = {"n": 0}

        def patched_resolve(self, **kwargs):
            call_count["n"] += 1
            # Raise on the second call (first is the library_path.resolve())
            if call_count["n"] == 2:
                raise OSError("simulated resolve failure")
            return original_resolve(self, **kwargs)

        with patch.object(Path, "resolve", patched_resolve):
            result = loader.load_procedure("MYPROC", libraries=["MYLIB"])
        # Result may be None (all candidates raised) or the proc if a
        # subsequent candidate succeeded — either way, no crash.
        assert result is None or result.name == "MYPROC"

    def test_valid_proc_loads_normally(self, tmp_path):
        lib_dir = tmp_path / "MYLIB"
        lib_dir.mkdir()
        proc_file = lib_dir / "MYPROC.jcl"
        proc_file.write_text("//MYPROC PROC\n//S1 EXEC PGM=IEFBR14\n//      PEND\n")

        loader = JCLLIBProcedureLoader(tmp_path)
        result = loader.load_procedure("MYPROC", libraries=["MYLIB"])
        assert result is not None
        assert result.name == "MYPROC"
