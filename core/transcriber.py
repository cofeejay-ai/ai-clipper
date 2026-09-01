"""Transcribes a video/audio file into word-level timestamped segments
using faster-whisper (runs locally, no API needed)."""

from faster_whisper import WhisperModel

_models = {}


def get_model(model_size: str = "tiny"):
    """Loads the whisper model once per size and reuses it. 'tiny' is the
    default so this fits comfortably on a free-tier host (512MB RAM, shared
    CPU). On your own computer with more RAM/CPU, 'small' or 'medium' will
    be noticeably more accurate — pick it in the UI."""
    if model_size not in _models:
        _models[model_size] = WhisperModel(model_size, device="cpu", compute_type="int8")
    return _models[model_size]


def transcribe(video_path: str, model_size: str = "tiny") -> dict:
    """Returns {
        'text': full transcript,
        'segments': [{'start': float, 'end': float, 'text': str, 'words': [{'start','end','word'}]}]
    }"""
    model = get_model(model_size)
    segments_iter, info = model.transcribe(
        video_path,
        word_timestamps=True,
        vad_filter=True,
    )

    segments = []
    full_text_parts = []
    for seg in segments_iter:
        words = [
            {"start": w.start, "end": w.end, "word": w.word}
            for w in (seg.words or [])
        ]
        segments.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text.strip(),
            "words": words,
        })
        full_text_parts.append(seg.text.strip())

    return {
        "text": " ".join(full_text_parts),
        "segments": segments,
        "duration": info.duration,
    }
