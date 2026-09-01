"""Does the actual video editing with ffmpeg: cut a segment, crop to 9:16,
burn in word-by-word captions, overlay a hook line, and optionally punch in
B-roll clips as picture-in-picture cutaways."""

import os
import random
import subprocess
import textwrap

VERTICAL_W = 1080
VERTICAL_H = 1920


def _fmt_ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def _words_in_range(all_segments: list, start: float, end: float) -> list:
    words = []
    for seg in all_segments:
        for w in seg.get("words", []):
            if w["start"] >= start and w["end"] <= end:
                words.append(w)
    return words


def build_caption_srt(words: list, clip_start: float, srt_path: str,
                       chunk_size: int = 4) -> None:
    """Groups words into small chunks (TikTok-style punchy captions) and
    writes an SRT file with times relative to the clip start."""
    lines = []
    idx = 1
    for i in range(0, len(words), chunk_size):
        chunk = words[i:i + chunk_size]
        if not chunk:
            continue
        start = chunk[0]["start"] - clip_start
        end = chunk[-1]["end"] - clip_start
        if end <= start:
            end = start + 0.3
        text = "".join(w["word"] for w in chunk).strip().upper()
        lines.append(str(idx))
        lines.append(f"{_fmt_ts(max(start,0))} --> {_fmt_ts(max(end,0.1))}")
        lines.append(text)
        lines.append("")
        idx += 1

    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _pick_broll(broll_dir: str) -> str | None:
    if not broll_dir or not os.path.isdir(broll_dir):
        return None
    candidates = [
        os.path.join(broll_dir, f) for f in os.listdir(broll_dir)
        if f.lower().endswith((".mp4", ".mov", ".mkv", ".webm"))
    ]
    return random.choice(candidates) if candidates else None


def render_clip(source_path: str, start: float, end: float, hook: str,
                 all_segments: list, out_path: str,
                 broll_dir: str | None = None) -> str:
    """Cuts [start, end] from source_path, converts to vertical 9:16,
    burns in captions + a hook line at the top, optionally punches in a
    B-roll cutaway (as a small overlay box) partway through, and writes
    the result to out_path. Returns out_path."""

    duration = end - start
    work_dir = os.path.dirname(out_path)
    os.makedirs(work_dir, exist_ok=True)
    srt_path = os.path.join(work_dir, f"_captions_{os.path.basename(out_path)}.srt")

    words = _words_in_range(all_segments, start, end)
    build_caption_srt(words, start, srt_path)

    # escape path for ffmpeg subtitles filter (colons need escaping on some platforms)
    srt_for_filter = srt_path.replace("\\", "/").replace(":", "\\:")

    hook_escaped = hook.replace("'", "\u2019").replace(":", "\\:")
    hook_wrapped = "\n".join(textwrap.wrap(hook_escaped, width=24)) or " "

    vf_parts = [
        f"crop=ih*9/16:ih,scale={VERTICAL_W}:{VERTICAL_H}",
    ]

    broll_path = _pick_broll(broll_dir) if broll_dir else None
    filter_complex = None
    inputs = ["-ss", str(start), "-t", str(duration), "-i", source_path]

    base_vf = (
        f"crop=ih*9/16:ih,scale={VERTICAL_W}:{VERTICAL_H},"
        f"subtitles='{srt_for_filter}':force_style="
        f"'FontName=Arial Black,FontSize=20,PrimaryColour=&HFFFFFF,"
        f"OutlineColour=&H000000,BorderStyle=1,Outline=3,Alignment=2,MarginV=180',"
        f"drawtext=text='{hook_wrapped}':fontcolor=white:fontsize=44:"
        f"fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
        f"box=1:boxcolor=black@0.55:boxborderw=20:x=(w-text_w)/2:y=120:"
        f"enable='lt(t,3.5)':line_spacing=8"
    )

    if broll_path:
        pip_start = max(2.0, duration * 0.35)
        pip_len = min(3.0, duration * 0.25)
        filter_complex = (
            f"[0:v]{base_vf}[main];"
            f"[1:v]scale={VERTICAL_W//2}:-1[pip];"
            f"[main][pip]overlay=x=(W-w)/2:y=H-h-260:"
            f"enable='between(t,{pip_start},{pip_start + pip_len})'[vout]"
        )
        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-t", str(pip_len), "-i", broll_path,
            "-filter_complex", filter_complex,
            "-map", "[vout]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac",
            out_path,
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-vf", base_vf,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac",
            out_path,
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed on clip {out_path}: {result.stderr[-2000:]}")

    return out_path
