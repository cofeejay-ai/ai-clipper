import os
import shutil
import threading
import traceback

from fastapi import FastAPI, UploadFile, Form, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core import downloader, transcriber, highlighter, clipper

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOBS_DIR = os.path.join(BASE_DIR, "jobs")
BROLL_DIR = os.path.join(BASE_DIR, "broll")
os.makedirs(JOBS_DIR, exist_ok=True)
os.makedirs(BROLL_DIR, exist_ok=True)

app = FastAPI()
JOBS: dict[str, dict] = {}  # job_id -> status dict, in-memory (fine for local single-user use)


def _process_job(job_id: str, source_path: str, clip_count: int, whisper_size: str):
    job = JOBS[job_id]
    try:
        job["status"] = "transcribing"
        transcript = transcriber.transcribe(source_path, model_size=whisper_size)

        job["status"] = "finding_clips"
        candidates = highlighter.find_clips(
            transcript["segments"], target_clip_count=clip_count
        )
        if not candidates:
            job["status"] = "error"
            job["error"] = "No clip candidates were returned. Try a longer source video."
            return

        job["status"] = "rendering"
        job["total_clips"] = len(candidates)
        job["clips"] = []

        job_dir = os.path.dirname(source_path)
        for i, c in enumerate(candidates):
            out_path = os.path.join(job_dir, f"clip_{i+1}.mp4")
            try:
                clipper.render_clip(
                    source_path=source_path,
                    start=c["start"],
                    end=c["end"],
                    hook=c["hook"] or c["caption_title"] or "Watch this",
                    all_segments=transcript["segments"],
                    out_path=out_path,
                    broll_dir=BROLL_DIR,
                )
                job["clips"].append({
                    "index": i + 1,
                    "hook": c["hook"],
                    "title": c["caption_title"],
                    "reason": c["reason"],
                    "start": c["start"],
                    "end": c["end"],
                    "file": f"clip_{i+1}.mp4",
                })
            except Exception as clip_err:
                job.setdefault("clip_errors", []).append(str(clip_err))
            job["rendered_count"] = i + 1

        job["status"] = "done"
    except Exception as e:
        job["status"] = "error"
        job["error"] = f"{e}"
        job["traceback"] = traceback.format_exc()


DEFAULT_WHISPER_SIZE = os.environ.get("WHISPER_MODEL_SIZE", "tiny")


@app.post("/api/jobs")
async def create_job(
    url: str = Form(default=""),
    clip_count: int = Form(default=6),
    whisper_size: str = Form(default=DEFAULT_WHISPER_SIZE),
    file: UploadFile | None = File(default=None),
):
    job_id = downloader.new_job_id()
    job_dir = os.path.join(JOBS_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    try:
        if file is not None and file.filename:
            content = await file.read()
            source_path = downloader.save_uploaded_file(content, file.filename, job_dir)
        elif url.strip():
            source_path = downloader.download_from_url(url.strip(), job_dir)
        else:
            return JSONResponse({"error": "Provide either a file or a URL."}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": f"Could not get source video: {e}"}, status_code=400)

    JOBS[job_id] = {"status": "queued", "clips": []}
    thread = threading.Thread(
        target=_process_job,
        args=(job_id, source_path, clip_count, whisper_size),
        daemon=True,
    )
    thread.start()

    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        return JSONResponse({"error": "unknown job"}, status_code=404)
    return job


@app.get("/api/jobs/{job_id}/clips/{filename}")
async def get_clip(job_id: str, filename: str):
    path = os.path.join(JOBS_DIR, job_id, filename)
    if not os.path.isfile(path):
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(path, media_type="video/mp4", filename=filename)


app.mount("/", StaticFiles(directory=os.path.join(BASE_DIR, "static"), html=True), name="static")
