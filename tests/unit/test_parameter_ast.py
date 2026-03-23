"""
Tests for parameter AST and complex parameter parsing.
"""
from jclparser.parameter_ast import (
    ParameterParser,
    SPACEParameter,
    SimpleParameter,
    ListParameter,
    NestedParameter
)


class TestDCBParsing:
    """Test DCB parameter parsing."""
    
    def test_parse_simple_dcb(self):
        """Test parsing simple DCB parameter."""
        parser = ParameterParser()
        dcb = parser.parse_dcb("RECFM=FB,LRECL=80,BLKSIZE=27920")
        
        assert dcb.recfm == "FB"
        assert dcb.lrecl == 80
        assert dcb.blksize == 27920
    
    def test_parse_dcb_with_parentheses(self):
        """Test parsing DCB with outer parentheses."""
        parser = ParameterParser()
        dcb = parser.parse_dcb("(RECFM=FB,LRECL=80)")
        
        assert dcb.recfm == "FB"
        assert dcb.lrecl == 80
    
    def test_parse_dcb_with_optcd(self):
        """Test parsing DCB with OPTCD subparameter."""
        parser = ParameterParser()
        dcb = parser.parse_dcb("RECFM=FB,LRECL=80,OPTCD=(Q,B)")
        
        assert dcb.recfm == "FB"
        assert "OPTCD" in dcb.subparameters
        assert dcb.subparameters["OPTCD"] == "(Q,B)"
    
    def test_parse_dcb_with_dsorg(self):
        """Test parsing DCB with DSORG."""
        parser = ParameterParser()
        dcb = parser.parse_dcb("RECFM=FB,LRECL=80,DSORG=PS")
        
        assert dcb.dsorg == "PS"
    
    def test_parse_dcb_with_bufno(self):
        """Test parsing DCB with BUFNO."""
        parser = ParameterParser()
        dcb = parser.parse_dcb("RECFM=FB,LRECL=80,BUFNO=20")
        
        assert dcb.bufno == 20
    
    def test_dcb_validation_valid(self):
        """Test DCB validation with valid parameters."""
        parser = ParameterParser()
        dcb = parser.parse_dcb("RECFM=FB,LRECL=80,BLKSIZE=27920")
        
        errors = dcb.validate()
        assert len(errors) == 0
    
    def test_dcb_validation_invalid_recfm(self):
        """Test DCB validation with invalid RECFM."""
        parser = ParameterParser()
        dcb = parser.parse_dcb("RECFM=INVALID,LRECL=80")
        
        errors = dcb.validate()
        assert len(errors) > 0
        assert any("RECFM" in err for err in errors)
    
    def test_dcb_validation_lrecl_out_of_range(self):
        """Test DCB validation with LRECL out of range."""
        parser = ParameterParser()
        dcb = parser.parse_dcb("RECFM=FB,LRECL=99999")
        
        errors = dcb.validate()
        assert len(errors) > 0
        assert any("LRECL" in err and "range" in err for err in errors)
    
    def test_dcb_validation_blksize_not_multiple(self):
        """Test DCB validation when BLKSIZE not multiple of LRECL."""
        parser = ParameterParser()
        dcb = parser.parse_dcb("RECFM=FB,LRECL=80,BLKSIZE=100")
        
        errors = dcb.validate()
        assert len(errors) > 0
        assert any("multiple" in err.lower() for err in errors)
    
    def test_dcb_validation_valid_blksize_multiple(self):
        """Test DCB validation with valid BLKSIZE multiple."""
        parser = ParameterParser()
        dcb = parser.parse_dcb("RECFM=FB,LRECL=80,BLKSIZE=160")
        
        errors = dcb.validate()
        assert len(errors) == 0
    
    def test_dcb_validation_invalid_dsorg(self):
        """Test DCB validation with invalid DSORG."""
        parser = ParameterParser()
        dcb = parser.parse_dcb("RECFM=FB,DSORG=INVALID")
        
        errors = dcb.validate()
        assert len(errors) > 0
        assert any("DSORG" in err for err in errors)
    
    def test_dcb_raw_value_preserved(self):
        """Test that raw value is preserved."""
        parser = ParameterParser()
        raw = "RECFM=FB,LRECL=80"
        dcb = parser.parse_dcb(raw)
        
        assert dcb.raw_value == raw


