"""
Data model classes for representing parsed JCL structures.

Contains dataclasses for Job, Step, DDStatement, and Parameter entities
with validation methods and type safety.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from .errors import ValidationError
from .parameter_ast import DCBParameter, ParameterParser, SPACEParameter

if TYPE_CHECKING:
    from .sql_detector import SQLDetectionResult


def _to_int_or_none(val) -> int | None:
    """Coerce *val* to int, returning None for empty or unconvertible values."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


@dataclass
class OutputStatement:
    """
    Represents an OUTPUT JCL statement.

    OUTPUT statements define JES output descriptors that control how job
    output is printed or routed. They are referenced by DD statements via
    ``OUTPUT=(name,...)``.

    Attributes:
        name: OUTPUT statement name (referenced by DD OUTPUT= parameter)
        parameters: Raw parameter dictionary (all OUTPUT parameters)
        line_number: Source line number
        step_name: Name of the step the statement is coded in (a step-level
            OUTPUT statement), or ``None`` for a job-level one (coded before
            the first EXEC). Inside an in-stream PROC body it names the
            procedure step. ``DD OUTPUT=*.name`` resolves to the OUTPUT
            statement of that name in the DD's own step, else to the
            job-level one; ``*.stepname.name`` to the one in step
            *stepname*.
        procedure_name: Name of the in-stream PROC whose body holds the
            statement, ``None`` outside a PROC/PEND body.
        type: Always ``"OUTPUT"`` — kept for compatibility with generic Statement access
    """

    name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    line_number: int = 0
    step_name: str | None = None
    procedure_name: str | None = None
    type: str = field(default="OUTPUT", init=False, repr=False)

    @property
    def dest(self) -> str | None:
        """Output destination (DEST= parameter)."""
        return self.parameters.get("DEST")

    @property
    def output_class(self) -> str | None:
        """Spool output class (CLASS= parameter)."""
        return self.parameters.get("CLASS")

    @property
    def copies(self) -> int | None:
        """Number of copies to print (COPIES= parameter)."""
        return _to_int_or_none(self.parameters.get("COPIES"))

    @property
    def forms(self) -> str | None:
        """Forms name (FORMS= parameter)."""
        return self.parameters.get("FORMS")

    @property
    def writer(self) -> str | None:
        """External writer name (WRITER= parameter)."""
        return self.parameters.get("WRITER")

    @property
    def prty(self) -> int | None:
        """Output priority (PRTY= parameter)."""
        return _to_int_or_none(self.parameters.get("PRTY"))

    @property
    def jesds(self) -> str | None:
        """JES data set (JESDS= parameter: ALL, LOG, JCL, MSG)."""
        return self.parameters.get("JESDS")

    @property
    def outlim(self) -> int | None:
        """Output line limit (OUTLIM= parameter)."""
        return _to_int_or_none(self.parameters.get("OUTLIM"))

    @property
    def recfm(self) -> str | None:
        """Record format for output data set (RECFM= parameter)."""
        return self.parameters.get("RECFM")

    @property
    def lrecl(self) -> int | None:
        """Logical record length (LRECL= parameter)."""
        return _to_int_or_none(self.parameters.get("LRECL"))

    @property
    def chars(self) -> str | list | None:
        """Character arrangement table (CHARS= parameter)."""
        return self.parameters.get("CHARS")

    @property
    def fcb(self) -> str | None:
        """Forms control buffer (FCB= parameter)."""
        return self.parameters.get("FCB")

    @property
    def flash(self) -> str | list | None:
        """Overlay flash name (FLASH= parameter)."""
        return self.parameters.get("FLASH")

    @property
    def index(self) -> int | None:
        """Horizontal position index (INDEX= parameter)."""
        return _to_int_or_none(self.parameters.get("INDEX"))

    @classmethod
    def from_statement(
        cls,
        stmt: Statement,
        step_name: str | None = None,
        procedure_name: str | None = None,
    ) -> OutputStatement:
        """Create an OutputStatement from a generic Statement object."""
        return cls(
            name=stmt.name,
            parameters=stmt.parameters,
            line_number=stmt.line_number,
            step_name=step_name,
            procedure_name=procedure_name,
        )


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
    value: str | list[str] | dict[str, str]
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
    parameters: dict[str, Any] = field(default_factory=dict)
    line_number: int = 0
    #: Non-fatal issues detected while parsing this single statement (e.g. a
    #: duplicate keyword parameter that silently overwrote an earlier value).
    #: Propagated into :attr:`Job.warnings` by the main parse loop.
    warnings: list[str] = field(default_factory=list)


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
    then_steps: list[Step | ConditionalBlock] = field(default_factory=list)
    else_steps: list[Step | ConditionalBlock] = field(default_factory=list)
    line_number: int = 0
    condition_ast: Any = field(default=None, repr=False)

    def add_then_step(self, step: Step | ConditionalBlock) -> None:
        """Add a step to the THEN block"""
        self.then_steps.append(step)

    def add_else_step(self, step: Step | ConditionalBlock) -> None:
        """Add a step to the ELSE block"""
        self.else_steps.append(step)

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready dict; see :mod:`jclparser.serialization`."""
        from .serialization import conditional_to_dict

        return conditional_to_dict(self)


@dataclass
class Procedure:
    """
    Represents a PROC (procedure) definition.

    Attributes:
        name: Procedure name
        parameters: PROC parameters with defaults
        steps: Steps within the procedure
        line_number: Source line number
        set_statements: Symbols assigned by ``SET`` statements coded inside
            the procedure body. They take effect only when the procedure is
            expanded, and never leak into the calling job's SET table.
    """

    name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    steps: list[Step | ConditionalBlock] = field(default_factory=list)
    line_number: int = 0
    is_external: bool = False
    set_statements: dict[str, str] = field(default_factory=dict)

    def add_step(self, step: Step | ConditionalBlock) -> None:
        """Add a step to this procedure"""
        self.steps.append(step)

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready dict; see :mod:`jclparser.serialization`."""
        from .serialization import procedure_to_dict

        return procedure_to_dict(self)


