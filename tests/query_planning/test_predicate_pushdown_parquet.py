"""
Test predicate pushdown using the document collections
"""
import os
import sys

sys.path.insert(1, os.path.join(sys.path[0], "../.."))

import opteryx


def test_predicate_pushdowns_blobs():

    os.environ["GCP_PROJECT_ID"] = "mabeldev"

    conn = opteryx.connect()

    # TEST PREDICATE PUSHDOWN
    cur = conn.cursor()
    cur.execute(
        "SET enable_optimizer = false; SELECT user_name FROM testdata.formats.parquet WITH(NO_PARTITION) WHERE user_verified = TRUE;"
    )
    # if we disable pushdown, we read all the rows from the source and we do the filter
    assert cur.rowcount == 711, cur.rowcount
    assert cur.stats["rows_read"] == 100000, cur.stats

    cur = conn.cursor()
    cur.execute(
        "SELECT user_name FROM testdata.formats.parquet WITH(NO_PARTITION, NO_PUSH_SELECTION) WHERE user_verified = TRUE;"
    )
    # if we disable pushdown, we read all the rows from the source and we do the filter
    assert cur.rowcount == 711, cur.rowcount
    assert cur.stats["rows_read"] == 100000, cur.stats

    cur = conn.cursor()
    cur.execute(
        "SELECT user_name FROM testdata.formats.parquet WITH(NO_PARTITION) WHERE user_verified = TRUE;"
    )
    # when pushdown is enabled, we only read the matching rows from the source
    assert cur.rowcount == 711, cur.rowcount
    assert cur.stats["rows_read"] == 711, cur.stats

    cur = conn.cursor()
    cur.execute(
        "SELECT user_name FROM testdata.formats.parquet WITH(NO_PARTITION) WHERE user_verified = TRUE and following < 1000;"
    )
    # test with a more complex filter
    assert cur.rowcount == 266, cur.rowcount
    assert cur.stats["rows_read"] == 266, cur.stats

    cur = conn.cursor()
    cur.execute(
        "SELECT user_name FROM testdata.formats.parquet WITH(NO_PARTITION) WHERE user_verified = TRUE and user_name LIKE '%b%';"
    )
    # we don't push all predicates down,
    assert cur.rowcount == 86, cur.rowcount
    assert cur.stats["rows_read"] == 711, cur.stats

    conn.close()


if __name__ == "__main__":  # pragma: no cover
    test_predicate_pushdowns_blobs()
    print("✅ okay")