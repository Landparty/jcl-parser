"""
Tests for peripheral error handling paths in various modules.

Covers defensive code paths for file I/O, encoding, path traversal,
bracket tracking, and edge-case parameter validation.
"""

import os
import tempfile
import pytest
from pathlib import Path
from jclparser.continuation_handler import ContinuationLineHandler
from jclparser.parameter_validators import DISPValidator, DatasetNameValidator
from jclparser.validators import validate_disposition, validate_dd_statement
from jclparser.model import DDStatement


# ---------------------------------------------------------------------------
# continuation_handler.py — bracket depth tracking
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestContinuationBracketTracking:
    """Test the bracket depth tracking in _analyze_line_context."""

    def test_square_brackets_tracked(self):
        """Square brackets increment/decrement bracket_depth."""
        handler = ContinuationLineHandler()
        ctx = handler._analyze_line_context("PARAM=[A,B,C]")
        assert ctx.bracket_depth == 0  # balanced
        assert ctx.is_complete is True

    def test_unclosed_bracket(self):
        """Unclosed bracket leaves context incomplete."""
        handler = ContinuationLineHandler()
        ctx = handler._analyze_line_context("PARAM=[A,B")
        assert ctx.bracket_depth == 1
        assert ctx.is_complete is False

    def test_extra_close_bracket(self):
        """Extra close bracket gives negative depth."""
        handler = ContinuationLineHandler()
        ctx = handler._analyze_line_context("PARAM=A]")
        assert ctx.bracket_depth == -1

    def test_mixed_parens_and_brackets(self):
        """Both parens and brackets tracked independently."""
        handler = ContinuationLineHandler()
        ctx = handler._analyze_line_context("PARAM=[(A,B)]")
        assert ctx.paren_depth == 0
        assert ctx.bracket_depth == 0
        assert ctx.is_complete is True

    def test_non_jcl_line_in_continuation_extraction(self):
        """Lines without // prefix get content extracted directly."""
        handler = ContinuationLineHandler()
        content = handler._extract_continuation_content("  SOME DATA LINE")
        assert content == "SOME DATA LINE"


# ---------------------------------------------------------------------------
# parameter_validators.py — empty DISP and empty DSN
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestParameterValidatorEdgeCases:
    """Test edge cases in parameter validators."""

    def test_disp_empty_after_strip(self):
        """DISP validator handles empty value after parenthesis stripping."""
        result = DISPValidator.validate("()")
        # After stripping parens, the value is empty → status check
        assert isinstance(result.is_valid, bool)

    def test_disp_only_commas(self):
        """DISP with only commas → empty parts."""
        result = DISPValidator.validate("(,,)")
        # Parts are all empty
        assert isinstance(result.is_valid, bool)

    def test_dataset_name_empty_after_processing(self):
        """DSN validator handles name that becomes empty after prefix removal."""
        result = DatasetNameValidator.validate("&&")
        # After removing &&, the name is empty
        assert result.is_valid is False
        assert any(
            "no qualifiers" in e.lower() or "empty" in e.lower() for e in result.errors
        )

    def test_dataset_name_only_gdg_suffix(self):
        """DSN with only a GDG suffix and nothing else."""
        result = DatasetNameValidator.validate("(+1)")
        # No base name at all
        assert isinstance(result.is_valid, bool)


# ---------------------------------------------------------------------------
# validators.py — list-form DISP and invalid DISP in DD
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidatorDispEdgeCases:
    """Test DISP validation edge cases in validators.py."""

    def test_list_form_disposition(self):
        """validate_disposition handles list-form DISP (as produced by some parsers)."""
        result = validate_disposition(["NEW", "CATLG", "DELETE"])
        assert result is True

    def test_list_form_disposition_invalid(self):
        """validate_disposition with invalid list-form DISP."""
        result = validate_disposition(["INVALID"])
        assert result is False

    def test_empty_list_disposition(self):
        """validate_disposition with empty list."""
        result = validate_disposition([])
        assert result is False

    def test_none_disposition(self):
        """validate_disposition with None."""
        result = validate_disposition(None)
        assert result is False

    def test_dd_with_invalid_disposition(self):
        """validate_dd_statement catches invalid DISP value."""
        dd = DDStatement(
            name="DD1",
            dataset_name="MY.DATASET",
            disposition="INVALID",
        )
        errors = validate_dd_statement(dd)
        disp_errors = [
            e
            for e in errors
            if "DISP" in e.message or "disposition" in e.message.lower()
        ]
        assert len(disp_errors) >= 1


