"""
Abstract Syntax Tree for JCL parameters.

Provides structured representation of complex parameters like DCB, SPACE, etc.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Module-level frozensets for DCB/SPACE validation (avoids per-call list construction)
_VALID_RECFM = frozenset({'F', 'FB', 'FBA', 'FBM', 'FBS', 'V', 'VB', 'VBA', 'VBM', 'VBS', 'U', 'D', 'DB'})
_VALID_DSORG = frozenset({'PS', 'PO', 'DA', 'IS', 'VS'})


@dataclass
class ParameterNode:
    """Base class for parameter AST nodes."""
    raw_value: str
    line_number: int = 0


@dataclass
class SimpleParameter(ParameterNode):
    """Simple key=value parameter."""
    key: str = ""
    value: str = ""


@dataclass
class ListParameter(ParameterNode):
    """List parameter: KEY=(val1,val2,val3)."""
    key: str = ""
    values: List[str] = field(default_factory=list)


@dataclass
class NestedParameter(ParameterNode):
    """Nested parameter: KEY=(SUB1=val1,SUB2=val2)."""
    key: str = ""
    subparameters: Dict[str, Any] = field(default_factory=dict)


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
    def recfm(self) -> Optional[str]:
        """Record format."""
        return self.subparameters.get("RECFM")
    
    @property
    def lrecl(self) -> Optional[int]:
        """Logical record length."""
        val = self.subparameters.get("LRECL")
        return int(val) if val and str(val).isdigit() else None
    
    @property
    def blksize(self) -> Optional[int]:
        """Block size."""
        val = self.subparameters.get("BLKSIZE")
        return int(val) if val and str(val).isdigit() else None
    
    @property
    def bufno(self) -> Optional[int]:
        """Number of buffers."""
        val = self.subparameters.get("BUFNO")
        return int(val) if val and str(val).isdigit() else None
    
    @property
    def dsorg(self) -> Optional[str]:
        """Dataset organization."""
        return self.subparameters.get("DSORG")
    
    def validate(self) -> List[str]:
        """
        Validate DCB parameters.
        
        Returns:
            List of validation error messages
        """
        errors = []
        
        # Validate RECFM
        if self.recfm:
            if self.recfm not in _VALID_RECFM:
                errors.append(f"Invalid RECFM value: {self.recfm}")
        
        # Validate LRECL
        if self.lrecl is not None:
            if self.lrecl < 1 or self.lrecl > 32760:
                errors.append(f"LRECL out of range (1-32760): {self.lrecl}")
        
        # Validate BLKSIZE
        if self.blksize is not None:
            if self.blksize < 1 or self.blksize > 32760:
                errors.append(f"BLKSIZE out of range (1-32760): {self.blksize}")
            
            # BLKSIZE should be multiple of LRECL for fixed-length records
            if self.lrecl and self.recfm and self.recfm.startswith('F'):
                if self.blksize % self.lrecl != 0:
                    errors.append(
                        f"BLKSIZE ({self.blksize}) should be multiple of "
                        f"LRECL ({self.lrecl}) for fixed-length records"
                    )
        
        # Validate DSORG
        if self.dsorg:
            if self.dsorg not in _VALID_DSORG:
                errors.append(f"Invalid DSORG value: {self.dsorg}")
        
        return errors


@dataclass
class SPACEParameter(NestedParameter):
    """
    Structured SPACE parameter.
    
    Format: SPACE=(unit,(primary,secondary,directory),RLSE,CONTIG/ROUND)
    """
    
    @property
    def unit(self) -> Optional[str]:
        """Space allocation unit (TRK, CYL, blksize)."""
        # First positional parameter
        return self.subparameters.get("_unit")
    
    @property
    def primary(self) -> Optional[int]:
        """Primary space allocation."""
        val = self.subparameters.get("_primary")
        if val:
            try:
                return int(val)
            except ValueError:
                return None
        return None
    
    @property
    def secondary(self) -> Optional[int]:
        """Secondary space allocation."""
        val = self.subparameters.get("_secondary")
        if val:
            try:
                return int(val)
            except ValueError:
                return None
        return None
    
    @property
    def directory(self) -> Optional[int]:
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
    
    def validate(self) -> List[str]:
        """Validate SPACE parameters."""
        errors = []
        
        # Validate unit
        if self.unit:
            valid_units = ['TRK', 'CYL']
            if self.unit not in valid_units and not self.unit.isdigit():
                errors.append(f"Invalid SPACE unit: {self.unit}")
        
        # Validate primary > 0
        if self.primary is not None and self.primary < 1:
            errors.append(f"Primary space must be > 0: {self.primary}")
        
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
        if dcb_string.startswith('(') and dcb_string.endswith(')'):
            dcb_string = dcb_string[1:-1]
        
        subparams = {}
        
        # Split by comma (respecting nested parentheses)
        parts = self._split_parameters(dcb_string)
        
        for part in parts:
            if '=' in part:
                key, value = part.split('=', 1)
                subparams[key.strip().upper()] = value.strip()
        
        return DCBParameter(
            key="DCB",
            raw_value=dcb_string,
            subparameters=subparams,
            line_number=line_number
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
        if space_string.startswith('(') and space_string.endswith(')'):
            space_string = space_string[1:-1]
        
        subparams: Dict[str, Any] = {}

        # Split by comma
        parts = self._split_parameters(space_string)
        
        if len(parts) >= 1:
            # First part is unit
            subparams["_unit"] = parts[0].strip().upper()
        
        if len(parts) >= 2:
            # Second part is (primary,secondary,directory)
            alloc_part = parts[1].strip()
            if alloc_part.startswith('(') and alloc_part.endswith(')'):
                alloc_part = alloc_part[1:-1]
            
            alloc_values = alloc_part.split(',')
            if len(alloc_values) >= 1:
                subparams["_primary"] = alloc_values[0].strip()
            if len(alloc_values) >= 2:
                subparams["_secondary"] = alloc_values[1].strip()
            if len(alloc_values) >= 3:
                subparams["_directory"] = alloc_values[2].strip()
        
        # Remaining parts are options (RLSE, CONTIG, ROUND)
        for i in range(2, len(parts)):
            option = parts[i].strip().upper()
            subparams[option] = True
        
        return SPACEParameter(
            key="SPACE",
            raw_value=space_string,
            subparameters=subparams,
            line_number=line_number
        )
    
    def _split_parameters(self, param_string: str) -> List[str]:
        """
        Split parameter string by comma, respecting parentheses and JCL-quoted strings.

        In JCL, a quoted string is delimited by ``'...'``.  A literal apostrophe
        inside a quoted string is represented by ``''`` (two consecutive single
        quotes).  Both pairs must be consumed together so the quote-depth
        tracker stays correct.

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
                    current = "".join(current_parts).strip()
                    if current:
                        parts.append(current)
                    current_parts = []
                else:
                    current_parts.append(char)

            i += 1

        current = "".join(current_parts).strip()
        if current:
            parts.append(current)

        return parts
