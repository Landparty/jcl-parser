"""
Abstract Syntax Tree for JCL parameters.

Provides structured representation of complex parameters like DCB, SPACE, etc.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Module-level frozensets for DCB/SPACE validation (avoids per-call list construction)
# RECFM is a record-format letter followed by optional attribute letters:
# B (blocked; not with U), S (standard / spanned; not with U), T (track
# overflow; not with D), and one control-character letter, A (ANSI) or M
# (machine).  So FA, VBSA, UA and FBSA are as valid as FB -- a fixed set of
# a dozen spellings reported every other one as invalid.
_RE_VALID_RECFM = re.compile(r"(?:F|V)B?S?T?[AM]?|UT?[AM]?|DB?S?A?")
# DSORG values: the U suffix marks a data set with location-dependent
# (unmovable) data; CX/GS/TX/TQ/TR are BTAM/GAM/TCAM organizations.
_VALID_DSORG = frozenset(
    {
        "PS",
        "PSU",
        "PO",
        "POU",
        "DA",
        "DAU",
        "IS",
        "ISU",
        "VS",
        "CX",
        "GS",
        "TX",
        "TQ",
        "TR",
    }
)


@dataclass
class ParameterNode:
    """Base class for parameter AST nodes."""

    raw_value: str
    line_number: int = 0


@dataclass
class NestedParameter(ParameterNode):
    """Nested parameter: KEY=(SUB1=val1,SUB2=val2)."""

    key: str = ""
    subparameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class DCBParameter(NestedParameter):
    """
    Structured DCB parameter.

    Common DCB subparameters:
    - RECFM: Record format (F, FB, V, VB, U, etc.)
    - LRECL: Logical record length
    - BLKSIZE: Block size
    - BUFNO: Number of buffers
    - OPTCD: Optional services
    - DSORG: Dataset organization
    """

    @property
    def recfm(self) -> str | None:
        """Record format."""
        return self.subparameters.get("RECFM")

    @property
    def lrecl(self) -> int | None:
        """Logical record length."""
        val = self.subparameters.get("LRECL")
        return int(val) if val and str(val).isdigit() else None

    @property
    def blksize(self) -> int | None:
        """Block size."""
        val = self.subparameters.get("BLKSIZE")
        return int(val) if val and str(val).isdigit() else None

    @property
    def bufno(self) -> int | None:
        """Number of buffers."""
        val = self.subparameters.get("BUFNO")
        return int(val) if val and str(val).isdigit() else None

    @property
    def dsorg(self) -> str | None:
        """Dataset organization."""
        return self.subparameters.get("DSORG")

    def validate(self) -> list[str]:
        """
        Validate DCB parameters.

        Returns:
            List of validation error messages
        """
        errors = []

        # Validate RECFM
        if self.recfm and not _RE_VALID_RECFM.fullmatch(str(self.recfm).upper()):
            errors.append(f"Invalid RECFM value: {self.recfm}")

        # Validate LRECL
        if self.lrecl is not None and (self.lrecl < 1 or self.lrecl > 32760):
            errors.append(f"LRECL out of range (1-32760): {self.lrecl}")

        # Validate BLKSIZE
        if self.blksize is not None:
            # BLKSIZE=0 asks the system to pick the block size (SDB).
            if self.blksize < 0 or self.blksize > 32760:
                errors.append(f"BLKSIZE out of range (0-32760): {self.blksize}")

            # BLKSIZE should be multiple of LRECL for fixed-length records
            if (
                self.lrecl
                and self.recfm
                and self.recfm.startswith("F")
                and self.blksize % self.lrecl != 0
            ):
                errors.append(
                    f"BLKSIZE ({self.blksize}) should be multiple of "
                    f"LRECL ({self.lrecl}) for fixed-length records"
                )

        # Validate DSORG
        if self.dsorg and self.dsorg not in _VALID_DSORG:
            errors.append(f"Invalid DSORG value: {self.dsorg}")

        return errors


@dataclass
class SPACEParameter(NestedParameter):
    """
    Structured SPACE parameter.

    Format: SPACE=(unit,(primary,secondary,directory),RLSE,CONTIG/ROUND)
    """

    @property
    def unit(self) -> str | None:
        """Space allocation unit (TRK, CYL, blksize)."""
        # First positional parameter
        return self.subparameters.get("_unit")

    @property
    def primary(self) -> int | None:
        """Primary space allocation."""
        val = self.subparameters.get("_primary")
        if val:
            try:
                return int(val)
            except ValueError:
                return None
        return None

    @property
    def secondary(self) -> int | None:
        """Secondary space allocation."""
        val = self.subparameters.get("_secondary")
        if val:
            try:
                return int(val)
            except ValueError:
                return None
        return None

    @property
    def directory(self) -> int | None:
        """Directory blocks (for PDS)."""
        val = self.subparameters.get("_directory")
        if val:
            try:
                return int(val)
            except ValueError:
                return None
        return None

    @property
    def rlse(self) -> bool:
        """Release unused space."""
        return self.subparameters.get("RLSE", False)

    @property
    def contig(self) -> bool:
        """Contiguous allocation."""
        return self.subparameters.get("CONTIG", False)

    @property
    def round(self) -> bool:
        """Round allocation."""
        return self.subparameters.get("ROUND", False)

    def validate(self) -> list[str]:
        """Validate SPACE parameters."""
        errors = []

        # Validate unit
        if self.unit:
            valid_units = ["TRK", "CYL"]
            if self.unit not in valid_units and not self.unit.isdigit():
                errors.append(f"Invalid SPACE unit: {self.unit}")

        # Validate primary >= 0.  SPACE=(TRK,0) is legal: it is the IEFBR14
        # "delete if it exists" idiom, DISP=(MOD,DELETE),SPACE=(TRK,0) (#65).
        if self.primary is not None and self.primary < 0:
            errors.append(f"Primary space cannot be negative: {self.primary}")

        # Validate secondary >= 0
        if self.secondary is not None and self.secondary < 0:
            errors.append(f"Secondary space cannot be negative: {self.secondary}")

        # Validate directory >= 0
        if self.directory is not None and self.directory < 0:
            errors.append(f"Directory blocks cannot be negative: {self.directory}")

        return errors


class ParameterParser:
    """Parser for complex JCL parameters."""

    def parse_dcb(self, dcb_string: str, line_number: int = 0) -> DCBParameter:
        """
        Parse DCB parameter string into structured object.

        Args:
            dcb_string: DCB parameter value (e.g., "RECFM=FB,LRECL=80")
            line_number: Source line number

        Returns:
            DCBParameter object
        """
        # Remove outer parentheses if present
        dcb_string = dcb_string.strip()
        if dcb_string.startswith("(") and dcb_string.endswith(")"):
            dcb_string = dcb_string[1:-1]

        subparams = {}

        # Split by comma (respecting nested parentheses)
        parts = self._split_parameters(dcb_string)

        for part in parts:
            if "=" in part:
                key, value = part.split("=", 1)
                subparams[key.strip().upper()] = value.strip()

        logger.debug(
            "parsed DCB at line %d into %d subparameter(s)",
            line_number,
            len(subparams),
        )
        return DCBParameter(
            key="DCB",
            raw_value=dcb_string,
            subparameters=subparams,
            line_number=line_number,
        )

    def parse_space(self, space_string: str, line_number: int = 0) -> SPACEParameter:
        """
        Parse SPACE parameter string into structured object.

        Args:
            space_string: SPACE parameter value
            line_number: Source line number

        Returns:
            SPACEParameter object
        """
        space_string = space_string.strip()
        if space_string.startswith("(") and space_string.endswith(")"):
            space_string = space_string[1:-1]

        subparams: dict[str, Any] = {}

        # Split by comma
        parts = self._split_parameters(space_string)

        if len(parts) >= 1:
            # First part is unit
            subparams["_unit"] = parts[0].strip().upper()

        if len(parts) >= 2:
            # Second part is (primary,secondary,directory)
            alloc_part = parts[1].strip()
            if alloc_part.startswith("(") and alloc_part.endswith(")"):
                alloc_part = alloc_part[1:-1]

            alloc_values = alloc_part.split(",")
            if len(alloc_values) >= 1:
                subparams["_primary"] = alloc_values[0].strip()
            if len(alloc_values) >= 2:
                subparams["_secondary"] = alloc_values[1].strip()
            if len(alloc_values) >= 3:
                subparams["_directory"] = alloc_values[2].strip()

        # Remaining parts are options (RLSE, CONTIG, ROUND); an omitted one
        # (``SPACE=(CYL,(1,1),,CONTIG)``) is just its comma.
        for i in range(2, len(parts)):
            option = parts[i].strip().upper()
            if option:
                subparams[option] = True

        logger.debug(
            "parsed SPACE at line %d into %d subparameter(s)",
            line_number,
            len(subparams),
        )
        return SPACEParameter(
            key="SPACE",
            raw_value=space_string,
            subparameters=subparams,
            line_number=line_number,
        )

    def _split_parameters(self, param_string: str) -> list[str]:
        """
        Split parameter string by comma, respecting parentheses and JCL-quoted strings.

        In JCL, a quoted string is delimited by ``'...'``.  A literal apostrophe
        inside a quoted string is represented by ``''`` (two consecutive single
        quotes).  Both pairs must be consumed together so the quote-depth
        tracker stays correct.

        Empty positional subfields are preserved (e.g. the omitted accounting
        info in ``JOB ,'PROGRAMMER',CLASS=A``, or an omitted DCB/SPACE
        subparameter) so later positionals keep their index -- mirrors
        ``_parse_list_parameter``'s handling of ``DISP=(,CATLG,DELETE)``.
        Only trailing empty elements (from a trailing comma) are stripped.

        Args:
            param_string: Parameter string to split

        Returns:
            List of parameter parts
        """
        parts = []
        current_parts: list[str] = []
        paren_depth = 0
        in_quotes = False
        i = 0

        while i < len(param_string):
            char = param_string[i]

            if in_quotes:
                if char == "'":
                    # Look-ahead: is this the start of an escaped '' pair?
                    if i + 1 < len(param_string) and param_string[i + 1] == "'":
                        # Escaped apostrophe — consume both and stay in-quotes
                        current_parts.append("''")
                        i += 2
                        continue
                    else:
                        # Closing quote
                        in_quotes = False
                        current_parts.append(char)
                else:
                    current_parts.append(char)
            else:
                if char == "'":
                    in_quotes = True
                    current_parts.append(char)
                elif char == "(":
                    paren_depth += 1
                    current_parts.append(char)
                elif char == ")":
                    paren_depth -= 1
                    current_parts.append(char)
                elif char == "," and paren_depth == 0:
                    parts.append("".join(current_parts).strip())
                    current_parts = []
                else:
                    current_parts.append(char)

            i += 1

        parts.append("".join(current_parts).strip())

        # Strip trailing empty elements (from a trailing comma) but keep
        # internal ones -- they are meaningful omitted positional subfields.
        while parts and parts[-1] == "":
            parts.pop()

        return parts