# ---------------------------------------------------------------------------
# jcl_file_type.py — OSError/ValueError in _read_source, non-seekable file
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFileTypeEdgeCases:
    """Test _read_source edge cases in jcl_file_type.py."""

    def test_non_seekable_file_object(self):
        """File-like objects that don't support seek() are handled gracefully."""
        from jclparser.utils import read_source

        class NonSeekableFile:
            def read(self):
                return "//TESTJOB JOB CLASS=A\n//STEP1 EXEC PGM=PROG1\n"

            def seek(self, pos):
                raise OSError("not seekable")

        source = NonSeekableFile()
        content = read_source(source)
        assert "TESTJOB" in content

    def test_string_that_looks_like_path_but_missing(self, tmp_path):
        """A .jcl-extension string that is not a real file raises FileNotFoundError.

        Uses a path inside a temporary directory to guarantee the target never
        exists, avoiding flakiness from coincidental filesystem matches.

        ``read_source`` is strict: a string ending in ``.jcl`` is treated as a
        path, and if it does not exist a ``FileNotFoundError`` is raised.
        Callers such as ``is_jcl_file`` catch ``OSError`` (the parent of
        ``FileNotFoundError``) and return ``False``, so consumers always have a
        safe entry point.
        """
        import pytest
        from jclparser.utils import read_source
        from jclparser.jcl_file_type import is_jcl_file

        nonexistent = str(tmp_path / "guaranteed_nonexistent.jcl")
        with pytest.raises(FileNotFoundError):
            read_source(nonexistent)

        # But the public convenience wrapper silences the error
        assert is_jcl_file(nonexistent) is False


# ---------------------------------------------------------------------------
# utils.py — binary fallback encoding
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUtilsEncodingFallback:
    """Test text decoding fallback behavior in _read_file_with_fallback."""

    def test_latin1_fallback_for_non_utf8_file(self):
        """File with non-UTF-8 bytes is still read successfully via fallback decoding."""
        from jclparser.utils import _read_file_with_fallback

        with tempfile.NamedTemporaryFile(suffix=".jcl", delete=False) as f:
            # Write bytes that are invalid in UTF-8.
            # Since Latin-1 can decode any byte, this exercises the encoding
            # fallback to Latin-1 rather than any binary-fallback branch.
            f.write(b"//TESTJOB JOB CLASS=A\n//STEP1 EXEC PGM=PROG\xff\xfe\n")
            f.flush()
            tmp_path = f.name

        try:
            result = _read_file_with_fallback(tmp_path)
            assert "TESTJOB" in result
        finally:
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# proc_loader.py — path traversal check
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProcLoaderPathTraversal:
    """Test path traversal guard in JCLLIBProcedureLoader."""

    def test_path_traversal_blocked(self):
        """Procedure names with '..' don't escape the library directory."""
        from jclparser.proc_loader import JCLLIBProcedureLoader

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a library directory
            lib_dir = Path(tmpdir) / "PROCLIB"
            lib_dir.mkdir()

            # Create a proc file OUTSIDE the library (in parent)
            secret_file = Path(tmpdir) / "SECRET.jcl"
            secret_file.write_text("//SECRET PROC\n//S1 EXEC PGM=EVIL\n// PEND\n")

            loader = JCLLIBProcedureLoader(lib_dir)
            # Try to load a PROC name that would traverse up
            result = loader.load_procedure("../SECRET", libraries=["PROCLIB"])
            assert result is None  # Should not load from outside the library
