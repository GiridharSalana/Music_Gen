#!/usr/bin/env python3
"""Modern future-bass / EDM track generator using mido."""
import sys
import mido
from mido import Message, MidiFile, MidiTrack, MetaMessage

BPM = 150
TPB = 480  # ticks per beat
BAR = TPB * 4  # 4/4

# ---------------------------------------------------------------------------
# Musical material
# ---------------------------------------------------------------------------
# Key: F minor (energetic festival future-bass key)
# Scale degrees of F natural minor: F G Ab Bb C Db Eb
KEY_ROOT = 53  # F3

# Chord progression (future-bass classic): Db - Ab - Fm - Eb  (VI - V/bIII - i - VII)
# Represented as root notes (MIDI) + chord type intervals.
def chord(root, kind="min"):
    if kind == "min":
        return [root, root + 3, root + 7]
    if kind == "maj":
        return [root, root + 4, root + 7]
    if kind == "sus2":
        return [root, root + 2, root + 7]
    if kind == "min7":
        return [root, root + 3, root + 7, root + 10]
    if kind == "maj7":
        return [root, root + 4, root + 7, root + 11]
    if kind == "add9":
        return [root, root + 4, root + 7, root + 14]
    return [root, root + 4, root + 7]

# Progression in F minor, 4 chords, one per bar
# Db(maj) - Eb(maj) - Fm(min) - Ab(maj)  -> bright, uplifting future-bass cadence
PROG = [
    (49, "maj7"),  # Db
    (51, "maj"),   # Eb
    (53, "min7"),  # Fm
    (56, "maj"),   # Ab
]

# scale for arps/melody (F minor, two octaves)
SCALE = []
steps = [0, 2, 3, 5, 7, 8, 10]
for octv in range(0, 3):
    for s in steps:
        SCALE.append(KEY_ROOT + octv * 12 + s)

# ---------------------------------------------------------------------------
# GM programs
# ---------------------------------------------------------------------------
PROG_PAD = 89      # Pad 2 (warm)
PROG_SAW = 81      # Lead 2 (sawtooth) -> supersaw stand-in
PROG_SUB = 38      # Synth Bass 1
PROG_PLUCK = 84    # Lead 5 (charang) plucky -> use 80 square? use 84 for pluck
PROG_BELL = 11     # Vibraphone / mallet for breakdown

# Channels
CH_PAD = 0
CH_SAW = 1
CH_SUB = 2
CH_PLUCK = 3
CH_BELL = 4
CH_DRUMS = 9

# Drums (GM)
KICK = 36
SNARE = 38
CLAP = 39
CHH = 42
OHH = 46
CRASH = 49
RIDE = 51
TOM_HI = 50
TOM_LO = 45

# ---------------------------------------------------------------------------
# Event-list helpers: build absolute-time events, then convert to delta.
# ---------------------------------------------------------------------------
class Part:
    def __init__(self, channel, program=None):
        self.channel = channel
        self.program = program
        self.events = []  # (abs_tick, msg_without_time)

    def note(self, start, dur, pitch, vel):
        if pitch < 0 or pitch > 127:
            return
        vel = max(1, min(127, int(vel)))
        self.events.append((start, Message('note_on', note=pitch, velocity=vel, channel=self.channel)))
        self.events.append((start + dur, Message('note_off', note=pitch, velocity=0, channel=self.channel)))

    def cc(self, start, control, value):
        self.events.append((start, Message('control_change', control=control,
                                            value=max(0, min(127, int(value))), channel=self.channel)))

    def to_track(self, name):
        trk = MidiTrack()
        trk.append(MetaMessage('track_name', name=name, time=0))
        if self.program is not None:
            trk.append(Message('program_change', program=self.program, channel=self.channel, time=0))
        # stable sort: note_off before note_on at same tick handled by velocity? sort by tick then off-first
        def keyf(e):
            t, m = e
            order = 0 if m.type == 'note_off' else (1 if m.type == 'control_change' else 2)
            return (t, order)
        evs = sorted(self.events, key=keyf)
        prev = 0
        for t, m in evs:
            dt = t - prev
            if dt < 0:
                dt = 0
            trk.append(m.copy(time=dt))
            prev = t
        return trk

