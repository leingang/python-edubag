from pathlib import Path
from typing import Annotated, Optional
import sys
import xml.etree.ElementTree as ET

from loguru import logger
import typer

from edubag import app as main_app
from edubag.albert.roster import AlbertRoster
from edubag.gmail.filters import generate_filter_xml

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
        typer.Option(help="Path to save the Gmail filter XML file. If not set, output to STDOUT."),
    ] = None,
):
    """Create a Gmail filter to label senders from class roster(s).

    Accepts one or more Albert roster Excel files and generates a Gmail filter XML file
    that can be imported into Gmail to automatically label emails from students on the roster(s).

    If no output path is specified, the filter will be printed to STDOUT.
    """
    # Load all rosters
    rosters = []
    for path in roster_paths:
        roster = AlbertRoster.from_xls(path)
        rosters.append(roster)
        logger.info(f"Loaded roster from {path}")

    # Generate the filter XML
    feed = generate_filter_xml(rosters, label=label)

    if output is None:
        # Write to STDOUT
        tree = ET.ElementTree(feed)
        ET.indent(tree, space="    ", level=0)
        tree.write(sys.stdout.buffer, encoding="UTF-8", xml_declaration=True)
    else:
        # Write to file
        output.parent.mkdir(parents=True, exist_ok=True)
        tree = ET.ElementTree(feed)
        ET.indent(tree, space="    ", level=0)
        tree.write(output, encoding="UTF-8", xml_declaration=True)
        logger.info(f"Gmail filter XML file saved to {output}")


# Register the gmail app as a subcommand with the main app
main_app.add_typer(app, name="gmail")
