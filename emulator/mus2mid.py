"""Convert Doom MUS music to a Standard MIDI File (format 1), in pure Python.

Port of prboom-go's mus2mid.c
(apps/retro-go/prboom-go/components/prboom/mus2mid.c), itself based on
S. Bacquet's QMUS2MID. Returns valid MIDI bytes (with correct MTrk chunk lengths,
including the end-of-track meta event) so synths like fluidsynth render it cleanly.
"""

import struct

MIDI_TRACKS = 16

# MUS event types
RELEASE_NOTE = 0
PLAY_NOTE = 1
BEND_NOTE = 2
SYS_EVENT = 3
CNTL_CHANGE = 4
SCORE_END = 6

# MUS controller -> MIDI controller number
MUS2MID_CONTROL = [
    0,     # 0: program change (handled specially)
    0x00,  # bank select
    0x01,  # modulation
    0x07,  # volume
    0x0A,  # pan
    0x0B,  # expression
    0x5B,  # reverb depth
    0x5D,  # chorus depth
    0x40,  # sustain pedal
    0x43,  # soft pedal
    0x78,  # all sounds off
    0x7B,  # all notes off
    0x7E,  # mono
    0x7F,  # poly
    0x79,  # reset all controllers
]

TRACK0_PREAMBLE = bytes([
    0x00, 0xff, 0x59, 0x02, 0x00, 0x00,        # key signature (C major)
    0x00, 0xff, 0x51, 0x03, 0x09, 0xa3, 0x1a,  # tempo
])


class Mus2MidError(Exception):
    pass


def _write_varlen(out, value):
    """Write a MIDI variable-length quantity (matches mus2mid.c's encoder)."""
    buffer = value & 0x7f
    value >>= 7
    while value:
        buffer <<= 8
        buffer |= (value & 0x7f) | 0x80
        value >>= 7
    while True:
        out.append(buffer & 0xff)
        if buffer & 0x80:
            buffer >>= 8
        else:
            break


def mus2mid(mus, division=64):
    """Convert a MUS byte string to MIDI bytes. Raises Mus2MidError on bad input."""
    if not mus or mus[:4] != b"MUS\x1a":
        raise Mus2MidError("not MUS data")

    # MUS header: ID[4], ScoreLength, ScoreStart, channels, SecChannels, InstrCnt
    _id, score_length, score_start, channels, _sec, _instr = struct.unpack_from(
        "<4sHHHHH", mus, 0
    )
    if channels > 15:
        raise Mus2MidError("too many channels")
    if score_start + score_length > len(mus):
        raise Mus2MidError("bad length")

    tracks = [bytearray() for _ in range(MIDI_TRACKS)]
    velocities = [64] * MIDI_TRACKS
    delta = [0] * MIDI_TRACKS

    mus2mid_channel = [-1] * MIDI_TRACKS
    midichan2track = [0] * MIDI_TRACKS

    tracks[0].extend(TRACK0_PREAMBLE)

    pos = score_start
    numtracks = 1

    while True:
        if pos >= len(mus):
            raise Mus2MidError("ran off the end")
        event = mus[pos]
        pos += 1
        event_type = (event & 0x7f) >> 4
        mus_channel = event & 0x0f

        if event_type == SCORE_END:
            break

        if mus2mid_channel[mus_channel] == -1:
            if mus_channel == 15:
                mus2mid_channel[mus_channel] = 9  # percussion
            else:
                mx = max(mus2mid_channel[:15])
                mus2mid_channel[mus_channel] = 10 if mx == 8 else mx + 1
            midichan2track[mus2mid_channel[mus_channel]] = numtracks
            numtracks += 1

        midi_channel = mus2mid_channel[mus_channel]
        midi_track = midichan2track[midi_channel]
        track = tracks[midi_track]

        _write_varlen(track, delta[midi_track])
        delta[midi_track] = 0

        if event_type == RELEASE_NOTE:
            track.append(0x90 | midi_channel)
            note = mus[pos]; pos += 1
            track.append(note & 0x7f)
            track.append(0)
        elif event_type == PLAY_NOTE:
            track.append(0x90 | midi_channel)
            note = mus[pos]; pos += 1
            track.append(note & 0x7f)
            if note & 0x80:
                velocities[midi_track] = mus[pos] & 0x7f; pos += 1
            track.append(velocities[midi_track])
        elif event_type == BEND_NOTE:
            track.append(0xE0 | midi_channel)
            bend = mus[pos]; pos += 1
            track.append((bend & 1) << 6)
            track.append(bend >> 1)
        elif event_type == SYS_EVENT:
            track.append(0x80 | midi_channel)
            ctrl = mus[pos]; pos += 1
            if ctrl < 10 or ctrl > 14:
                raise Mus2MidError("bad sys event")
            track.append(MUS2MID_CONTROL[ctrl])
            track.append((channels + 1) if ctrl == 12 else 0)
        elif event_type == CNTL_CHANGE:
            ctrl = mus[pos]; pos += 1
            if ctrl > 9:
                raise Mus2MidError("bad control change")
            if ctrl:
                track.append(0x80 | midi_channel)
                track.append(MUS2MID_CONTROL[ctrl])
            else:
                track.append(0xC0 | midi_channel)
            val = mus[pos]; pos += 1
            track.append(val & 0x7f)
        else:
            raise Mus2MidError("unknown event %d" % event_type)

        if event & 0x80:  # last-event flag: a delta time follows
            delta_time = 0
            while True:
                b = mus[pos]; pos += 1
                delta_time = (delta_time << 7) + (b & 0x7f)
                if not (b & 0x80):
                    break
            for i in range(MIDI_TRACKS):
                delta[i] += delta_time

    # Assemble the MIDI file
    used = [t for t in tracks if t]
    out = bytearray()
    out.extend(b"MThd")
    out.extend(struct.pack(">IHHH", 6, 1, len(used), division & 0x7fff))
    for t in used:
        body = bytes(t) + b"\x00\xff\x2f\x00"  # append end-of-track meta event
        out.extend(b"MTrk")
        out.extend(struct.pack(">I", len(body)))
        out.extend(body)
    return bytes(out)
