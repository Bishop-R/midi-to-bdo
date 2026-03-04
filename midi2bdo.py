#!/usr/bin/env python3
"""Convert MIDI files to Black Desert Online music composer format."""

import argparse
from collections import defaultdict, namedtuple
import struct
import os
import sys
import mido
from ICECipher import IceKey

Note = namedtuple('Note', ['pitch', 'vel', 'start', 'dur', 'ntype'])

ICE_KEY = bytes.fromhex('51F30F1104246A00')
BDO_VERSION = 9
HEADER_SIZE = 0x150  # Fixed header size before track data
NAME_FIELD_SIZE = 62  # Each character name field in bytes (31 UTF-16LE chars)
NOTE_SIZE = 20
MAX_NOTES_PER_TRACK = 730
DEFAULT_BPM = 120
DEFAULT_TIME_SIG = 4
# Track settings: 8 bytes per track
# [0] inst_reverb  (per-instrument)  [1] eff_reverb     (global)
# [2] inst_delay   (per-instrument)  [3] eff_delay      (global)
# [4] inst_chorus  (per-instrument)  [5] chorus_feedback (global)
# [6] chorus_lfo_depth (global)      [7] chorus_lfo_freq (global)
TRACK_SETTINGS = bytes(8)  # all zeros = dry/no effector
DEFAULT_VOLUME = 0x46  # 70 — BDO's default track volume

BDO_INSTRUMENTS = {
    # Beginner
    'beginner_guitar':    0x00,
    'beginner_flute':     0x01,
    'beginner_recorder':  0x02,
    'hand_drum':          0x04,
    'cymbals':            0x05,
    'beginner_harp':      0x06,
    'beginner_piano':     0x07,
    'beginner_violin':    0x08,
    # Florchestra
    'guitar':             0x0a,
    'flute':              0x0b,
    'drum_set':           0x0d,
    'marnibass':          0x0e,
    'contrabass':         0x0f,
    'harp':               0x10,
    'piano':              0x11,
    'violin':             0x12,
    'handpan':            0x13,
    # Marnian
    'marnian_wavy':       0x14,
    'marnian_illusion':   0x18,
    'marnian_secret':     0x1c,
    'marnian_sandwich':   0x20,
    # Electric Guitar
    'eguitar_silver':     0x24,
    'eguitar_highway':    0x25,
    'eguitar_hexe':       0x26,
    # Florchestra (continued)
    'clarinet':           0x27,
    'horn':               0x28,
}

DEFAULT_INSTRUMENT = BDO_INSTRUMENTS['piano']

BDO_INSTRUMENT_NAMES = {
    0x00: 'Beginner Guitar',
    0x01: 'Beginner Flute',
    0x02: 'Beginner Recorder',
    0x04: 'Hand Drum',
    0x05: 'Cymbals',
    0x06: 'Beginner Harp',
    0x07: 'Beginner Piano',
    0x08: 'Beginner Violin',
    0x0a: 'Florchestra Acoustic Guitar',
    0x0b: 'Florchestra Flute',
    0x0d: 'Drum Set',
    0x0e: 'Marnibass',
    0x0f: 'Florchestra Contrabass',
    0x10: 'Florchestra Harp',
    0x11: 'Florchestra Piano',
    0x12: 'Florchestra Violin',
    0x13: 'Handpan',
    0x14: 'Marnian Wavy Planet',
    0x18: 'Marnian Illusion Tree',
    0x1c: 'Marnian Secret Note',
    0x20: 'Marnian Sandwich',
    0x24: 'Guitar Silver Wave',
    0x25: 'Guitar Highway',
    0x26: 'Guitar Hexe Glam',
    0x27: 'Florchestra Clarinet',
    0x28: 'Florchestra Horn',
}

