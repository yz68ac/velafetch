"""Application services used by the CLI."""

from velafetch.application.assets import SubtitleOutputFormat
from velafetch.application.doctor import DoctorCheck, DoctorReport, DoctorService
from velafetch.application.download import (
    DownloadItemResult,
    DownloadResult,
    DownloadService,
    DownloadStatus,
    ProgressCallback,
    ProgressUpdate,
)
from velafetch.application.ffmpeg import FfmpegExecutable, FfmpegSource, resolve_ffmpeg
from velafetch.application.media import MediaApplicationService
from velafetch.application.naming import safe_filename

__all__ = [
    "DoctorCheck",
    "DoctorReport",
    "DoctorService",
    "DownloadItemResult",
    "DownloadResult",
    "DownloadService",
    "DownloadStatus",
    "FfmpegExecutable",
    "FfmpegSource",
    "MediaApplicationService",
    "ProgressCallback",
    "ProgressUpdate",
    "SubtitleOutputFormat",
    "safe_filename",
    "resolve_ffmpeg",
]
