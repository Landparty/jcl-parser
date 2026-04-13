"""
Dedicated unit tests for jclparser/dataset_lifecycle.py.

Covers:
- _parse_disp_tokens: all input forms (string, list, parenthesized, bare)
- _action_from_disp: all status tokens
- analyze_dataset_lifecycle: event log construction
- validate_dataset_lifecycle: duplicate-catlg, use-after-uncatlg,
  forward-reference (with and without later ALLOCATE) detection
"""

import pytest

from jclparser.dataset_lifecycle import (
    DatasetEvent,
    _action_from_disp,
    _parse_disp_tokens,
    analyze_dataset_lifecycle,
    validate_dataset_lifecycle,
)
from jclparser import parse_jcl


# ---------------------------------------------------------------------------
# _parse_disp_tokens
# ---------------------------------------------------------------------------


class TestParseDispTokens:
    """Unit tests for the internal _parse_disp_tokens helper."""

    def test_empty_disposition_returns_empty_tuple(self):
        assert _parse_disp_tokens(None) == ("", "", "")
        assert _parse_disp_tokens("") == ("", "", "")

    def test_bare_string_status_only(self):
        status, normal, abnormal = _parse_disp_tokens("SHR")
        assert status == "SHR"
        assert normal == ""
        assert abnormal == ""

    def test_parenthesized_two_token(self):
        status, normal, abnormal = _parse_disp_tokens("(NEW,CATLG)")
        assert status == "NEW"
        assert normal == "CATLG"
        assert abnormal == ""

    def test_parenthesized_three_token(self):
        status, normal, abnormal = _parse_disp_tokens("(NEW,CATLG,DELETE)")
        assert status == "NEW"
        assert normal == "CATLG"
        assert abnormal == "DELETE"

    def test_list_form_two_elements(self):
        status, normal, abnormal = _parse_disp_tokens(["OLD", "KEEP"])
        assert status == "OLD"
        assert normal == "KEEP"
        assert abnormal == ""

    def test_list_form_three_elements(self):
        status, normal, abnormal = _parse_disp_tokens(["MOD", "CATLG", "KEEP"])
        assert status == "MOD"
        assert normal == "CATLG"
        assert abnormal == "KEEP"

    def test_list_form_is_uppercased(self):
        status, normal, abnormal = _parse_disp_tokens(["new", "catlg", "delete"])
        assert status == "NEW"
        assert normal == "CATLG"
        assert abnormal == "DELETE"

    def test_string_without_parens_comma_separated(self):
        status, normal, abnormal = _parse_disp_tokens("NEW,CATLG,DELETE")
        assert status == "NEW"
        assert normal == "CATLG"
        assert abnormal == "DELETE"

    def test_whitespace_is_stripped(self):
        status, normal, abnormal = _parse_disp_tokens("( NEW , CATLG , DELETE )")
        assert status == "NEW"
        assert normal == "CATLG"
        assert abnormal == "DELETE"

    def test_list_with_none_elements(self):
        status, normal, abnormal = _parse_disp_tokens([None, "CATLG"])
        assert status == "NONE"  # str(None).upper() == 'NONE' — implementation behaviour
        assert normal == "CATLG"

    def test_single_element_list(self):
        status, normal, abnormal = _parse_disp_tokens(["SHR"])
        assert status == "SHR"
        assert normal == ""
        assert abnormal == ""


# ---------------------------------------------------------------------------
# _action_from_disp
# ---------------------------------------------------------------------------


class TestActionFromDisp:
    """_action_from_disp maps all four recognised status tokens."""

    def test_new_maps_to_allocate(self):
        assert _action_from_disp("NEW") == "ALLOCATE"

    def test_old_maps_to_open_exclusive(self):
        assert _action_from_disp("OLD") == "OPEN_EXCLUSIVE"

    def test_shr_maps_to_open_shared(self):
        assert _action_from_disp("SHR") == "OPEN_SHARED"

    def test_mod_maps_to_extend(self):
        assert _action_from_disp("MOD") == "EXTEND"

    def test_unknown_maps_to_unknown(self):
        assert _action_from_disp("BOGUS") == "UNKNOWN"

    def test_empty_string_maps_to_unknown(self):
        assert _action_from_disp("") == "UNKNOWN"


