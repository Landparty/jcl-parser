"""
Test edge cases for proc_loader.py to improve coverage.

Simplified tests focusing on achievable edge cases without complex mocking.
"""

import pytest
import tempfile
from pathlib import Path
from jclparser.proc_loader import (
    JCLLIBProcedureLoader, InlineProcedureLoader, CompositeProcedureLoader
)
from jclparser.model import Procedure, Step
from jclparser.errors import ProcedureNotFoundError


class TestJCLLIBProcedureLoaderEdgeCases:
    """Test JCLLIBProcedureLoader edge cases."""
    
    def test_load_procedure_from_jcl_file(self):
        """Test loading procedure from file that's actually a JCL file."""
        # Create a temp file with JOB card (not a PROC file)
        with tempfile.TemporaryDirectory() as tmpdir:
            proc_file = Path(tmpdir) / "NOTPROC.jcl"
            with open(proc_file, 'w', encoding='utf-8') as f:
                f.write("""//MYJOB JOB
//STEP1 EXEC PGM=PROG
//DD1 DD DSN=FILE""")
            
            loader = JCLLIBProcedureLoader(Path(tmpdir))
            
            # Should return None - file is JCL, not PROC
            proc = loader.load_procedure("NOTPROC", libraries=["."])
            assert proc is None
    
    def test_load_procedure_from_valid_proc_file(self):
        """Test loading procedure from valid PROC file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proc_file = Path(tmpdir) / "lib" / "MYPROC.jcl"
            proc_file.parent.mkdir(exist_ok=True)
            with open(proc_file, 'w', encoding='utf-8') as f:
                f.write("""//MYPROC PROC
//STEP1 EXEC PGM=PROG1
//DD1 DD DSN=FILE1
//PEND""")
            
            loader = JCLLIBProcedureLoader(Path(tmpdir))
            proc = loader.load_procedure("MYPROC", libraries=["lib"])
            
            assert proc is not None
            assert proc.name == "MYPROC"
            assert len(proc.steps) == 1
    
    def test_load_procedure_file_not_found(self):
        """Test loading non-existent procedure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = JCLLIBProcedureLoader(Path(tmpdir))
            
            proc = loader.load_procedure("NONEXISTENT", libraries=["lib"])
            assert proc is None
    
    def test_load_procedure_caching(self):
        """Test that loader caches procedures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proc_file = Path(tmpdir) / "lib" / "CACHED.jcl"
            proc_file.parent.mkdir(exist_ok=True)
            with open(proc_file, 'w', encoding='utf-8') as f:
                f.write("""//CACHED PROC
//STEP1 EXEC PGM=PROG
//PEND""")
            
            loader = JCLLIBProcedureLoader(Path(tmpdir))
            
            # Load twice - should use cache second time
            proc1 = loader.load_procedure("CACHED", libraries=["lib"])
            proc2 = loader.load_procedure("CACHED", libraries=["lib"])
            
            # Should return same object (cached)
            assert proc1 is proc2


class TestProcedureParsingEdgeCases:
    """Test procedure file parsing edge cases."""
    
    def test_parse_procedure_file_without_pend(self):
        """Test PROC file missing PEND statement."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proc_file = Path(tmpdir) / "lib" / "NOPEND.jcl"
            proc_file.parent.mkdir(exist_ok=True)
            with open(proc_file, 'w', encoding='utf-8') as f:
                # PROC without PEND
                f.write("""//NOPEND PROC
//STEP1 EXEC PGM=PROG1
//DD1 DD DSN=FILE1""")
            
            loader = JCLLIBProcedureLoader(Path(tmpdir))
            proc = loader.load_procedure("NOPEND", libraries=["lib"])
            
            # Should still parse successfully
            assert proc is not None
            assert proc.name == "NOPEND"
    
    def test_parse_procedure_file_with_comments(self):
        """Test PROC file with comments."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proc_file = Path(tmpdir) / "lib" / "COMMENTS.jcl"
            proc_file.parent.mkdir(exist_ok=True)
            with open(proc_file, 'w', encoding='utf-8') as f:
                f.write("""//* This is a comment