# Standard General MIDI program names (0–127)
_GM_PROGRAM_NAMES = [
    # 0–7: Piano
    'Acoustic Grand Piano', 'Bright Acoustic Piano', 'Electric Grand Piano',
    'Honky-tonk Piano', 'Electric Piano 1', 'Electric Piano 2', 'Harpsichord', 'Clavinet',
    # 8–15: Chromatic Percussion
    'Celesta', 'Glockenspiel', 'Music Box', 'Vibraphone',
    'Marimba', 'Xylophone', 'Tubular Bells', 'Dulcimer',
    # 16–23: Organ
    'Drawbar Organ', 'Percussive Organ', 'Rock Organ', 'Church Organ',
    'Reed Organ', 'Accordion', 'Harmonica', 'Tango Accordion',
    # 24–31: Guitar
    'Acoustic Guitar (nylon)', 'Acoustic Guitar (steel)', 'Electric Guitar (jazz)',
    'Electric Guitar (clean)', 'Electric Guitar (muted)', 'Overdriven Guitar',
    'Distortion Guitar', 'Guitar Harmonics',
    # 32–39: Bass
    'Acoustic Bass', 'Electric Bass (finger)', 'Electric Bass (pick)',
    'Fretless Bass', 'Slap Bass 1', 'Slap Bass 2', 'Synth Bass 1', 'Synth Bass 2',
    # 40–47: Strings
    'Violin', 'Viola', 'Cello', 'Contrabass',
    'Tremolo Strings', 'Pizzicato Strings', 'Orchestral Harp', 'Timpani',
    # 48–55: Ensemble
    'String Ensemble 1', 'String Ensemble 2', 'Synth Strings 1', 'Synth Strings 2',
    'Choir Aahs', 'Voice Oohs', 'Synth Choir', 'Orchestra Hit',
    # 56–63: Brass
    'Trumpet', 'Trombone', 'Tuba', 'Muted Trumpet',
    'French Horn', 'Brass Section', 'Synth Brass 1', 'Synth Brass 2',
    # 64–71: Reed
    'Soprano Sax', 'Alto Sax', 'Tenor Sax', 'Baritone Sax',
    'Oboe', 'English Horn', 'Bassoon', 'Clarinet',
    # 72–79: Pipe
    'Piccolo', 'Flute', 'Recorder', 'Pan Flute',
    'Blown Bottle', 'Shakuhachi', 'Whistle', 'Ocarina',
    # 80–87: Synth Lead
    'Lead 1 (square)', 'Lead 2 (sawtooth)', 'Lead 3 (calliope)', 'Lead 4 (chiff)',
    'Lead 5 (charang)', 'Lead 6 (voice)', 'Lead 7 (fifths)', 'Lead 8 (bass + lead)',
    # 88–95: Synth Pad
    'Pad 1 (new age)', 'Pad 2 (warm)', 'Pad 3 (polysynth)', 'Pad 4 (choir)',
    'Pad 5 (bowed)', 'Pad 6 (metallic)', 'Pad 7 (halo)', 'Pad 8 (sweep)',
    # 96–103: Synth Effects
    'FX 1 (rain)', 'FX 2 (soundtrack)', 'FX 3 (crystal)', 'FX 4 (atmosphere)',
    'FX 5 (brightness)', 'FX 6 (goblins)', 'FX 7 (echoes)', 'FX 8 (sci-fi)',
    # 104–111: Ethnic
    'Sitar', 'Banjo', 'Shamisen', 'Koto', 'Kalimba', 'Bagpipe', 'Fiddle', 'Shanai',
    # 112–119: Percussive
    'Tinkle Bell', 'Agogo', 'Steel Drums', 'Woodblock',
    'Taiko Drum', 'Melodic Tom', 'Synth Drum', 'Reverse Cymbal',
    # 120–127: Sound Effects
    'Guitar Fret Noise', 'Breath Noise', 'Seashore', 'Bird Tweet',
    'Telephone Ring', 'Helicopter', 'Applause', 'Gunshot',
]


def gm_program_name(program):
    """Return the human-readable GM instrument name for a program number (0–127)."""
    if 0 <= program < len(_GM_PROGRAM_NAMES):
        return _GM_PROGRAM_NAMES[program]
    return f'Program {program}'


# BDO drum note type (melodic notes use 0, drums use 99)
DRUM_NOTE_TYPE = 99

# GM MIDI percussion note → BDO drum pitch (range 48–64)
_GM_TO_BDO_DRUM = {
    35: 48,  # Acoustic Bass Drum → Kck
    36: 48,  # Bass Drum 1 → Kck
    37: 51,  # Side Stick → RimShot
    38: 50,  # Acoustic Snare → SnrHit
    39: 50,  # Hand Clap → SnrHit
    40: 50,  # Electric Snare → SnrHit
    41: 53,  # Low Floor Tom → Tom1
    42: 54,  # Closed Hi-Hat → HihatC
    43: 55,  # High Floor Tom → Tom2
    44: 56,  # Pedal Hi-Hat → HatPdl
    45: 57,  # Low Tom → Tom3
    46: 58,  # Open Hi-Hat → HihatO
    47: 59,  # Low-Mid Tom → Tom4
    48: 60,  # Hi-Mid Tom → Tom5
    49: 61,  # Crash Cymbal 1 → CymCrsh
    50: 60,  # High Tom → Tom5
    51: 62,  # Ride Cymbal 1 → CymRide
    52: 61,  # Chinese Cymbal → CymCrsh
    53: 62,  # Ride Bell → CymRide
    54: 61,  # Tambourine → CymCrsh
    55: 61,  # Splash Cymbal → CymCrsh
    56: 51,  # Cowbell → RimShot
    57: 61,  # Crash Cymbal 2 → CymCrsh
    58: 51,  # Vibraslap → RimShot
    59: 62,  # Ride Cymbal 2 → CymRide
}


