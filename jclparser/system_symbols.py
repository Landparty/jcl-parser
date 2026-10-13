"""
System symbol resolution for JCL explosion.

Provides abstract interface and implementations for resolving z/OS system symbols
like &SYSUID, &SYSDATE, &SYSTIME during procedure explosion.
"""

import os
from abc import ABC, abstractmethod
from datetime import datetime


class SystemSymbolProvider(ABC):
    """
    Abstract base class for system symbol resolution.

    Implementations provide values for z/OS system symbols during
    procedure explosion and symbolic parameter substitution.
    """

    @abstractmethod
    def get_symbol(self, symbol_name: str) -> str | None:
        """
        Get the value for a system symbol.

        Args:
            symbol_name: Name of system symbol (without leading &)

        Returns:
            Symbol value or None if not available
        """

    def has_symbol(self, symbol_name: str) -> bool:
        """
        Check if a system symbol is available.

        Args:
            symbol_name: Name of system symbol (without leading &)

        Returns:
            True if symbol can be resolved
        """
        return self.get_symbol(symbol_name) is not None


class MockSystemSymbolProvider(SystemSymbolProvider):
    """
    Mock implementation for testing and non-production use.

    Provides configurable mock values for system symbols with
    sensible defaults for common symbols.
    """

    def __init__(self, custom_symbols: dict[str, str] | None = None):
        """
        Initialize mock provider.

        Args:
            custom_symbols: Optional dictionary of symbol name -> value mappings
        """
        self._symbols: dict[str, str] = {
            "SYSUID": "TESTUSER",
            "SYSDATE": "25/12/09",  # YY/MM/DD format
            "SYSTIME": "14:30",  # HH:MM format
            "SYSJOBID": "JOB12345",
            "SYSJOBNAME": "TESTJOB",
            "SYSNODE": "NODE01",
            "SYSPLEX": "PLEX01",
            "SYSCLONE": "A",
            "SYSSYMDEF": "STATIC",
        }

        if custom_symbols:
            self._symbols.update(custom_symbols)

    def get_symbol(self, symbol_name: str) -> str | None:
        """Get mock symbol value"""
        return self._symbols.get(symbol_name.upper())

    def set_symbol(self, symbol_name: str, value: str):
        """
        Set a mock symbol value (for testing).

        Args:
            symbol_name: Symbol name (without leading &)
            value: Symbol value
        """
        self._symbols[symbol_name.upper()] = value


class RuntimeSystemSymbolProvider(SystemSymbolProvider):
    """
    Runtime implementation providing dynamic system symbols.

    Generates symbol values based on current runtime context (time, user, etc.)
    suitable for production use.
    """

    def __init__(
        self,
        userid: str | None = None,
        jobid: str | None = None,
        jobname: str | None = None,
        node: str | None = None,
        sysplex: str | None = None,
        clone: str | None = None,
    ):
        """
        Initialize runtime provider.

        Args:
            userid: User ID (defaults to environment variable USER or USERNAME)
            jobid: Job ID (defaults to 'JOB00000')
            jobname: Job name (defaults to 'RUNTIME')
            node: Node name (defaults to 'NODE01')
            sysplex: Sysplex name (defaults to None)
            clone: Clone ID (defaults to None)
        """
        self.userid = (
            userid or os.environ.get("USER") or os.environ.get("USERNAME") or "UNKNOWN"
        )
        self.jobid = jobid or "JOB00000"
        self.jobname = jobname or "RUNTIME"
        self.node = node or "NODE01"
        self.sysplex = sysplex
        self.clone = clone

        # Build symbol map once at init time (date/time captured at construction)
        now = datetime.now()  # noqa: DTZ005 -- &SYSDATE/&SYSTIME are local time
        self._symbol_map = {
            "SYSUID": self.userid.upper()[:8],  # Max 8 chars
            "SYSDATE": now.strftime("%y/%m/%d"),  # YY/MM/DD
            "SYSTIME": now.strftime("%H:%M"),  # HH:MM
            "SYSJOBID": self.jobid,
            "SYSJOBNAME": self.jobname.upper()[:8],  # Max 8 chars
            "SYSNODE": self.node,
            "SYSSYMDEF": "DYNAMIC",
        }
        if self.sysplex:
            self._symbol_map["SYSPLEX"] = self.sysplex
        if self.clone:
            self._symbol_map["SYSCLONE"] = self.clone

    def get_symbol(self, symbol_name: str) -> str | None:
        """Get runtime symbol value"""
        return self._symbol_map.get(symbol_name.upper())


class EnvironmentSystemSymbolProvider(SystemSymbolProvider):
    """
    Environment-based provider reading from environment variables.

    Allows system symbols to be configured via environment variables with
    JCL_SYS_ prefix (e.g., JCL_SYS_UID for SYSUID).
    """

    def __init__(
        self, prefix: str = "JCL_SYS_", fallback: SystemSymbolProvider | None = None
    ):
        """
        Initialize environment provider.

        Args:
            prefix: Prefix for environment variables
            fallback: Optional fallback provider if env var not found
        """
        self.prefix = prefix
        self.fallback = fallback or RuntimeSystemSymbolProvider()

    def get_symbol(self, symbol_name: str) -> str | None:
        """Get symbol from environment or fallback"""
        # Try environment variable first
        env_var = f"{self.prefix}{symbol_name.upper()}"
        value = os.environ.get(env_var)

        if value is not None:
            return value

        # Fall back to default provider
        return self.fallback.get_symbol(symbol_name)


# Default provider for convenience
_default_provider: SystemSymbolProvider | None = None


# JES / z/OS dynamic symbols that do not carry the reserved ``SYS`` prefix.
_DYNAMIC_SYSTEM_SYMBOLS = frozenset(
    {
        "JOBNAME",
        "SID",
        "SEQ",
        "YYMMDD",
        "HHMMSS",
        "YR2",
        "YR4",
        "MON",
        "DAY",
        "HR",
        "MIN",
        "SEC",
        "JDAY",
        "WDAY",
        "LYYMMDD",
        "LHHMMSS",
        "LYR2",
        "LYR4",
        "LMON",
        "LDAY",
        "LHR",
        "LMIN",
        "LSEC",
        "LJDAY",
        "LWDAY",
    }
)


def is_system_symbol_name(symbol_name: str) -> bool:
    """Return True when *symbol_name* names a z/OS system symbol.

    IBM reserves the ``SYS`` prefix for system symbols (``&SYSUID``,
    ``&SYSNAME``, ``&SYSPLEX``...); the dynamic date/time and job symbols
    (``&LYYMMDD``, ``&JOBNAME``...) are listed explicitly. Such a symbol is
    resolved by a :class:`SystemSymbolProvider` at explosion time, not by a
    SET statement, so a SET-only pass must leave it as written.
    """
    name = symbol_name.upper()
    return name.startswith("SYS") or name in _DYNAMIC_SYSTEM_SYMBOLS


def get_default_provider() -> SystemSymbolProvider:
    """
    Get the default system symbol provider.

    Returns:
        Current default provider (creates MockSystemSymbolProvider if none set)
    """
    global _default_provider
    if _default_provider is None:
        _default_provider = MockSystemSymbolProvider()
    return _default_provider


def set_default_provider(provider: SystemSymbolProvider):
    """
    Set the default system symbol provider.

    Args:
        provider: Provider to use as default
    """
    global _default_provider
    _default_provider = provider
