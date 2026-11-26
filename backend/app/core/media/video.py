import json
import math
import re
import shutil
import subprocess
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from app.config import get_settings
from app.core.media.cover import create_cover


class VideoError(ValueError):
    pass


@dataclass
class VideoMetadata:
    video_path: str
    duration: int
    width: int
    height: int
    size_bytes: int
    codec: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def ffmpeg_executable() -> str:
    settings = get_settings()
    if settings.ffmpeg_bin:
        return settings.ffmpeg_bin
    bundled = shutil.which("ffmpeg")
    if bundled:
        return bundled
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError) as exc:
        raise VideoError("未找到 ffmpeg，请安装 imageio-ffmpeg 或配置 FFMPEG_BIN。") from exc


def resolve_video_path(stored_path: str) -> Path:
    settings = get_settings()
    relative = Path(stored_path)
    if (
        relative.is_absolute()
        or not relative.parts
        or relative.parts[0] != "videos"
        or ".." in relative.parts
    ):
        raise VideoError("视频路径无效，只能使用 PublishFlow 上传目录中的文件。")
    video_dir = settings.video_dir.resolve()
    candidate = (settings.data_dir / relative).resolve()
    try:
        candidate.relative_to(video_dir)
    except ValueError as exc:
        raise VideoError("视频路径越界，已拒绝访问。") from exc
    if not candidate.is_file():
        raise VideoError("视频文件不存在，请重新上传。")
    return candidate


def _run(command: list[str], timeout: int) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise VideoError("视频工具未安装或路径配置错误。") from exc
    except subprocess.TimeoutExpired as exc:
        raise VideoError("视频处理超时，请检查文件或提高处理超时时间。") from exc


def _probe_with_ffmpeg(path: Path) -> dict:
    result = _run([ffmpeg_executable(), "-hide_banner", "-nostdin", "-i", str(path)], 60)
    output = f"{result.stdout}\n{result.stderr}"
    duration_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", output)
    video_match = re.search(
        r"Stream[^\n]*Video:\s*([^\n,]+),[^\n]*?\b(\d{2,5})x(\d{2,5})\b", output
    )
    if not duration_match or not video_match:
        raise VideoError("无法识别视频时长或画面尺寸，请确认文件为有效视频。")
    hours, minutes, seconds = duration_match.groups()
    return {
        "duration": int(hours) * 3600 + int(minutes) * 60 + math.ceil(float(seconds)),
        "width": int(video_match.group(2)),
        "height": int(video_match.group(3)),
        "codec": video_match.group(1).strip(),
    }


def probe_video(stored_path: str) -> VideoMetadata:
    path = resolve_video_path(stored_path)
    settings = get_settings()
    ffprobe = settings.ffprobe_bin or shutil.which("ffprobe")
    if ffprobe:
        result = _run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=codec_type,codec_name,width,height",
                "-of",
                "json",
                str(path),
            ],
            60,
        )
        if result.returncode != 0:
            raise VideoError("ffprobe 无法读取该视频，请检查文件是否完整。")
        try:
            payload = json.loads(result.stdout)
            streams = payload.get("streams", [])
            video = next(stream for stream in streams if stream.get("codec_type") == "video")
            duration = math.ceil(float(payload["format"]["duration"]))
            width, height = int(video["width"]), int(video["height"])
            codec = str(video.get("codec_name", ""))
        except (ValueError, KeyError, TypeError, StopIteration) as exc:
            raise VideoError("视频缺少可读取的画面或时长信息。") from exc
    else:
        metadata = _probe_with_ffmpeg(path)
        duration, width, height, codec = (
            metadata["duration"],
            metadata["width"],
            metadata["height"],
            metadata["codec"],
        )
    if duration <= 0 or width <= 0 or height <= 0:
        raise VideoError("视频时长或画面尺寸无效。")
    return VideoMetadata(
        video_path=Path(stored_path).as_posix(),
        duration=duration,
        width=width,
        height=height,
        size_bytes=path.stat().st_size,
        codec=codec,
    )


def validate_video(stored_path: str) -> VideoMetadata:
    metadata = probe_video(stored_path)
    settings = get_settings()
    if metadata.size_bytes > settings.max_video_upload_mb * 1024 * 1024:
        raise VideoError(f"视频不能超过 {settings.max_video_upload_mb} MB。")
    if metadata.duration > settings.max_video_duration_seconds:
        raise VideoError(f"视频时长不能超过 {settings.max_video_duration_seconds // 60} 分钟。")
    return metadata


def transcode_video(stored_path: str) -> VideoMetadata:
    source = resolve_video_path(stored_path)
    validate_video(stored_path)
    output = get_settings().video_dir / f"transcoded-{uuid.uuid4().hex}.mp4"
    command = [
        ffmpeg_executable(),
        "-nostdin",
        "-y",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-map_metadata",
        "-1",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-vf",
        "scale='min(1920,iw)':-2",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(output),
    ]
    try:
        result = _run(command, get_settings().video_transcode_timeout_seconds)
        if result.returncode != 0 or not output.exists():
            raise VideoError("视频转码失败，请检查编码、磁盘空间或 ffmpeg 配置。")
        return validate_video(f"videos/{output.name}")
    except Exception:
        output.unlink(missing_ok=True)
        raise


def create_video_cover(stored_path: str, title: str, at_seconds: float | None = None) -> str:
    metadata = validate_video(stored_path)
    source = resolve_video_path(stored_path)
    timestamp = min(1.0, metadata.duration / 2) if at_seconds is None else at_seconds
    if timestamp >= metadata.duration:
        raise VideoError("抽帧时间必须早于视频结束时间。")
    frame = get_settings().upload_dir / f"video-frame-{uuid.uuid4().hex}.jpg"
    try:
        result = _run(
            [
                ffmpeg_executable(),
                "-nostdin",
                "-y",
                "-ss",
                str(timestamp),
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                "-update",
                "1",
                str(frame),
            ],
            120,
        )
        if result.returncode != 0 or not frame.exists():
            raise VideoError("视频抽帧失败，请尝试其他时间点。")
        return create_cover(title, background=frame)
    finally:
        frame.unlink(missing_ok=True)
