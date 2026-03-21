"""
Unit tests for procedure loaders.
"""

from pathlib import Path
import tempfile

from jclparser.proc_loader import (
    InlineProcedureLoader,
    JCLLIBProcedureLoader,
    CompositeProcedureLoader,
    create_default_loader
)
from jclparser.model import Procedure, Step


class TestInlineProcedureLoader:
    """Test inline procedure loader"""
    
    def test_load_existing_procedure(self):
        """Test loading an existing inline procedure"""
        proc = Procedure(
            name='TESTPROC',
            parameters={'DSN': 'TEST.DATA'},
            steps=[
                Step(name='STEP1', program='IEFBR14')
            ],
            line_number=1
        )
        
        loader = InlineProcedureLoader([proc])
        loaded = loader.load_procedure('TESTPROC')
        
        assert loaded is not None
        assert loaded.name == 'TESTPROC'
        assert len(loaded.steps) == 1
    
    def test_case_insensitive_lookup(self):
        """Test case-insensitive procedure name lookup"""
        proc = Procedure(name='MyProc', parameters={}, steps=[], line_number=1)
        loader = InlineProcedureLoader([proc])
        
        assert loader.load_procedure('MYPROC') is not None
        assert loader.load_procedure('myproc') is not None
    
    def test_load_nonexistent_procedure(self):
        """Test loading a nonexistent procedure"""
        loader = InlineProcedureLoader([])
        
        assert loader.load_procedure('NOTFOUND') is None
    
    def test_has_procedure(self):
        """Test has_procedure method"""
        proc = Procedure(name='EXISTS', parameters={}, steps=[], line_number=1)
        loader = InlineProcedureLoader([proc])
        
        assert loader.has_procedure('EXISTS')
        assert not loader.has_procedure('NOTEXIST')


class TestJCLLIBProcedureLoader:
    """Test JCLLIB procedure loader"""
    
    def test_load_from_file(self):
        """Test loading procedure from file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create procedure library
            lib_dir = Path(tmpdir) / 'PROCLIB'
            lib_dir.mkdir()
            
            # Create procedure file
            proc_file = lib_dir / 'TESTPROC.jcl'
            proc_file.write_text("""//TESTPROC PROC DSN=DEFAULT.DATA
//STEP1    EXEC PGM=IEFBR14
//DD1      DD DSN=&DSN,DISP=SHR
//         PEND
//""")
            
            loader = JCLLIBProcedureLoader(base_path=Path(tmpdir))
            proc = loader.load_procedure('TESTPROC', ['PROCLIB'])
            
            assert proc is not None
            assert proc.name == 'TESTPROC'
            assert len(proc.steps) == 1
    
    def test_env_variable_base_path(self, monkeypatch):
        """Test using JCL_PROCLIB_PATH environment variable"""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv('JCL_PROCLIB_PATH', tmpdir)
            
            loader = JCLLIBProcedureLoader()
            assert loader.base_path == Path(tmpdir)
    
    def test_load_nonexistent_library(self):
        """Test loading from nonexistent library"""
        loader = JCLLIBProcedureLoader(base_path=Path('/nonexistent'))
        
        assert loader.load_procedure('TEST', ['BADLIB']) is None
    
    def test_load_nonexistent_procedure(self):
        """Test loading nonexistent procedure"""
        with tempfile.TemporaryDirectory() as tmpdir:
            lib_dir = Path(tmpdir) / 'PROCLIB'
            lib_dir.mkdir()
            
            loader = JCLLIBProcedureLoader(base_path=Path(tmpdir))
            assert loader.load_procedure('NOTFOUND', ['PROCLIB']) is None
    
    def test_caching(self):
        """Test that loader caches results"""
        with tempfile.TemporaryDirectory() as tmpdir:
            lib_dir = Path(tmpdir) / 'PROCLIB'
            lib_dir.mkdir()
            
            proc_file = lib_dir / 'CACHED.jcl'
            proc_file.write_text("""//CACHED   PROC
//STEP1    EXEC PGM=IEFBR14
//         PEND
//""")
            
            loader = JCLLIBProcedureLoader(base_path=Path(tmpdir))
            
            # Load twice - second should be cached
            proc1 = loader.load_procedure('CACHED', ['PROCLIB'])
            proc2 = loader.load_procedure('CACHED', ['PROCLIB'])
            
            assert proc1 is proc2  # Same object due to caching


class TestCompositeProcedureLoader:
    """Test composite procedure loader"""
    
    def test_fallback_chain(self):
        """Test loader fallback chain"""
        inline_proc = Procedure(name='INLINE', parameters={}, steps=[], line_number=1)
        inline_loader = InlineProcedureLoader([inline_proc])
        
        with tempfile.TemporaryDirectory() as tmpdir:
            lib_dir = Path(tmpdir) / 'PROCLIB'
            lib_dir.mkdir()
            
            proc_file = lib_dir / 'EXTERNAL.jcl'
            proc_file.write_text("""//EXTERNAL PROC
//STEP1    EXEC PGM=IEFBR14
//         PEND
//""")
            
            jcllib_loader = JCLLIBProcedureLoader(base_path=Path(tmpdir))
            
            composite = CompositeProcedureLoader([inline_loader, jcllib_loader])
            
            # Should find inline first
            assert composite.load_procedure('INLINE') is not None
            
            # Should fall through to JCLLIB
            assert composite.load_procedure('EXTERNAL', ('PROCLIB',)) is not None
            
            # Should not find
            assert composite.load_procedure('NOTFOUND') is None
    
    def test_has_procedure(self):
        """Test has_procedure with composite loader"""
        proc = Procedure(name='TEST', parameters={}, steps=[], line_number=1)
        loader = CompositeProcedureLoader([InlineProcedureLoader([proc])])
        
        assert loader.has_procedure('TEST')
        assert not loader.has_procedure('NOTFOUND')
    
    def test_caching(self):
        """Test composite loader caching"""
        proc = Procedure(name='CACHED', parameters={}, steps=[], line_number=1)
        loader = CompositeProcedureLoader([InlineProcedureLoader([proc])])
        
        # Load twice
        proc1 = loader.load_procedure('CACHED')
        proc2 = loader.load_procedure('CACHED')
        
        assert proc1 is proc2


class TestCreateDefaultLoader:
    """Test default loader creation"""
    
    def test_create_with_inline_only(self):
        """Test creating loader with inline procedures only"""
        proc = Procedure(name='TEST', parameters={}, steps=[], line_number=1)
        loader = create_default_loader([proc], include_jcllib=False)
        
        assert isinstance(loader, CompositeProcedureLoader)
        assert loader.load_procedure('TEST') is not None
    
    def test_create_with_jcllib(self):
        """Test creating loader with JCLLIB support"""
        loader = create_default_loader([], include_jcllib=True)
        
        assert isinstance(loader, CompositeProcedureLoader)
        assert len(loader.loaders) == 2  # Inline + JCLLIB
