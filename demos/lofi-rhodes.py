import sys
import random
import mido
from mido import Message, MidiFile, MidiTrack, MetaMessage

random.seed(78)

# ----------------------------------------------------------------------
# Global setup
# ----------------------------------------------------------------------
BPM = 78
TPB = 480                      # ticks per beat
BEAT = TPB
BAR = BEAT * 4                 # 4/4 time

# GM programs
RHODES   = 4    # Electric Piano 1 (Rhodes)
PAD      = 89   # Pad 2 (warm)
BASS     = 33   # Electric Bass (finger)

# channels
CH_RHODES = 0
CH_PAD    = 1
CH_BASS   = 2
CH_DRUMS  = 9

# ----------------------------------------------------------------------
# Music theory: key of F minor (mellow lofi flavor)
# F minor scale: F G Ab Bb C Db Eb
# ----------------------------------------------------------------------
# MIDI note numbers (octave naming: C4 = 60)
# We'll work mostly in the F2/F3 region.

# Lofi chord progression (i - VI - III - VII style): Fm9 - Db maj7 - Ab maj7 - Eb7
# voiced as 7th/9th chords for that smooth jazzy feel.
PROG = [
    # (root for bass, [chord tones for rhodes voicing])
    (41, [53, 56, 60, 63, 67]),   # Fm9   : F  Ab C Eb G   (Ab+C+Eb+G+ root-ish)
    (37, [53, 57, 60, 64]),       # Dbmaj7: Db F  Ab C
    (44, [56, 60, 63, 67]),       # Abmaj7: Ab C  Eb G
    (39, [55, 58, 62, 65]),       # Eb9    : Eb G  Bb Db (approx)
]

# Scale tones for the melody (F natural minor across two octaves)
F_MINOR = [65, 67, 68, 70, 72, 73, 75, 77, 79, 80, 82, 84]

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def add_note(track, note, ch, start, dur, vel):
    """Schedule an absolute-time note as (start, msg) pairs collected later."""
    track.append((start, Message('note_on',  note=note, velocity=vel, channel=ch)))
    track.append((start + dur, Message('note_off', note=note, velocity=0, channel=ch)))

def flush(events):
    """Convert absolute-timed (time, msg) events into a delta-timed MidiTrack."""
    events.sort(key=lambda e: (e[0], e[1].type != 'note_off'))
    track = MidiTrack()
    prev = 0
    for t, msg in events:
        track.append(msg.copy(time=t - prev))
        prev = t
    return track

# ----------------------------------------------------------------------
# Build tracks
# ----------------------------------------------------------------------
mid = MidiFile(ticks_per_beat=TPB)

# Meta / tempo track
meta = MidiTrack()
meta.append(MetaMessage('set_tempo', tempo=mido.bpm2tempo(BPM), time=0))
meta.append(MetaMessage('time_signature', numerator=4, denominator=4, time=0))
meta.append(MetaMessage('track_name', name='Mellow Lofi Beat', time=0))
mid.tracks.append(meta)

drum_ev, bass_ev, rhodes_ev, pad_ev = [], [], [], []

# program changes
rhodes_ev.append((0, Message('program_change', program=RHODES, channel=CH_RHODES)))
pad_ev.append((0, Message('program_change', program=PAD, channel=CH_PAD)))
bass_ev.append((0, Message('program_change', program=BASS, channel=CH_BASS)))

# At 78 BPM, one bar = ~3.08s. ~10 bars ≈ 30s.
# Structure: intro(2 bars, no drums) / A(4 bars full) / B(4 bars full) = 10 bars
SECTIONS = [
    ('intro', 2),
    ('A',     4),
    ('B',     4),
]

