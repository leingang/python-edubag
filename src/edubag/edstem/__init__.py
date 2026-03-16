from pathlib import Path
from typing import Annotated

import typer

from edubag import app as main_app

from .client import EdstemClient

# Create edstem subcommands app
app = typer.Typer(help="EdSTEM management commands")

# Nested Typer app for web client automation
client_app = typer.Typer(help="Automate EdSTEM web client interactions")


@client_app.command()
def authenticate(
    base_url: Annotated[
        str | None, typer.Option(help="Override EdSTEM base URL")
    ] = None,
    auth_state_path: Annotated[
        Path | None, typer.Option(help="Path to save auth state JSON")
    ] = None,
    headless: Annotated[
        bool,
        typer.Option(
            "--headless/--headed",
            help="Run browser headless (for automation) or headed (for debugging)",
        ),
    ] = False,
) -> None:
    """Open EdSTEM for login and persist authentication state."""
    client = EdstemClient(base_url=base_url, auth_state_path=auth_state_path)
    try:
        client.authenticate(headless=headless)
        typer.echo("Authentication state saved.")
    except Exception as e:
        typer.echo(f"Authentication failed: {e}", err=True)
        raise typer.Exit(code=1)


@client_app.command("save-analytics")
def save_analytics(
    course: Annotated[str, typer.Argument(help="EdSTEM course ID")],
    save_dir: Annotated[
        Path | None, typer.Option(help="Target directory for the saved analytics file")
    ] = None,
    headless: Annotated[
        bool,
        typer.Option(
            "--headless/--headed",
            help="Run browser headless (for automation) or headed (for debugging)",
        ),
    ] = True,
    base_url: Annotated[
        str | None, typer.Option(help="Override EdSTEM base URL")
    ] = None,
    auth_state_path: Annotated[
        Path | None, typer.Option(help="Path to stored auth state JSON")
    ] = None,
) -> None:
    """Download the analytics CSV for an EdSTEM course."""
    client = EdstemClient(base_url=base_url, auth_state_path=auth_state_path)
    paths = client.save_analytics(
        course=course,
        save_dir=save_dir,
        headless=headless,
    )
    for path in paths:
        typer.echo(str(path))


# Optional underscore alias to match user muscle memory/examples
@client_app.command("save_analytics", hidden=True)
def save_analytics_alias(
    course: Annotated[str, typer.Argument(help="EdSTEM course ID")],
    save_dir: Annotated[
        Path | None, typer.Option(help="Target directory for the saved analytics file")
    ] = None,
    headless: Annotated[
        bool,
        typer.Option(
            "--headless/--headed",
            help="Run browser headless (for automation) or headed (for debugging)",
        ),
    ] = True,
    base_url: Annotated[
        str | None, typer.Option(help="Override EdSTEM base URL")
    ] = None,
    auth_state_path: Annotated[
        Path | None, typer.Option(help="Path to stored auth state JSON")
    ] = None,
) -> None:
    """Alias for save-analytics."""
    save_analytics(
        course=course,
        save_dir=save_dir,
        headless=headless,
        base_url=base_url,
        auth_state_path=auth_state_path,
    )


# Register the edstem app as a subcommand with the main app
main_app.add_typer(app, name="edstem")
app.add_typer(client_app, name="client")
