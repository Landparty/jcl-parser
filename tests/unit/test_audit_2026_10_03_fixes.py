"""Regression tests for the jcl-parser findings of the 2026-10-03 project audit.

* A one-line string was read as a file path (anything ending in ``.jcl``,
  containing a slash, or naming an existing file), so upload text such as
  ``/etc/passwd`` read a server file and echoed its first line in the error.
* Any DD whose operands contained the text ``DLM=`` -- even inside a quoted
  value, or on a DD that is neither ``DD *`` nor ``DD DATA`` -- opened
  in-stream data in the source pre-scan, while the JobBuilder (which only
  opens data for ``*`` / ``DATA``) had no DD to attach it to: every later
  statement was silently dropped.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from jclparser import parse_jcl
from jclparser.errors import JCLSyntaxError
from jclparser.jcl_file_type import detect_file_type
from jclparser.utils import instream_delimiter, read_source

pytestmark = pytest.mark.unit

SECRET = "root:x:0:0:SECRET-FIRST-LINE"


class TestStringIsNeverAPath:
    @pytest.fixture
    def secret_file(self, tmp_path: Path) -> Path:
        path = tmp_path / "passwd"
        path.write_text(SECRET + "\nsecond line\n")
        return path

    def test_absolute_path_string_is_not_read(self, secret_file: Path) -> None:
        assert read_source(str(secret_file)) == str(secret_file)

    def test_parse_error_does_not_echo_file_contents(self, secret_file: Path) -> None:
        try:
            parse_jcl(str(secret_file))
        except JCLSyntaxError as exc:
            assert "SECRET" not in str(exc)
        # (no error is fine too, as long as nothing was read)

    def test_relative_name_of_existing_file_is_not_read(
        self, secret_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(secret_file.parent)
        assert read_source("passwd") == "passwd"
        (secret_file.parent / "JOB.jcl").write_text("//J JOB\n")
        assert read_source("JOB.jcl") == "JOB.jcl"

    def test_detect_file_type_does_not_read_a_string(self, secret_file: Path) -> None:
        secret_file.write_text("//P PROC\n//S EXEC PGM=X\n// PEND\n")
        assert detect_file_type(secret_file) != detect_file_type(str(secret_file))

    def test_path_and_file_object_still_read(self, tmp_path: Path) -> None:
        path = tmp_path / "job.jcl"
        path.write_text("//J JOB\n//S EXEC PGM=X\n")
        assert parse_jcl(path).name == "J"
        with path.open() as fh:
            assert parse_jcl(fh).name == "J"
        assert parse_jcl(io.StringIO("//J JOB\n//S EXEC PGM=X\n")).name == "J"

    def test_missing_path_still_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            parse_jcl(tmp_path / "nope.jcl")


def _step_names(jcl: str) -> list[str]:
    return [s.name for s in parse_jcl(jcl).steps]


class TestDlmOnlyMeansSomethingOnInstreamDds:
    def test_dlm_inside_quoted_path_does_not_swallow_job(self) -> None:
        jcl = (
            "//J JOB\n"
            "//S1 EXEC PGM=A\n"
            "//DD1 DD PATH='/u/app/DLM=1/in',PATHDISP=KEEP\n"
            "//S2 EXEC PGM=B\n"
            "//DD2 DD DSN=X.Y,DISP=SHR\n"
        )
        assert _step_names(jcl) == ["S1", "S2"]
        assert parse_jcl(jcl).steps[1].dd_statements[0].name == "DD2"

    def test_dlm_on_dataset_dd_is_ignored(self) -> None:
        jcl = (
            "//J JOB\n"
            "//S1 EXEC PGM=A\n"
            "//DD1 DD DSN=A.B,DISP=SHR,DLM=$$\n"
            "//S2 EXEC PGM=B\n"
        )
        assert _step_names(jcl) == ["S1", "S2"]

    def test_dlm_inside_quoted_dsn_on_continued_dd(self) -> None:
        jcl = (
            "//J JOB\n"
            "//S1 EXEC PGM=A\n"
            "//DD1 DD DISP=SHR,\n"
            "//   PATH='/u/DLM=$$'\n"
            "//S2 EXEC PGM=B\n"
        )
        assert _step_names(jcl) == ["S1", "S2"]

    @pytest.mark.parametrize(
        "dd, delimiter",
        [
            ("//SYSIN DD *,DLM=$$", "$$"),
            ("//SYSIN DD DATA,DLM=$$", "$$"),
            ("//SYSIN DD *,DLM='@@'", "@@"),
        ],
    )
    def test_real_dlm_still_delimits(self, dd: str, delimiter: str) -> None:
        jcl = (
            "//J JOB\n"
            "//S1 EXEC PGM=A\n"
            f"{dd}\n"
            "DATA LINE\n"
            "//NOT A STATEMENT\n"
            f"{delimiter}\n"
            "//S2 EXEC PGM=B\n"
        )
        job = parse_jcl(jcl)
        assert [s.name for s in job.steps] == ["S1", "S2"]
        sysin = job.steps[0].dd_statements[0]
        assert "DATA LINE" in sysin.inline_data
        assert "//NOT A STATEMENT" in sysin.inline_data


class TestInstreamDelimiterRule:
    @pytest.mark.parametrize(
        "params, expected",
        [
            ({"*": True}, ("/*", True)),
            ({"_pos_0": "*", "DLM": "$$"}, ("$$", False)),
            ({"DATA": True}, ("/*", False)),
            ({"DATA": True, "DLM": "'@@'"}, ("@@", False)),
            ({"DSN": "A.B", "DLM": "$$"}, None),
            ({"PATH": "/u/DLM=1"}, None),
        ],
    )
    def test_rule(self, params: dict, expected: tuple | None) -> None:
        assert instream_delimiter(params) == expected


INCLUDE_JOB = (
    "//J JOB\n//LIB JCLLIB ORDER=(MY.LIB)\n//S EXEC PGM=X\n//I INCLUDE MEMBER=SECRET\n"
)
PROC_JOB = "//J JOB\n//LIB JCLLIB ORDER=(MYLIB)\n//S EXEC MYPROC\n"


class TestNoImplicitWorkingDirectory:
    """Library members are named by the JCL, so only a configured base is searched."""

    @pytest.fixture
    def cwd_with_libraries(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> Path:
        monkeypatch.delenv("JCL_PROCLIB_PATH", raising=False)
        (tmp_path / "MY" / "LIB").mkdir(parents=True)
        (tmp_path / "MY" / "LIB" / "SECRET.jcl").write_text("//LEAKED DD DSN=SECRET\n")
        (tmp_path / "MYLIB").mkdir()
        (tmp_path / "MYLIB" / "MYPROC.jcl").write_text(
            "//MYPROC PROC\n//PS EXEC PGM=FROMCWD\n// PEND\n"
        )
        monkeypatch.chdir(tmp_path)
        return tmp_path

    def test_include_member_not_read_from_cwd(self, cwd_with_libraries: Path) -> None:
        from jclparser.include_loader import JCLLIBMemberLoader

        assert JCLLIBMemberLoader().load_member("SECRET", ["MY.LIB"]) is None
        try:
            job = parse_jcl(INCLUDE_JOB)
        except Exception as exc:  # an unresolved INCLUDE may be reported
            assert "LEAKED" not in str(exc)
        else:
            assert all(dd.name != "LEAKED" for s in job.steps for dd in s.dd_statements)

    def test_proc_not_read_from_cwd(self, cwd_with_libraries: Path) -> None:
        from jclparser.proc_loader import JCLLIBProcedureLoader, create_default_loader

        assert JCLLIBProcedureLoader().load_procedure("MYPROC", ["MYLIB"]) is None
        assert JCLLIBProcedureLoader().list_all_procedures() == {}
        loader = create_default_loader([])
        assert loader.load_procedure("MYPROC", ["MYLIB"]) is None

    def test_explicit_base_and_env_var_still_work(
        self, cwd_with_libraries: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from jclparser.include_loader import JCLLIBMemberLoader
        from jclparser.proc_loader import JCLLIBProcedureLoader

        base = cwd_with_libraries
        assert JCLLIBProcedureLoader(base).load_procedure("MYPROC", ["MYLIB"])
        assert JCLLIBMemberLoader(base).load_member("SECRET", ["MY.LIB"])
        monkeypatch.setenv("JCL_PROCLIB_PATH", str(base))
        assert JCLLIBProcedureLoader().load_procedure("MYPROC", ["MYLIB"])
        assert JCLLIBMemberLoader().load_member("SECRET", ["MY.LIB"])


class TestLibraryMemberSizeCap:
    def test_oversized_members_are_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from jclparser import include_loader, proc_loader
        from jclparser.include_loader import JCLLIBMemberLoader
        from jclparser.proc_loader import JCLLIBProcedureLoader

        (tmp_path / "LIB").mkdir()
        proc = "//BIG PROC\n//PS EXEC PGM=X\n// PEND\n" + "//* pad\n" * 50
        (tmp_path / "LIB" / "BIG.jcl").write_text(proc)
        monkeypatch.setattr(proc_loader, "MAX_LIBRARY_MEMBER_BYTES", 64)
        monkeypatch.setattr(include_loader, "MAX_LIBRARY_MEMBER_BYTES", 64)
        assert JCLLIBProcedureLoader(tmp_path).load_procedure("BIG", ["LIB"]) is None
        assert JCLLIBMemberLoader(tmp_path).load_member("BIG", ["LIB"]) is None

    def test_read_refuses_before_reading(self, tmp_path: Path) -> None:
        import errno

        from jclparser.utils import _read_file_with_fallback

        path = tmp_path / "f"
        path.write_text("x" * 100)
        with pytest.raises(OSError) as info:
            _read_file_with_fallback(path, max_bytes=10)
        assert info.value.errno == errno.EFBIG
        assert _read_file_with_fallback(path, max_bytes=100) == "x" * 100


class TestMaxStepsBoundsFanOut:
    @staticmethod
    def _fan_out_job(width: int, depth: int) -> str:
        """P0 calls P1 *width* times, P1 calls P2 *width* times, ... P<depth> is a leaf."""
        lines = ["//J JOB"]
        for level in range(depth):
            lines.append(f"//P{level} PROC")
            lines += [f"//C{i} EXEC P{level + 1}" for i in range(width)]
            lines.append("// PEND")
        lines += [f"//P{depth} PROC", "//LEAF EXEC PGM=IEFBR14", "// PEND"]
        lines.append("//S EXEC P0")
        return "\n".join(lines) + "\n"

    def test_limit_stops_explosion_while_it_is_built(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from jclparser import explosion
        from jclparser.errors import JCLStructureError

        job = parse_jcl(self._fan_out_job(width=6, depth=5))  # 7,776 leaf steps
        produced: list[int] = []
        real = explosion._clone_step_for_explosion

        def counting_clone(step):  # type: ignore[no-untyped-def]
            produced.append(1)
            return real(step)

        monkeypatch.setattr(explosion, "_clone_step_for_explosion", counting_clone)
        with pytest.raises(JCLStructureError, match="more than 10 steps"):
            job.explode(max_steps=10)
        assert len(produced) < 100

    def test_default_limit_is_on(self) -> None:
        from jclparser.errors import JCLStructureError
        from jclparser.explosion import DEFAULT_MAX_STEPS

        assert DEFAULT_MAX_STEPS > 255  # never trips on a real z/OS job
        job = parse_jcl(self._fan_out_job(width=11, depth=4))  # 14,641 leaves
        with pytest.raises(JCLStructureError):
            job.explode()
        assert len(job.explode(max_steps=0).steps) == 11**4

    def test_counts_steps_inside_if_blocks_and_plain_steps(self) -> None:
        from jclparser.errors import JCLStructureError

        jcl = self._fan_out_job(width=3, depth=1) + "//T EXEC PGM=X\n"
        job = parse_jcl(jcl)
        assert len(job.explode(max_steps=4).steps) == 4
        with pytest.raises(JCLStructureError):
            job.explode(max_steps=3)


class TestOkfStalenessHook:
    """The pre-commit hook pointed every path at a docs/OKF.md that never existed."""

    @pytest.fixture
    def hook(self):  # type: ignore[no-untyped-def]
        import importlib.util

        root = Path(__file__).resolve().parents[2]
        spec = importlib.util.spec_from_file_location(
            "okf_staleness_check", root / "scripts" / "okf_staleness_check.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module, root

    def test_every_mapped_page_exists(self, hook) -> None:  # type: ignore[no-untyped-def]
        module, root = hook
        pages = {page for _, pages in module.OKF_MAP for page in pages}
        pages.add(module.OKF_LOG)
        assert all((root / page).is_file() for page in pages), pages

    def test_specific_page_before_directory_fallback(self, hook) -> None:  # type: ignore[no-untyped-def]
        module, _ = hook
        assert module._get_okf_files("jclparser/explosion.py")[0].endswith(
            "proc-expansion.md"
        )
        assert module.OKF_LOG in module._get_okf_files("tests/unit/x.py")
        assert module._get_okf_files("README.md") == []