def map_drum_notes(notes):
    """Convert MIDI percussion notes to BDO drum format.

    Maps GM percussion pitches to BDO drum pitches (48–64) and sets
    the note type to DRUM_NOTE_TYPE (99).
    """
    mapped = []
    for n in notes:
        bdo_pitch = _GM_TO_BDO_DRUM.get(n.pitch, 48)  # default to kick
        mapped.append(Note(bdo_pitch, n.vel, n.start, n.dur, DRUM_NOTE_TYPE))
    return mapped


# GM program number → BDO instrument name
_GM_RANGES = [
    (24,  'piano'),           # 0–23: pianos, chromatic perc, organs
    (32,  'guitar'),          # 24–31: guitar
    (40,  'contrabass'),      # 32–39: bass
    (42,  'violin'),          # 40–41: violin, viola
    (44,  'contrabass'),      # 42–43: cello, contrabass
    (47,  'harp'),            # 44–46: pizz strings, harp
    (48,  'drum_set'),        # 47: timpani
    (56,  'violin'),          # 48–55: string ensembles, choir
    (64,  'horn'),            # 56–63: brass
    (72,  'clarinet'),        # 64–71: sax, reed woodwinds
    (80,  'flute'),           # 72–79: flute family
    (88,  'marnian_wavy'),    # 80–87: lead synths
    (96,  'marnian_illusion'),# 88–95: pad synths
    (104, 'marnibass'),       # 96–103: synth effects
    (112, 'handpan'),         # 104–111: ethnic
    (120, 'hand_drum'),       # 112–119: percussive
    (128, 'piano'),           # 120–127: sound FX — fallback
]


def gm_to_bdo_instrument(program, is_percussion=False):
    """Map a GM program number (0–127) to a BDO instrument ID."""
    if is_percussion:
        return BDO_INSTRUMENTS['drum_set']
    for upper, name in _GM_RANGES:
        if program < upper:
            return BDO_INSTRUMENTS[name]
    return DEFAULT_INSTRUMENT

# BDO piano range (MIDI note numbers)
BDO_NOTE_MIN = 24   # C1
BDO_NOTE_MAX = 108  # C8