@dataclass
class DDStatement:
    """
    Represents a DD (Data Definition) statement.

    Attributes:
        name: DD name (e.g., "SYSOUT", "INPUT")
        dataset_name: Dataset name from DSN parameter
        disposition: DISP parameter value -- a string for a bare status
            (``"SHR"``), a list for a parenthesised one (``["NEW", "CATLG"]``)
        parameters: All DD parameters
        inline_data: In-stream data content for DD *
        comments: DD-level comments
        line_number: Source line number
    """

    name: str
    dataset_name: str | None = None
    disposition: str | list[str] | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    inline_data: str | None = None
    comments: list[str] = field(default_factory=list)
    line_number: int = 0
    #: Resolved :class:`OutputStatement` objects referenced by this DD via
    #: ``OUTPUT=*.name``.  Populated by ``parse_jcl`` after the full job has
    #: been parsed.  ``OUTPUT=*.NAME`` values that do not match any OUTPUT
    #: statement in the job are recorded on :attr:`Job.unresolved_output_refs`
    #: instead of here.
    output_refs: list[OutputStatement] = field(
        default_factory=list, repr=False, compare=False
    )
    #: The dataset name as coded, before any symbol substitution (e.g.
    #: ``"&HLQ..DATA"`` when :attr:`dataset_name` now reads ``"PROD.DATA"``).
    #: ``None`` when the coded name had no symbols to substitute.
    coded_dataset_name: str | None = field(default=None, repr=False, compare=False)

    # Cached parsed parameters (not included in __init__)
    _dcb_parsed: DCBParameter | None = field(
        default=None, init=False, repr=False, compare=False
    )
    _space_parsed: SPACEParameter | None = field(
        default=None, init=False, repr=False, compare=False
    )
    _disp_tokens_cache: list | None = field(
        default=None, init=False, repr=False, compare=False
    )

    def __setattr__(self, name: str, value) -> None:
        object.__setattr__(self, name, value)
        # Invalidate lazy parse caches whenever the backing data fields change.
        # Use __dict__ membership to avoid AttributeError during __init__ (the
        # cache fields are declared with init=False so they are set last).
        d = self.__dict__
        if name == "parameters":
            if "_dcb_parsed" in d:
                object.__setattr__(self, "_dcb_parsed", None)
            if "_space_parsed" in d:
                object.__setattr__(self, "_space_parsed", None)
        elif name == "disposition" and "_disp_tokens_cache" in d:
            object.__setattr__(self, "_disp_tokens_cache", None)

    def _lazy_parse_param(self, key: str, cache_attr: str, parse_method: str):
        """Return the cached parsed form of a structured DD parameter.

        Reads ``self.parameters[key]`` and only parses supported textual forms:
        a string value or a list of values joined with commas.  Unsupported
        runtime types are ignored and return ``None`` rather than raising from
        ``ParameterParser.<parse_method>``.  The result is stored on *cache_attr*
        so subsequent calls skip parsing entirely.
        """
        cached = getattr(self, cache_attr)
        if cached is None and key in self.parameters:
            raw = self.parameters[key]
            if isinstance(raw, list):
                param_str = ",".join(str(v) for v in raw)
            elif isinstance(raw, str):
                param_str = raw
            else:
                return None
            parser = ParameterParser()
            cached = getattr(parser, parse_method)(param_str, self.line_number)
            object.__setattr__(self, cache_attr, cached)
        return cached

    @property
    def dcb(self) -> DCBParameter | None:
        """
        Get parsed DCB parameter.

        Returns:
            DCBParameter object or None if no DCB parameter

        Example:
            >>> dd.dcb.recfm  # 'FB'
            >>> dd.dcb.lrecl  # 80
            >>> dd.dcb.blksize  # 27920

        DCB subparameters coded directly on the DD (``RECFM=FB,LRECL=80``
        with no ``DCB=``) are included too, and override the same
        subparameter inside ``DCB=``.
        """
        if self._dcb_parsed is not None:
            return self._dcb_parsed
        dcb = self._lazy_parse_param("DCB", "_dcb_parsed", "parse_dcb")
        dd_level = {
            key: str(value)
            for key in self._DD_LEVEL_DCB_KEYWORDS
            if isinstance(value := self.parameters.get(key), (str, int))
        }
        if dd_level:
            if dcb is None:
                dcb = DCBParameter(
                    key="DCB",
                    raw_value=",".join(f"{k}={v}" for k, v in dd_level.items()),
                    subparameters=dict(dd_level),
                    line_number=self.line_number,
                )
            else:
                dcb.subparameters.update(dd_level)
            object.__setattr__(self, "_dcb_parsed", dcb)
        return dcb

    @property
    def space(self) -> SPACEParameter | None:
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
        return self._lazy_parse_param("SPACE", "_space_parsed", "parse_space")

    @property
    def dataclas(self) -> str | None:
        """
        Get DATACLAS (SMS data class) parameter.

        Returns:
            DATACLAS value or None if not specified

        Example:
            >>> dd.dataclas  # 'DCPROD'
        """
        return self.parameters.get("DATACLAS")

    @property
    def mgmtclas(self) -> str | None:
        """
        Get MGMTCLAS (SMS management class) parameter.

        Returns:
            MGMTCLAS value or None if not specified

        Example:
            >>> dd.mgmtclas  # 'MCPROD'
        """
        return self.parameters.get("MGMTCLAS")

    @property
    def storclas(self) -> str | None:
        """
        Get STORCLAS (SMS storage class) parameter.

        Returns:
            STORCLAS value or None if not specified

        Example:
            >>> dd.storclas  # 'SCPROD'
        """
        return self.parameters.get("STORCLAS")

    @property
    def dsntype(self) -> str | None:
        """
        Get DSNTYPE (Dataset Type) parameter.

        Returns:
            DSNTYPE value or None if not specified

        Example:
            >>> dd.dsntype  # 'LIBRARY'
        """
        return self.parameters.get("DSNTYPE")

    @property
    def has_inline_data(self) -> bool:
        """True if this DD contains inline data (DD *)"""
        return self.inline_data is not None

    # DISP status values used by is_input / is_output.  Defined at class scope
    # (ClassVar, so not dataclass fields) and shared across all instances.
    _INPUT_DISPOSITIONS: ClassVar[frozenset[str]] = frozenset({"OLD", "SHR"})
    _OUTPUT_DISPOSITIONS: ClassVar[frozenset[str]] = frozenset({"NEW", "MOD"})
    # DCB subparameters that may also be coded as DD keywords of their own.
    _DD_LEVEL_DCB_KEYWORDS: ClassVar[tuple[str, ...]] = (
        "RECFM",
        "LRECL",
        "BLKSIZE",
        "DSORG",
        "BUFNO",
        "KEYLEN",
        "OPTCD",
    )

    def _disp_tokens(self) -> list[str]:
        """Return disposition as an uppercase list of individual tokens (cached).

        An omitted status (``DISP=(,CATLG)``) is reported as ``NEW``.
        """
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
            # An omitted status (DISP=(,CATLG)) defaults to NEW in JCL.
            if result and not result[0]:
                result[0] = "NEW"
            self._disp_tokens_cache = result
        return self._disp_tokens_cache

    def _disp_status(self) -> str | None:
        """Return the DISP status (first token).

        With no DISP, a DD that names a dataset defaults to ``NEW`` -- z/OS
        treats an omitted DISP as ``(NEW,DELETE)`` (issue #105).  A backward
        reference (``DSN=*.S.DD``), ``NULLFILE`` and a ``DUMMY`` DD define no
        new data, so they still report None.
        """
        if self.disposition:
            tokens = self._disp_tokens()
            return tokens[0] if tokens else None
        if self._defaults_to_new():
            return "NEW"
        return None

    def _defaults_to_new(self) -> bool:
        """True if this DD, coded without DISP, defines a new dataset."""
        dsn = self.dataset_name
        if not dsn or dsn.startswith("*") or dsn.upper() == "NULLFILE":
            return False
        return not any(
            key.startswith("_pos_") and str(value).upper() == "DUMMY"
            for key, value in self.parameters.items()
        )

    def is_input(self) -> bool:
        """True if this DD defines input data (DISP status is OLD or SHR).

        Only the status subparameter counts; the normal/abnormal
        dispositions (KEEP, CATLG, ...) say nothing about data direction.
        """
        return self._disp_status() in self._INPUT_DISPOSITIONS

    def is_output(self) -> bool:
        """True if this DD defines output data (DISP status is NEW or MOD).

        An omitted status (``DISP=(,CATLG)``) and an omitted DISP on a DD
        that names a dataset both default to NEW.  CATLG/UNCATLG
        in the disposition positions do not make ``DISP=(SHR,PASS,CATLG)`` an
        output.
        """
        return self._disp_status() in self._OUTPUT_DISPOSITIONS

    def is_temporary(self) -> bool:
        """True if dataset is temporary (&&name)"""
        return self.dataset_name is not None and self.dataset_name.startswith("&&")

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready dict; see :mod:`jclparser.serialization`."""
        from .serialization import dd_to_dict

        return dd_to_dict(self)


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
        dd_override_concatenations: For a qualified override key in
            ``dd_overrides``, the unnamed DDs coded after it -- overrides of
            the 2nd, 3rd, ... members of that DD's concatenation, in order
        set_symbols: SET symbols in effect at this step when a later SET
            redefines one of them, else None
    """

    name: str | None = None
    program: str | None = None
    procedure: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    dd_statements: list[DDStatement] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)
    line_number: int = 0
    is_exploded: bool = False
    original_proc_call: str | None = None
    dd_overrides: dict[str, DDStatement] = field(default_factory=dict)
    dd_override_concatenations: dict[str, list[DDStatement]] = field(
        default_factory=dict
    )
    #: The job's SET symbols as they stood when this step's EXEC was read
    #: (for a step inside a PROC body, the procedure's own SETs), kept only
    #: when a later ``SET`` redefines one of them (``None`` otherwise): a SET
    #: value is in effect from the SET statement onward, so this step's
    #: ``&SYM`` references must not see the redefinition.
    set_symbols: dict[str, str] | None = field(default=None, repr=False, compare=False)

    @property
    def is_procedure(self) -> bool:
        """True if step executes a procedure"""
        return self.procedure is not None

    def add_dd(self, dd_statement: DDStatement) -> None:
        """Add a DD statement to this step"""
        self.dd_statements.append(dd_statement)

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready dict; see :mod:`jclparser.serialization`."""
        from .serialization import step_to_dict

        return step_to_dict(self)

    def get_dd(self, name: str) -> DDStatement | None:
        """Find DD statement by name"""
        for dd in self.dd_statements:
            if dd.name == name:
                return dd
        return None

    @property
    def sysin(self) -> DDStatement | None:
        """Return the SYSIN DD statement for this step, or None if not present."""
        return self.get_dd("SYSIN")

    @property
    def steplib(self) -> list[str]:
        """Dataset names in the STEPLIB concatenation for this step, in order.

        STEPLIB overrides the job-level JOBLIB for program loading.  Returns
        the ordered list of DSN strings; empty list if no STEPLIB is defined
        on this step.

        Handles DD concatenation: empty-name ``//  DD DSN=...`` cards that
        immediately follow the ``//STEPLIB DD`` card are included as part of
        the concatenation until the next named DD is encountered.

        Example::

            step.steplib  # ['USER.LOADLIB', 'SYS2.LOADLIB']
        """
        datasets: list[str] = []
        in_steplib = False

        for dd in self.dd_statements:
            if dd.name == "STEPLIB":
                in_steplib = True
            elif dd.name:
                in_steplib = False

            if in_steplib and dd.dataset_name:
                datasets.append(dd.dataset_name)

        return datasets

    def get_input_datasets(self) -> list[str]:
        """Get all input dataset names"""
        datasets = []
        for dd in self.dd_statements:
            if dd.is_input() and dd.dataset_name:
                datasets.append(dd.dataset_name)
        return datasets

    def get_output_datasets(self) -> list[str]:
        """Get all output dataset names"""
        datasets = []
        for dd in self.dd_statements:
            if dd.is_output() and dd.dataset_name:
                datasets.append(dd.dataset_name)
        return datasets

    # EXEC Parameter Properties (KISS - simple accessors)

    @property
    def dynamnbr(self) -> int | None:
        """Dynamic allocation count."""
        return _to_int_or_none(self.parameters.get("DYNAMNBR"))

    @property
    def memlimit(self) -> str | None:
        """Memory limit above the bar (e.g., '2G')."""
        return self.parameters.get("MEMLIMIT")

    @property
    def acct(self) -> str | list[str] | None:
        """Step-level accounting."""
        return self.parameters.get("ACCT")

    @property
    def addrspc(self) -> str | None:
        """Address space type (REAL, VIRT)."""
        return self.parameters.get("ADDRSPC")

    @property
    def dprty(self) -> str | list[int] | None:
        """Dispatching priority."""
        return self.parameters.get("DPRTY")

    @property
    def perform(self) -> int | None:
        """Performance group."""
        return _to_int_or_none(self.parameters.get("PERFORM"))

    @property
    def rd(self) -> str | None:
        """Restart definition (R, RNC, NR, NC)."""
        return self.parameters.get("RD")

    def detect_sql(self) -> SQLDetectionResult:
        """Detect SQL statements in this step's inline data and program name.

        Returns:
            SQLDetectionResult with details about detected SQL.
        """
        from .sql_detector import detect_sql_in_step

        return detect_sql_in_step(self)

    @property
    def has_sql(self) -> bool:
        """True if this step contains SQL (DB2 program or SQL in inline data)."""
        return self.detect_sql().has_sql


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
    parameters: dict[str, Any] = field(default_factory=dict)
    accounting_info: str | None = None
    steps: list[Step | ConditionalBlock] = field(default_factory=list)
    procedures: list[Procedure] = field(default_factory=list)
    conditionals: list[ConditionalBlock] = field(default_factory=list)
    set_statements: dict[str, str] = field(default_factory=dict)
    jcllib_order: list[str] = field(default_factory=list)
    includes: list[str] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)
    line_number: int = 0
    explosion_audit: list[Any] = field(default_factory=list)
    explosion_map: dict[str, Any] = field(default_factory=dict)
    jes_statements: list[str] = field(default_factory=list)
    #: Typed JES2/JES3 control statements (``/*JOBPARM``, ``/*ROUTE``, etc.).
    #: Populated in parallel with :attr:`jes_statements` (which retains the
    #: raw string form) so both old and new consumers work.  Unknown JES
    #: commands are *not* added here — they only appear in
    #: :attr:`jes_statements`.
    jes_typed_statements: list[Any] = field(default_factory=list)
    output_statements: list[OutputStatement] = field(default_factory=list)
    joblib_dds: list[DDStatement] = field(default_factory=list)
    #: Statements the model has no richer representation for but that are part
    #: of the job stream — ``COMMAND``, ``SCHEDULE`` and ``CNTL``.  A ``CNTL``
    #: entry carries the program control records of its ``CNTL``/``ENDCNTL``
    #: block in ``parameters["_records"]``.  Kept verbatim so no source
    #: statement is dropped without a trace.
    control_statements: list[Statement] = field(default_factory=list)
    #: Statements of a type the parser has no model for, in source order --
    #: typically a custom ``Statement.type`` returned by an enabled
    #: :class:`~jclparser.plugins.StatementPlugin`.  Kept verbatim instead of
    #: being dropped; consumers that understand the type interpret them.
    custom_statements: list[Statement] = field(default_factory=list)
    #: Optional SQL detection results, keyed by step name.  Populated when
    #: ``parse_jcl`` is called with ``ParserConfig(detect_sql=True)``; otherwise
    #: left empty.  Each entry is a
    #: :class:`~jclparser.sql_detector.SQLDetectionResult`.
    sql_detections: dict[str, Any] = field(default_factory=dict)
    #: Optional dictionary of OUTPUT statement names referenced by
    #: ``OUTPUT=*.name`` DD parameters but *not* defined anywhere in the job.
    #: Populated after OUTPUT back-reference resolution during parsing.
    unresolved_output_refs: list[tuple[str, str, int]] = field(default_factory=list)
    #: ``IF``/``THEN``/``ELSE``/``ENDIF`` statements that do not pair up --
    #: an IF with no ENDIF, an ELSE or ENDIF with no IF, a second ELSE -- as
    #: ``(line_number, message)``.  The parser recovers from them (and says
    #: so on :attr:`warnings`), but z/OS rejects such a job, so
    #: :meth:`validate` reports each as an error.
    conditional_errors: list[tuple[int, str]] = field(default_factory=list)
    #: Symbols listed in ``EXPORT SYMLIST=(...)`` statements at job scope.
    #: Propagated into invoked PROC scopes during explosion.  A literal ``"*"``
    #: exports every SET symbol.
    exported_symbols: set[str] = field(default_factory=set)
    #: Non-fatal parsing issues collected while building this job — e.g.
    #: duplicate keyword parameters, unrecognized statement types, or
    #: symbols that resolved to an empty string because they were never
    #: defined.  Parsing never fails because of these; they exist so a
    #: consumer can detect silent data loss without re-scanning the source.
    warnings: list[str] = field(default_factory=list)
    #: ``True`` for the synthetic ``Job(name="")`` that :func:`parse_jcl`
    #: returns for a JOB-less PROC member (a cataloged procedure): it has no
    #: JOB statement and its steps live in :attr:`procedures`, so the
    #: job-level checks (job name, "at least one step", JOB-card lint rules)
    #: do not apply to it.
    is_procedure_member: bool = False

    def add_step(self, step: Step | ConditionalBlock) -> None:
        """Add an execution step to this job"""
        self.steps.append(step)

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready dict of the whole job, versioned by
        :data:`jclparser.serialization.SCHEMA_VERSION` and described by
        :data:`jclparser.serialization.JOB_JSON_SCHEMA`."""
        from .serialization import job_to_dict

        return job_to_dict(self)

    def to_json(self, **kwargs: Any) -> str:
        """``json.dumps(self.to_dict(), **kwargs)``."""
        from .serialization import job_to_json

        return job_to_json(self, **kwargs)

    def add_procedure(self, procedure: Procedure) -> None:
        """Add an inline procedure definition"""
        self.procedures.append(procedure)

    def add_conditional(self, conditional: ConditionalBlock) -> None:
        """Add a conditional block"""
        self.conditionals.append(conditional)

    def add_set(self, symbol: str, value: str) -> None:
        """Add a SET symbol definition"""
        self.set_statements[symbol] = value

    def get_step(self, name: str) -> Step | None:
        """Find step by name"""
        for step in iter_execution_steps(self.steps):
            if step.name == name:
                return step
        return None

    def get_procedure(self, name: str) -> Procedure | None:
        """Find procedure by name"""
        for proc in self.procedures:
            if proc.name == name:
                return proc
        return None

    def get_dd_statements(self) -> list[DDStatement]:
        """Get all DD statements from all steps"""
        all_dds = []
        for step in iter_execution_steps(self.steps):
            all_dds.extend(step.dd_statements)
        return all_dds

    def get_sysin_statements(self) -> list[DDStatement]:
        """Return all SYSIN DD statements across every step in the job."""
        return [dd for dd in self.get_dd_statements() if dd.name == "SYSIN"]

    def validate(self) -> list[ValidationError]:
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
        max_steps: int = 10_000,
        loader: Any | None = None,
        audit: bool = True,
        system_provider: Any | None = None,
        strict_symbols: bool = False,
    ) -> Job:
        """
        Explode all procedure invocations in this job.

        Creates a new Job instance with all PROC invocations expanded into
        their constituent steps with symbolic parameters fully resolved.

        Args:
            max_depth: Maximum procedure nesting depth (default 10)
            max_steps: Maximum total expanded steps, 0 = unlimited (default
                       10,000, ``explosion.DEFAULT_MAX_STEPS``; z/OS allows 255).
                       Raises JCLStructureError if the limit is exceeded.
            loader: Optional custom procedure loader
            audit: Whether to generate audit logs (default True)
            system_provider: Optional system symbol provider
            strict_symbols: If True, raise errors for undefined symbols

        Returns:
            New Job instance with exploded procedures

        Raises:
            ExplosionDepthError: If nesting exceeds max_depth
            JCLStructureError: If max_steps > 0 and expanded step count exceeds it
            CircularProcedureError: If circular references detected
            ProcedureNotFoundError: If referenced procedure not found
            UndefinedSymbolError: If strict_symbols=True and symbol undefined
        """
        from .explosion import explode_job

        return explode_job(
            job=self,
            proc_loader=loader,
            max_depth=max_depth,
            max_steps=max_steps,
            audit=audit,
            system_provider=system_provider,
            strict_symbols=strict_symbols,
        )

    # JOB Parameter Properties (KISS - simple accessors)

    # ── JOB statement typed parameter accessors ──────────────────────────────

    @property
    def notify(self) -> str | None:
        """User or group to notify on job completion (NOTIFY= parameter)."""
        return self.parameters.get("NOTIFY")

    @property
    def typrun(self) -> str | None:
        """Type of run (TYPRUN=SCAN|HOLD|JCLHOLD|COPY|RUN).

        Common values:
        * ``SCAN``    — syntax-check only, do not execute
        * ``HOLD``    — hold in queue until released
        * ``JCLHOLD`` — hold after JCL conversion
        """
        return self.parameters.get("TYPRUN")

    @property
    def restart(self) -> str | None:
        """Step name at which to restart the job (RESTART= parameter).

        ``*`` means restart from the beginning.
        """
        return self.parameters.get("RESTART")

    @property
    def msgclass(self) -> str | None:
        """Output class for job log messages (MSGCLASS= parameter)."""
        return self.parameters.get("MSGCLASS")

    @property
    def job_class(self) -> str | None:
        """Job execution class (CLASS= parameter).

        Named ``job_class`` to avoid shadowing the Python built-in ``class``.
        """
        return self.parameters.get("CLASS")

    @property
    def prty(self) -> int | None:
        """Job dispatching priority, 0–15 (PRTY= parameter)."""
        return _to_int_or_none(self.parameters.get("PRTY"))

    @property
    def time(self) -> str | list | None:
        """CPU time limit for the job (TIME= parameter).

        May be a string (e.g. ``"1440"``) or a list (e.g. ``["2", "30"]``
        for 2 minutes and 30 seconds), depending on how the JCL was written.
        """
        return self.parameters.get("TIME")

    @property
    def region(self) -> str | None:
        """Region size for the job (REGION= parameter, e.g. ``"4M"``)."""
        return self.parameters.get("REGION")

    @property
    def msglevel(self) -> list | str | None:
        """Message level controlling what appears in the job log (MSGLEVEL= parameter).

        Typically a two-element list ``[statements, messages]``, e.g. ``["1", "1"]``.
        """
        return self.parameters.get("MSGLEVEL")

    @property
    def cond(self) -> list | str | None:
        """Job-level COND parameter used to bypass or flush remaining steps."""
        return self.parameters.get("COND")

    # ── JOBLIB helpers ────────────────────────────────────────────────────────

    @property
    def joblib(self) -> list[str]:
        """Dataset names in the JOBLIB concatenation, in order.

        JOBLIB defines the load-module library search path used by all steps
        that do not specify their own STEPLIB.  Returns the ordered list of
        DSN strings; empty list if no JOBLIB was defined.

        Example::

            job.joblib  # ['SYS2.LOADLIB', 'USER.LOADLIB']
        """
        return [dd.dataset_name for dd in self.joblib_dds if dd.dataset_name]

    def get_library_search_order(self, step_name: str) -> list[str]:
        """Return the effective program-library search order for a step.

        STEPLIB, when present on a step, overrides JOBLIB entirely — just as
        it does on the mainframe.  If the step has no STEPLIB, the job's
        JOBLIB concatenation is returned.  If neither is defined, returns an
        empty list.

        Args:
            step_name: Name of the step to query.

        Returns:
            Ordered list of dataset names that would be searched for
            load modules when the step executes.

        Example::

            order = job.get_library_search_order("STEP1")
            # ['STEP1.LOADLIB'] if STEPLIB present, else job.joblib
        """
        step = self.get_step(step_name)
        if step is not None:
            sl = step.steplib
            if sl:
                return sl
        return list(self.joblib)

    @property
    def bytes_limit(self) -> int | list | None:
        """Output byte limit."""
        return self.parameters.get("BYTES")

    @property
    def lines_limit(self) -> int | list | None:
        """Output line limit."""
        return self.parameters.get("LINES")

    @property
    def pages_limit(self) -> int | list | None:
        """Output page limit."""
        return self.parameters.get("PAGES")

    @property
    def sysaff(self) -> str | None:
        """System affinity."""
        return self.parameters.get("SYSAFF")

    @property
    def schenv(self) -> str | None:
        """Scheduling environment."""
        return self.parameters.get("SCHENV")

    def detect_sql(self) -> list:
        """Detect SQL across all steps in this job.

        Returns:
            List of SQLDetectionResult for steps that contain SQL.
        """
        from .sql_detector import detect_sql_in_job

        return detect_sql_in_job(self)

    @property
    def has_sql(self) -> bool:
        """True if any step in this job contains SQL."""
        return bool(self.detect_sql())


def iter_execution_steps(steps: list[Step | ConditionalBlock]) -> Iterator[Step]:
    """Recursively yield all flattened Step objects from a step list."""
    for s in steps:
        if isinstance(s, Step):
            yield s
        elif isinstance(s, ConditionalBlock):
            yield from iter_execution_steps(s.then_steps)
            yield from iter_execution_steps(s.else_steps)


def _dataset_dds(step: Step) -> list[DDStatement]:
    """The DDs of *step* that can name a dataset, in source order.

    On a PROC call that is not exploded, the ``//PROCSTEP.DD`` overrides
    (and the concatenation members coded after them) live in
    ``dd_overrides`` rather than ``dd_statements``; they allocate and open
    datasets all the same, so dataset checks must see them too.  A
    qualified DD under an ``EXEC PGM=`` step overrides nothing and is ignored
    (it is reported at parse time), so it is left out here as well.
    """
    if not step.is_procedure:
        return step.dd_statements
    overrides = [
        member
        for key, dd in step.dd_overrides.items()
        for member in (dd, *step.dd_override_concatenations.get(key, ()))
    ]
    if not overrides:
        return step.dd_statements
    return sorted([*step.dd_statements, *overrides], key=lambda dd: dd.line_number)
