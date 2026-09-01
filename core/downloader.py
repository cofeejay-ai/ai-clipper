"""Handles getting a source video onto disk, either from an uploaded file
or from a URL (YouTube, TikTok, etc.) via yt-dlp."""

import os
import subprocess
import uuid


def download_from_url(url: str, dest_dir: str) -> str:
    """Downloads a video from a URL using yt-dlp. Returns the local file path."""
    os.makedirs(dest_dir, exist_ok=True)
    out_template = os.path.join(dest_dir, "source.%(ext)s")

    cmd = [
        "yt-dlp",
        "-f", "mp4/bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", out_template,
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {result.stderr[-2000:]}")

    # find the resulting file
    for f in os.listdir(dest_dir):
        if f.startswith("source."):
            return os.path.join(dest_dir, f)
    raise RuntimeError("yt-dlp reported success but no output file was found.")


def save_uploaded_file(file_bytes: bytes, filename: str, dest_dir: str) -> str:
    """Saves an uploaded file to disk. Returns the local file path."""
    os.makedirs(dest_dir, exist_ok=True)
    ext = os.path.splitext(filename)[1] or ".mp4"
    dest_path = os.path.join(dest_dir, f"source{ext}")
    with open(dest_path, "wb") as f:
        f.write(file_bytes)
    return dest_path


def new_job_id() -> str:
    return uuid.uuid4().hex[:10]
