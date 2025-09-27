"""
Data model classes for representing parsed JCL structures.

Contains dataclasses for Job, Step, DDStatement, and Parameter entities
with validation methods and type safety.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union
from .errors import ValidationError, ErrorType


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
        type: Statement type (JOB, EXEC, DD, etc.)
        name: Statement name
        parameters: Dictionary of parameters
        line_number: Source line number
    """
    type: str
    name: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    line_number: int = 0


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
    
    @property
    def has_inline_data(self) -> bool:
        """True if this DD contains inline data (DD *)"""
        return self.inline_data is not None
    
    def is_input(self) -> bool:
        """True if this DD defines input data"""
        if self.disposition:
            disp = self.disposition.upper()
            return "SHR" in disp or "OLD" in disp
        return False
    
    def is_output(self) -> bool:
        """True if this DD defines output data"""
        if self.disposition:
            disp = self.disposition.upper()
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
    """
    name: Optional[str] = None
    program: Optional[str] = None
    procedure: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    dd_statements: List[DDStatement] = field(default_factory=list)
    comments: List[str] = field(default_factory=list)
    line_number: int = 0
    
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
        comments: Job-level comments
        line_number: Source line number
    """
    name: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    accounting_info: Optional[str] = None
    steps: List[Step] = field(default_factory=list)
    comments: List[str] = field(default_factory=list)
    line_number: int = 0
    
    def add_step(self, step: Step) -> None:
        """Add an execution step to this job"""
        self.steps.append(step)
    
    def get_step(self, name: str) -> Optional[Step]:
        """Find step by name"""
        for step in self.steps:
            if step.name == name:
                return step
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
    
    def _validate_step(self, step: Step) -> List[ValidationError]:
        """Validate a single step"""
        errors = []
        
        # Step must have program or procedure
        if not step.program and not step.procedure:
            errors.append(ValidationError(
                f"Step {step.name or '(unnamed)'} must specify a program or procedure",
                ErrorType.VALIDATION_ERROR
            ))
        
        # Validate DD names are unique within step
        dd_names = []
        for dd in step.dd_statements:
            if dd.name in dd_names:
                errors.append(ValidationError(
                    f"Duplicate DD name in step {step.name or '(unnamed)'}: {dd.name}",
                    ErrorType.VALIDATION_ERROR
                ))
            else:
                dd_names.append(dd.name)
        
        return errors