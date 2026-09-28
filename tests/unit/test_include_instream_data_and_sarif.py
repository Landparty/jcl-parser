"""Round-4 regressions: INCLUDE inside in-stream data, quoted JCLLIB
libraries, and SARIF physicalLocation.artifactLocation."""

import pytest

from jclparser import parse_jcl
from jclparser.include_loader import IncludeMemberLoader, resolve_includes
from jclparser.lint import lint_job, to_sarif


class _Loader(IncludeMemberLoader):
    def load_member(self, member_name, libraries=None):
        if member_name == "COMMON":
            return "//EXTRA    DD DSN=X.Y,DISP=SHR\n"
        return None


@pytest.mark.unit
class TestIncludeInsideInstreamData:
    def test_include_in_dd_data_is_data(self):
        jcl = (
            "//J        JOB 1\n"
            "//S1       EXEC PGM=IEBGENER\n"
            "//SYSUT1   DD DATA,DLM=@@\n"
            "// INCLUDE MEMBER=COMMON\n"
            "@@\n"
            "//SYSUT2   DD SYSOUT=*\n"
        )
        assert resolve_includes(jcl, loader=_Loader()) == jcl
        step = parse_jcl(jcl, include_loader=_Loader()).steps[0]
        assert [d.name for d in step.dd_statements] == ["SYSUT1", "SYSUT2"]
        assert "INCLUDE MEMBER=COMMON" in step.dd_statements[0].inline_data

    def test_include_after_dd_star_data_is_expanded(self):
        # ``DD *`` data ends at the next ``//`` record, so this INCLUDE is JCL.
        jcl = (
            "//J        JOB 1\n"
            "//S1       EXEC PGM=IEBGENER\n"
            "//SYSUT1   DD *\n"
            "DATA\n"
            "// INCLUDE MEMBER=COMMON\n"
        )
        step = parse_jcl(jcl, include_loader=_Loader()).steps[0]
        assert [d.name for d in step.dd_statements] == ["SYSUT1", "EXTRA"]


@pytest.mark.unit
def test_quoted_jcllib_library_resolves_include(tmp_path):
    lib = tmp_path / "MY.PROCLIB"
    lib.mkdir()
    (lib / "COMMON.jcl").write_text("//INCDD    DD DSN=A.B,DISP=SHR\n")
    jcl = (
        "//J        JOB 1\n"
        "//L        JCLLIB ORDER=('MY.PROCLIB')\n"
        "//S        EXEC PGM=A\n"
        "// INCLUDE MEMBER=COMMON\n"
    )
    step = parse_jcl(jcl, proc_base_path=tmp_path).steps[0]
    assert [d.name for d in step.dd_statements] == ["INCDD"]


@pytest.mark.unit
class TestSarifArtifactLocation:
    def _findings(self):
        return lint_job(parse_jcl("//MYJOB    JOB  (ACCT)\n//STEP1    EXEC PGM=X\n"))

    def test_every_physical_location_has_artifact_location(self):
        sarif = to_sarif(self._findings())
        locations = [loc for r in sarif["runs"][0]["results"] for loc in r["locations"]]
        assert locations
        for loc in locations:
            assert "artifactLocation" in loc["physicalLocation"]

    def test_artifact_uri_is_emitted(self):
        sarif = to_sarif(self._findings(), artifact_uri="jobs/MYJOB.jcl")
        for result in sarif["runs"][0]["results"]:
            for loc in result["locations"]:
                assert loc["physicalLocation"]["artifactLocation"] == {
                    "uri": "jobs/MYJOB.jcl"
                }
