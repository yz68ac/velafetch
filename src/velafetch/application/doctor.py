"""Simple checks used by the ``doctor`` command."""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path

import httpx


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    name: str
    status: str
    message: str


@dataclass(frozen=True, slots=True)
class DoctorReport:
    checks: tuple[DoctorCheck, ...]

    @property
    def ok(self) -> bool:
        return all(check.status != "failed" for check in self.checks)


class DoctorService:
    async def run(
        self,
        *,
        ffmpeg_path: Path | None,
        check_network: bool,
        timeout: float,
        proxy: str | None,
    ) -> DoctorReport:
        checks = [await self._check_ffmpeg(ffmpeg_path)]
        checks.append(await self._check_network(check_network, timeout, proxy))
        return DoctorReport(tuple(checks))

    @staticmethod
    async def _check_ffmpeg(configured: Path | None) -> DoctorCheck:
        executable = str(configured) if configured else shutil.which("ffmpeg")
        if not executable:
            return DoctorCheck("ffmpeg", "failed", "FFmpeg was not found.")
        try:
            process = await asyncio.create_subprocess_exec(
                executable,
                "-version",
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(process.wait(), timeout=5)
        except (OSError, TimeoutError):
            return DoctorCheck("ffmpeg", "failed", "FFmpeg could not be started.")
        if process.returncode != 0:
            return DoctorCheck("ffmpeg", "failed", "FFmpeg returned an error.")
        return DoctorCheck("ffmpeg", "ok", "FFmpeg is available.")

    @staticmethod
    async def _check_network(
        enabled: bool,
        timeout: float,
        proxy: str | None,
    ) -> DoctorCheck:
        if not enabled:
            return DoctorCheck("network", "skipped", "Use --network to run this check.")
        try:
            async with httpx.AsyncClient(timeout=timeout, proxy=proxy, trust_env=False) as client:
                response = await client.get("https://api.bilibili.com/x/web-interface/nav")
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or payload.get("code") != 0:
                    raise ValueError
        except (httpx.HTTPError, ValueError):
            return DoctorCheck("network", "failed", "Bilibili is not reachable.")
        return DoctorCheck("network", "ok", "Bilibili is reachable.")
