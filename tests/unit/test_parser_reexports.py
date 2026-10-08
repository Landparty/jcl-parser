"""``jclparser.parser`` keeps every name it exposed before the module split.

Downstream code (the vendored backend copy among it) imports helpers straight
from ``jclparser.parser``; moving an implementation to a private module must
not turn those imports into ``ImportError``.
"""

import pytest

from jclparser import parser

pytestmark = pytest.mark.unit

# Names that moved out of parser.py but must stay importable from it.
LEGACY_NAMES = [
    # moved to _source_scanner.py
    "_merge_source_lines",
    "_instream_delimiter",
    "_expects_continuation",
    # imported by the pre-scan before it moved
    "ContinuationLineHandler",
    "instream_delimiter",
    "is_continued_card_image",
    # moved to _statement_parser.py / _job_builder.py earlier
    "parse_statement",
    "_parse_parameters",
    "_STATEMENT_TYPES",
    "JobBuilder",
    "resolve_set_symbols",
    "load_external_procedures",
]


@pytest.mark.parametrize("name", LEGACY_NAMES)
def test_legacy_name_still_importable(name):
    assert hasattr(parser, name), f"jclparser.parser.{name} is no longer importable"
