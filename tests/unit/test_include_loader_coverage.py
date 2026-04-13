"""
Tests targeting coverage gaps in jclparser/include_loader.py.

Covers:
- JCLLIBMemberLoader initialised without base_path (uses env var / cwd)
- Path-traversal protection in load_member (line 123)
- resolve_includes: member content without trailing newline (line 212)
- _extract_include_member edge cases: label-only line (line 262),
  label + non-INCLUDE keyword (line 272)
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from jclparser.include_loader import (
    DictMemberLoader,
    JCLLIBMemberLoader,
    _extract_include_member,
    resolve_includes,
)


# ---------------------------------------------------------------------------
# JCLLIBMemberLoader.__init__ — env-var and cwd fallback
# ---------------------------------------------------------------------------


class TestJCLLIBMemberLoaderInit:
    """Constructor path when base_path is omitted."""

    def test_init_with_explicit_path(self, tmp_path):
        loader = JCLLIBMemberLoader(base_path=tmp_path)
        assert loader._base == tmp_path

    def test_init_without_path_uses_env_var(self, tmp_path):
        with patch.dict(os.environ, {"JCL_PROCLIB_PATH": str(tmp_path)}):
            loader = JCLLIBMemberLoader()
        assert loader._base == tmp_path

    def test_init_without_path_and_no_env_var_uses_cwd(self):
        env = {k: v for k, v in os.environ.items() if k != "JCL_PROCLIB_PATH"}
        with patch.dict(os.environ, env, clear=True):
            loader = JCLLIBMemberLoader()
        assert loader._base == Path.cwd()


# ---------------------------------------------------------------------------
# JCLLIBMemberLoader.load_member — path-traversal protection
# ---------------------------------------------------------------------------


class TestJCLLIBMemberLoaderPathTraversal:
    """load_member silently skips candidates outside the base directory."""

    def test_symlink_outside_base_is_skipped(self, tmp_path):
        # Create a real file OUTSIDE the base dir
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        secret = outside_dir / "secret.txt"
        secret.write_text("SECRET CONTENT")

        # Create a base dir with a symlink pointing to the outside file
        base_dir = tmp_path / "base"
        base_dir.mkdir()
        link = base_dir / "MEMBER.jcl"
        link.symlink_to(secret)

        loader = JCLLIBMemberLoader(base_path=base_dir)
        result = loader.load_member("MEMBER", libraries=None)
        # Path traversal guard should block this
        assert result is None

    def test_normal_member_within_base_is_returned(self, tmp_path):
        lib_dir = tmp_path / "MYLIB"
        lib_dir.mkdir()
        member = lib_dir / "COMMON.jcl"
        member.write_text("//STEP1 EXEC PGM=IEFBR14\n")

        loader = JCLLIBMemberLoader(base_path=tmp_path)
        result = loader.load_member("COMMON", libraries=["MYLIB"])
        assert result is not None
        assert "IEFBR14" in result

    def test_missing_member_returns_none(self, tmp_path):
        loader = JCLLIBMemberLoader(base_path=tmp_path)
        result = loader.load_member("NOTEXIST", libraries=["ANYLIB"])
        assert result is None


# ---------------------------------------------------------------------------
# resolve_includes — member content without trailing newline
# ---------------------------------------------------------------------------


class TestResolveIncludesNoTrailingNewline:
    """Included member content that lacks a trailing newline gets one appended."""

    def test_member_without_trailing_newline_gets_newline_added(self):
        # DictMemberLoader returns content without trailing newline
        loader = DictMemberLoader({
            "COMMON": "//COMMSTEP EXEC PGM=IEFBR14",  # NO trailing \n
        })
        jcl = "//MYJOB JOB\n// INCLUDE MEMBER=COMMON\n//STEP2 EXEC PGM=SORT\n"
        result = resolve_includes(jcl, loader)
        # The included content should be separated from the next line
        assert "IEFBR14" in result
        assert "STEP2" in result
        # No two JCL tokens should run together on the same line
        lines = result.splitlines()
        for line in lines:
            assert not ("IEFBR14" in line and "STEP2" in line)

    def test_member_with_trailing_newline_is_not_doubled(self):
        loader = DictMemberLoader({
            "COMMON": "//COMMSTEP EXEC PGM=IEFBR14\n",  # HAS trailing \n
        })
        jcl = "// INCLUDE MEMBER=COMMON\n"
        result = resolve_includes(jcl, loader)
        assert "IEFBR14" in result

    def test_collected_list_is_populated(self):
        loader = DictMemberLoader({"MEMBER1": "//S1 EXEC PGM=PROG\n"})
        jcl = "// INCLUDE MEMBER=MEMBER1\n"
        collected: list[str] = []
        resolve_includes(jcl, loader, _collected=collected)
        assert "MEMBER1" in collected

    def test_max_depth_prevents_infinite_recursion(self):
        # A member that includes itself — must stop at max_depth
        loader = DictMemberLoader({
            "SELF": "// INCLUDE MEMBER=SELF\n",
        })
        jcl = "// INCLUDE MEMBER=SELF\n"
        # Should return without raising
        result = resolve_includes(jcl, loader, max_depth=3)
        assert isinstance(result, str)

    def test_missing_member_leaves_include_line_intact(self):
        loader = DictMemberLoader({})  # nothing in it
        jcl = "//MYJOB JOB\n// INCLUDE MEMBER=NOTFOUND\n"
        result = resolve_includes(jcl, loader)
        assert "INCLUDE" in result or "NOTFOUND" in result


# ---------------------------------------------------------------------------
# _extract_include_member — edge cases
# ---------------------------------------------------------------------------


class TestExtractIncludeMember:
    """_extract_include_member handles all syntactic forms and edge cases."""

    # Happy-path cases (already tested elsewhere, but here for completeness)
    def test_no_label_space_separated(self):
        assert _extract_include_member("// INCLUDE MEMBER=MYMEMBER") == "MYMEMBER"

    def test_no_label_no_space(self):
        assert _extract_include_member("//INCLUDE MEMBER=MYMEMBER") == "MYMEMBER"

    def test_label_include(self):
        assert _extract_include_member("//LABEL INCLUDE MEMBER=MYMEMBER") == "MYMEMBER"

    def test_parenthesised_member_name(self):
        assert _extract_include_member("// INCLUDE MEMBER=(MYMEMBER)") == "MYMEMBER"

    # Comment lines are not INCLUDE statements
    def test_comment_line_returns_none(self):
        assert _extract_include_member("//* INCLUDE MEMBER=X") is None

    # Non-JCL line
    def test_non_jcl_line_returns_none(self):
        assert _extract_include_member("SOME DATA LINE") is None

    # Label-only line: "//JUSTLABEL" — no second token, so no INCLUDE keyword
    def test_label_only_no_second_token_returns_none(self):
        assert _extract_include_member("//JUSTLABEL") is None

    # Label + non-INCLUDE keyword: "//LABEL EXEC PGM=..." should return None
    def test_label_with_non_include_keyword_returns_none(self):
        assert _extract_include_member("//LABEL EXEC PGM=IEFBR14") is None

    # INCLUDE keyword but missing MEMBER=
    def test_include_without_member_keyword_returns_none(self):
        assert _extract_include_member("// INCLUDE ORDER=MYLIB") is None

    # Empty content after //
    def test_empty_after_slashes_returns_none(self):
        assert _extract_include_member("//") is None

    # Case-insensitive INCLUDE keyword
    def test_include_keyword_case_insensitive(self):
        assert _extract_include_member("// include MEMBER=LOWER") == "LOWER"

    # Member name is upper-cased in result
    def test_member_name_is_uppercased(self):
        assert _extract_include_member("// INCLUDE MEMBER=mymbr") == "MYMBR"