def lofi_drums(track, bar_start, swing=True, fill=False):
    """Soft boom-bap drum pattern with a little swing and humanization."""
    # kick on 1 and the 'and' of 2-ish (lofi syncopation)
    kicks = [0, BEAT*2 + TPB//2]
    snares = [BEAT, BEAT*3]
    for k in kicks:
        add_note(track, 36, CH_DRUMS, bar_start + k, TPB//2, random.randint(78, 92))
    for s in snares:
        add_note(track, 38, CH_DRUMS, bar_start + s, TPB//2, random.randint(70, 84))
    # closed hats in 8ths with swing + soft velocities
    for i in range(8):
        pos = bar_start + i * (TPB // 2)
        if swing and i % 2 == 1:
            pos += TPB // 8       # delay off-beats -> swung feel
        hum = random.randint(-8, 8)
        vel = random.randint(40, 58)
        if i == 6 and fill:       # tiny open hat lift before section change
            add_note(track, 46, CH_DRUMS, pos + hum, TPB//2, 58)
        else:
            add_note(track, 42, CH_DRUMS, pos + hum, TPB//4, vel)

# ----------------------------------------------------------------------
# Sequence the song
# ----------------------------------------------------------------------
bar = 0
for name, length in SECTIONS:
    for b in range(length):
        bar_start = bar * BAR
        chord_root, voicing = PROG[bar % len(PROG)]
        is_last_bar = (b == length - 1)

        # ---- Drums (skip during intro for a soft build) ----
        if name != 'intro':
            lofi_drums(drum_ev, bar_start, swing=True, fill=is_last_bar)

        # ---- Bass: root on 1, soft fifth/octave movement ----
        bvel = random.randint(72, 86)
        add_note(bass_ev, chord_root, CH_BASS, bar_start, BEAT*2 - 20, bvel)
        # walking-ish note into next: root up an octave on beat 3
        add_note(bass_ev, chord_root + 12, CH_BASS, bar_start + BEAT*2, BEAT - 20, bvel - 8)
        add_note(bass_ev, chord_root + 7,  CH_BASS, bar_start + BEAT*3, BEAT - 20, bvel - 10)

        # ---- Rhodes: lazy off-beat comping with the chord voicing ----
        comp_hits = [0, BEAT + TPB//2, BEAT*2 + TPB//2, BEAT*3]
        for hi, hit in enumerate(comp_hits):
            dur = BEAT - 40 if hi % 2 == 0 else TPB - 30
            for j, n in enumerate(voicing):
                # roll the chord slightly (humanized arpeggiation)
                roll = j * 12
                vel = random.randint(52, 70) - (4 if hi % 2 else 0)
                add_note(rhodes_ev, n, CH_RHODES, bar_start + hit + roll, dur, max(40, vel))

        # ---- Pad: sustained warm bed under everything (enters after intro start) ----
        pvel = 42 if name == 'intro' else 50
        for n in (voicing[0], voicing[1], voicing[-1]):
            add_note(pad_ev, n - 12, CH_PAD, bar_start, BAR - 30, pvel)

        # ---- Simple melodic motif on the A & B sections (sparse, mellow) ----
        if name in ('A', 'B'):
            mel_slots = [BEAT*0, BEAT*1 + TPB//2, BEAT*2, BEAT*3 + TPB//2]
            # choose a few notes from the scale, leave space
            for ms in mel_slots:
                if random.random() < (0.5 if name == 'A' else 0.7):
                    note = random.choice(F_MINOR[2:8])
                    add_note(rhodes_ev, note, CH_RHODES,
                             bar_start + ms, random.choice([TPB//2, TPB]), random.randint(58, 74))

        bar += 1

# Final sustained Fm9 chord to resolve
end_start = bar * BAR
_, final_voicing = PROG[0]
for n in final_voicing:
    add_note(rhodes_ev, n, CH_RHODES, end_start, BAR, random.randint(46, 60))
for n in (final_voicing[0] - 12, final_voicing[1] - 12):
    add_note(pad_ev, n, CH_PAD, end_start, BAR, 46)
add_note(bass_ev, PROG[0][0], CH_BASS, end_start, BAR, 70)

# ----------------------------------------------------------------------
# Assemble & save
# ----------------------------------------------------------------------
mid.tracks.append(flush(drum_ev))
mid.tracks.append(flush(bass_ev))
mid.tracks.append(flush(rhodes_ev))
mid.tracks.append(flush(pad_ev))

mid.save(sys.argv[1])