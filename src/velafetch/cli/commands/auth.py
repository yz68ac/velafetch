"""Local Bilibili authentication commands."""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Annotated, Any, TextIO, cast

import qrcode
import typer
from qrcode.constants import ERROR_CORRECT_M
from rich.console import Console
from rich.markup import escape
from rich.table import Table

import velafetch.cli.rendering as rendering
from velafetch.auth import AccountSummary, AuthStatus
from velafetch.cli.dependencies import AuthRunner, runtime_options
from velafetch.errors import AuthenticationError

_MAX_STDIN_CHARS = 16 * 1024 + 1


def _interactive_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _render_qr(value: str) -> None:
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, border=2)
    qr.add_data(value)
    qr.make(fit=True)
    printer = cast("Any", qr).print_ascii
    printer(out=cast("TextIO", sys.stdout), tty=True)


def _account_line(account: AccountSummary) -> str:
    return f"Logged in as {account.username} (UID {account.user_id})."


def _emit_status(status: AuthStatus, *, json_output: bool) -> None:
    if json_output:
        account = status.account
        typer.echo(
            json.dumps(
                {
                    "stored": status.stored,
                    "logged_in": status.logged_in,
                    "account": (
                        None
                        if account is None
                        else {
                            "user_id": account.user_id,
                            "username": account.username,
                            "vip_status": account.vip_status,
                            "vip_type": account.vip_type,
                        }
                    ),
                    "message": status.message,
                },
                ensure_ascii=False,
            )
        )
        return
    if status.account is None:
        typer.echo(status.message)
        return
    table = Table(title="Bilibili Login", show_header=False)
    table.add_column("Field", style="bold")
    table.add_column("Value")
    for name, value in (
        ("Stored", "yes" if status.stored else "no"),
        ("Logged in", "yes" if status.logged_in else "no"),
        ("UID", str(status.account.user_id)),
        ("Username", escape(status.account.username)),
        ("VIP status", str(status.account.vip_status)),
        ("VIP type", str(status.account.vip_type)),
    ):
        table.add_row(name, value)
    Console().print(table)
    if not status.logged_in:
        Console(stderr=True).print(f"[yellow]Warning:[/] {status.message}")


def register_auth_commands(cli: typer.Typer, service: AuthRunner) -> None:
    auth_cli = typer.Typer(help="Manage the local Bilibili login.", add_completion=False)

    @auth_cli.command()
    def login(context: typer.Context) -> None:
        """Log in by scanning a terminal QR code."""

        if not _interactive_terminal():
            rendering.emit_error(
                AuthenticationError("QR login requires an interactive terminal."),
                json_output=False,
            )
        options = runtime_options(context)
        try:
            account = asyncio.run(
                service.login(
                    timeout=options.timeout,
                    proxy=options.proxy,
                    render_qr=_render_qr,
                    report_status=lambda message: typer.echo(message, err=True),
                )
            )
            typer.echo(_account_line(account))
        except BaseException as error:
            rendering.emit_error(error, json_output=False)

    @auth_cli.command("import-cookie")
    def import_cookie(
        context: typer.Context,
        from_stdin: Annotated[
            bool,
            typer.Option("--stdin", help="Read the Cookie from standard input."),
        ] = False,
    ) -> None:
        """Validate and store a Cookie without putting it in command history."""

        options = runtime_options(context)
        try:
            raw = (
                sys.stdin.read(_MAX_STDIN_CHARS)
                if from_stdin
                else typer.prompt(
                    "Cookie",
                    hide_input=True,
                )
            )
            account = asyncio.run(
                service.import_cookie(raw, timeout=options.timeout, proxy=options.proxy)
            )
            typer.echo(_account_line(account))
        except BaseException as error:
            rendering.emit_error(error, json_output=False)

    @auth_cli.command()
    def status(
        context: typer.Context,
        json_output: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
    ) -> None:
        """Validate the locally stored login."""

        options = runtime_options(context)
        try:
            result = asyncio.run(service.status(timeout=options.timeout, proxy=options.proxy))
            _emit_status(result, json_output=json_output)
            if result.stored and not result.logged_in:
                raise typer.Exit(1)
        except typer.Exit:
            raise
        except BaseException as error:
            rendering.emit_error(error, json_output=json_output)

    @auth_cli.command()
    def logout() -> None:
        """Remove only the local credential file."""

        try:
            removed = service.logout()
            typer.echo(
                "Local Bilibili login removed." if removed else "No Bilibili login is stored."
            )
        except BaseException as error:
            rendering.emit_error(error, json_output=False)

    cli.add_typer(auth_cli, name="auth")
    _ = login, import_cookie, status, logout
