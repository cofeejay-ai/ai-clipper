"""Uses the Claude API to read a timestamped transcript and pick out
clip-worthy moments, each with a suggested hook/title text."""

import json
import os
from anthropic import Anthropic

MODEL = "claude-sonnet-4-6"


def _client() -> Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Get a key at console.anthropic.com "
            "and set it as an environment variable before starting the app."
        )
    return Anthropic(api_key=api_key)


def _format_transcript_for_prompt(segments: list) -> str:
    lines = []
    for seg in segments:
        lines.append(f"[{seg['start']:.1f}-{seg['end']:.1f}] {seg['text']}")
    return "\n".join(lines)


def find_clips(segments: list, target_clip_count: int = 6,
                min_len: float = 20.0, max_len: float = 90.0) -> list:
    """Returns a list of clip candidates:
    [{'start': float, 'end': float, 'hook': str, 'caption_title': str, 'reason': str}]
    """
    transcript_block = _format_transcript_for_prompt(segments)

    system_prompt = (
        "You are an expert short-form video editor (like Opus Clip). You are given "
        "a timestamped transcript of a long video. Find the best self-contained "
        f"moments to cut into short clips ({min_len:.0f}-{max_len:.0f} seconds each), "
        "the kind that perform well on TikTok/Reels/Shorts: strong emotional beats, "
        "surprising claims, concrete stories, punchlines, useful tips, or arguments. "
        "For each clip, write a punchy hook — the first line of on-screen text/spoken "
        "line that stops someone scrolling — and a short caption_title. "
        "Respond ONLY with a JSON array, no other text, no markdown fences. "
        "Each element: {\"start\": number, \"end\": number, \"hook\": string, "
        "\"caption_title\": string, \"reason\": string}. Start/end must be real "
        "timestamps from the transcript (in seconds). Pick non-overlapping clips."
    )

    user_prompt = (
        f"Find the best {target_clip_count} clips from this transcript.\n\n"
        f"TRANSCRIPT:\n{transcript_block}"
    )

    client = _client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_text = "".join(
        block.text for block in response.content if block.type == "text"
    ).strip()

    # strip stray markdown fences just in case
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]

    try:
        clips = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Could not parse highlight response as JSON: {e}\nRaw: {raw_text[:500]}")

    # basic validation/cleanup
    clean = []
    for c in clips:
        try:
            clean.append({
                "start": float(c["start"]),
                "end": float(c["end"]),
                "hook": str(c.get("hook", "")).strip(),
                "caption_title": str(c.get("caption_title", "")).strip(),
                "reason": str(c.get("reason", "")).strip(),
            })
        except (KeyError, ValueError, TypeError):
            continue
    return clean
