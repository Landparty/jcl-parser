"""
Coverage-focused tests for ``jclparser.utils``.
"""

from pathlib import Path

import pytest

from jclparser.utils import read_source


class TestReadSource:
    """Tests for read_source path/string/file-like resolution."""

    def test_path_object_reads_file(self, tmp_path: Path):
        f = tmp_path / "job.jcl"
        f.write_text("//J JOB\n")
        assert read_source(f) == "//J JOB\n"

    def test_path_object_missing_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            read_source(tmp_path / "nope.jcl")

    def test_string_with_jcl_extension_reads_file(self, tmp_path: Path):
        f = tmp_path / "job.jcl"
        f.write_text("//J JOB\n")
        assert read_source(str(f)) == "//J JOB\n"

    def test_plain_string_naming_existing_file_is_read(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        # No extension and no separator in the name, but it exists on disk.
        f = tmp_path / "PROCMEMB"
        f.write_text("//STEP EXEC PGM=X\n")
        # Pass just the file name while cwd is tmp_path so there is no separator.
        monkeypatch.chdir(tmp_path)
        assert read_source("PROCMEMB") == "//STEP EXEC PGM=X\n"

    def test_plain_jcl_content_returned_as_is(self):
        content = "//J JOB\n//S EXEC PGM=X\n"
        assert read_source(content) == content

    def test_file_like_object(self):
        import io

        stream = io.StringIO("//J JOB\n")
        assert read_source(stream) == "//J JOB\n"
        # seek(0) is best-effort; the stream should be rewound for reuse.
        assert stream.tell() == 0

    def test_invalid_source_type_raises(self):
        with pytest.raises(TypeError):
            read_source(12345)
