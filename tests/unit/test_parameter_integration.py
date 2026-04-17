"""
Integration tests for parameter parsing with the model.
"""

from jclparser import parse_jcl


class TestDCBIntegration:
    """Test DCB parameter integration with DDStatement."""

    def test_parse_jcl_with_dcb(self):
        """Test parsing JCL with DCB parameter."""
        jcl = """
//MYJOB JOB (12345),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1   DD DSN=MY.DATA,
//         DISP=(NEW,CATLG),
//         DCB=(RECFM=FB,LRECL=80,BLKSIZE=27920)
"""
        job = parse_jcl(jcl)

        dd = job.steps[0].get_dd("DD1")
        assert dd is not None

        # Access structured DCB
        dcb = dd.dcb
        assert dcb is not None
        assert dcb.recfm == "FB"
        assert dcb.lrecl == 80
        assert dcb.blksize == 27920

        # Validation should pass
        errors = dcb.validate()
        assert len(errors) == 0

    def test_dcb_with_bufno(self):
        """Test DCB with BUFNO parameter."""
        jcl = """
//MYJOB JOB (12345),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1   DD DSN=MY.DATA,
//         DCB=(RECFM=FB,LRECL=80,BLKSIZE=27920,BUFNO=20)
"""
        job = parse_jcl(jcl)

        dd = job.steps[0].get_dd("DD1")
        dcb = dd.dcb

        assert dcb.bufno == 20

    def test_dcb_with_dsorg(self):
        """Test DCB with DSORG parameter."""
        jcl = """
//MYJOB JOB (12345),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1   DD DSN=MY.DATA,
//         DCB=(RECFM=FB,LRECL=80,DSORG=PS)
"""
        job = parse_jcl(jcl)

        dd = job.steps[0].get_dd("DD1")
        dcb = dd.dcb

        assert dcb.dsorg == "PS"

    def test_dcb_validation_invalid(self):
        """Test DCB validation with invalid parameters."""
        jcl = """
//MYJOB JOB (12345),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1   DD DSN=MY.DATA,
//         DCB=(RECFM=INVALID,LRECL=80)
"""
        job = parse_jcl(jcl)

        dd = job.steps[0].get_dd("DD1")
        dcb = dd.dcb

        errors = dcb.validate()
        assert len(errors) > 0
        assert any("RECFM" in err for err in errors)

    def test_dcb_none_when_not_present(self):
        """Test that dcb is None when DCB parameter not present."""
        jcl = """
//MYJOB JOB (12345),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1   DD DSN=MY.DATA,DISP=SHR
"""
        job = parse_jcl(jcl)

        dd = job.steps[0].get_dd("DD1")
        assert dd.dcb is None

    def test_dcb_caching(self):
        """Test that DCB parsing is cached."""
        jcl = """
//MYJOB JOB (12345),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1   DD DSN=MY.DATA,
//         DCB=(RECFM=FB,LRECL=80)
"""
        job = parse_jcl(jcl)

        dd = job.steps[0].get_dd("DD1")

        # Access twice - should return same object
        dcb1 = dd.dcb
        dcb2 = dd.dcb

        assert dcb1 is dcb2


class TestSPACEIntegration:
    """Test SPACE parameter integration with DDStatement."""

    def test_parse_jcl_with_space(self):
        """Test parsing JCL with SPACE parameter."""
        jcl = """
//MYJOB JOB (12345),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1   DD DSN=MY.DATA,
//         DISP=(NEW,CATLG),
//         SPACE=(CYL,(100,10),RLSE)
"""
        job = parse_jcl(jcl)

        dd = job.steps[0].get_dd("DD1")
        assert dd is not None

        # Access structured SPACE
        space = dd.space
        assert space is not None
        assert space.unit == "CYL"
        assert space.primary == 100
        assert space.secondary == 10
        assert space.rlse is True

        # Validation should pass
        errors = space.validate()
        assert len(errors) == 0

    def test_space_with_directory(self):
        """Test SPACE with directory blocks."""
        jcl = """
//MYJOB JOB (12345),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1   DD DSN=MY.PDS,
//         DISP=(NEW,CATLG),
//         SPACE=(CYL,(10,5,20))
"""
        job = parse_jcl(jcl)

        dd = job.steps[0].get_dd("DD1")
        space = dd.space

        assert space.directory == 20

    def test_space_track_allocation(self):
        """Test SPACE with track allocation."""
        jcl = """
//MYJOB JOB (12345),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1   DD DSN=MY.DATA,
//         SPACE=(TRK,(500,100))
"""
        job = parse_jcl(jcl)

        dd = job.steps[0].get_dd("DD1")
        space = dd.space

        assert space.unit == "TRK"
        assert space.primary == 500
        assert space.secondary == 100

    def test_space_with_contig(self):
        """Test SPACE with CONTIG option."""
        jcl = """
//MYJOB JOB (12345),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1   DD DSN=MY.DATA,
//         SPACE=(CYL,(10,5),RLSE,CONTIG)
"""
        job = parse_jcl(jcl)

        dd = job.steps[0].get_dd("DD1")
        space = dd.space

        assert space.rlse is True
        assert space.contig is True

    def test_space_none_when_not_present(self):
        """Test that space is None when SPACE parameter not present."""
        jcl = """
//MYJOB JOB (12345),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1   DD DSN=MY.DATA,DISP=SHR
"""
        job = parse_jcl(jcl)

        dd = job.steps[0].get_dd("DD1")
        assert dd.space is None

    def test_space_validation_invalid(self):
        """Test SPACE validation with invalid parameters."""
        jcl = """
//MYJOB JOB (12345),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1   DD DSN=MY.DATA,
//         SPACE=(CYL,(0,5))
"""
        job = parse_jcl(jcl)

        dd = job.steps[0].get_dd("DD1")
        space = dd.space

        errors = space.validate()
        assert len(errors) > 0
        assert any("primary" in err.lower() for err in errors)


