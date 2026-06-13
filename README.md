# 🎵 musicgen

**Text → song, fully headless.** Describe music in plain English and get back a real audio file. An LLM writes the music as code, a synthesizer renders it.

```bash
./musicgen "mellow lofi hip hop beat with rhodes piano" --bpm 78
./musicgen "modern future-bass EDM with supersaw drops" --bpm 150 --duration 240
./musicgen "8-bit chiptune platformer level" --bpm 150 --play
```

## How it works

```
prompt ─► claude -p ─► song.py (mido) ─► song.mid ─► fluidsynth + GM soundfont ─► song.wav ─► ffmpeg ─► song.mp3
         (writes code)   (runs it)        (MIDI)        (renders audio)                          (final)
```

1. **Claude** (via the logged-in `claude` CLI — no API key) is asked to write a complete Python script using [`mido`](https://mido.readthedocs.io) that composes the requested piece and saves a Standard MIDI File.
2. The script runs via `uv run --with mido` (uv auto-installs the dependency — zero setup).
3. **fluidsynth** renders the MIDI to WAV using a General-MIDI soundfont (128 instruments + drums).
4. **ffmpeg** encodes the WAV to MP3.

If the generated script errors, the traceback is fed back to Claude for repair (up to `--retries` times), so you reliably get a working song.

## Requirements

| Tool | Purpose | Install |
|---|---|---|
| `claude` | the composer (Claude Code CLI, logged in) | https://claude.com/claude-code |
| `uv` | runs the generated script with `mido` | https://docs.astral.sh/uv |
| `fluidsynth` | MIDI → audio renderer | `sudo apt install fluidsynth` |
| a `.sf2` soundfont | the actual instrument sounds | `sudo apt install fluid-soundfont-gm` (FluidR3_GM) |
| `ffmpeg` | WAV → MP3 (optional) | `sudo apt install ffmpeg` |

## Usage

```
./musicgen "<description>" [options]

  --bpm N           tempo (default 90)
  --duration N      target length in seconds (a hint to the LLM)
  --out DIR         output directory (default ./out/<slug>-<timestamp>)
  --model ID        claude model id (default claude-opus-4-8)
  --soundfont PATH  override the .sf2 soundfont
  --gain G          fluidsynth gain (default 1.0)
  --retries N       LLM repair attempts on failure (default 2)
  --play            play the result when done (mpv/ffplay)
```

Each run drops everything in `out/<slug>-<timestamp>/`: the generated `song.py`, `song.mid`, `song.wav`, and `song.mp3`.

## Reading a MIDI file

```bash
./midread out/.../song.mid          # readable event dump
./midread out/.../song.mid --full   # every event
```

## Demos

See [`demos/`](demos/) for example output.

## Notes & limits

- The 128 General-MIDI instruments + drum kit cover most genres. MIDI **cannot** produce human vocals — that needs a neural audio model, a different paradigm.
- Sound quality depends on the soundfont. [FluidR3_GM](https://member.keymusician.com/Member/FluidR3_GM/index.html) (~140 MB) is the recommended free one.
- `--duration` is a hint; the LLM estimates bar counts, so final length can vary by ±30s.
