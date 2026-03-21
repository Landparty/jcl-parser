"""
Data model classes for representing parsed JCL structures.

Contains dataclasses for Job, Step, DDStatement, and Parameter entities
with validation methods and type safety.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union, Iterator
from .errors import ValidationError, ErrorType
from .parameter_ast import DCBParameter, SPACEParameter, ParameterParser


@dataclass
class Parameter:
    """
    Represents a parsed parameter with type awareness.
    
    Attributes:
        name: Parameter name
        value: Parameter value (supports strings, lists, dicts)
        quoted: Whether the original value was quoted
        line_number: Source line for error reporting
    """
    name: str
    value: Union[str, List[str], Dict[str, str]]
    quoted: bool = False
    line_number: int = 0


@dataclass
class Statement:
    """
    Base class for JCL statements.
    
    Attributes:
        type: Statement type (JOB, EXEC, DD, PROC, SET, IF, etc.)
        name: Statement name
        parameters: Dictionary of parameters
        line_number: Source line number
    """
    type: str
    name: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    line_number: int = 0


@dataclass
class ConditionalBlock:
    """
    Represents an IF/THEN/ELSE conditional block.

    Attributes:
        condition: Conditional expression string (raw, always populated)
        then_steps: Steps to execute if condition is true
        else_steps: Steps to execute if condition is false (optional)
        line_number: Source line number
        condition_ast: Structured AST of the condition expression, or None if
            the condition could not be parsed into a known structure.
            Use :func:`jclparser.condition_parser.parse_condition` to obtain
            this value; it is populated automatically by the parser.
    """
    condition: str
    then_steps: List[Union['Step', 'ConditionalBlock']] = field(default_factory=list)
    else_steps: List[Union['Step', 'ConditionalBlock']] = field(default_factory=list)
    line_number: int = 0
    condition_ast: Any = field(default=None, repr=False)
    
    def add_then_step(self, step: Union['Step', 'ConditionalBlock']) -> None:
        """Add a step to the THEN block"""
        self.then_steps.append(step)
    
    def add_else_step(self, step: Union['Step', 'ConditionalBlock']) -> None:
        """Add a step to the ELSE block"""
        self.else_steps.append(step)


@dataclass
class Procedure:
    """
    Represents a PROC (procedure) definition.
    
    Attributes:
        name: Procedure name
        parameters: PROC parameters with defaults
        steps: Steps within the procedure
        line_number: Source line number
    """
    name: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    steps: List[Union['Step', 'ConditionalBlock']] = field(default_factory=list)
    line_number: int = 0
    
    def add_step(self, step: Union['Step', 'ConditionalBlock']) -> None:
        """Add a step to this procedure"""
        self.steps.append(step)


@dataclass
class DDStatement:
    """
    Represents a DD (Data Definition) statement.
    
    Attributes:
        name: DD name (e.g., "SYSOUT", "INPUT")
        dataset_name: Dataset name from DSN parameter
        disposition: DISP parameter value
        parameters: All DD parameters
        inline_data: In-stream data content for DD *
        comments: DD-level comments
        line_number: Source line number
    """
    name: str
    dataset_name: Optional[str] = None
    disposition: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    inline_data: Optional[str] = None
    comments: List[str] = field(default_factory=list)
    line_number: int = 0
    
    # Cached parsed parameters (not included in __init__)
    _dcb_parsed: Optional[DCBParameter] = field(default=None, init=False, repr=False, compare=False)
    _space_parsed: Optional[SPACEParameter] = field(default=None, init=False, repr=False, compare=False)
    _disp_tokens_cache: Optional[list] = field(default=None, init=False, repr=False, compare=False)
    
    @property
    def dcb(self) -> Optional[DCBParameter]:
        """
        Get parsed DCB parameter.
        
        Returns:
            DCBParameter object or None if no DCB parameter
            
        Example:
            >>> dd.dcb.recfm  # 'FB'
            >>> dd.dcb.lrecl  # 80
            >>> dd.dcb.blksize  # 27920
        """
        if self._dcb_parsed is None and "DCB" in self.parameters:
            parser = ParameterParser()
            dcb_value = self.parameters["DCB"]
            if isinstance(dcb_value, str):
                self._dcb_parsed = parser.parse_dcb(dcb_value, self.line_number)
            elif isinstance(dcb_value, list):
                # Handle list format
                dcb_str = ','.join(str(v) for v in dcb_value)
                self._dcb_parsed = parser.parse_dcb(dcb_str, self.line_number)
        
        return self._dcb_parsed
    
    @property
    def space(self) -> Optional[SPACEParameter]:
        """
        Get parsed SPACE parameter.
        
        Returns:
            SPACEParameter object or None if no SPACE parameter
            
        Example:
            >>> dd.space.unit  # 'CYL'
            >>> dd.space.primary  # 10
            >>> dd.space.secondary  # 5
            >>> dd.space.rlse  # True
        """
        if self._space_parsed is None and "SPACE" in self.parameters:
            parser = ParameterParser()
            space_value = self.parameters["SPACE"]
            if isinstance(space_value, str):
                self._space_parsed = parser.parse_space(space_value, self.line_number)
            elif isinstance(space_value, list):
                space_str = ','.join(str(v) for v in space_value)
                self._space_parsed = parser.parse_space(space_str, self.line_number)
        
        return self._space_parsed
    
    @property
    def dataclas(self) -> Optional[str]:
        """
        Get DATACLAS (SMS data class) parameter.
        
        Returns:
            DATACLAS value or None if not specified
            
        Example:
            >>> dd.dataclas  # 'DCPROD'
        """
        return self.parameters.get('DATACLAS')
    
    @property
    def mgmtclas(self) -> Optional[str]:
        """
        Get MGMTCLAS (SMS management class) parameter.
        
        Returns:
            MGMTCLAS value or None if not specified
            
        Example:
            >>> dd.mgmtclas  # 'MCPROD'
        """
        return self.parameters.get('MGMTCLAS')
    
    @property
    def storclas(self) -> Optional[str]:
        """
        Get STORCLAS (SMS storage class) parameter.
        
        Returns:
            STORCLAS value or None if not specified
            
        Example:
            >>> dd.storclas  # 'SCPROD'
        """
        return self.parameters.get('STORCLAS')
    
    @property
    def dsntype(self) -> Optional[str]:
        """
        Get DSNTYPE (Dataset Type) parameter.
        
        Returns:
            DSNTYPE value or None if not specified
            
        Example:
            >>> dd.dsntype  # 'LIBRARY'
        """
        return self.parameters.get('DSNTYPE')
    
    @property
    def has_inline_data(self) -> bool:
        """True if this DD contains inline data (DD *)"""
        return self.inline_data is not None
    
    # Disposition sets used by is_input / is_output.  Defined at class scope
    # so the sets are built once and shared across all instances.
    _INPUT_DISPOSITIONS: frozenset = frozenset({"OLD", "SHR"})
    _OUTPUT_DISPOSITIONS: frozenset = frozenset({"NEW", "MOD", "CATLG", "UNCATLG"})

    def _disp_tokens(self) -> List[str]:
        """Return disposition as an uppercase list of individual tokens (cached)."""
        if self._disp_tokens_cache is None:
            if isinstance(self.disposition, list):
                result = [
                    (d.upper() if isinstance(d, str) else str(d).upper())
                    for d in self.disposition
                ]
            else:
                # String form: may be bare "SHR", "(NEW,CATLG,DELETE)", or "NEW,CATLG"
                result = [
                    t.strip()
                    for t in str(self.disposition).upper().strip("()").split(",")
                ]
            self._disp_tokens_cache = result
        return self._disp_tokens_cache

    def is_input(self) -> bool:
        """True if this DD defines input data (DISP status is OLD or SHR)."""
        if self.disposition:
            return any(t in self._INPUT_DISPOSITIONS for t in self._disp_tokens())
        return False

    def is_output(self) -> bool:
        """True if this DD defines output data (DISP status is NEW, MOD, CATLG, or UNCATLG)."""
        if self.disposition:
            return any(t in self._OUTPUT_DISPOSITIONS for t in self._disp_tokens())
        return False
    
    def is_temporary(self) -> bool:
        """True if dataset is temporary (&&name)"""
        return self.dataset_name is not None and self.dataset_name.startswith("&&")


@dataclass
class Step:
    """
    Represents a single execution step within a job.
    
    Attributes:
        name: Step name (optional, generated if not provided)
        program: Program name from EXEC statement
        procedure: Procedure name if EXEC references procedure
        parameters: EXEC parameters (PARM, COND, etc.)
        dd_statements: Data definitions for this step
        comments: Step-level comments
        line_number: Source line number
        is_exploded: True if this step was generated from procedure explosion
        original_proc_call: Original procedure call step name (if exploded)
        dd_overrides: DD overrides for qualified DD names (PROC.STEP.DD format)
    """
    name: Optional[str] = None
    program: Optional[str] = None
    procedure: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    dd_statements: List[DDStatement] = field(default_factory=list)
    comments: List[str] = field(default_factory=list)
    line_number: int = 0
    is_exploded: bool = False
    original_proc_call: Optional[str] = None
    dd_overrides: Dict[str, DDStatement] = field(default_factory=dict)
    
    @property
    def is_procedure(self) -> bool:
        """True if step executes a procedure"""
        return self.procedure is not None
    
    def add_dd(self, dd_statement: DDStatement) -> None:
        """Add a DD statement to this step"""
        self.dd_statements.append(dd_statement)
    
    def get_dd(self, name: str) -> Optional[DDStatement]:
        """Find DD statement by name"""
        for dd in self.dd_statements:
            if dd.name == name:
                return dd
        return None

    @property
    def sysin(self) -> Optional[DDStatement]:
        """Return the SYSIN DD statement for this step, or None if not present."""
        return self.get_dd("SYSIN")

    def get_input_datasets(self) -> List[str]:
        """Get all input dataset names"""
        datasets = []
        for dd in self.dd_statements:
            if dd.is_input() and dd.dataset_name:
                datasets.append(dd.dataset_name)
        return datasets
    
    def get_output_datasets(self) -> List[str]:
        """Get all output dataset names"""
        datasets = []
        for dd in self.dd_statements:
            if dd.is_output() and dd.dataset_name:
                datasets.append(dd.dataset_name)
        return datasets
    
    # EXEC Parameter Properties (KISS - simple accessors)
    
    @property
    def dynamnbr(self) -> Optional[int]:
        """Dynamic allocation count."""
        val = self.parameters.get('DYNAMNBR')
        return int(val) if val else None
    
    @property
    def memlimit(self) -> Optional[str]:
        """Memory limit above the bar (e.g., '2G')."""
        return self.parameters.get('MEMLIMIT')
    
    @property
    def acct(self) -> Optional[Union[str, List[str]]]:
        """Step-level accounting."""
        return self.parameters.get('ACCT')
    
    @property
    def addrspc(self) -> Optional[str]:
        """Address space type (REAL, VIRT)."""
        return self.parameters.get('ADDRSPC')
    
    @property
    def dprty(self) -> Optional[Union[str, List[int]]]:
        """Dispatching priority."""
        return self.parameters.get('DPRTY')
    
    @property
    def perform(self) -> Optional[int]:
        """Performance group."""
        val = self.parameters.get('PERFORM')
        return int(val) if val else None
    
    @property
    def rd(self) -> Optional[str]:
        """Restart definition (R, RNC, NR, NC)."""
        return self.parameters.get('RD')


@dataclass  
class Job:
    """
    Represents a complete JCL job definition.
    
    Attributes:
        name: Job name from JOB statement
        parameters: Job parameters (accounting, class, etc.)
        accounting_info: Accounting information from JOB statement
        steps: Execution steps in order
        procedures: Inline procedure definitions
        conditionals: IF/THEN/ELSE conditional blocks
        set_statements: SET symbol definitions
        jcllib_order: JCLLIB library concatenation
        includes: INCLUDE member references
        comments: Job-level comments
        line_number: Source line number
        explosion_audit: Audit records from procedure explosion
        explosion_map: Cross-reference map of exploded procedures
    """
    name: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    accounting_info: Optional[str] = None
    steps: List[Union['Step', 'ConditionalBlock']] = field(default_factory=list)
    procedures: List[Procedure] = field(default_factory=list)
    conditionals: List[ConditionalBlock] = field(default_factory=list)
    set_statements: Dict[str, str] = field(default_factory=dict)
    jcllib_order: List[str] = field(default_factory=list)
    includes: List[str] = field(default_factory=list)
    comments: List[str] = field(default_factory=list)
    line_number: int = 0
    explosion_audit: List[Any] = field(default_factory=list)
    explosion_map: Dict[str, Any] = field(default_factory=dict)
    jes_statements: List[str] = field(default_factory=list)
    
    def add_step(self, step: Union['Step', 'ConditionalBlock']) -> None:
        """Add an execution step to this job"""
        self.steps.append(step)
    
    def add_procedure(self, procedure: Procedure) -> None:
        """Add an inline procedure definition"""
        self.procedures.append(procedure)
    
    def add_conditional(self, conditional: ConditionalBlock) -> None:
        """Add a conditional block"""
        self.conditionals.append(conditional)
    
    def add_set(self, symbol: str, value: str) -> None:
        """Add a SET symbol definition"""
        self.set_statements[symbol] = value
    
    def get_step(self, name: str) -> Optional[Step]:
        """Find step by name"""
        for step in iter_execution_steps(self.steps):
            if step.name == name:
                return step
        return None
    
    def get_procedure(self, name: str) -> Optional[Procedure]:
        """Find procedure by name"""
        for proc in self.procedures:
            if proc.name == name:
                return proc
        return None
    
    def get_dd_statements(self) -> List[DDStatement]:
        """Get all DD statements from all steps"""
        all_dds = []
        for step in iter_execution_steps(self.steps):
            all_dds.extend(step.dd_statements)
        return all_dds

    def get_sysin_statements(self) -> List[DDStatement]:
        """Return all SYSIN DD statements across every step in the job."""
        return [dd for dd in self.get_dd_statements() if dd.name == "SYSIN"]
    
    def validate(self) -> List[ValidationError]:
        """
        Validate job structure and dependencies.

        Delegates to :func:`jclparser.validators.validate_job_structure` which
        performs all structural checks *and* data-dependency validation.
        """
        from .validators import validate_job_structure
        return validate_job_structure(self)
    
    def explode(
        self,
        max_depth: int = 10,
        loader: Optional[Any] = None,
        audit: bool = True,
        system_provider: Optional[Any] = None,
        strict_symbols: bool = False
    ) -> 'Job':
        """
        Explode all procedure invocations in this job.
        
        Creates a new Job instance with all PROC invocations expanded into
        their constituent steps with symbolic parameters fully resolved.
        
        Args:
            max_depth: Maximum procedure nesting depth (default 10)
            loader: Optional custom procedure loader
            audit: Whether to generate audit logs (default True)
            system_provider: Optional system symbol provider
            strict_symbols: If True, raise errors for undefined symbols
            
        Returns:
            New Job instance with exploded procedures
            
        Raises:
            ExplosionDepthError: If nesting exceeds max_depth
            CircularProcedureError: If circular references detected
            ProcedureNotFoundError: If referenced procedure not found
            UndefinedSymbolError: If strict_symbols=True and symbol undefined
        """
        from .explosion import explode_job
        
        return explode_job(
            job=self,
            proc_loader=loader,
            max_depth=max_depth,
            audit=audit,
            system_provider=system_provider,
            strict_symbols=strict_symbols
        )
    
    # JOB Parameter Properties (KISS - simple accessors)
    
    @property
    def bytes_limit(self) -> Optional[Union[int, List]]:
        """Output byte limit."""
        return self.parameters.get('BYTES')
    
    @property
    def lines_limit(self) -> Optional[Union[int, List]]:
        """Output line limit."""
        return self.parameters.get('LINES')
    
    @property
    def pages_limit(self) -> Optional[Union[int, List]]:
        """Output page limit."""
        return self.parameters.get('PAGES')
    
    @property
    def sysaff(self) -> Optional[str]:
        """System affinity."""
        return self.parameters.get('SYSAFF')
    
    @property
    def schenv(self) -> Optional[str]:
        """Scheduling environment."""
        return self.parameters.get('SCHENV')


def iter_execution_steps(steps: List[Union[Step, ConditionalBlock]]) -> Iterator[Step]:
    """Recursively yield all flattened Step objects from a step list."""
    for s in steps:
        if isinstance(s, Step):
            yield s
        elif isinstance(s, ConditionalBlock):
            yield from iter_execution_steps(s.then_steps)
            yield from iter_execution_steps(s.else_steps)