class TestCombinedParameters:
    """Test DD statements with both DCB and SPACE."""

    def test_dd_with_dcb_and_space(self):
        """Test DD with both DCB and SPACE parameters."""
        jcl = """
//MYJOB JOB (12345),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1   DD DSN=MY.DATA,
//         DISP=(NEW,CATLG),
//         SPACE=(CYL,(100,10),RLSE),
//         DCB=(RECFM=FB,LRECL=80,BLKSIZE=27920)
"""
        job = parse_jcl(jcl)

        dd = job.steps[0].get_dd("DD1")

        # Both should be accessible
        assert dd.dcb is not None
        assert dd.space is not None

        # Verify DCB
        assert dd.dcb.recfm == "FB"
        assert dd.dcb.lrecl == 80

        # Verify SPACE
        assert dd.space.unit == "CYL"
        assert dd.space.primary == 100
        assert dd.space.rlse is True

    def test_complex_dd_with_continuation(self):
        """Test complex DD with continuation lines."""
        jcl = """
//MYJOB JOB (12345),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1   DD DSN=MY.VERY.LONG.DATASET.NAME,
//         DISP=(NEW,CATLG,DELETE),
//         UNIT=SYSDA,
//         SPACE=(CYL,(100,10,5),RLSE),
//         DCB=(RECFM=FB,LRECL=80,BLKSIZE=27920,
//              BUFNO=20,DSORG=PS)
"""
        job = parse_jcl(jcl)

        dd = job.steps[0].get_dd("DD1")

        # Verify DCB with all parameters
        dcb = dd.dcb
        assert dcb.recfm == "FB"
        assert dcb.lrecl == 80
        assert dcb.blksize == 27920
        assert dcb.bufno == 20
        assert dcb.dsorg == "PS"

        # Verify SPACE
        space = dd.space
        assert space.unit == "CYL"
        assert space.primary == 100
        assert space.secondary == 10
        assert space.directory == 5
        assert space.rlse is True

        # Both should validate successfully
        assert len(dcb.validate()) == 0
        assert len(space.validate()) == 0


class TestBackwardCompatibility:
    """Test that existing code still works."""

    def test_raw_parameters_still_accessible(self):
        """Test that raw parameter values are still accessible."""
        jcl = """
//MYJOB JOB (12345),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1   DD DSN=MY.DATA,
//         DCB=(RECFM=FB,LRECL=80)
"""
        job = parse_jcl(jcl)

        dd = job.steps[0].get_dd("DD1")

        # Raw parameter should still be accessible
        assert "DCB" in dd.parameters
        # Parameter can be string or list depending on how it was parsed

        # Structured access works
        assert dd.dcb.recfm == "FB"

    def test_dd_without_dcb_or_space(self):
        """Test DD without DCB or SPACE parameters."""
        jcl = """
//MYJOB JOB (12345),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1   DD DSN=MY.DATA,DISP=SHR
//DD2   DD SYSOUT=*
"""
        job = parse_jcl(jcl)

        dd1 = job.steps[0].get_dd("DD1")
        dd2 = job.steps[0].get_dd("DD2")

        # Should not raise errors
        assert dd1.dcb is None
        assert dd1.space is None
        assert dd2.dcb is None
        assert dd2.space is None