def parse_midi(midi_path, apply_sustain=True, flatten_tempo=False):
    """Parse a MIDI file and extract notes grouped by channel.

    Notes are grouped by MIDI channel so that each channel's instrument
    (program change) can be mapped to a BDO instrument.

    Args:
        midi_path: Path to the MIDI file.
        apply_sustain: Whether to extend notes held by sustain pedal (CC64).
        flatten_tempo: If True and the MIDI has multiple tempos, set the BPM
            header to 200 (BDO's max).  Note positions are still computed with
            variable tempo (real-time ms), so playback preserves rubato.  The
            high BPM minimizes quantization error from BDO's 1/64 grid.

    Returns:
        (bpm, time_sig_num, channel_groups, tempo_changes) where
        channel_groups is a list of (notes, gm_program, is_percussion)
        per channel that has notes, and tempo_changes is the number of
        tempo change events found.
    """
    mid = mido.MidiFile(midi_path)

    # Build tempo map from all tracks
    tempo_map = []  # [(tick, tempo_us)]
    for track in mid.tracks:
        abs_tick = 0
        for msg in track:
            abs_tick += msg.time
            if msg.type == 'set_tempo':
                tempo_map.append((abs_tick, msg.tempo))
    tempo_map.sort(key=lambda x: x[0])
    if not tempo_map:
        tempo_map = [(0, mido.bpm2tempo(DEFAULT_BPM))]

    # Extract time signature
    time_sig_num = DEFAULT_TIME_SIG
    for track in mid.tracks:
        for msg in track:
            if msg.type == 'time_signature':
                time_sig_num = msg.numerator
                break

    if flatten_tempo and len(tempo_map) > 1:
        bpm = 200  # max BDO allows — minimizes 1/64 grid quantization error
    else:
        bpm = round(mido.tempo2bpm(tempo_map[0][1]))

    def ticks_to_ms(ticks):
        """Convert absolute ticks to milliseconds using the tempo map."""
        ms = 0.0
        remaining = ticks
        current_tempo = tempo_map[0][1]
        current_tick = 0

        for i, (map_tick, tempo) in enumerate(tempo_map):
            if map_tick > ticks:
                break
            delta = map_tick - current_tick
            if delta > 0 and delta <= remaining:
                ms += mido.tick2second(delta, mid.ticks_per_beat, current_tempo) * 1000
                remaining -= delta
            current_tick = map_tick
            current_tempo = tempo

        if remaining > 0:
            ms += mido.tick2second(remaining, mid.ticks_per_beat, current_tempo) * 1000
        return ms

    # Collect notes per MIDI channel across all tracks
    # Note tuple: (pitch, vel, start_ms, dur_ms, note_type)
    # note_type: 0 = normal
    channel_notes = {}   # {channel: [note_tuples]}
    channel_program = {}  # {channel: gm_program} (last program_change wins)

    for track in mid.tracks:
        active = {}     # {(channel, pitch): (velocity, start_tick)}
        sustain = {}    # {channel: bool}
        sustained = {}  # {(channel, pitch): (velocity, start_tick)}
        abs_tick = 0
        for msg in track:
            abs_tick += msg.time
            if not hasattr(msg, 'channel'):
                continue
            ch = msg.channel
            if ch not in channel_notes:
                channel_notes[ch] = []

            if msg.type == 'program_change':
                channel_program[ch] = msg.program

            elif msg.type == 'note_on' and msg.velocity > 0:
                key = (ch, msg.note)
                # End any sustained version of this note
                if key in sustained:
                    vel, start_tick = sustained.pop(key)
                    start_ms = ticks_to_ms(start_tick)
                    dur_ms = ticks_to_ms(abs_tick) - start_ms
                    if dur_ms > 0:
                        channel_notes[ch].append(Note(msg.note, vel, start_ms, dur_ms, 0))
                if key in active:
                    vel, start_tick = active.pop(key)
                    start_ms = ticks_to_ms(start_tick)
                    dur_ms = ticks_to_ms(abs_tick) - start_ms
                    if dur_ms > 0:
                        channel_notes[ch].append(Note(msg.note, vel, start_ms, dur_ms, 0))
                active[key] = (msg.velocity, abs_tick)

            elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                key = (ch, msg.note)
                if key in active:
                    if sustain.get(ch, False):
                        sustained[key] = active.pop(key)
                    else:
                        vel, start_tick = active.pop(key)
                        start_ms = ticks_to_ms(start_tick)
                        dur_ms = ticks_to_ms(abs_tick) - start_ms
                        if dur_ms > 0:
                            channel_notes[ch].append(Note(msg.note, vel, start_ms, dur_ms, 0))

            elif msg.type == 'control_change' and msg.control == 64 and apply_sustain:
                if msg.value >= 64:
                    sustain[ch] = True
                else:
                    sustain[ch] = False
                    # Release all sustained notes on this channel
                    to_release = [(k, v) for k, v in sustained.items() if k[0] == ch]
                    for key, (vel, start_tick) in to_release:
                        start_ms = ticks_to_ms(start_tick)
                        dur_ms = ticks_to_ms(abs_tick) - start_ms
                        if dur_ms > 0:
                            channel_notes[ch].append(Note(key[1], vel, start_ms, dur_ms, 0))
                        del sustained[key]

        # End any still-active or sustained notes from this track
        for store in (active, sustained):
            for (ch, pitch), (vel, start_tick) in store.items():
                start_ms = ticks_to_ms(start_tick)
                if ch not in channel_notes:
                    channel_notes[ch] = []
                channel_notes[ch].append(Note(pitch, vel, start_ms, 100.0, 0))

    # Build channel_groups: (notes, gm_program, is_percussion)
    channel_groups = []
    for ch in sorted(channel_notes):
        notes = channel_notes[ch]
        if not notes:
            continue
        notes.sort(key=lambda n: n.start)
        is_perc = (ch == 9)
        program = channel_program.get(ch, 0)
        channel_groups.append((notes, program, is_perc))

    return bpm, time_sig_num, channel_groups, len(tempo_map)


