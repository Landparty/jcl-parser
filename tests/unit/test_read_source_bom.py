"""JCL with a UTF-8 byte-order mark parses, and JCL text is never a path.

A BOM (common in files saved by Windows editors) hid the first ``//`` —
``JCLSyntaxError: must start with //`` for a file, and for a string
``read_source`` fell into its file-path heuristic (the text contains ``/``) and
raised ``FileNotFoundError``. Any multi-line text not starting with ``//`` was
likewise mistaken for a path.
"""

import io

import pytest

from jclparser import JCLSyntaxError, parse_jcl
from jclparser.proc_loader import JCLLIBProcedureLoader
from jclparser.utils import read_source

JCL = "//J        JOB (A),'B'\n//S        EXEC PGM=X\n"
BOM = "﻿"


@pytest.mark.unit
class TestReadSourceBom:
    def test_bom_string(self):
        assert read_source(BOM + JCL) == JCL
        assert [s.name for s in parse_jcl(BOM + JCL).steps] == ["S"]

    def test_bom_file(self, tmp_path):
        path = tmp_path / "j.jcl"
        path.write_bytes((BOM + JCL).encode("utf-8"))
        assert read_source(path) == JCL
        assert parse_jcl(str(path)).name == "J"

    def test_bom_file_like(self):
        assert read_source(io.StringIO(BOM + JCL)) == JCL

    def test_multiline_text_is_not_a_path(self):
        with pytest.raises(JCLSyntaxError):
            parse_jcl("Header text/notes\n" + JCL)

    def test_single_line_path_still_read(self, tmp_path):
        path = tmp_path / "j.jcl"
        path.write_text(JCL)
        assert read_source(str(path)) == JCL

    def test_bom_proc_member(self, tmp_path):
        lib = tmp_path / "SYS1.PROCLIB"
        lib.mkdir()
        (lib / "MYPROC.jcl").write_bytes(
            (BOM + "//MYPROC   PROC\n//P1       EXEC PGM=Y\n").encode("utf-8")
        )
        proc = JCLLIBProcedureLoader(tmp_path).load_procedure(
            "MYPROC", ["SYS1.PROCLIB"]
        )
        assert proc is not None
        assert [s.program for s in proc.steps] == ["Y"]