# ---------------------------------------------------------------------------
# Sidechain "pump" via volume CC (channel volume CC#7) to simulate sidechaining.
# ---------------------------------------------------------------------------
def sidechain_cc(part, bar_start, bars, beats=4):
    """Pump volume down on each beat then ramp back up."""
    for b in range(bars):
        for beat in range(beats):
            t0 = bar_start + b * BAR + beat * TPB
            part.cc(t0, 7, 35)              # ducked
            part.cc(t0 + TPB // 6, 7, 70)
            part.cc(t0 + TPB // 3, 7, 100)
            part.cc(t0 + TPB // 2, 7, 120)  # recovered

# ---------------------------------------------------------------------------
# Build parts
# ---------------------------------------------------------------------------
pad = Part(CH_PAD, PROG_PAD)
saw = Part(CH_SAW, PROG_SAW)
sub = Part(CH_SUB, PROG_SUB)
pluck = Part(CH_PLUCK, PROG_PLUCK)
bell = Part(CH_BELL, PROG_BELL)
drums = Part(CH_DRUMS, None)

# ---- section pattern generators -------------------------------------------

def pad_chords(part, bar_start, bars, octave=0, vel=58):
    """Sustained lush chords following progression."""
    for b in range(bars):
        root, kind = PROG[b % len(PROG)]
        notes = chord(root + 12 * octave, kind)
        # add an extra octave-down anchor for lushness
        for n in notes + [notes[0] - 12]:
            part.note(bar_start + b * BAR, BAR, n, vel)

def supersaw_chords(part, bar_start, bars, vel=92):
    """Stacked detuned-feel saw chords, rhythmic stabs on a syncopated pattern."""
    # syncopated 1/8 + 1/16 future-bass rhythm pattern (in 16th units, 16 per bar)
    pattern = [0, 3, 4, 6, 8, 10, 11, 14]
    sixteenth = TPB // 4
    for b in range(bars):
        root, kind = PROG[b % len(PROG)]
        notes = chord(root + 12, "add9" if kind.startswith("maj") else "min7")
        # detune layer simulated by two close octaves
        layer = notes + [n + 12 for n in notes[:2]]
        for i, p in enumerate(pattern):
            start = bar_start + b * BAR + p * sixteenth
            dur = sixteenth * 2 if i % 2 == 0 else sixteenth
            v = vel + (12 if p in (0, 8) else 0)
            for n in layer:
                part.note(start, dur, n, v)

def sub_bass(part, bar_start, bars, vel=100, octave=-1):
    """Punchy sub following chord roots, sidechain feel via short notes on offbeats."""
    sixteenth = TPB // 4
    for b in range(bars):
        root, kind = PROG[b % len(PROG)]
        base = root + 12 * octave
        # rhythm: hit on each beat with a little syncopation
        hits = [0, 4, 6, 8, 12, 14]
        for h in hits:
            start = bar_start + b * BAR + h * sixteenth
            dur = sixteenth * 2
            part.note(start, dur, base, vel)

def pluck_arp(part, bar_start, bars, vel=80):
    """16th-note plucky arpeggio over the chords."""
    sixteenth = TPB // 4
    for b in range(bars):
        root, kind = PROG[b % len(PROG)]
        notes = chord(root + 12, kind)
        arp = [notes[0], notes[1], notes[2], notes[1],
               notes[0] + 12, notes[2], notes[1], notes[0]]
        for i in range(16):
            start = bar_start + b * BAR + i * sixteenth
            n = arp[i % len(arp)]
            part.note(start, sixteenth - 10, n, vel + (8 if i % 4 == 0 else 0))

def lead_melody(part, bar_start, bars, vel=100):
    """Singable lead riff sitting on top of the drop."""
    eighth = TPB // 2
    # motif in 8th notes (scale indices into SCALE around mid range)
    base = 7  # start index in SCALE
    motif = [0, 2, 1, 3, 2, 4, 3, 5,
             4, 3, 2, 1, 2, 0, -1, 0]
    for b in range(bars):
        for i in range(16):
            idx = base + motif[i % len(motif)]
            idx = max(0, min(len(SCALE) - 1, idx))
            n = SCALE[idx] + 12
            start = bar_start + b * BAR + i * eighth // 2  # actually 16th spacing
            # use 8th feel: only play every other 16th
            if i % 2 == 0:
                part.note(bar_start + b * BAR + (i // 2) * eighth, eighth - 20, n,
                          vel + (10 if i == 0 else 0))

def bell_melody(part, bar_start, bars, vel=78):
    """Gentle mallet melody for breakdown."""
    quarter = TPB
    for b in range(bars):
        root, kind = PROG[b % len(PROG)]
        notes = chord(root + 12, kind)
        seq = [notes[0] + 12, notes[2], notes[1] + 12, notes[0] + 12]
        for i, n in enumerate(seq):
            part.note(bar_start + b * BAR + i * quarter, quarter - 30, n, vel)

# ---- drum generators -------------------------------------------------------

def drum_four_floor(part, bar_start, bars, with_clap=True, hats=True):
    sixteenth = TPB // 4
    for b in range(bars):
        bs = bar_start + b * BAR
        for beat in range(4):
            part.note(bs + beat * TPB, sixteenth, KICK, 110)
        if with_clap:
            part.note(bs + 1 * TPB, sixteenth, CLAP, 100)
            part.note(bs + 3 * TPB, sixteenth, SNARE, 95)
        if hats:
            for i in range(8):
                t = bs + i * (TPB // 2)
                v = 70 if i % 2 == 0 else 50
                part.note(t, sixteenth, CHH, v)
            # open hat accents
            part.note(bs + TPB // 2 * 1 + TPB // 2, sixteenth, OHH, 60)

def drum_drop(part, bar_start, bars):
    sixteenth = TPB // 4
    for b in range(bars):
        bs = bar_start + b * BAR
        # kick four-on-floor with extra ghost
        for beat in range(4):
            part.note(bs + beat * TPB, sixteenth, KICK, 115)
        part.note(bs + 2 * TPB + sixteenth * 2, sixteenth, KICK, 80)
        # claps + snare on 2 and 4
        part.note(bs + 1 * TPB, sixteenth, CLAP, 110)
        part.note(bs + 3 * TPB, sixteenth, CLAP, 110)
        part.note(bs + 3 * TPB, sixteenth, SNARE, 100)
        # busy hats 16ths
        for i in range(16):
            t = bs + i * sixteenth
            v = 80 if i % 4 == 0 else (45 if i % 2 else 60)
            part.note(t, sixteenth - 5, CHH, v)
        # open hat off-beats
        for i in (2, 6, 10, 14):
            part.note(bs + i * sixteenth, sixteenth, OHH, 65)
        if b % 4 == 3:
            # tom fill last bar
            part.note(bs + 3 * TPB + sixteenth * 0, sixteenth, TOM_HI, 90)
            part.note(bs + 3 * TPB + sixteenth * 1, sixteenth, TOM_HI, 95)
            part.note(bs + 3 * TPB + sixteenth * 2, sixteenth, TOM_LO, 100)
            part.note(bs + 3 * TPB + sixteenth * 3, sixteenth, TOM_LO, 105)

def buildup(part, bar_start, bars):
    """Rising snare roll: subdivide faster each bar, crescendo."""
    for b in range(bars):
        bs = bar_start + b * BAR
        # kick on each beat for first bars, drop out at the end
        if b < bars - 1:
            for beat in range(4):
                part.note(bs + beat * TPB, TPB // 8, KICK, 100)
        # snare roll: divisions increase
        divs = [4, 8, 8, 16][min(b, 3)] if bars >= 4 else 8
        step = BAR // divs
        for i in range(divs):
            t = bs + i * step
            v = 50 + int((i / divs) * 60) + b * 5
            part.note(t, max(20, step - 10), SNARE, min(120, v))
        # hats rising
        for i in range(16):
            part.note(bs + i * (BAR // 16), 30, CHH, 40 + i * 2)

# ---------------------------------------------------------------------------
# Arrange the song (150 BPM -> 1 bar = 4 beats = 1.6 s).  Target ~240 s.
# 240 s / 1.6 s = 150 bars.  Lay out sections to ~150 bars.
# ---------------------------------------------------------------------------
cur = 0  # current bar

def crash(part, bar):
    part.note(bar * BAR, TPB, CRASH, 110)

# --- INTRO (16 bars): atmospheric pad ---
INTRO = 16
pad_chords(pad, cur * BAR, INTRO, octave=0, vel=50)
pad_chords(pad, cur * BAR, INTRO, octave=1, vel=38)
# soft pluck enters second half
pluck_arp(pluck, (cur + 8) * BAR, 8, vel=58)
crash(drums, cur)
cur += INTRO

# --- VERSE 1 (16 bars): drums + sub + pluck ---
V1 = 16
drum_four_floor(drums, cur * BAR, V1)
sub_bass(sub, cur * BAR, V1, vel=90)
pluck_arp(pluck, cur * BAR, V1, vel=78)
pad_chords(pad, cur * BAR, V1, octave=0, vel=45)
cur += V1

# --- BUILD-UP 1 (8 bars): rising snare rolls ---
B1 = 8
buildup(drums, cur * BAR, B1)
pad_chords(pad, cur * BAR, B1, octave=1, vel=55)
sub_bass(sub, cur * BAR, B1, vel=70)
cur += B1

# --- DROP 1 (16 bars): supersaw lead chords + sidechained sub + lead ---
D1 = 16
crash(drums, cur)
drum_drop(drums, cur * BAR, D1)
supersaw_chords(saw, cur * BAR, D1, vel=95)
sidechain_cc(saw, cur * BAR, D1)
sub_bass(sub, cur * BAR, D1, vel=110)
sidechain_cc(sub, cur * BAR, D1)
lead_melody(saw, cur * BAR, D1, vel=100)
cur += D1

# --- BREAKDOWN (16 bars): pad + bell melody, calm ---
BD = 16
pad_chords(pad, cur * BAR, BD, octave=0, vel=52)
pad_chords(pad, cur * BAR, BD, octave=1, vel=36)
bell_melody(bell, cur * BAR, BD, vel=80)
pluck_arp(pluck, (cur + 8) * BAR, 8, vel=60)
crash(drums, cur)
cur += BD

# --- BUILD-UP 2 (8 bars) ---
B2 = 8
buildup(drums, cur * BAR, B2)
pad_chords(pad, cur * BAR, B2, octave=1, vel=58)
bell_melody(bell, cur * BAR, B2, vel=66)
sub_bass(sub, cur * BAR, B2, vel=72)
cur += B2

# --- DROP 2 (24 bars): bigger, add pluck arp layer ---
D2 = 24
crash(drums, cur)
drum_drop(drums, cur * BAR, D2)
supersaw_chords(saw, cur * BAR, D2, vel=98)
sidechain_cc(saw, cur * BAR, D2)
sub_bass(sub, cur * BAR, D2, vel=112)
sidechain_cc(sub, cur * BAR, D2)
lead_melody(saw, cur * BAR, D2, vel=104)
pluck_arp(pluck, cur * BAR, D2, vel=70)
cur += D2

# --- OUTRO (16 bars): pad fade + sparse pluck ---
OUT = 16
pad_chords(pad, cur * BAR, OUT, octave=0, vel=48)
pad_chords(pad, cur * BAR, OUT, octave=1, vel=34)
pluck_arp(pluck, cur * BAR, OUT // 2, vel=55)
crash(drums, cur)
# final long pad chord tail
root, kind = PROG[2]  # land on Fm (i)
for n in chord(root, "min7") + [root - 12]:
    pad.note((cur + OUT) * BAR, BAR, n, 44)
cur += OUT + 1

# ---------------------------------------------------------------------------
# Assemble MIDI file
# ---------------------------------------------------------------------------
mid = MidiFile(ticks_per_beat=TPB)

# Tempo / meta track
meta = MidiTrack()
meta.append(MetaMessage('track_name', name='Future Bass', time=0))
meta.append(MetaMessage('set_tempo', tempo=mido.bpm2tempo(BPM), time=0))
meta.append(MetaMessage('time_signature', numerator=4, denominator=4, time=0))
mid.tracks.append(meta)

mid.tracks.append(pad.to_track('Pad'))
mid.tracks.append(saw.to_track('Supersaw'))
mid.tracks.append(sub.to_track('Sub Bass'))
mid.tracks.append(pluck.to_track('Pluck Arp'))
mid.tracks.append(bell.to_track('Bells'))
mid.tracks.append(drums.to_track('Drums'))

if len(sys.argv) < 2:
    sys.stderr.write("usage: python script.py <output.mid>\n")
    sys.exit(1)

mid.save(sys.argv[1])
print(f"Saved {sys.argv[1]} ({mid.length:.1f}s, {cur} bars)")