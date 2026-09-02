"""
Tests targeting uncovered lines in parameter_ast.py.

Covers: non-numeric property edge cases for DCB and SPACE,
negative value validation, and SPACE validate edge cases.
"""

import pytest

from jclparser.parameter_ast import (
    ParameterParser,
    SPACEParameter,
)


@pytest.fixture
def parser():
    return ParameterParser()


# ---------------------------------------------------------------------------
# DCBParameter property edge cases — line 115
# ---------------------------------------------------------------------------


class TestDCBPropertyEdges:
    """Test DCBParameter properties with non-standard values."""

    def test_lrecl_non_numeric_returns_none(self, parser):
        """Non-numeric LRECL returns None (line 115 — else branch of isdigit)."""
        dcb = parser.parse_dcb("RECFM=FB,LRECL=X")
        assert dcb.lrecl is None

    def test_blksize_non_numeric_returns_none(self, parser):
        """Non-numeric BLKSIZE returns None."""
        dcb = parser.parse_dcb("RECFM=FB,BLKSIZE=ABC")
        assert dcb.blksize is None

    def test_bufno_non_numeric_returns_none(self, parser):
        """Non-numeric BUFNO returns None."""
        dcb = parser.parse_dcb("BUFNO=XYZ")
        assert dcb.bufno is None

    def test_lrecl_empty_string_returns_none(self, parser):
        """Empty LRECL value returns None."""
        dcb = parser.parse_dcb("LRECL=")
        assert dcb.lrecl is None

    def test_valid_numeric_properties(self, parser):
        """Valid numeric properties parse correctly (ensure no regression)."""
        dcb = parser.parse_dcb("RECFM=FB,LRECL=80,BLKSIZE=27920,BUFNO=5")
        assert dcb.lrecl == 80
        assert dcb.blksize == 27920
        assert dcb.bufno == 5


# ---------------------------------------------------------------------------
# SPACEParameter property edge cases — lines 154-156, 165-166, 176-177
# ---------------------------------------------------------------------------


class TestSPACEPropertyEdges:
    """Test SPACEParameter properties with non-numeric values."""

    def test_primary_non_numeric_returns_none(self, parser):
        """Non-numeric primary returns None (lines 154-156)."""
        space = SPACEParameter(
            key="SPACE",
            raw_value="CYL,(ABC,5)",
            subparameters={"_unit": "CYL", "_primary": "ABC", "_secondary": "5"},
        )
        assert space.primary is None

    def test_secondary_non_numeric_returns_none(self, parser):
        """Non-numeric secondary returns None (lines 165-166)."""
        space = SPACEParameter(
            key="SPACE",
            raw_value="CYL,(10,XYZ)",
            subparameters={"_unit": "CYL", "_primary": "10", "_secondary": "XYZ"},
        )
        assert space.secondary is None

    def test_directory_non_numeric_returns_none(self, parser):
        """Non-numeric directory returns None (lines 176-177)."""
        space = SPACEParameter(
            key="SPACE",
            raw_value="CYL,(10,5,BAD)",
            subparameters={
                "_unit": "CYL",
                "_primary": "10",
                "_secondary": "5",
                "_directory": "BAD",
            },
        )
        assert space.directory is None

    def test_primary_absent_returns_none(self, parser):
        """Missing primary returns None."""
        space = parser.parse_space("CYL")
        assert space.primary is None

    def test_valid_numeric_space(self, parser):
        """Valid numeric SPACE parses correctly (no regression)."""
        space = parser.parse_space("CYL,(10,5,2)")
        assert space.primary == 10
        assert space.secondary == 5
        assert space.directory == 2


# ---------------------------------------------------------------------------
# SPACEParameter.validate edge cases — line 215
# ---------------------------------------------------------------------------


class TestSPACEValidation:
    """Test SPACEParameter.validate() with edge-case values."""

    def test_negative_secondary_flagged(self):
        """Negative secondary produces validation error (line 210)."""
        space = SPACEParameter(
            key="SPACE",
            raw_value="CYL,(10,-1)",
            subparameters={"_unit": "CYL", "_primary": "10", "_secondary": "-1"},
        )
        errors = space.validate()
        assert any("negative" in e.lower() or "Secondary" in e for e in errors)

    def test_negative_directory_flagged(self):
        """Negative directory produces validation error (line 215)."""
        space = SPACEParameter(
            key="SPACE",
            raw_value="CYL,(10,5,-1)",
            subparameters={
                "_unit": "CYL",
                "_primary": "10",
                "_secondary": "5",
                "_directory": "-1",
            },
        )
        errors = space.validate()
        assert any("negative" in e.lower() or "Directory" in e for e in errors)

    def test_zero_primary_flagged(self):
        """Zero primary produces validation error."""
        space = SPACEParameter(
            key="SPACE",
            raw_value="CYL,(0,5)",
            subparameters={"_unit": "CYL", "_primary": "0", "_secondary": "5"},
        )
        errors = space.validate()
        assert any("Primary" in e or "> 0" in e for e in errors)

    def test_invalid_unit_flagged(self):
        """Invalid SPACE unit produces validation error."""
        space = SPACEParameter(
            key="SPACE",
            raw_value="INVALID,(10,5)",
            subparameters={"_unit": "INVALID", "_primary": "10", "_secondary": "5"},
        )
        errors = space.validate()
        assert any("unit" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# DCBParameter.validate edge cases
# ---------------------------------------------------------------------------


class TestDCBValidation:
    """Test DCBParameter.validate() edge cases."""

    def test_invalid_dsorg(self, parser):
        """Invalid DSORG value flagged."""
        dcb = parser.parse_dcb("DSORG=XX")
        errors = dcb.validate()
        assert any("DSORG" in e for e in errors)

    def test_blksize_not_multiple_of_lrecl(self, parser):
        """BLKSIZE not a multiple of LRECL for FB records."""
        dcb = parser.parse_dcb("RECFM=FB,LRECL=80,BLKSIZE=100")
        errors = dcb.validate()
        assert any("multiple" in e.lower() for e in errors)

    def test_lrecl_out_of_range(self, parser):
        """LRECL out of range flagged."""
        dcb = parser.parse_dcb("LRECL=99999")
        errors = dcb.validate()
        assert any("LRECL" in e for e in errors)

    def test_blksize_out_of_range(self, parser):
        """BLKSIZE out of range flagged."""
        dcb = parser.parse_dcb("BLKSIZE=99999")
        errors = dcb.validate()
        assert any("BLKSIZE" in e for e in errors)