class TestSPACEParsing:
    """Test SPACE parameter parsing."""
    
    def test_parse_simple_space(self):
        """Test parsing simple SPACE parameter."""
        parser = ParameterParser()
        space = parser.parse_space("CYL,(10,5)")
        
        assert space.unit == "CYL"
        assert space.primary == 10
        assert space.secondary == 5
    
    def test_parse_space_with_directory(self):
        """Test parsing SPACE with directory blocks."""
        parser = ParameterParser()
        space = parser.parse_space("CYL,(10,5,20)")
        
        assert space.unit == "CYL"
        assert space.primary == 10
        assert space.secondary == 5
        assert space.directory == 20
    
    def test_parse_space_with_rlse(self):
        """Test parsing SPACE with RLSE option."""
        parser = ParameterParser()
        space = parser.parse_space("CYL,(10,5),RLSE")
        
        assert space.unit == "CYL"
        assert space.rlse is True
    
    def test_parse_space_with_contig(self):
        """Test parsing SPACE with CONTIG option."""
        parser = ParameterParser()
        space = parser.parse_space("TRK,(100,10),RLSE,CONTIG")
        
        assert space.unit == "TRK"
        assert space.rlse is True
        assert space.contig is True
    
    def test_parse_space_with_round(self):
        """Test parsing SPACE with ROUND option."""
        parser = ParameterParser()
        space = parser.parse_space("CYL,(10,5),ROUND")
        
        assert space.round is True
    
    def test_parse_space_with_parentheses(self):
        """Test parsing SPACE with outer parentheses."""
        parser = ParameterParser()
        space = parser.parse_space("(CYL,(10,5))")
        
        assert space.unit == "CYL"
        assert space.primary == 10
    
    def test_parse_space_with_blksize_unit(self):
        """Test parsing SPACE with block size as unit."""
        parser = ParameterParser()
        space = parser.parse_space("800,(100,10)")
        
        assert space.unit == "800"
        assert space.primary == 100
    
    def test_space_validation_valid(self):
        """Test SPACE validation with valid parameters."""
        parser = ParameterParser()
        space = parser.parse_space("CYL,(10,5)")
        
        errors = space.validate()
        assert len(errors) == 0
    
    def test_space_validation_invalid_unit(self):
        """Test SPACE validation with invalid unit."""
        parser = ParameterParser()
        space = parser.parse_space("INVALID,(10,5)")
        
        errors = space.validate()
        assert len(errors) > 0
        assert any("unit" in err.lower() for err in errors)
    
    def test_space_validation_invalid_primary(self):
        """Test SPACE validation with invalid primary."""
        parser = ParameterParser()
        space = parser.parse_space("CYL,(0,5)")
        
        errors = space.validate()
        assert len(errors) > 0
        assert any("primary" in err.lower() for err in errors)
    
    def test_space_validation_negative_secondary(self):
        """Test SPACE validation with negative secondary."""
        # This would require manual construction since parser won't create negative
        space = SPACEParameter(
            key="SPACE",
            raw_value="test",
            subparameters={"_unit": "CYL", "_primary": "10", "_secondary": "-5"}
        )
        
        errors = space.validate()
        assert len(errors) > 0
        assert any("secondary" in err.lower() for err in errors)
    
    def test_space_properties_none_when_missing(self):
        """Test that properties return None when not present."""
        parser = ParameterParser()
        space = parser.parse_space("CYL,(10)")
        
        assert space.secondary is None
        assert space.directory is None
        assert space.rlse is False
        assert space.contig is False


class TestParameterParserUtilities:
    """Test parameter parser utility methods."""
    
    def test_split_parameters_simple(self):
        """Test splitting simple parameters."""
        parser = ParameterParser()
        parts = parser._split_parameters("A,B,C")
        
        assert parts == ["A", "B", "C"]
    
    def test_split_parameters_with_parentheses(self):
        """Test splitting parameters with nested parentheses."""
        parser = ParameterParser()
        parts = parser._split_parameters("A,(B,C),D")
        
        assert len(parts) == 3
        assert parts[0] == "A"
        assert parts[1] == "(B,C)"
        assert parts[2] == "D"
    
    def test_split_parameters_with_quotes(self):
        """Test splitting parameters with quoted strings."""
        parser = ParameterParser()
        parts = parser._split_parameters("A='B,C',D")
        
        assert len(parts) == 2
        assert parts[0] == "A='B,C'"
        assert parts[1] == "D"
    
    def test_split_parameters_deeply_nested(self):
        """Test splitting deeply nested parameters."""
        parser = ParameterParser()
        parts = parser._split_parameters("A,((B,C),(D,E)),F")
        
        assert len(parts) == 3
        assert parts[0] == "A"
        assert parts[1] == "((B,C),(D,E))"
        assert parts[2] == "F"
    
    def test_split_parameters_empty_parts(self):
        """Test that empty parts are filtered out."""
        parser = ParameterParser()
        parts = parser._split_parameters("A,,B")
        
        # Empty parts should be filtered
        assert "A" in parts
        assert "B" in parts


