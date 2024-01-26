"""
Performance tests are not intended to be ran as part of the regression set.

This tests the relative performance of different storage formats - results should be
used as instructive with caution - i.e. don't change formats between parquet and orc
based on these results. So many things affect the performance that 10th of a second
differences in this test are unlikely to be meaningful in real world situations.

Best of three runs, lower is better

500 cycles  orc_zstd        1.38 seconds    ▏
500 cycles  parquet_zstd    1.57 seconds    ▎
500 cycles  orc_snappy      1.64 seconds    ▎
500 cycles  parquet_lz4     1.72 seconds    ▎
500 cycles  parquet_snappy  1.76 seconds    ▎
500 cycles  arrow_lz4       6.28 seconds    ▊
500 cycles  arrow_zstd      9.67 seconds    █▎
500 cycles  jsonl took      18.6 seconds    ██▍
500 cycles  jsonl_zstd      23.5 seconds    ████
"""

import os
import sys

sys.path.insert(1, os.path.join(sys.path[0], "../.."))

import time

import opteryx
from opteryx.connectors import DiskConnector


class Timer(object):
    def __init__(self, name="test"):
        self.name = name

    def __enter__(self):
        self.start = time.time_ns()

    def __exit__(self, type, value, traceback):
        print("{} took {} seconds".format(self.name, (time.time_ns() - self.start) / 1e9))


FORMATS = (
    "arrow",
    "arrow_lz4",
    "jsonl",
    "orc",
    "orc_snappy",
    "parquet",
    "parquet_snappy",
    "parquet_lz4",
    "zstd",
)


if __name__ == "__main__":
    CYCLES = 100

    opteryx.register_store("tests", DiskConnector)

    conn = opteryx.connect()

    for format in FORMATS:
        with Timer(f"{CYCLES} cycles of {format}"):
            for round in range(CYCLES):
                cur = conn.cursor()
                cur.execute_to_arrow(
                    f"SELECT followers FROM testdata.flat.formats.{format} WITH(NO_PARTITION);"
                )
