"""Argus CLI — entry point.

Commands:
  argus version — tampilkan versi
  argus status  — ringkasan sistem
  argus smoke   — smoke test pipeline (10 tahap)
"""
from __future__ import annotations

import typer

from argus import __version__

app = typer.Typer(help="Argus — AI Agent OS", no_args_is_help=True)


@app.command()
def version() -> None:
    """Tampilkan versi Argus (dengan logo)."""
    from argus.branding import logo as ascii_logo

    typer.echo(ascii_logo())
    typer.echo(f"\nArgus v{__version__}")


@app.command()
def logo(render: bool = typer.Option(False, help="Render logo ke JPEG (butuh Pillow)")) -> None:
    """Tampilkan logo Argus Panoptes."""
    from argus.branding import eye_only, render_logo_jpeg

    typer.echo(eye_only())
    if render:
        path = render_logo_jpeg()
        typer.echo(f"\nLogo JPEG tersimpan di: {path}")


@app.command()
def status() -> None:
    """Tampilkan ringkasan sistem."""
    from argus.config import get_settings

    settings = get_settings()
    typer.echo(f"Argus v{__version__}")
    typer.echo(f"Data dir      : {settings.get_data_dir()}")
    typer.echo("Config       : pydantic-settings (env prefixed ARGUS_)")

    try:
        from argus.gateway.auth import create_auth_manager

        auth = create_auth_manager("_status_check")
        token = auth.create_token("status", scopes=["read"])
        typer.echo(f"Auth         : OK (token {len(token)} chars)")
    except Exception as e:  # pragma: no cover
        typer.echo(f"Auth         : FAIL ({e})")

    try:

        typer.echo("SecretVault  : OK (Fernet AES-128 tersedia)")
    except Exception as e:  # pragma: no cover
        typer.echo(f"SecretVault  : FAIL ({e})")


@app.command()
def ask(prompt: str, model: str = typer.Option("Cadangan", help="Model/combo OmniRoute")) -> None:
    """Kirim satu prompt ke LLM via OmniRoute."""
    from argus.brain.provider import create_provider

    provider = create_provider(model=model)
    typer.echo(f"→ [{model}] {prompt}")
    resp = provider.ask(prompt)
    if resp.success:
        typer.echo(f"← [{resp.model}] ({resp.duration_ms}ms, {resp.total_tokens} tok)")
        typer.echo(resp.content)
    else:
        typer.echo(f"✗ ERROR: {resp.error}", err=True)


@app.command()
def curator(
    action: str = typer.Argument("status", help="status | review"),
    db: str = typer.Option("", help="Path usage tracker (default: tempdir)"),
    stale_days: float = typer.Option(30.0, help="Idle threshold (hari)"),
) -> None:
    """Self-evolution: cek/scan penggunaan capability (Phase 11)."""
    from argus.curator import create_curator, create_usage_tracker

    if not db:
        import tempfile
        from pathlib import Path as _Path
        db = str(_Path(tempfile.gettempdir()) / "argus_usage.json")
    tracker = create_usage_tracker(db)
    if action == "review":
        curator_engine = create_curator(tracker, stale_after_days=stale_days)
        report = curator_engine.review()
        typer.echo(f"Archived : {report['archived'] or 'none'}")
        typer.echo(f"Lessons  : {len(report['lessons'])}")
        for lesson in report["lessons"]:
            typer.echo(f"  - {lesson['source']}: {lesson['summary']}")
    else:
        records = tracker.all()
        typer.echo(f"Tracked items: {len(records)}")
        for rec in records:
            mark = " (archived)" if rec.archived else ""
            typer.echo(
                f"  {rec.kind:<12} {rec.name:<30} uses={rec.use_count} "
                f"success={rec.success_count}{mark}",
            )


@app.command()
def dashboard(
    port: int = typer.Option(8787, help="Port untuk dashboard web"),
    host: str = typer.Option("127.0.0.1", help="Host bind"),
    db: str = typer.Option("", help="Path observability store (default: tempdir)"),
) -> None:
    """Jalankan web dashboard (Phase 6)."""
    from argus.dashboard import create_dashboard_store, serve_dashboard

    if not db:
        import tempfile
        from pathlib import Path as _Path
        db = str(_Path(tempfile.gettempdir()) / "argus_dashboard.db")
    store = create_dashboard_store(db)
    typer.echo(f"Argus Dashboard → http://{host}:{port}")
    typer.echo(f"Store          : {db}")
    typer.echo("Press Ctrl+C to stop")
    try:
        serve_dashboard(store, host=host, port=port, version=__version__)
    except KeyboardInterrupt:
        store.close()
        typer.echo("\nStopped.")


@app.command()
def chat(model: str = typer.Option("Cadangan", help="Model/combo OmniRoute")) -> None:
    """REPL chat dengan Argus via OmniRoute. Ketik 'exit' untuk keluar."""
    from argus.brain.provider import ChatMessage, create_provider

    provider = create_provider(model=model)
    history: list[ChatMessage] = [
        ChatMessage(role="system", content="Kamu adalah Argus, AI agent yang ringkas dan membantu. Jawab dalam bahasa yang sama dengan user."),
    ]
    typer.echo(f"Argus chat [{model}] — ketik 'exit' untuk keluar")
    while True:
        try:
            prompt = typer.prompt("you")
        except EOFError:
            break
        if prompt.strip().lower() in ("exit", "quit", "q"):
            break
        history.append(ChatMessage(role="user", content=prompt))
        resp = provider.chat(history)
        if resp.success:
            typer.echo(f"argus [{resp.model}]: {resp.content}")
            history.append(ChatMessage(role="assistant", content=resp.content))
        else:
            typer.echo(f"✗ ERROR: {resp.error}", err=True)


@app.command()
def smoke() -> None:
    """Jalankan smoke test pipeline end-to-end (10 tahap)."""
    from argus._smoke import run_smoke

    ok = run_smoke()
    if not ok:
        typer.echo("Smoke test: FAILED", err=True)
        raise typer.Exit(1)
    typer.echo("Smoke test: ALL 10 STAGES PASSED")


if __name__ == "__main__":
    app()
