from __future__ import annotations

import os
import queue
import re
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from flask import Flask, abort, jsonify, render_template, request, send_file
from mutagen.id3 import ID3, TALB, TPE1
from mutagen.mp3 import MP3

DOWNLOAD_DIR = Path(os.environ.get("DOWNLOAD_DIR", "/downloads")).resolve()
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
STAGING_ROOT = (DOWNLOAD_DIR / ".staging").resolve()
if DOWNLOAD_DIR not in STAGING_ROOT.parents:
    raise RuntimeError("A pasta temporária precisa estar dentro do volume de downloads.")
if STAGING_ROOT.exists():
    for stale_job in STAGING_ROOT.iterdir():
        if stale_job.is_dir() and not stale_job.is_symlink():
            shutil.rmtree(stale_job, ignore_errors=True)
PORT = int(os.environ.get("PORT", "8080"))
MAX_JOBS = 50

app = Flask(__name__)
job_queue: queue.Queue[str] = queue.Queue()
jobs: list[dict] = []
job_by_id: dict[str, dict] = {}
lock = threading.RLock()


def safe_text(value: object, limit: int = 200) -> str:
    return re.sub(r"[\x00-\x1f\x7f]", "", str(value or "")).strip()[:limit]


def valid_youtube_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower().rstrip(".")
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and (
        host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com")
    )


def update_job(job_id: str, **values: object) -> None:
    with lock:
        job = job_by_id.get(job_id)
        if job:
            job.update(values)
            job["updated_at"] = datetime.now(timezone.utc).isoformat()


class JobLogger:
    def __init__(self, job_id: str):
        self.job_id = job_id

    def debug(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        self._log(message)

    def error(self, message: str) -> None:
        self._log(message)

    def _log(self, message: str) -> None:
        message = safe_text(message, 500)
        if not message:
            return
        with lock:
            job = job_by_id.get(self.job_id)
            if job:
                job["messages"].append(message)
                job["updated_at"] = datetime.now(timezone.utc).isoformat()


def progress_hook(job_id: str, data: dict) -> None:
    status = data.get("status")
    info = data.get("info_dict") or {}
    if status == "downloading":
        update_job(
            job_id,
            current_title=safe_text(info.get("title"), 180),
            progress=data.get("_percent_str", "").strip(),
            speed=data.get("_speed_str", "").strip(),
            phase="Baixando áudio",
        )
    elif status == "finished":
        update_job(
            job_id,
            current_title=safe_text(info.get("title"), 180),
            progress="",
            phase="Convertendo e aplicando metadados",
        )


def apply_tags(path: Path, artist: str, album: str) -> None:
    audio = MP3(path, ID3=ID3)
    if audio.tags is None:
        audio.add_tags()
    if artist:
        audio.tags.delall("TPE1")
        audio.tags.add(TPE1(encoding=3, text=[artist]))
    if album:
        audio.tags.delall("TALB")
        audio.tags.add(TALB(encoding=3, text=[album]))
    else:
        audio.tags.delall("TALB")
    audio.save(v2_version=3)


def run_job(job: dict) -> None:
    job_id = job["id"]
    staging_dir = (STAGING_ROOT / job_id).resolve()
    update_job(
        job_id,
        status="downloading",
        phase="Preparando download",
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    try:
        if STAGING_ROOT not in staging_dir.parents:
            raise ValueError("A pasta temporária precisa estar dentro do volume de downloads.")
        staging_dir.mkdir(parents=True, exist_ok=True)
        options = {
            "format": "bestaudio/best",
            "outtmpl": str(staging_dir / "%(uploader|Unknown)s" / "%(title)s [%(id)s].%(ext)s"),
            "noplaylist": False,
            "ignoreerrors": False,
            "extractor_args": {"youtube": {"player_client": ["android"]}},
            "sleep_interval": 5,
            "max_sleep_interval": 45,
            "writethumbnail": True,
            "convertthumbnails": "jpg",
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"},
                {"key": "FFmpegMetadata", "add_metadata": True},
                {"key": "EmbedThumbnail"},
            ],
            "windowsfilenames": False,
            "restrictfilenames": False,
            "overwrites": False,
            "continuedl": True,
            "progress_hooks": [lambda data: progress_hook(job_id, data)],
            "logger": JobLogger(job_id),
            "quiet": True,
            "no_warnings": False,
        }
        with yt_dlp.YoutubeDL(options) as downloader:
            result = downloader.download([job["url"]])

        mp3s = sorted(staging_dir.rglob("*.mp3"), key=lambda path: path.stat().st_mtime)
        outputs: list[str] = []
        for path in mp3s:
            resolved = path.resolve()
            if staging_dir not in resolved.parents or not resolved.is_file():
                continue
            try:
                apply_tags(resolved, job["artist"], job["album"])
                target = (DOWNLOAD_DIR / resolved.relative_to(staging_dir)).resolve()
                if DOWNLOAD_DIR not in target.parents:
                    raise ValueError("O caminho final saiu da pasta de downloads.")
                target.parent.mkdir(parents=True, exist_ok=True)
                original_stem, extension = target.stem, target.suffix
                candidate = target
                collision_index = 2
                while candidate.exists():
                    candidate = target.with_name(f"{original_stem} ({collision_index}){extension}")
                    collision_index += 1
                shutil.move(str(resolved), str(candidate))
                outputs.append(str(candidate.relative_to(DOWNLOAD_DIR)).replace("\\", "/"))
            except Exception as exc:
                JobLogger(job_id).warning(f"Não foi possível finalizar {path.name}: {exc}")

        if result == 0 and outputs:
            update_job(
                job_id,
                status="done",
                phase="Concluído",
                progress="100%",
                output_count=len(outputs),
                outputs=outputs,
            )
        elif outputs:
            update_job(
                job_id,
                status="error",
                phase="Download parcial",
                output_count=len(outputs),
                outputs=outputs,
                error=f"yt-dlp terminou com código {result}; alguns itens podem ter falhado.",
            )
        else:
            update_job(
                job_id,
                status="error",
                phase="Falha no download",
                error=f"Nenhum MP3 foi finalizado (código yt-dlp: {result}).",
            )
    except Exception as exc:
        update_job(job_id, status="error", phase="Falha no download", error=safe_text(exc, 1000))
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)


