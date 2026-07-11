from __future__ import annotations

import os
import struct

try:
    from fastrand import xorshift128plus_bytes as _xorshift128plus_bytes
    from fastrand import xorshift128plusrandint as _xorshift128plusrandint
except ImportError:
    def _xorshift128plus_bytes(length: int) -> bytes:
        return os.urandom(length)

    def _xorshift128plusrandint(start: int, end: int) -> int:
        span = end - start + 1
        rand_max = 2 ** 32
        limit = rand_max - (rand_max % span)
        while True:
            value = struct.unpack("I", os.urandom(4))[0]
            if value < limit:
                return start + (value % span)


def xorshift128plus_bytes(length: int) -> bytes:
    return _xorshift128plus_bytes(length)


def xorshift128plusrandint(start: int, end: int) -> int:
    return _xorshift128plusrandint(start, end)