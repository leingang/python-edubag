from pathlib import Path
from typing import Annotated, Optional

from loguru import logger
import typer

from edubag import app as main_app
from edubag.albert.roster import AlbertRoster
from edubag.gmail.filters import filter_from_rosters

# Create a local Typer app for gmail subcommands
app = typer.Typer(help="Gmail filter management commands")


@app.command("filter-from-roster")
def filter_from_roster_command(
    roster_paths: Annotated[
        list[Path], typer.Argument(help="One or more Albert roster XLS files")
    ],
    label: Annotated[
        Optional[str],
        typer.Option(help="Label to apply to emails. If not set, derived from roster."),
    ] = None,
    output: Annotated[
        Optional[Path],
        typer.Option(help="Path to save the Gmail filter XML file."),
    ] = None,
):
    """Create a Gmail filter to label senders from class roster(s).

    Accepts one or more Albert roster Excel files and generates a Gmail filter XML file
    that can be imported into Gmail to automatically label emails from students on the roster(s).

    If no output path is specified, the filter will be saved to the processed data directory.
    """
    # Load all rosters
    rosters = []
    for path in roster_paths:
        roster = AlbertRoster.from_xls(path)
        rosters.append(roster)
        logger.info(f"Loaded roster from {path}")

    # Generate the filter
    filter_from_rosters(rosters, label=label, output=output)

    if output:
        logger.info(f"Gmail filter XML file saved to {output}")
    else:
        logger.info("Gmail filter XML file saved to processed data directory")


# Register the gmail app as a subcommand with the main app
main_app.add_typer(app, name="gmail")
