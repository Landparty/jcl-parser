"""
Data model classes for representing parsed JCL structures.

Contains dataclasses for Job, Step, DDStatement, and Parameter entities
with validation methods and type safety.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union
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
        condition: Conditional expression string
        then_steps: Steps to execute if condition is true
        else_steps: Steps to execute if condition is false (optional)
        line_number: Source line number
    """
    condition: str
    then_steps: List['Step'] = field(default_factory=list)
    else_steps: List['Step'] = field(default_factory=list)
    line_number: int = 0
    
    def add_then_step(self, step: 'Step') -> None:
        """Add a step to the THEN block"""
        self.then_steps.append(step)
    
    def add_else_step(self, step: 'Step') -> None:
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
    steps: List['Step'] = field(default_factory=list)
    line_number: int = 0
    
    def add_step(self, step: 'Step') -> None:
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
    _dcb_parsed: Optional[DCBParameter] = field(default=None, init=False, repr=False)
    _space_parsed: Optional[SPACEParameter] = field(default=None, init=False, repr=False)
    
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
    def has_inline_data(self) -> bool:
        """True if this DD contains inline data (DD *)"""
        return self.inline_data is not None
    
    def is_input(self) -> bool:
        """True if this DD defines input data"""
        if self.disposition:
            # Handle both string and list disposition
            if isinstance(self.disposition, list):
                disp_upper = [d.upper() if isinstance(d, str) else str(d).upper() for d in self.disposition]
                return any(d in ["OLD", "SHR"] for d in disp_upper)
            disp = self.disposition.upper() if isinstance(self.disposition, str) else str(self.disposition).upper()
            return "SHR" in disp or "OLD" in disp
        return False
    
    def is_output(self) -> bool:
        """True if this DD defines output data"""
        if self.disposition:
            # Handle both string and list disposition
            if isinstance(self.disposition, list):
                disp_upper = [d.upper() if isinstance(d, str) else str(d).upper() for d in self.disposition]
                return any(d in ["NEW", "MOD", "CATLG"] for d in disp_upper)
            disp = self.disposition.upper() if isinstance(self.disposition, str) else str(self.disposition).upper()
            return "NEW" in disp or "CATLG" in disp
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
    
    @property
    def is_proc_invocation(self) -> bool:
        """True if step is a procedure invocation (alias for is_procedure)"""
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
    steps: List[Step] = field(default_factory=list)
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
    
    def add_step(self, step: Step) -> None:
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
        for step in self.steps:
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
        for step in self.steps:
            all_dds.extend(step.dd_statements)
        return all_dds
    
    def validate(self) -> List[ValidationError]:
        """Validate job structure and dependencies"""
        errors = []
        
        # Job must have a name
        if not self.name or not self.name.strip():
            errors.append(ValidationError(
                "Job must have a name",
                ErrorType.VALIDATION_ERROR
            ))
        elif len(self.name) > 8:
            errors.append(ValidationError(
                f"Invalid job name '{self.name}': must be 1-8 characters",
                ErrorType.VALIDATION_ERROR
            ))
        
        # Job must have at least one step
        if not self.steps:
            errors.append(ValidationError(
                "Job must contain at least one execution step",
                ErrorType.STRUCTURE_ERROR
            ))
        
        # Validate step names are unique
        step_names = []
        for step in self.steps:
            if step.name:
                if step.name in step_names:
                    errors.append(ValidationError(
                        f"Duplicate step name: {step.name}",
                        ErrorType.VALIDATION_ERROR
                    ))
                else:
                    step_names.append(step.name)
        
        # Validate each step
        for step in self.steps:
            errors.extend(self._validate_step(step))
        
        return errors
    
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
    
    def _validate_step(self, step: Step) -> List[ValidationError]:
        """Validate a single step"""
        errors = []
        
        # Step must have program or procedure
        if not step.program and not step.procedure:
            errors.append(ValidationError(
                f"Step {step.name or '(unnamed)'} must specify a program or procedure",
                ErrorType.VALIDATION_ERROR
            ))
        
        # Validate DD names are unique within step (except for empty names used in concatenation)
        dd_names = []
        for dd in step.dd_statements:
            # Empty DD names are allowed for concatenation - skip duplicate check
            if dd.name and dd.name in dd_names:
                errors.append(ValidationError(
                    f"Duplicate DD name in step {step.name or '(unnamed)'}: {dd.name}",
                    ErrorType.VALIDATION_ERROR
                ))
            elif dd.name:  # Only add non-empty names to the list
                dd_names.append(dd.name)
        
        return errors