# ---------------------------------------------------------------------------
# analyze_dataset_lifecycle
# ---------------------------------------------------------------------------


class TestAnalyzeDatasetLifecycle:
    """analyze_dataset_lifecycle builds a correct per-dataset event log."""

    def _job(self, jcl: str):
        return parse_jcl(jcl)

    def test_single_step_new_catlg(self):
        jcl = (
            "//MYJOB  JOB\n"
            "//STEP1  EXEC PGM=IEFBR14\n"
            "//DD1    DD DSN=MY.DATASET,DISP=(NEW,CATLG,DELETE)\n"
        )
        job = self._job(jcl)
        events = analyze_dataset_lifecycle(job)
        assert "MY.DATASET" in events
        evts = events["MY.DATASET"]
        assert len(evts) == 1
        assert evts[0].action == "ALLOCATE"
        assert evts[0].disp_status == "NEW"
        assert evts[0].disp_normal == "CATLG"
        assert evts[0].disp_abnormal == "DELETE"

    def test_two_step_lifecycle(self):
        jcl = (
            "//MYJOB  JOB\n"
            "//STEP1  EXEC PGM=IEFBR14\n"
            "//DD1    DD DSN=MY.DATASET,DISP=(NEW,CATLG)\n"
            "//STEP2  EXEC PGM=SORT\n"
            "//DD2    DD DSN=MY.DATASET,DISP=(OLD,KEEP)\n"
        )
        job = self._job(jcl)
        events = analyze_dataset_lifecycle(job)
        evts = events.get("MY.DATASET", [])
        assert len(evts) == 2
        assert evts[0].action == "ALLOCATE"
        assert evts[1].action == "OPEN_EXCLUSIVE"

    def test_shr_disposition(self):
        jcl = (
            "//MYJOB  JOB\n"
            "//STEP1  EXEC PGM=IEFBR14\n"
            "//DD1    DD DSN=SHARED.DS,DISP=SHR\n"
        )
        job = self._job(jcl)
        events = analyze_dataset_lifecycle(job)
        evts = events.get("SHARED.DS", [])
        assert evts[0].action == "OPEN_SHARED"

    def test_dd_without_dsn_is_skipped(self):
        jcl = (
            "//MYJOB  JOB\n"
            "//STEP1  EXEC PGM=IEFBR14\n"
            "//SYSOUT DD SYSOUT=*\n"
        )
        job = self._job(jcl)
        events = analyze_dataset_lifecycle(job)
        assert len(events) == 0

    def test_dd_without_disp_is_skipped(self):
        jcl = (
            "//MYJOB  JOB\n"
            "//STEP1  EXEC PGM=IEFBR14\n"
            "//DD1    DD DSN=MY.DS\n"
        )
        job = self._job(jcl)
        events = analyze_dataset_lifecycle(job)
        # No DISP → no status → event is skipped
        assert "MY.DS" not in events

    def test_dataset_name_key_is_uppercased(self):
        jcl = (
            "//MYJOB  JOB\n"
            "//STEP1  EXEC PGM=IEFBR14\n"
            "//DD1    DD DSN=My.Dataset,DISP=(NEW,CATLG)\n"
        )
        job = self._job(jcl)
        events = analyze_dataset_lifecycle(job)
        assert "MY.DATASET" in events

    def test_mod_disposition(self):
        jcl = (
            "//MYJOB  JOB\n"
            "//STEP1  EXEC PGM=IEFBR14\n"
            "//DD1    DD DSN=MY.DS,DISP=(MOD,KEEP)\n"
        )
        job = self._job(jcl)
        events = analyze_dataset_lifecycle(job)
        evts = events.get("MY.DS", [])
        assert evts[0].action == "EXTEND"


# ---------------------------------------------------------------------------
# validate_dataset_lifecycle
# ---------------------------------------------------------------------------


