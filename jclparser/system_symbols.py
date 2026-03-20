"""
System symbol resolution for JCL explosion.

Provides abstract interface and implementations for resolving z/OS system symbols
like &SYSUID, &SYSDATE, &SYSTIME during procedure explosion.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Optional
import os


class SystemSymbolProvider(ABC):
    """
    Abstract base class for system symbol resolution.
    
    Implementations provide values for z/OS system symbols during
    procedure explosion and symbolic parameter substitution.
    """
    
    @abstractmethod
    def get_symbol(self, symbol_name: str) -> Optional[str]:
        """
        Get the value for a system symbol.
        
        Args:
            symbol_name: Name of system symbol (without leading &)
            
        Returns:
            Symbol value or None if not available
        """
        pass
    
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
    
    def __init__(self, custom_symbols: Optional[Dict[str, str]] = None):
        """
        Initialize mock provider.
        
        Args:
            custom_symbols: Optional dictionary of symbol name -> value mappings
        """
        self._symbols: Dict[str, str] = {
            'SYSUID': 'TESTUSER',
            'SYSDATE': '25/12/09',  # YY/MM/DD format
            'SYSTIME': '14:30',      # HH:MM format
            'SYSJOBID': 'JOB12345',
            'SYSJOBNAME': 'TESTJOB',
            'SYSNODE': 'NODE01',
            'SYSPLEX': 'PLEX01',
            'SYSCLONE': 'A',
            'SYSSYMDEF': 'STATIC',
        }
        
        if custom_symbols:
            self._symbols.update(custom_symbols)
    
    def get_symbol(self, symbol_name: str) -> Optional[str]:
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
        userid: Optional[str] = None,
        jobid: Optional[str] = None,
        jobname: Optional[str] = None,
        node: Optional[str] = None,
        sysplex: Optional[str] = None,
        clone: Optional[str] = None
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
        self.userid = userid or os.environ.get('USER') or os.environ.get('USERNAME') or 'UNKNOWN'
        self.jobid = jobid or 'JOB00000'
        self.jobname = jobname or 'RUNTIME'
        self.node = node or 'NODE01'
        self.sysplex = sysplex
        self.clone = clone

        # Build symbol map once at init time (date/time captured at construction)
        now = datetime.now()
        self._symbol_map = {
            'SYSUID':    self.userid.upper()[:8],       # Max 8 chars
            'SYSDATE':   now.strftime('%y/%m/%d'),       # YY/MM/DD
            'SYSTIME':   now.strftime('%H:%M'),           # HH:MM
            'SYSJOBID':  self.jobid,
            'SYSJOBNAME': self.jobname.upper()[:8],      # Max 8 chars
            'SYSNODE':   self.node,
            'SYSSYMDEF': 'DYNAMIC',
        }
        if self.sysplex:
            self._symbol_map['SYSPLEX'] = self.sysplex
        if self.clone:
            self._symbol_map['SYSCLONE'] = self.clone

    def get_symbol(self, symbol_name: str) -> Optional[str]:
        """Get runtime symbol value"""
        return self._symbol_map.get(symbol_name.upper())


class EnvironmentSystemSymbolProvider(SystemSymbolProvider):
    """
    Environment-based provider reading from environment variables.
    
    Allows system symbols to be configured via environment variables with
    JCL_SYS_ prefix (e.g., JCL_SYS_UID for SYSUID).
    """
    
    def __init__(self, prefix: str = 'JCL_SYS_', fallback: Optional[SystemSymbolProvider] = None):
        """
        Initialize environment provider.
        
        Args:
            prefix: Prefix for environment variables
            fallback: Optional fallback provider if env var not found
        """
        self.prefix = prefix
        self.fallback = fallback or RuntimeSystemSymbolProvider()
    
    def get_symbol(self, symbol_name: str) -> Optional[str]:
        """Get symbol from environment or fallback"""
        # Try environment variable first
        env_var = f"{self.prefix}{symbol_name.upper()}"
        value = os.environ.get(env_var)
        
        if value is not None:
            return value
        
        # Fall back to default provider
        return self.fallback.get_symbol(symbol_name)


# Default provider for convenience
_default_provider: Optional[SystemSymbolProvider] = None


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
