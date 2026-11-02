"""Issue #166: a dataset in an unnamed concatenation member is reported
under the name of the DD its concatenation belongs to."""

import pytest

from jclparser import parse_jcl
from jclparser.dataset_lifecycle import (
    analyze_dataset_lifecycle,
    validate_dataset_lifecycle,
)

pytestmark = pytest.mark.unit

JCL = """//J JOB 1
//S1 EXEC PGM=A
//D1 DD DSN=A.B,DISP=(OLD,UNCATLG)
//S2 EXEC PGM=A
//IN DD DSN=X.Y,DISP=SHR
//   DD DSN=Q.R,DISP=SHR
//   DD DSN=A.B,DISP=SHR
//OUT DD DSN=Z.Z,DISP=SHR
"""


def test_message_names_the_owning_dd_and_member() -> None:
    messages = [e.message for e in validate_dataset_lifecycle(parse_jcl(JCL))]
    expected = (
        "Dataset 'A.B' opened in step 'S2' (DD IN, concatenation member 3) "
        "after being uncataloged in step 'S1'"
    )
    assert messages == [expected]


def test_events_carry_the_owning_dd_name() -> None:
    lifecycle = analyze_dataset_lifecycle(parse_jcl(JCL))
    first, second = lifecycle["A.B"]
    assert (first.dd_name, first.concatenation_member) == ("D1", 0)
    assert (second.dd_name, second.concatenation_member) == ("IN", 3)
    assert second.dd_label == "IN, concatenation member 3"
    member2 = lifecycle["Q.R"][0]
    assert (member2.dd_name, member2.concatenation_member) == ("IN", 2)
    # A named DD after the concatenation starts a new owner.
    out = lifecycle["Z.Z"][0]
    assert (out.dd_name, out.concatenation_member, out.dd_label) == ("OUT", 0, "OUT")


def test_leading_unnamed_dd_keeps_empty_name() -> None:
    jcl = """//J JOB 1
//S1 EXEC PGM=A
//   DD DSN=A.B,DISP=SHR
"""
    lifecycle = analyze_dataset_lifecycle(parse_jcl(jcl))
    events = lifecycle.get("A.B", [])
    assert all(e.dd_name == "" and e.concatenation_member == 0 for e in events)
