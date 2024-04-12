#!/usr/bin/env python3
#
# MDS to standard MIDI file converter
#
# see also http://www.vgmpf.com/Wiki/index.php?title=MDS
#
import argparse
import io
import struct
from typing import BinaryIO, List, Optional

class MDSEvent:
    def __init__(self, abs_time: int, stream_id: Optional[int], midi_data: bytes, flag: int) -> None:
        self.abs_time: int = abs_time
        self.stream_id: Optional[int] = stream_id
        self.midi_data: bytes = midi_data
        self.flag: int = flag

    def __repr__(self) -> str:
        return f"MDSEvent({self.abs_time!r}, {self.stream_id!r}, {self.midi_data!r}, {self.flag!r})"


class MDSFileData:
    def __init__(self, time_format: int, max_buf_size: int, have_stream_id: bool) -> None:
        self.time_format: int = time_format
        self.max_buf_size: int = max_buf_size
        self.have_stream_id: bool = have_stream_id

        self.events: List[MDSEvent] = []

    def __repr__(self) -> str:
        return f"MDSFileData({self.time_format!r}, {self.max_buf_size!r}, {self.have_stream_id!r})<events={self.events!r}>"


def to_midi_vlq(value: int) -> bytes:
    if value == 0:
        return b"\x00"
    if value < 0:
        raise ValueError(f"value ({value!r}) must not be negative")

    # break apart into 7-bit chunks
    ret = []
    while value > 0:
        b = value & 0b0111_1111
        ret.append(b)
        value >>= 7

    # big endian
    ret.reverse()

    # set top bit on all except the last byte
    for i in range(len(ret)-1):
        ret[i] |= 0b1000_0000

    return bytes(ret)


def check_expected(expected: bytes, received: bytes):
    if expected != received:
        raise ValueError(f"expected {expected!r}, got {received!r}")

def check_expected_len(expected_len: int, received: bytes):
    if expected_len != len(received):
        raise ValueError(f"expected {expected_len} bytes, got {len(received)} bytes")

def read_len_le4(file: BinaryIO) -> int:
    len_bytes = file.read(4)
    if len(len_bytes) != 4:
        raise ValueError(
            f"short read ({len(len_bytes)}) when reading 4-byte little-endian length value"
        )
    (len_val,) = struct.unpack('<I', len_bytes)
    return len_val

def read_len_le4_and_value(file: BinaryIO) -> bytes:
    len_val = read_len_le4(file)
    bs = file.read(len_val)
    if len(bs) != len_val:
        raise ValueError(
            f"short read ({len(bs)} bytes) when reading data with length {len_val}"
        )
    return bs


def read_mds(mds_file: BinaryIO) -> MDSFileData:
    riff = mds_file.read(4)
    check_expected(b'RIFF', riff)

    riff_bytes = read_len_le4_and_value(mds_file)

    with io.BytesIO(riff_bytes) as riff_file:
        mids = riff_file.read(4)
        check_expected(b'MIDS', mids)

        fmt_ = riff_file.read(4)
        check_expected(b'fmt ', fmt_)

        fmt_data = read_len_le4_and_value(riff_file)
        if len(fmt_data) != 12:
            raise ValueError(
                f"'fmt ' block should be 12 bytes long; obtained {len(fmt_data)} bytes"
            )

        (
            time_format,
            max_buffer,
            fmt_flags,
        ) = struct.unpack('<III', fmt_data)
        mfd = MDSFileData(
            time_format,
            max_buffer,
            have_stream_id=(fmt_flags & 0b1) == 0
        )

        data = riff_file.read(4)
        check_expected(b'data', data)

        data_bytes = read_len_le4_and_value(riff_file)

    with io.BytesIO(data_bytes) as data_file:
        chunk_count = read_len_le4(data_file)

        for _i in range(chunk_count):
            chunk_abs_offset_ticks = read_len_le4(data_file)
            midi_bytes = read_len_le4_and_value(data_file)

            u32s_per_event = 3 if mfd.have_stream_id else 2
            bytes_per_event = 4 * u32s_per_event
            event_count = len(midi_bytes) // bytes_per_event

            with io.BytesIO(midi_bytes) as midi_file:
                cur_ticks = 0
                for _j in range(event_count):
                    delta_ticks = read_len_le4(midi_file)
                    if mfd.have_stream_id:
                        stream_id: Optional[int] = read_len_le4(midi_file)
                    else:
                        stream_id = None
                    event_data = midi_file.read(4)
                    check_expected_len(4, event_data)

                    cur_ticks += delta_ticks
                    mfd.events.append(MDSEvent(
                        chunk_abs_offset_ticks + cur_ticks,
                        stream_id,
                        event_data[0:3],
                        event_data[3],
                    ))

    return mfd


def write_mds_as_midi(mds: MDSFileData, out_file: BinaryIO) -> None:
    # prepare header chunk
    header_bytes = struct.pack(
        '>HHH',
        0, # format (single MTrk)
        1, # number of tracks (always 1 for format=0)
        mds.time_format, # time format
    )
    header_len_bytes = struct.pack('>I', len(header_bytes))
    out_file.write(b'MThd')
    out_file.write(header_len_bytes)
    out_file.write(header_bytes)

    # assemble the track
    event_pieces: List[bytes] = []
    last_time = 0
    for ev in mds.events:
        delta_time = ev.abs_time - last_time
        if delta_time < 0:
            raise ValueError("events in MDSFileData are not sorted!")
        last_time = ev.abs_time
        delta_time_bytes = to_midi_vlq(delta_time)
        event_pieces.append(delta_time_bytes)

        if ev.flag == 0:
            # short (max. 3-byte) MIDI event
            if len(ev.midi_data) != 3:
                raise ValueError("incorrect MIDI data length")

            # program change (0xCx) and channel pressure (0xDx) messages are only 2b long
            if ev.midi_data[0] & 0xF0 in (0xC0, 0xD0):
                event_pieces.append(ev.midi_data[0:2])
            else:
                event_pieces.append(ev.midi_data)

        elif ev.flag == 1:
            # tempo change (little -> big endian conversion!)
            event_pieces.append(bytes((0xFF, 0x51, 0x03)))
            event_pieces.append(bytes((ev.midi_data[2], ev.midi_data[1], ev.midi_data[0])))
        else:
            raise ValueError(f"unknown event flag value {ev.flag}")

    # end of track
    event_pieces.append(bytes((0x00, 0xFF, 0x2F, 0x00)))

    track_bytes = b"".join(event_pieces)
    track_len_bytes = struct.pack('>I', len(track_bytes))
    out_file.write(b'MTrk')
    out_file.write(track_len_bytes)
    out_file.write(track_bytes)


def main():
    parser = argparse.ArgumentParser(
        description="Converts MDS (MIDI Stream) files to standard MIDI files.",
    )
    parser.add_argument(
        dest='in_file', metavar="INFILE", type=argparse.FileType('rb'),
        help="The MDS file to convert to a standard MIDI file."
    )
    parser.add_argument(
        dest='out_file', metavar="OUTFILE", type=argparse.FileType('wb'),
        help="The output file into which to write standard MIDI data."
    )
    args = parser.parse_args()

    with args.in_file:
        mfd = read_mds(args.in_file)
    mfd.events.sort(key=lambda ev: ev.abs_time)
    with args.out_file:
        write_mds_as_midi(mfd, args.out_file)


if __name__ == "__main__":
    main()