class TestValidateDatasetLifecycle:
    """validate_dataset_lifecycle produces correct diagnostics."""

    def _job(self, jcl: str):
        return parse_jcl(jcl)

    def test_no_errors_for_clean_job(self):
        jcl = (
            "//MYJOB  JOB\n"
            "//STEP1  EXEC PGM=IEFBR14\n"
            "//DD1    DD DSN=MY.DATASET,DISP=(NEW,CATLG,DELETE)\n"
            "//STEP2  EXEC PGM=SORT\n"
            "//DD2    DD DSN=MY.DATASET,DISP=(OLD,KEEP)\n"
        )
        job = self._job(jcl)
        errors = validate_dataset_lifecycle(job)
        assert errors == []

    def test_duplicate_catlg_produces_warning(self):
        jcl = (
            "//MYJOB  JOB\n"
            "//STEP1  EXEC PGM=IEFBR14\n"
            "//DD1    DD DSN=MY.DATASET,DISP=(NEW,CATLG)\n"
            "//STEP2  EXEC PGM=SORT\n"
            "//DD2    DD DSN=MY.DATASET,DISP=(NEW,CATLG)\n"
        )
        job = self._job(jcl)
        errors = validate_dataset_lifecycle(job)
        assert len(errors) >= 1
        messages = " ".join(e.message for e in errors)
        assert "MY.DATASET" in messages.upper() or "dataset" in messages.lower()

    def test_use_after_uncatlg_produces_warning(self):
        jcl = (
            "//MYJOB  JOB\n"
            "//STEP1  EXEC PGM=IEFBR14\n"
            "//DD1    DD DSN=MY.DATASET,DISP=(NEW,UNCATLG)\n"
            "//STEP2  EXEC PGM=SORT\n"
            "//DD2    DD DSN=MY.DATASET,DISP=(OLD,KEEP)\n"
        )
        job = self._job(jcl)
        errors = validate_dataset_lifecycle(job)
        assert len(errors) >= 1

    def test_forward_reference_with_later_allocate_produces_warning(self):
        """Step 1 opens OLD before Step 2 allocates it → forward-reference warning."""
        jcl = (
            "//MYJOB  JOB\n"
            "//STEP1  EXEC PGM=IEFBR14\n"
            "//DD1    DD DSN=MY.DATASET,DISP=(OLD,KEEP)\n"
            "//STEP2  EXEC PGM=SORT\n"
            "//DD2    DD DSN=MY.DATASET,DISP=(NEW,CATLG)\n"
        )
        job = self._job(jcl)
        errors = validate_dataset_lifecycle(job)
        assert len(errors) >= 1
        messages = " ".join(e.message for e in errors)
        assert "MY.DATASET" in messages.upper() or "forward" in messages.lower() or "catalog" in messages.lower()

    def test_forward_reference_without_later_allocate_no_warning(self):
        """Step opens OLD, but no later step allocates it — no forward-ref warning."""
        jcl = (
            "//MYJOB  JOB\n"
            "//STEP1  EXEC PGM=IEFBR14\n"
            "//DD1    DD DSN=EXISTING.DATASET,DISP=(OLD,KEEP)\n"
        )
        job = self._job(jcl)
        errors = validate_dataset_lifecycle(job)
        # No later ALLOCATE → the forward-reference heuristic does NOT fire
        # (the dataset may simply already exist in the catalog)
        assert errors == []

    def test_empty_job_no_errors(self):
        jcl = "//MYJOB  JOB\n//STEP1  EXEC PGM=IEFBR14\n"
        job = self._job(jcl)
        errors = validate_dataset_lifecycle(job)
        assert errors == []

    def test_delete_resets_catlg_tracking(self):
        """DELETE after CATLG allows a fresh CATLG in a later step."""
        jcl = (
            "//MYJOB  JOB\n"
            "//STEP1  EXEC PGM=IEFBR14\n"
            "//DD1    DD DSN=MY.DATASET,DISP=(NEW,CATLG)\n"
            "//STEP2  EXEC PGM=SORT\n"
            "//DD2    DD DSN=MY.DATASET,DISP=(OLD,DELETE)\n"
            "//STEP3  EXEC PGM=IEFBR14\n"
            "//DD3    DD DSN=MY.DATASET,DISP=(NEW,CATLG)\n"
        )
        job = self._job(jcl)
        errors = validate_dataset_lifecycle(job)
        # DELETE in step 2 resets the catalog state, so step 3's CATLG is fine
        assert errors == []
