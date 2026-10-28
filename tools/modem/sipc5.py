"""Small SIPC5 link-frame codec for the J701F modem bring-up.

This is link framing only, not Samsung IPC command decoding or an RFS server.
The layout follows the GPL Samsung modem_v1/include/sipc5.h used by the
factory Exynos7870 kernel. No device or private file is opened here.
"""

from dataclasses import dataclass, field


START = 0xF8
PADDED = 0x04
EXTENDED = 0x02
MULTIFRAME = 0x03
ALIGNMENT = 8  # sizeof(size_t) on the factory AArch64 kernel
MAX_FRAME = 1024 * 1024


class FrameError(ValueError):
    pass


@dataclass(frozen=True)
class Frame:
    channel: int
    payload: bytes = field(repr=False)
    padded: bool = False
    control: int | None = None

    @property
    def kind(self) -> str:
        if 215 <= self.channel <= 224:
            return "boot"
        if 225 <= self.channel <= 234:
            return "dump"
        if 235 <= self.channel <= 244:
            return "fmt"
        if 245 <= self.channel <= 254:
            return "rfs"
        return "raw"


def decode_one(data: bytes | bytearray) -> tuple[Frame, int] | None:
    """Decode one complete frame; return None when more bytes are needed."""
    if len(data) < 4:
        return None
    config = data[0]
    if config & START != START:
        raise FrameError("SIPC5 start bits are invalid")
    mode = config & 0x03
    if mode == 1:
        raise FrameError("unsupported SIPC5 control-only configuration")
    header_size = 6 if mode == EXTENDED else 5 if mode == MULTIFRAME else 4
    if len(data) < header_size:
        return None
    channel = data[1]
    if channel in (0, 255):
        raise FrameError("reserved SIPC5 channel")
    length_size = 4 if mode == EXTENDED else 2
    frame_size = int.from_bytes(data[2:2 + length_size], "little")
    if frame_size < header_size or frame_size > MAX_FRAME:
        raise FrameError("SIPC5 frame length outside allowed bounds")
    padded = bool(config & PADDED)
    total_size = (frame_size + ALIGNMENT - 1) & ~(ALIGNMENT - 1) if padded else frame_size
    if len(data) < total_size:
        return None
    control = data[4] if mode == MULTIFRAME else None
    return Frame(channel, bytes(data[header_size:frame_size]), padded, control), total_size


def encode_frame(frame: Frame) -> bytes:
    """Encode one frame. Control selects the 16-bit multi-frame form."""
    if not 1 <= frame.channel <= 254:
        raise FrameError("reserved SIPC5 channel")
    if frame.control is not None and not 0 <= frame.control <= 255:
        raise FrameError("control byte outside range")
    mode = MULTIFRAME if frame.control is not None else (
        EXTENDED if len(frame.payload) + 4 > 0xFFFF else 0
    )
    header_size = 6 if mode == EXTENDED else 5 if mode == MULTIFRAME else 4
    frame_size = header_size + len(frame.payload)
    if frame_size > MAX_FRAME or (mode == MULTIFRAME and frame_size > 0xFFFF):
        raise FrameError("SIPC5 frame length outside allowed bounds")
    config = START | mode | (PADDED if frame.padded else 0)
    length_size = 4 if mode == EXTENDED else 2
    result = bytes((config, frame.channel)) + frame_size.to_bytes(length_size, "little")
    if mode == MULTIFRAME:
        result += bytes((frame.control,))
    result += frame.payload
    if frame.padded:
        result += bytes((-len(result)) % ALIGNMENT)
    return result


class FrameDecoder:
    """Reassemble frames from bounded chunks without logging their payloads."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> list[Frame]:
        if len(self._buffer) + len(chunk) > MAX_FRAME + ALIGNMENT:
            raise FrameError("SIPC5 input buffer limit exceeded")
        self._buffer.extend(chunk)
        frames = []
        while result := decode_one(self._buffer):
            frame, consumed = result
            frames.append(frame)
            del self._buffer[:consumed]
        return frames