class TestParameterNodeClasses:
    """Test parameter node base classes."""
    
    def test_simple_parameter(self):
        """Test SimpleParameter creation."""
        param = SimpleParameter(
            key="TEST",
            value="VALUE",
            raw_value="TEST=VALUE",
            line_number=10
        )
        
        assert param.key == "TEST"
        assert param.value == "VALUE"
        assert param.raw_value == "TEST=VALUE"
        assert param.line_number == 10
    
    def test_list_parameter(self):
        """Test ListParameter creation."""
        param = ListParameter(
            key="TEST",
            values=["A", "B", "C"],
            raw_value="TEST=(A,B,C)",
            line_number=10
        )
        
        assert param.key == "TEST"
        assert len(param.values) == 3
        assert "B" in param.values
    
    def test_nested_parameter(self):
        """Test NestedParameter creation."""
        param = NestedParameter(
            key="TEST",
            subparameters={"SUB1": "VAL1", "SUB2": "VAL2"},
            raw_value="TEST=(SUB1=VAL1,SUB2=VAL2)",
            line_number=10
        )
        
        assert param.key == "TEST"
        assert param.subparameters["SUB1"] == "VAL1"
        assert param.subparameters["SUB2"] == "VAL2"


class TestComplexDCBScenarios:
    """Test complex DCB parsing scenarios."""
    
    def test_dcb_with_all_parameters(self):
        """Test DCB with all common parameters."""
        parser = ParameterParser()
        dcb = parser.parse_dcb(
            "RECFM=FB,LRECL=80,BLKSIZE=27920,BUFNO=20,DSORG=PS"
        )
        
        assert dcb.recfm == "FB"
        assert dcb.lrecl == 80
        assert dcb.blksize == 27920
        assert dcb.bufno == 20
        assert dcb.dsorg == "PS"
        
        errors = dcb.validate()
        assert len(errors) == 0
    
    def test_dcb_variable_length(self):
        """Test DCB for variable length records."""
        parser = ParameterParser()
        dcb = parser.parse_dcb("RECFM=VB,LRECL=255")
        
        assert dcb.recfm == "VB"
        assert dcb.lrecl == 255
        
        # Variable length doesn't require BLKSIZE to be multiple
        errors = dcb.validate()
        assert len(errors) == 0
    
    def test_dcb_undefined_format(self):
        """Test DCB with undefined format."""
        parser = ParameterParser()
        dcb = parser.parse_dcb("RECFM=U,BLKSIZE=32760")
        
        assert dcb.recfm == "U"
        assert dcb.blksize == 32760
        
        errors = dcb.validate()
        assert len(errors) == 0


class TestComplexSPACEScenarios:
    """Test complex SPACE parsing scenarios."""
    
    def test_space_pds_allocation(self):
        """Test SPACE allocation for PDS."""
        parser = ParameterParser()
        space = parser.parse_space("CYL,(10,5,20),RLSE")
        
        assert space.unit == "CYL"
        assert space.primary == 10
        assert space.secondary == 5
        assert space.directory == 20
        assert space.rlse is True
        
        errors = space.validate()
        assert len(errors) == 0
    
    def test_space_track_allocation(self):
        """Test SPACE allocation in tracks."""
        parser = ParameterParser()
        space = parser.parse_space("TRK,(500,100)")
        
        assert space.unit == "TRK"
        assert space.primary == 500
        assert space.secondary == 100
        
        errors = space.validate()
        assert len(errors) == 0
    
    def test_space_with_all_options(self):
        """Test SPACE with multiple options."""
        parser = ParameterParser()
        space = parser.parse_space("CYL,(10,5,10),RLSE,CONTIG")
        
        assert space.rlse is True
        assert space.contig is True
        
        errors = space.validate()
        assert len(errors) == 0
