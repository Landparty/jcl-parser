"""
Unit tests for system symbol providers.
"""

from datetime import datetime

from jclparser.system_symbols import (
    EnvironmentSystemSymbolProvider,
    MockSystemSymbolProvider,
    RuntimeSystemSymbolProvider,
    SystemSymbolProvider,
    get_default_provider,
    set_default_provider,
)


class TestMockSystemSymbolProvider:
    """Test mock system symbol provider"""

    def test_default_symbols(self):
        """Test default system symbols"""
        provider = MockSystemSymbolProvider()

        assert provider.get_symbol("SYSUID") == "TESTUSER"
        assert provider.get_symbol("SYSDATE") is not None
        assert provider.get_symbol("SYSTIME") is not None
        assert provider.get_symbol("SYSJOBID") == "JOB12345"

    def test_custom_symbols(self):
        """Test custom symbol values"""
        provider = MockSystemSymbolProvider({"CUSTOM": "VALUE", "SYSUID": "OVERRIDE"})

        assert provider.get_symbol("CUSTOM") == "VALUE"
        assert provider.get_symbol("SYSUID") == "OVERRIDE"

    def test_case_insensitive(self):
        """Test symbol names are case-insensitive"""
        provider = MockSystemSymbolProvider()

        assert provider.get_symbol("sysuid") == provider.get_symbol("SYSUID")
        assert provider.get_symbol("SysUid") == provider.get_symbol("SYSUID")

    def test_has_symbol(self):
        """Test has_symbol method"""
        provider = MockSystemSymbolProvider()

        assert provider.has_symbol("SYSUID")
        assert not provider.has_symbol("UNDEFINED")

    def test_set_symbol(self):
        """Test setting symbol values"""
        provider = MockSystemSymbolProvider()
        provider.set_symbol("NEWSYM", "NEWVAL")

        assert provider.get_symbol("NEWSYM") == "NEWVAL"

    def test_undefined_symbol(self):
        """Test undefined symbol returns None"""
        provider = MockSystemSymbolProvider()

        assert provider.get_symbol("NOTEXIST") is None


class TestRuntimeSystemSymbolProvider:
    """Test runtime system symbol provider"""

    def test_default_values(self):
        """Test runtime provider with default values"""
        provider = RuntimeSystemSymbolProvider()

        assert provider.get_symbol("SYSUID") is not None
        assert provider.get_symbol("SYSJOBID") == "JOB00000"
        assert provider.get_symbol("SYSJOBNAME") == "RUNTIME"

    def test_custom_values(self):
        """Test runtime provider with custom values"""
        provider = RuntimeSystemSymbolProvider(
            userid="MYUSER", jobid="JOB99999", jobname="CUSTOMJOB", node="MYNODE"
        )

        assert provider.get_symbol("SYSUID") == "MYUSER"
        assert provider.get_symbol("SYSJOBID") == "JOB99999"
        assert provider.get_symbol("SYSJOBNAME") == "CUSTOMJO"  # Truncated to 8
        assert provider.get_symbol("SYSNODE") == "MYNODE"

    def test_dynamic_datetime(self):
        """Test dynamic date/time symbols"""
        provider = RuntimeSystemSymbolProvider()

        datetime.now()
        sysdate = provider.get_symbol("SYSDATE")
        systime = provider.get_symbol("SYSTIME")

        assert sysdate is not None
        assert systime is not None
        assert "/" in sysdate  # Format: YY/MM/DD
        assert ":" in systime  # Format: HH:MM

    def test_optional_symbols(self):
        """Test optional symbols"""
        provider = RuntimeSystemSymbolProvider(sysplex="MYPLEX", clone="A")

        assert provider.get_symbol("SYSPLEX") == "MYPLEX"
        assert provider.get_symbol("SYSCLONE") == "A"

        provider2 = RuntimeSystemSymbolProvider()
        assert provider2.get_symbol("SYSPLEX") is None
        assert provider2.get_symbol("SYSCLONE") is None


class TestEnvironmentSystemSymbolProvider:
    """Test environment-based system symbol provider"""

    def test_environment_variable(self, monkeypatch):
        """Test reading from environment variables"""
        monkeypatch.setenv("JCL_SYS_UID", "ENVUSER")

        provider = EnvironmentSystemSymbolProvider()
        assert provider.get_symbol("UID") == "ENVUSER"

    def test_fallback_provider(self):
        """Test fallback to runtime provider"""
        mock_fallback = MockSystemSymbolProvider({"SYSUID": "FALLBACK"})
        provider = EnvironmentSystemSymbolProvider(fallback=mock_fallback)

        assert provider.get_symbol("SYSUID") == "FALLBACK"

    def test_custom_prefix(self, monkeypatch):
        """Test custom environment variable prefix"""
        monkeypatch.setenv("CUSTOM_PREFIX_TEST", "VALUE")

        provider = EnvironmentSystemSymbolProvider(prefix="CUSTOM_PREFIX_")
        assert provider.get_symbol("TEST") == "VALUE"


class TestDefaultProvider:
    """Test default provider management"""

    def test_get_default_provider(self):
        """Test getting default provider"""
        provider = get_default_provider()

        assert provider is not None
        assert isinstance(provider, SystemSymbolProvider)

    def test_set_default_provider(self):
        """Test setting default provider"""
        custom = MockSystemSymbolProvider({"TEST": "VALUE"})
        set_default_provider(custom)

        provider = get_default_provider()
        assert provider.get_symbol("TEST") == "VALUE"

        # Reset to avoid affecting other tests
        set_default_provider(MockSystemSymbolProvider())
