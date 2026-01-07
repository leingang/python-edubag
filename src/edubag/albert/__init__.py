from pathlib import Path
import sys
from typing import List, Optional, Annotated

from rich.progress import track

from edubag import config
from edubag.gradescope.roster import GradescopeRoster
from .roster import AlbertRoster

import typer
from edubag import app as main_app

# Create a local Typer app for albert subcommands
app = typer.Typer(help="Albert roster management commands")


@app.command()
def xls2csv(
    paths: Annotated[list[Path], typer.Argument(help="One or more roster XLS files")],
    output: Annotated[Optional[Path], typer.Option(help="Output CSV file path")] = None,
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
                # construct output path based on input path
                # If the input path comes from data/raw/albert/roster/.../foo.XLS,
                # the output path should go to data/interim/albert/roster/.../pathstem.csv
                # where `pathstem` is the roster's pathstem property.
                try:
                    relative_path = p.resolve().relative_to(
                        config.RAW_DATA_DIR / "albert" / "roster"
                    )
                    effective_output = (
                        config.INTERIM_DATA_DIR
                        / "albert"
                        / "roster"
                        / relative_path.with_stem(roster.pathstem).with_suffix(".csv")
                    )
                    effective_output.parent.mkdir(parents=True, exist_ok=True)
                    typer.echo(f"Writing CSV roster to {effective_output}")
                except ValueError:
                    raise typer.BadParameter(
                        f"Cannot derive output path for input file {p}. "
                        "Please specify an explicit --output path."
                    )
            else:
                effective_output.parent.mkdir(parents=True, exist_ok=True)
                typer.echo(f"Writing CSV roster to {effective_output}")
            roster.to_csv(effective_output)
        else:
            roster.to_csv(sys.stdout)


@app.command("xls2gs")
def albert_xls_roster_to_gradescope_csv_roster(
    paths: Annotated[
        List[Path],
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


# Register the albert app as a subcommand with the main app
main_app.add_typer(app, name="albert")
