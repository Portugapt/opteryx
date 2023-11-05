"""
Test we can read from Sqlite - this is a basic exercise of the SQL Connector
"""
import os
import sys

sys.path.insert(1, os.path.join(sys.path[0], "../.."))

import opteryx
from opteryx.connectors import SqlConnector
from tests.tools import is_arm, is_mac, is_windows, skip_if

BIG_QUERY_PROJECT: str = "mabeldev"


# skip to reduce billing
@skip_if(is_arm() or is_windows() or is_mac())
def test_bigquery_storage():
    from sqlalchemy.engine import create_engine

    engine = create_engine(f"bigquery://{BIG_QUERY_PROJECT}")

    opteryx.register_store("bq", SqlConnector, remove_prefix=True, engine=engine)

    results = opteryx.query("SELECT * FROM bq.public.planets")
    assert results.rowcount == 9, results.rowcount

    # PROCESS THE DATA IN SOME WAY
    results = opteryx.query("SELECT COUNT(*) FROM bq.public.planets;")
    assert results.rowcount == 1, results.rowcount


if __name__ == "__main__":  # pragma: no cover
    from tests.tools import run_tests

    run_tests()