//COMMENTS PROC
//* Another comment
//STEP1 EXEC PGM=PROG1
//DD1 DD DSN=FILE1
//* Final comment
//PEND""")
            
            loader = JCLLIBProcedureLoader(Path(tmpdir))
            proc = loader.load_procedure("COMMENTS", libraries=["lib"])
            
            assert proc is not None
            assert len(proc.steps) == 1
    
    def test_parse_empty_procedure_file(self):
        """Test empty PROC file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proc_file = Path(tmpdir) / "lib" / "EMPTY.jcl"
            proc_file.parent.mkdir(exist_ok=True)
            with open(proc_file, 'w', encoding='utf-8') as f:
                f.write("")
            
            loader = JCLLIBProcedureLoader(Path(tmpdir))
            
            # Should return None - no PROC found
            proc = loader.load_procedure("EMPTY", libraries=["lib"])
            assert proc is None


class TestInlineProcedureLoader:
    """Test InlineProcedureLoader edge cases."""
    
    def test_load_inline_procedure(self):
        """Test loading inline procedure."""
        proc = Procedure(name="INLINEPROC", parameters={"PARM": "VALUE"})
        step = Step(name="STEP1", program="PROG1", parameters={})
        proc.steps.append(step)
        
        loader = InlineProcedureLoader([proc])
        loaded_proc = loader.load_procedure("INLINEPROC")
        
        assert loaded_proc is not None
        assert loaded_proc.name == "INLINEPROC"
        assert len(loaded_proc.steps) == 1
    
    def test_load_nonexistent_inline_procedure(self):
        """Test loading non-existent inline procedure."""
        loader = InlineProcedureLoader([])
        
        proc = loader.load_procedure("NONEXISTENT")
        assert proc is None
    
    def test_has_procedure_inline(self):
        """Test has_procedure for inline procedures."""
        proc = Procedure(name="MYPROC", parameters={})
        loader = InlineProcedureLoader([proc])
        
        assert loader.has_procedure("MYPROC") == True
        assert loader.has_procedure("NONEXISTENT") == False


class TestCompositeProcedureLoader:
    """Test CompositeProcedureLoader edge cases."""
    
    def test_composite_loader_tries_all_loaders(self):
        """Test composite loader tries all loaders in order."""
        inline_proc = Procedure(name="INLINE", parameters={})
        inline_loader = InlineProcedureLoader([inline_proc])
        
        # Create temp JCLLIB with different procedure
        with tempfile.TemporaryDirectory() as tmpdir:
            proc_file = Path(tmpdir) / "lib" / "JCLLIB.jcl"
            proc_file.parent.mkdir(exist_ok=True)
            with open(proc_file, 'w', encoding='utf-8') as f:
                f.write("""//JCLLIB PROC
//STEP1 EXEC PGM=PROG
//PEND""")
            
            jcllib_loader = JCLLIBProcedureLoader(Path(tmpdir))
            
            composite = CompositeProcedureLoader([inline_loader, jcllib_loader])
            
            # Should find inline procedure first
            proc1 = composite.load_procedure("INLINE")
            assert proc1.name == "INLINE"
            
            # Should find JCLLIB procedure second
            proc2 = composite.load_procedure("JCLLIB", libraries=("lib",))
            assert proc2.name == "JCLLIB"
    
    def test_composite_loader_procedure_not_found(self):
        """Test composite loader when procedure not in any loader."""
        inline_loader = InlineProcedureLoader([])
        composite = CompositeProcedureLoader([inline_loader])
        
        proc = composite.load_procedure("NONEXISTENT")
        assert proc is None
    
    def test_composite_loader_has_procedure(self):
        """Test has_procedure in composite loader."""
        proc = Procedure(name="MYPROC", parameters={})
        inline_loader = InlineProcedureLoader([proc])
        composite = CompositeProcedureLoader([inline_loader])
        
        assert composite.has_procedure("MYPROC") == True
        assert composite.has_procedure("NONEXISTENT") == False
    
    def test_composite_loader_empty_loaders_list(self):
        """Test composite loader with empty loaders list."""
        composite = CompositeProcedureLoader([])
        
        proc = composite.load_procedure("ANYPROC")
        assert proc is None
        
        assert composite.has_procedure("ANYPROC") == False
