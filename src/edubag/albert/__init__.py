import json
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.progress import track

from edubag import app as main_app
from edubag.gradescope.roster import GradescopeRoster

from .client import (
    authenticate as client_authenticate,
)
from .client import (
    fetch_and_save_rosters as client_fetch_and_save_rosters,
)
from .client import (
    fetch_class_details as client_fetch_class_details,
)
from .roster import AlbertRoster

# Create a local Typer app for albert subcommands
app = typer.Typer(help="Albert roster management commands")


@app.command()
def xls2csv(
    paths: Annotated[list[Path], typer.Argument(help="One or more roster XLS files")],
    output: Annotated[Path | None, typer.Option(help="Output CSV file path")] = None,
    save: Annotated[
        bool,
        typer.Option(help="Save the CSV file to disk instead of printing to stdout"),
    ] = False,
):
    """Convert one or more Albert roster Excel files to CSV.

    If multiple input paths are provided and `output` is a directory, each CSV is written into
    that directory using the roster's `pathstem` for the filename. If `output` is omitted, the
    default behavior is used per file (derive the output path under interim data or stream to
    stdout when `save` is False).
    """

    # If an output path is provided, ensure it is a directory when multiple inputs are given.
    if output and len(paths) > 1 and not output.is_dir():
        raise typer.BadParameter(
            "When providing multiple input files, --output must be a directory."
        )

    for p in paths:
        roster = AlbertRoster.from_xls(p)
        effective_output = output

        # If the caller passed a directory, build a file path within it.
        if effective_output and effective_output.is_dir():
            effective_output = (
                effective_output / p.with_stem(roster.pathstem).with_suffix(".csv").name
            )

        if effective_output:
            save = True

        if save:
            if effective_output is None:
                raise typer.BadParameter("Please specify --output when using --save.")
            effective_output.parent.mkdir(parents=True, exist_ok=True)
            typer.echo(f"Writing CSV roster to {effective_output}")
            roster.to_csv(effective_output)
        else:
            roster.to_csv(sys.stdout)


@app.command("xls2gs")
def albert_xls_roster_to_gradescope_csv_roster(
    paths: Annotated[
        list[Path],
        typer.Argument(
            help="Path(s) to one or more Albert roster files in Excel format."
        ),
    ],
    output_path: Annotated[
        Path, typer.Argument(help="Save a Gradescope roster CSV file to this path.")
    ],
    read_section: Annotated[
        bool,
        typer.Option(
            help="Read the section number from the Albert roster file and add it to the Gradescope roster."
        ),
    ] = True,
    obscure_email: Annotated[
        bool,
        typer.Option(
            help="Change the students' email addresses so they don't know they're in the course."
        ),
    ] = False,
):
    """Merge one or more Albert roster files in "Excel" format into a single Gradescope roster file."""
    merged_roster = GradescopeRoster.merge(
        list(
            [
                GradescopeRoster.from_albert_roster(
                    AlbertRoster.from_xls(p), read_section=read_section
                )
                for p in track(paths, description="Processing Albert roster files")
            ]
        )
    )
    if obscure_email:
        merged_roster.obscure_emails()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged_roster.to_csv(output_path)


# Nested Typer app for web client automation
client_app = typer.Typer(help="Automate Albert web client interactions")


@client_app.command()
def authenticate(
    base_url: Annotated[
        str | None, typer.Option(help="Override Albert base URL")
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
    """Open Albert for login and persist authentication state."""
    ok = client_authenticate(
        base_url=base_url,
        auth_state_path=auth_state_path,
        headless=headless,
    )
    if ok:
        typer.echo("Authentication state saved.")
    else:
        raise typer.Exit(code=1)


@client_app.command("fetch-rosters")
def fetch_rosters(
    course_name: Annotated[str, typer.Argument(help="Course name to match in Albert")],
    term: Annotated[str, typer.Argument(help="Term, e.g., 'Fall 2025'")],
    save_path: Annotated[
        Path | None, typer.Option(help="Directory to save roster files")
    ] = None,
    headless: Annotated[
        bool,
        typer.Option(
            "--headless/--headed",
            help="Run browser headless (for automation) or headed (for debugging)",
        ),
    ] = True,
    base_url: Annotated[
        str | None, typer.Option(help="Override Albert base URL")
    ] = None,
    auth_state_path: Annotated[
        Path | None, typer.Option(help="Path to stored auth state JSON")
    ] = None,
) -> None:
    """Fetch class rosters for a course offering and save files."""
    paths = client_fetch_and_save_rosters(
        course_name=course_name,
        term=term,
        save_path=save_path,
        headless=headless,
        base_url=base_url,
        auth_state_path=auth_state_path,
    )
    for p in paths:
        typer.echo(str(p))


@client_app.command("fetch-details")
def fetch_class_details(
    course_name: Annotated[str, typer.Argument(help="Course name to match in Albert")],
    term: Annotated[str, typer.Argument(help="Term, e.g., 'Fall 2025'")],
    output: Annotated[Path | None, typer.Option(help="Path to save output in")] = None,
    headless: Annotated[
        bool,
        typer.Option(
            "--headless/--headed",
            help="Run browser headless (for automation) or headed (for debugging)",
        ),
    ] = True,
    base_url: Annotated[
        str | None, typer.Option(help="Override Albert base URL")
    ] = None,
    auth_state_path: Annotated[
        Path | None, typer.Option(help="Path to stored auth state JSON")
    ] = None,
) -> None:
    """Fetch class details for a course offering and optionally save."""
    result = client_fetch_class_details(
        course_name=course_name,
        term=term,
        headless=headless,
        output=output,
        base_url=base_url,
        auth_state_path=auth_state_path,
    )

    # If output is None, pretty-print to STDOUT
    if output is None:
        typer.echo(json.dumps(result, indent=2))


# Register the albert app as a subcommand with the main app
main_app.add_typer(app, name="albert")
app.add_typer(client_app, name="client")