def clamp_notes(notes):
    """Clamp note pitches to BDO's supported range."""
    clamped = []
    for n in notes:
        p = n.pitch
        if p < BDO_NOTE_MIN:
            p = p + 12 * ((BDO_NOTE_MIN - p + 11) // 12)
        elif p > BDO_NOTE_MAX:
            p = p - 12 * ((p - BDO_NOTE_MAX + 11) // 12)
        p = max(BDO_NOTE_MIN, min(BDO_NOTE_MAX, p))
        clamped.append(n._replace(pitch=p))
    return clamped


def split_notes(notes, max_per_track=MAX_NOTES_PER_TRACK):
    """Split a note list into chunks that fit BDO's per-track limit."""
    if len(notes) <= max_per_track:
        return [notes]
    chunks = []
    for i in range(0, len(notes), max_per_track):
        chunks.append(notes[i:i + max_per_track])
    return chunks


def encode_name(name, size=NAME_FIELD_SIZE):
    """Encode a character name as UTF-16LE, padded/truncated to size bytes."""
    max_chars = size // 2
    encoded = name[:max_chars].encode('utf-16-le')
    return encoded.ljust(size, b'\x00')[:size]


def build_bdo_binary(bpm, time_sig_num, instrument_groups, char_name='MIDI',
                     owner_id=0, track_settings=None):
    """Build the plaintext BDO binary (everything after the 4-byte version).

    Args:
        bpm: Tempo in BPM
        time_sig_num: Time signature numerator
        instrument_groups: List of (inst_id, [track_note_lists]) tuples.
            Each group is one BDO instrument with its tracks (already split
            at 730).  An empty trailing track is appended automatically.
        char_name: Character name to embed
        owner_id: Account/family ID for edit permissions
        track_settings: 8 bytes for track settings (pan, effector, etc.).
            If None, uses TRACK_SETTINGS (all zeros).

    Returns:
        bytes: The plaintext payload (to be encrypted)
    """
    settings = track_settings if track_settings is not None else TRACK_SETTINGS
    num_instruments = len(instrument_groups)

    # Build comma-separated instrument tag (ASCII decimal IDs)
    inst_tag = ','.join(str(inst_id) for inst_id, _ in instrument_groups).encode('ascii')

    buf = bytearray()

    # Owner ID (4 bytes) — controls who can edit in-game
    buf.extend(struct.pack('<I', owner_id))
    # Zeros (4 bytes)
    buf.extend(b'\x00' * 4)
    # Character names (62 bytes each, BPM follows immediately after)
    buf.extend(encode_name(char_name))
    buf.extend(encode_name(char_name))
    # BPM (uint16 LE)
    buf.extend(struct.pack('<H', bpm))
    # Time signature numerator (uint16 LE)
    buf.extend(struct.pack('<H', time_sig_num))
    # Instrument tag (variable length, zero-padded into the padding area)
    buf.extend(inst_tag)
    # Zero padding to HEADER_SIZE (0x150)
    padding_needed = HEADER_SIZE - len(buf)
    buf.extend(b'\x00' * padding_needed)

    def _write_track(buf, inst_id, notes):
        """Write a single track: data_size + marker + settings + note_count + notes."""
        note_count = len(notes)
        track_marker = inst_id | (DEFAULT_VOLUME << 8)
        data_size = 2 + 8 + 2 + note_count * NOTE_SIZE
        buf.extend(struct.pack('<H', data_size))
        buf.extend(struct.pack('<H', track_marker))
        buf.extend(settings)
        buf.extend(struct.pack('<H', note_count))
        for n in notes:
            buf.append(n.pitch & 0x7F)
            buf.append(n.ntype & 0xFF)
            buf.append(n.vel & 0x7F)
            buf.append(n.vel & 0x7F)
            buf.extend(struct.pack('<d', n.start))
            buf.extend(struct.pack('<d', n.dur))

    # Write instrument groups
    for g, (inst_id, tracks) in enumerate(instrument_groups):
        # Each group's track count: first group's count is in the file header,
        # subsequent groups prefix their own count
        group_track_count = len(tracks) + 1  # +1 for empty trailing track

        if g == 0:
            # File header: 0x00 byte + num_instruments(u16) + first_group_tracks(u16)
            buf.append(0x00)
            buf.extend(struct.pack('<H', num_instruments))
            buf.extend(struct.pack('<H', group_track_count))
        else:
            # Subsequent groups: just the track count
            buf.extend(struct.pack('<H', group_track_count))

        # Data tracks
        for track_notes in tracks:
            _write_track(buf, inst_id, track_notes)

        # Empty trailing track (required by BDO)
        _write_track(buf, inst_id, [])

    # Pad to 8-byte alignment (ICE cipher block size)
    remainder = len(buf) % 8
    if remainder:
        buf.extend(b'\x00' * (8 - remainder))

    return bytes(buf)


def encrypt_bdo(plaintext):
    """Encrypt the plaintext payload with ICE and prepend the version header."""
    ice = IceKey(0, ICE_KEY)
    encrypted = ice.Encrypt(plaintext)
    return struct.pack('<I', BDO_VERSION) + encrypted


def extract_owner_id(bdo_path):
    """Extract the owner ID and character name from an existing BDO file.

    Returns:
        (owner_id, char_name) where owner_id is an int and char_name is a str.
    """
    with open(bdo_path, 'rb') as f:
        data = f.read()
    ice = IceKey(0, ICE_KEY)
    plaintext = ice.Decrypt(data[4:])
    owner_id = struct.unpack_from('<I', plaintext, 0)[0]
    char_name = plaintext[8:8 + NAME_FIELD_SIZE].decode('utf-16-le', errors='replace').rstrip('\x00')
    return owner_id, char_name


def rescale_velocity(notes, vel_min=0, vel_max=127):
    """Rescale note velocities to fit within [vel_min, vel_max]. Skips sustain pedal notes."""
    if not notes:
        return notes
    normal = [n for n in notes if n.ntype == 0]
    if not normal:
        return notes
    src_min = min(n.vel for n in normal)
    src_max = max(n.vel for n in normal)
    if src_min == src_max:
        flat_vel = (vel_min + vel_max) // 2
        return [n._replace(vel=flat_vel) if n.ntype == 0 else n for n in notes]
    result = []
    for n in notes:
        if n.ntype == 0:
            scaled = vel_min + (n.vel - src_min) / (src_max - src_min) * (vel_max - vel_min)
            result.append(n._replace(vel=round(scaled)))
        else:
            result.append(n)
    return result


def floor_velocity(notes, floor=100):
    """Proportionally scale velocities so the quietest note becomes floor, clamped to 127."""
    if not notes:
        return notes
    normal = [n for n in notes if n.ntype == 0]
    if not normal:
        return notes
    src_min = min(n.vel for n in normal)
    if src_min == 0 or src_min >= floor:
        return notes
    ratio = floor / src_min
    return [n._replace(vel=min(round(n.vel * ratio), 127)) if n.ntype == 0 else n
            for n in notes]


def stepped_velocity(notes, base=99, step=5):
    """Map each unique velocity level to stepped values: base, base+step, base+2*step, ..., 127."""
    if not notes:
        return notes
    normal_vels = sorted(set(n.vel for n in notes if n.ntype == 0))
    if not normal_vels:
        return notes
    vel_map = {}
    for i, v in enumerate(normal_vels):
        vel_map[v] = min(base + i * step, 127)
    # Ensure the loudest is always 127
    vel_map[normal_vels[-1]] = 127
    return [n._replace(vel=vel_map.get(n.vel, n.vel)) if n.ntype == 0 else n
            for n in notes]


# Layer-aware velocity levels based on analysis of well-made BDO compositions.
# Good composers use discrete steps that avoid harsh sample-switch boundaries.
BDO_VEL_LEVELS = [80, 90, 100, 121]


def layered_velocity(notes, levels=None):
    """Map velocities to BDO-optimized discrete levels.

    Distributes unique MIDI velocity values evenly across the given levels,
    preserving relative dynamics while avoiding harsh sample-switch boundaries.
    """
    if not notes:
        return notes
    if levels is None:
        levels = BDO_VEL_LEVELS
    normal_vels = sorted(set(n.vel for n in notes if n.ntype == 0))
    if not normal_vels:
        return notes
    if len(normal_vels) == 1:
        vel_map = {normal_vels[0]: levels[len(levels) // 2]}
    else:
        vel_map = {}
        for i, v in enumerate(normal_vels):
            # Map position in the velocity range to position in levels
            idx = round(i / (len(normal_vels) - 1) * (len(levels) - 1))
            vel_map[v] = levels[idx]
    return [n._replace(vel=vel_map.get(n.vel, n.vel)) if n.ntype == 0 else n
            for n in notes]


def transpose_notes(notes, semitones):
    """Shift all note pitches by the given number of semitones."""
    return [n._replace(pitch=n.pitch + semitones) for n in notes]


def make_track_settings(reverb=0, delay=0, chorus=None):
    """Build the 8-byte track settings from effector parameters.

    Args:
        reverb: Reverb level 0-127 (global effector only)
        delay: Delay level 0-127 (global effector only)
        chorus: None or tuple (feedback, lfo_depth, lfo_freq) each 0-127

    Returns:
        bytes: 8-byte track settings (per-instrument sends left at 0)
    """
    s = bytearray(8)
    # Per-instrument sends (bytes 0, 2, 4) left at 0 — set manually in editor
    s[1] = min(max(int(reverb), 0), 127)    # eff reverb
    s[3] = min(max(int(delay), 0), 127)     # eff delay
    if chorus:
        fb, depth, freq = chorus
        s[5] = min(max(int(fb), 0), 127)    # chorus feedback
        s[6] = min(max(int(depth), 0), 127) # chorus LFO depth
        s[7] = min(max(int(freq), 0), 127)  # chorus LFO freq
    return bytes(s)


def midi_to_bdo(midi_path, bpm_override=None, char_name='MIDI', vel_range=None,
                vel_floor=None, vel_step=None, vel_layered=False, transpose=0,
                apply_sustain=True, flatten_tempo=False, owner_id=0,
                instrument_map=None, reverb=0, delay=0, chorus=None):
    """Convert a MIDI file to BDO format.

    Args:
        instrument_map: Optional dict {(gm_program, is_percussion): bdo_instrument_id}.
            When provided, overrides automatic GM→BDO mapping.  Groups that
            resolve to the same BDO instrument have their notes merged.
        reverb: Reverb level 0-127
        delay: Delay level 0-127
        chorus: None or tuple (feedback, lfo_depth, lfo_freq) each 0-127

    Returns:
        (bdo_data, summary) where summary is a dict with keys:
            bpm, time_sig, tracks, total_notes, track_details
        track_details is a list of dicts with: notes, pitch_min, pitch_max, duration_ms
    """
    bpm, time_sig_num, channel_groups, _tempo_changes = parse_midi(
        midi_path, apply_sustain=apply_sustain, flatten_tempo=flatten_tempo)

    if bpm_override:
        bpm = bpm_override

    # Process each channel group and merge by assigned BDO instrument
    merged = defaultdict(list)
    for notes, gm_program, is_perc in channel_groups:
        if is_perc:
            # Percussion: map GM drum notes to BDO drum pitches + type 99
            notes = map_drum_notes(notes)
        else:
            # Melodic: transpose and clamp to BDO range
            if transpose:
                notes = transpose_notes(notes, transpose)
            notes = clamp_notes(notes)
        if vel_range:
            notes = rescale_velocity(notes, vel_range[0], vel_range[1])
        if vel_floor:
            notes = floor_velocity(notes, vel_floor)
        if vel_step:
            notes = stepped_velocity(notes, vel_step[0], vel_step[1])
        if vel_layered:
            notes = layered_velocity(notes)
        if instrument_map is not None:
            inst = instrument_map.get((gm_program, is_perc),
                                      gm_to_bdo_instrument(gm_program, is_perc))
        else:
            inst = gm_to_bdo_instrument(gm_program, is_perc)
        merged[inst].extend(notes)

    # Build instrument groups: [(inst_id, [track_note_lists]), ...]
    instrument_groups = []
    for inst, notes in merged.items():
        notes.sort(key=lambda n: n.start)
        chunks = split_notes(notes)
        instrument_groups.append((inst, chunks))

    if not instrument_groups:
        instrument_groups = [(DEFAULT_INSTRUMENT, [[]])]

    # Build summary
    track_details = []
    total_notes = 0
    total_tracks = 0
    for inst, chunks in instrument_groups:
        inst_name = BDO_INSTRUMENT_NAMES.get(inst, f'0x{inst:02x}')
        for chunk in chunks:
            total_tracks += 1
            total_notes += len(chunk)
            if chunk:
                track_details.append({
                    'notes': len(chunk),
                    'pitch_min': min(n.pitch for n in chunk),
                    'pitch_max': max(n.pitch for n in chunk),
                    'duration_ms': chunk[-1].start + chunk[-1].dur,
                    'instrument': inst_name,
                })
            else:
                track_details.append({'notes': 0, 'pitch_min': 0, 'pitch_max': 0,
                                      'duration_ms': 0, 'instrument': inst_name})
        total_tracks += 1  # empty trailing track per group

    summary = {
        'bpm': bpm,
        'time_sig': time_sig_num,
        'tracks': total_tracks,
        'total_notes': total_notes,
        'instruments': len(instrument_groups),
        'track_details': track_details,
    }

    track_settings = make_track_settings(reverb, delay, chorus)
    plaintext = build_bdo_binary(bpm, time_sig_num, instrument_groups, char_name,
                                 owner_id=owner_id, track_settings=track_settings)
    return encrypt_bdo(plaintext), summary


def main():
    parser = argparse.ArgumentParser(
        description='Convert MIDI files to BDO music composer format')
    parser.add_argument('input', help='Input MIDI file')
    parser.add_argument('output', nargs='?',
                        help='Output filename (no extension, default: input basename)')
    parser.add_argument('--bpm', type=int, help='Override BPM from MIDI')
    parser.add_argument('--name', default='MIDI',
                        help='Character name to embed (default: MIDI)')
    parser.add_argument('--outdir', default=None,
                        help='Output directory (default: ./converted/)')
    parser.add_argument('--vel', nargs=2, type=int, metavar=('MIN', 'MAX'),
                        help='Rescale velocities to MIN-MAX range (e.g. --vel 80 127)')
    parser.add_argument('--transpose', type=int, default=0,
                        help='Transpose by N semitones (e.g. -12 = down one octave)')
    parser.add_argument('--vel-floor', type=int, metavar='N',
                        help='Proportionally scale velocities so quietest becomes N')
    parser.add_argument('--vel-step', nargs=2, type=int, metavar=('BASE', 'STEP'),
                        help='Stepped velocity: BASE for quietest, +STEP per level, max 127')
    parser.add_argument('--no-sustain', action='store_true',
                        help='Ignore sustain pedal (use raw note durations)')
    parser.add_argument('--flatten-tempo', action='store_true',
                        help='Set BPM to 200 (BDO max) for multi-tempo MIDIs — minimizes grid quantization')
    parser.add_argument('--owner-file', metavar='BDO_FILE',
                        help='Extract owner ID from an existing BDO file (needed to edit in-game)')
    parser.add_argument('--reverb', type=int, default=0, metavar='N',
                        help='Reverb level 0-127')
    parser.add_argument('--delay', type=int, default=0, metavar='N',
                        help='Delay level 0-127')
    parser.add_argument('--chorus', nargs=3, type=int, metavar=('FB', 'DEPTH', 'FREQ'),
                        help='Chorus: feedback, LFO depth, LFO frequency (each 0-127)')

    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"Error: {args.input} not found", file=sys.stderr)
        sys.exit(1)

    # Determine output path
    if args.output:
        out_name = args.output
    else:
        out_name = os.path.splitext(os.path.basename(args.input))[0]

    out_dir = args.outdir or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'converted')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, out_name)

    owner_id = 0
    if args.owner_file:
        owner_id, owner_name = extract_owner_id(args.owner_file)
        print(f"Owner ID: 0x{owner_id:08x} (from \"{owner_name}\")")

    print(f"Converting: {args.input}")
    bdo_data, summary = midi_to_bdo(args.input, bpm_override=args.bpm, char_name=args.name,
                                     vel_range=args.vel, vel_floor=args.vel_floor,
                                     vel_step=args.vel_step, transpose=args.transpose,
                                     apply_sustain=not args.no_sustain,
                                     flatten_tempo=args.flatten_tempo,
                                     owner_id=owner_id,
                                     reverb=args.reverb, delay=args.delay,
                                     chorus=tuple(args.chorus) if args.chorus else None)

    print(f"BPM: {summary['bpm']}, Time sig: {summary['time_sig']}/4")
    print(f"Tracks: {summary['tracks']}, Total notes: {summary['total_notes']}")
    for i, td in enumerate(summary['track_details']):
        if td['notes']:
            print(f"  Track {i}: {td['notes']} notes, "
                  f"range: {td['pitch_min']}-{td['pitch_max']}, "
                  f"duration: {td['duration_ms']:.0f}ms, "
                  f"instrument: {td['instrument']}")
        else:
            print(f"  Track {i}: empty ({td['instrument']})")

    with open(out_path, 'wb') as f:
        f.write(bdo_data)
    print(f"Saved: {out_path} ({len(bdo_data)} bytes)")


if __name__ == '__main__':
    main()
