"""Bounded RFS NV request model; no filesystem or modem access.

The six-byte RFS envelope and NV item request shapes follow the public
libsamsung-ipc protocol headers. The J701F wire dialect has not yet been
verified with a live CP, so this module deliberately does not emit responses.
"""

from dataclasses import dataclass, field
import hashlib
import struct


NV_SIZE = 1024 * 1024  # J701F RADIO TOC: external NV image size
MAX_CHUNK = 65536
READ_ITEM = 1
WRITE_ITEM = 2
RFS_HEADER = struct.Struct("<IBB")
ITEM_HEADER = struct.Struct("<II")


class RFSError(ValueError):
    pass


@dataclass(frozen=True)
class NVRequest:
    index: int
    sequence: int
    offset: int
    length: int
    data: bytes = field(default=b"", repr=False)


def parse_request(payload: bytes) -> NVRequest:
    """Parse one complete RFS message; reject unknown commands and sizes."""
    if len(payload) < RFS_HEADER.size + ITEM_HEADER.size:
        raise RFSError("truncated RFS NV request")
    length, index, sequence = RFS_HEADER.unpack_from(payload)
    if length != len(payload) or length > RFS_HEADER.size + ITEM_HEADER.size + MAX_CHUNK:
        raise RFSError("RFS envelope length mismatch or too large")
    if index not in (READ_ITEM, WRITE_ITEM):
        raise RFSError("unsupported RFS command")
    offset, size = ITEM_HEADER.unpack_from(payload, RFS_HEADER.size)
    if not 0 < size <= MAX_CHUNK or offset > NV_SIZE or size > NV_SIZE - offset:
        raise RFSError("NV range outside the private RAM copy")
    data = payload[RFS_HEADER.size + ITEM_HEADER.size:]
    if index == READ_ITEM and data:
        raise RFSError("NV read request has unexpected data")
    if index == WRITE_ITEM and len(data) != size:
        raise RFSError("NV write payload length mismatch")
    return NVRequest(index, sequence, offset, size, data)


class NVMemory:
    """A private, exact-size NV snapshot whose writes remain in RAM."""

    def __init__(self, image: bytes) -> None:
        if len(image) != NV_SIZE:
            raise RFSError("NV snapshot must be exactly 1 MiB")
        self._image = bytearray(image)

    def apply(self, request: NVRequest) -> bytes | None:
        if not 0 <= request.sequence <= 255:
            raise RFSError("RFS sequence outside byte range")
        if not 0 < request.length <= MAX_CHUNK or request.offset < 0 or request.offset > NV_SIZE or request.length > NV_SIZE - request.offset:
            raise RFSError("NV range outside the private RAM copy")
        if request.index == READ_ITEM:
            if request.data:
                raise RFSError("NV read request has unexpected data")
            return bytes(self._image[request.offset:request.offset + request.length])
        if request.index == WRITE_ITEM and len(request.data) == request.length:
            self._image[request.offset:request.offset + request.length] = request.data
            return None
        raise RFSError("invalid NV operation")

    def digest(self) -> str:
        return hashlib.sha256(self._image).hexdigest()
