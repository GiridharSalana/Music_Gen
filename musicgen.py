#!/usr/bin/env python3
"""
musicgen — headless "text -> song" CLI.

Pipeline:
  prompt --> claude -p (writes a mido Python script)
         --> run script (via `uv run --with mido`) --> song.mid
         --> fluidsynth + GM soundfont          --> song.wav
         --> ffmpeg                              --> song.mp3

Everything runs headless. No GUI, no API key (uses the logged-in `claude` CLI).
"""
import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys
import textwrap

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SOUNDFONTS = [
    os.path.expanduser("~/soundfonts/TimbresOfHeaven-4.00.sf2"),  # best free GM (~440MB)
    "/usr/share/sounds/sf2/FluidR3_GM.sf2",  # great free GM (~140MB)
    "/usr/share/sounds/sf2/default-GM.sf2",
    "/usr/share/sounds/sf2/TimGM6mb.sf2",
    "/usr/share/soundfonts/default.sf2",
]


def log(msg):
    print(f"\033[36m[musicgen]\033[0m {msg}", flush=True)


def die(msg, code=1):
    print(f"\033[31m[musicgen] error:\033[0m {msg}", file=sys.stderr, flush=True)
    sys.exit(code)


def need(tool, hint):
    if shutil.which(tool) is None:
        die(f"`{tool}` not found. {hint}")


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s[:40] or "song")


def pick_soundfont(explicit):
    # priority: --soundfont flag > $MUSICGEN_SOUNDFONT > built-in default list
    explicit = explicit or os.environ.get("MUSICGEN_SOUNDFONT")
    if explicit:
        explicit = os.path.expanduser(explicit)
        if not os.path.exists(explicit):
            die(f"soundfont not found: {explicit}")
        return explicit
    for sf in DEFAULT_SOUNDFONTS:
        if os.path.exists(sf):
            return sf
    die("no soundfont found. Install one, e.g. `sudo apt install fluid-soundfont-gm`, "
        "or pass --soundfont /path/to.sf2")


SYSTEM_BRIEF = textwrap.dedent("""\
    You are a music composer that writes Python code using ONLY the `mido` library
    (standard library is also allowed). You output a COMPLETE, RUNNABLE Python script
    and NOTHING ELSE — no prose, no markdown fences, no explanations.

    Hard requirements for the script:
    - Take the output MIDI path as sys.argv[1] and save a Standard MIDI File there.
    - Use `import mido` and `from mido import Message, MidiFile, MidiTrack, MetaMessage`.
    - Set tempo with MetaMessage('set_tempo', tempo=mido.bpm2tempo(BPM)).
    - Use General MIDI program numbers via Message('program_change', program=N, channel=C).
      Put drums on channel 9 (GM percussion). Use proper GM note numbers for drums
      (e.g. 36 kick, 38 snare, 42 closed hat, 46 open hat, 49 crash).
    - Compose REAL structure: intro / verse / chorus or A/B sections, multiple tracks
      (e.g. drums, bass, chords/pads, melody), tasteful velocities, and the requested length.
    - Make it musical: pick a key/scale, use chord progressions, keep rhythm coherent.
    - The script must run to completion and write the file with no manual edits.

    Output the raw Python source only.
""")


def build_prompt(args):
    length = f"about {args.duration} seconds long" if args.duration else "30-60 seconds long"
    return (
        f"{SYSTEM_BRIEF}\n\n"
        f"Compose this piece:\n"
        f"  Description : {args.prompt}\n"
        f"  Tempo       : {args.bpm} BPM\n"
        f"  Length      : {length}\n"
        f"Write the Python script now."
    )


def build_repair_prompt(args, code, error):
    return (
        f"{SYSTEM_BRIEF}\n\n"
        f"Your previous script failed. Fix it and output the FULL corrected script only.\n\n"
        f"Original request: {args.prompt} ({args.bpm} BPM)\n\n"
        f"--- previous script ---\n{code}\n\n"
        f"--- error when run ---\n{error}\n"
    )


def call_claude(prompt, model):
    cmd = ["claude", "-p", "--model", model]
    log(f"asking claude ({model}) to compose...")
    try:
        res = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        die("claude timed out after 300s")
    if res.returncode != 0:
        die(f"claude failed (exit {res.returncode}):\n{res.stderr}")
    return res.stdout


def extract_code(text):
    # Strip markdown fences if the model added them despite instructions.
    fence = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    code = fence.group(1) if fence else text
    return code.strip()


