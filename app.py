from __future__ import annotations

import os
import queue
import random
import re
import shutil
import threading
import time
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


def clean_folder_name(value: object) -> str:
    name = safe_text(value, 100)
    name = re.sub(r'[<>:"/\\|?*]', "_", name).strip(" .")
    if not name or name in {".", ".."} or name.lower() == ".staging":
        raise ValueError("Informe um nome de pasta válido.")
    return name


def update_job(job_id: str, **values: object) -> None:
    with lock:
        job = job_by_id.get(job_id)
        if job:
            job.update(values)
            job["updated_at"] = datetime.now(timezone.utc).isoformat()


class JobLogger:
    """Suppress routine yt-dlp chatter and retain only actual error messages."""

    def __init__(self):
        self.errors: list[str] = []

    def debug(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        message = safe_text(message, 1000)
        if message:
            self.errors.append(message)


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
            wait_seconds=0,
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
    audio.tags.delall("TRCK")
    audio.save(v2_version=3)


def video_urls_from_info(info: dict) -> tuple[list[tuple[str, str]], bool]:
    entries = info.get("entries")
    is_playlist = entries is not None
    videos: list[tuple[str, str]] = []
    if is_playlist:
        for entry in entries:
            if not entry:
                continue
            title = safe_text(entry.get("title"), 180) or "Vídeo"
            video_url = entry.get("webpage_url")
            candidate = entry.get("url")
            if not video_url and candidate:
                parsed = urlparse(str(candidate))
                if parsed.scheme in {"http", "https"} and parsed.hostname:
                    video_url = str(candidate)
                else:
                    video_id = str(entry.get("id") or candidate)
                    if re.fullmatch(r"[A-Za-z0-9_-]+", video_id):
                        video_url = f"https://www.youtube.com/watch?v={video_id}"
            if video_url:
                videos.append((str(video_url), title))
    else:
        videos.append((str(info.get("webpage_url") or info.get("original_url") or ""), safe_text(info.get("title"), 180) or "Vídeo"))
    videos = [(url, title) for url, title in videos if url]
    return videos, is_playlist


def download_options(job_id: str, item_dir: Path, logger: JobLogger) -> dict:
    return {
        "format": "bestaudio/best",
        "outtmpl": str(item_dir / "%(title)s.%(ext)s"),
        "noplaylist": True,
        "ignoreerrors": False,
        "extractor_args": {"youtube": {"player_client": ["android"]}},
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
        "logger": logger,
        "quiet": True,
        "no_warnings": True,
    }


def wait_between_items(job: dict, item_number: int, seconds: int) -> None:
    for remaining in range(seconds, 0, -1):
        update_job(
            job["id"],
            phase=f"Pausa de {seconds} s antes do próximo áudio",
            wait_seconds=remaining,
            current_title=f"Próximo: {job.get('next_title') or 'próximo áudio'}",
            progress=f"{item_number - 1}/{job.get('total_count', item_number)} concluídos",
            speed="",
        )
        time.sleep(1)


def run_job(job: dict) -> None:
    job_id = job["id"]
    staging_dir = (STAGING_ROOT / job_id).resolve()
    update_job(
        job_id,
        status="downloading",
        phase="Lendo vídeo ou playlist",
        started_at=datetime.now(timezone.utc).isoformat(),
        wait_seconds=0,
    )
    outputs: list[str] = []
    errors: list[str] = []
    try:
        if STAGING_ROOT not in staging_dir.parents:
            raise ValueError("A pasta temporária precisa estar dentro do volume de downloads.")
        staging_dir.mkdir(parents=True, exist_ok=True)
        metadata_logger = JobLogger()
        metadata_options = {
            "extractor_args": {"youtube": {"player_client": ["android"]}},
            "extract_flat": "in_playlist",
            "ignoreerrors": False,
            "logger": metadata_logger,
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(metadata_options) as downloader:
            info = downloader.extract_info(job["url"], download=False)
        if not info:
            raise RuntimeError("Não foi possível ler os dados desse vídeo ou playlist.")
        videos, is_playlist = video_urls_from_info(info)
        if not videos:
            raise RuntimeError("Não foi encontrado nenhum vídeo disponível nessa URL.")
        total = len(videos)
        update_job(job_id, total_count=total, phase="Na fila para download", is_playlist=is_playlist)
        destination = (DOWNLOAD_DIR / job["folder"]).resolve()
        if DOWNLOAD_DIR not in destination.parents:
            raise ValueError("O caminho final saiu da pasta de downloads.")
        destination.mkdir(parents=True, exist_ok=True)

        for index, (video_url, title) in enumerate(videos, start=1):
            update_job(
                job_id,
                current_index=index,
                current_title=title,
                next_title=videos[index][1] if index < total else "",
                phase=f"Preparando áudio {index}/{total}",
                progress="",
                speed="",
                wait_seconds=0,
            )
            if is_playlist and index > 1:
                delay = random.randint(job["delay_min"], job["delay_max"])
                wait_between_items(job, index, delay)
            item_dir = (staging_dir / f"item-{index:04d}").resolve()
            if staging_dir not in item_dir.parents:
                raise ValueError("Pasta temporária do item inválida.")
            item_dir.mkdir(parents=True, exist_ok=True)
            item_logger = JobLogger()
            try:
                with yt_dlp.YoutubeDL(download_options(job_id, item_dir, item_logger)) as downloader:
                    result = downloader.download([video_url])
                if result:
                    detail = item_logger.errors[-1] if item_logger.errors else f"yt-dlp terminou com código {result}."
                    raise RuntimeError(detail)
                mp3s = list(item_dir.rglob("*.mp3"))
                if not mp3s:
                    detail = item_logger.errors[-1] if item_logger.errors else "O download não gerou um MP3."
                    raise RuntimeError(detail)
                for mp3_path in mp3s:
                    resolved = mp3_path.resolve()
                    if item_dir not in resolved.parents or not resolved.is_file():
                        continue
                    apply_tags(resolved, job["artist"], job["album"])
                    candidate = (destination / resolved.name).resolve()
                    if destination not in candidate.parents:
                        raise ValueError("O nome do arquivo saiu da pasta escolhida.")
                    original_stem, extension = candidate.stem, candidate.suffix
                    collision_index = 2
                    while candidate.exists():
                        candidate = destination / f"{original_stem} ({collision_index}){extension}"
                        collision_index += 1
                    shutil.move(str(resolved), str(candidate))
                    outputs.append(str(candidate.relative_to(DOWNLOAD_DIR)).replace("\\", "/"))
            except Exception as exc:
                detail = safe_text(exc, 1000)
                if item_logger.errors and item_logger.errors[-1] not in detail:
                    detail = f"{detail} — {item_logger.errors[-1]}"
                errors.append(f"{title}: {detail}")
            update_job(
                job_id,
                outputs=outputs.copy(),
                output_count=len(outputs),
                errors=errors.copy(),
                current_index=index,
                current_title=title,
                phase=f"Processado {index}/{total}",
                progress=f"{index}/{total}",
                wait_seconds=0,
            )

        if errors:
            update_job(
                job_id,
                status="error",
                phase="Concluído com erros" if outputs else "Falha no download",
                error=f"{len(errors)} de {total} item(ns) falharam.",
                errors=errors,
                progress=f"{len(outputs)}/{total}",
            )
        elif outputs:
            update_job(job_id, status="done", phase="Concluído", progress="100%", output_count=len(outputs), outputs=outputs)
        else:
            update_job(job_id, status="error", phase="Falha no download", error="Nenhum MP3 foi finalizado.")
    except Exception as exc:
        update_job(job_id, status="error", phase="Falha no download", error=safe_text(exc, 1000), errors=errors)
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
    try:
        folder = clean_folder_name(data.get("folder"))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    try:
        delay_min = int(data.get("delay_min", 5))
        delay_max = int(data.get("delay_max", 45))
    except (TypeError, ValueError):
        return jsonify(error="Informe intervalos inteiros entre 5 e 45 segundos."), 400
    if not (5 <= delay_min <= delay_max <= 45):
        return jsonify(error="O intervalo deve estar entre 5 e 45 segundos, com o mínimo menor ou igual ao máximo."), 400

    now = datetime.now(timezone.utc).isoformat()
    job = {
        "id": uuid.uuid4().hex[:12],
        "url": url,
        "folder": folder,
        "artist": safe_text(data.get("artist"), 200),
        "album": safe_text(data.get("album"), 200),
        "delay_min": delay_min,
        "delay_max": delay_max,
        "status": "queued",
        "phase": "Na fila",
        "progress": "",
        "speed": "",
        "current_title": "",
        "current_index": 0,
        "total_count": 0,
        "wait_seconds": 0,
        "output_count": 0,
        "outputs": [],
        "errors": [],
        "error": "",
        "created_at": now,
        "updated_at": now,
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