def worker() -> None:
    while True:
        job_id = job_queue.get()
        try:
            with lock:
                job = job_by_id.get(job_id)
            if job:
                run_job(job)
        finally:
            job_queue.task_done()


threading.Thread(target=worker, daemon=True, name="download-worker").start()


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/jobs")
def list_jobs():
    with lock:
        return jsonify(list(reversed(jobs)))


@app.post("/api/jobs")
def create_job():
    data = request.get_json(silent=True) or request.form
    url = safe_text(data.get("url"), 2048)
    if not valid_youtube_url(url):
        return jsonify(error="Informe uma URL válida de vídeo ou playlist do YouTube."), 400
    job = {
        "id": uuid.uuid4().hex[:12],
        "url": url,
        "artist": safe_text(data.get("artist"), 200),
        "album": safe_text(data.get("album"), 200),
        "status": "queued",
        "phase": "Na fila",
        "progress": "",
        "speed": "",
        "current_title": "",
        "output_count": 0,
        "outputs": [],
        "messages": [],
        "error": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    with lock:
        active_count = sum(item["status"] in {"queued", "downloading"} for item in jobs)
        if active_count >= MAX_JOBS:
            return jsonify(error="A fila está cheia. Aguarde alguns trabalhos terminarem."), 429
        while len(jobs) >= MAX_JOBS:
            removable = next(
                (index for index, item in enumerate(jobs) if item["status"] not in {"queued", "downloading"}),
                None,
            )
            if removable is None:
                return jsonify(error="O histórico está cheio de trabalhos ativos."), 429
            old_job = jobs.pop(removable)
            job_by_id.pop(old_job["id"], None)
        jobs.append(job)
        job_by_id[job["id"]] = job
    job_queue.put(job["id"])
    return jsonify(job), 202


@app.get("/api/files")
def list_files():
    files = []
    for path in DOWNLOAD_DIR.rglob("*.mp3"):
        try:
            if ".staging" in path.relative_to(DOWNLOAD_DIR).parts:
                continue
            resolved = path.resolve()
            if DOWNLOAD_DIR in resolved.parents and resolved.is_file():
                files.append(
                    {
                        "name": path.name,
                        "path": str(path.relative_to(DOWNLOAD_DIR)).replace("\\", "/"),
                        "size": path.stat().st_size,
                        "modified": path.stat().st_mtime,
                    }
                )
        except OSError:
            continue
    files.sort(key=lambda item: item["modified"], reverse=True)
    return jsonify(files[:100])


@app.get("/files/<path:relative_path>")
def get_file(relative_path: str):
    target = (DOWNLOAD_DIR / relative_path).resolve()
    if ".staging" in Path(relative_path).parts or DOWNLOAD_DIR not in target.parents or target.suffix.lower() != ".mp3" or not target.is_file():
        abort(404)
    return send_file(target, as_attachment=True, download_name=target.name, mimetype="audio/mpeg")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)