def run_script(script_path, midi_path):
    cmd = ["uv", "run", "--quiet", "--with", "mido", "python", script_path, midi_path]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    ok = res.returncode == 0 and os.path.exists(midi_path) and os.path.getsize(midi_path) > 0
    return ok, (res.stderr + res.stdout)


def render(midi_path, wav_path, soundfont, gain):
    need("fluidsynth", "Install with:  sudo apt install fluidsynth")
    cmd = ["fluidsynth", "-ni", "-g", str(gain), "-F", wav_path,
           "-r", "44100", soundfont, midi_path]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if not (os.path.exists(wav_path) and os.path.getsize(wav_path) > 0):
        die(f"fluidsynth produced no audio:\n{res.stderr}")


def to_mp3(wav_path, mp3_path):
    need("ffmpeg", "Install ffmpeg to get mp3 output (wav is still produced).")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", wav_path,
         "-codec:a", "libmp3lame", "-q:a", "2", mp3_path],
        check=False,
    )


def main():
    ap = argparse.ArgumentParser(
        prog="musicgen",
        description="Generate a song from a text prompt, fully headless.")
    ap.add_argument("prompt", help="describe the music, e.g. 'mellow lofi hip hop beat'")
    ap.add_argument("--bpm", type=int, default=90, help="tempo in BPM (default 90)")
    ap.add_argument("--duration", type=int, default=None, help="target length in seconds")
    ap.add_argument("--out", default=None, help="output directory (default ./out/<slug>-<time>)")
    ap.add_argument("--model", default="claude-opus-4-8", help="claude model id")
    ap.add_argument("--soundfont", default=None, help="path to a .sf2 soundfont")
    ap.add_argument("--gain", type=float, default=1.0, help="fluidsynth gain (default 1.0)")
    ap.add_argument("--retries", type=int, default=2, help="LLM repair attempts on failure")
    ap.add_argument("--play", action="store_true", help="play the result when done (mpv)")
    ap.add_argument("--keep-going", action="store_true",
                    help="don't exit if mp3 step missing; keep wav")
    args = ap.parse_args()

    need("claude", "Claude Code CLI must be installed and logged in.")
    need("uv", "Install uv: https://docs.astral.sh/uv/")
    soundfont = pick_soundfont(args.soundfont)

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = args.out or os.path.join(ROOT, "out", f"{slugify(args.prompt)}-{stamp}")
    os.makedirs(outdir, exist_ok=True)
    script_path = os.path.join(outdir, "song.py")
    midi_path = os.path.join(outdir, "song.mid")
    wav_path = os.path.join(outdir, "song.wav")
    mp3_path = os.path.join(outdir, "song.mp3")
    log(f"output dir: {outdir}")
    log(f"soundfont : {soundfont}")

    prompt = build_prompt(args)
    code = None
    last_err = ""
    for attempt in range(args.retries + 1):
        raw = call_claude(prompt, args.model)
        code = extract_code(raw)
        if not code:
            last_err = "claude returned empty output"
            continue
        with open(script_path, "w") as f:
            f.write(code)
        log(f"generated {len(code)} chars of mido code -> running (attempt {attempt+1})")
        ok, output = run_script(script_path, midi_path)
        if ok:
            log("MIDI generated ✔")
            break
        last_err = output.strip()[-1500:]
        log("script failed; asking claude to repair...")
        prompt = build_repair_prompt(args, code, last_err)
    else:
        die(f"could not produce a working script after {args.retries+1} tries.\n"
            f"last error:\n{last_err}\nsaved attempt: {script_path}")

    log("rendering audio with fluidsynth...")
    render(midi_path, wav_path, soundfont, args.gain)
    log("WAV rendered ✔")

    have_mp3 = shutil.which("ffmpeg") is not None
    if have_mp3:
        to_mp3(wav_path, mp3_path)
        log("MP3 encoded ✔")

    final = mp3_path if (have_mp3 and os.path.exists(mp3_path)) else wav_path
    print()
    log(f"\033[32mDONE\033[0m  →  {final}")
    log(f"files: {script_path}, {midi_path}, {wav_path}" + (f", {mp3_path}" if have_mp3 else ""))

    if args.play:
        player = shutil.which("mpv") or shutil.which("ffplay")
        if player:
            subprocess.run([player, "--no-video", final] if player.endswith("mpv")
                           else [player, "-nodisp", "-autoexit", final])


if __name__ == "__main__":
    main()
