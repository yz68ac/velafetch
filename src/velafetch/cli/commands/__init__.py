"""Registration helpers for the public CLI commands."""

from velafetch.cli.commands.doctor import register_doctor_command
from velafetch.cli.commands.download import register_download_command
from velafetch.cli.commands.inspection import register_inspection_commands

__all__ = [
    "register_doctor_command",
    "register_download_command",
    "register_inspection_commands",
]
