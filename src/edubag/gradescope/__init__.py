from pathlib import Path
from typing import Annotated

import typer
from loguru import logger

from edubag import app as main_app
from edubag.albert.roster import AlbertRoster
from edubag.brightspace.gradebook import Gradebook
from edubag.gradescope.roster import GradescopeRoster
from edubag.gradescope.scoresheet import (
    Scoresheet,
    SectionedScoresheet,
    VersionedScoresheet,
)

from .client import authenticate as client_authenticate
from .client import fetch_class_details as client_fetch_class_details
from .client import sync_roster as client_sync_roster

# Create a local Typer app for gradescope subcommands
app = typer.Typer(help="Gradescope management commands")


@app.command("gs2bs")
def gradescope_scores_file_to_brightspace_gradebook_csv(
    input: Annotated[
        Path, typer.Argument(help="Path to the Gradescope scores zip or CSV file.")
    ],
    output: Annotated[
        Path | None,
        typer.Argument(help="Path to the output Brightspace gradebook CSV file."),
    ] = None,
    by_section: Annotated[
        bool, typer.Option(help="Save separate files for each section.")
    ] = False,
):
    """Convert a Gradescope scores file to a Brightspace gradebook CSV file.

    `input` can be either a zip file containing versioned assignment scores
    or a CSV file for unversioned assignments.

    If no `output` path is provided, the output file is created in the same
    directory as the input file, with spaces in the filename replaced by
    underscores and the suffix changed to `.csv`.

    If `by_section` is True, separate gradebook files are created for each section.

    """
    if input.name.endswith("_Version_Set_Scores.zip"):
        scoresheet = VersionedScoresheet.from_zip(input)
    elif input.name.endswith("_scores.csv"):
        scoresheet = Scoresheet.from_csv(input)
    else:
        raise ValueError("Input file must be a Gradescope scores zip or CSV file.")
    if output is None:
        output = input.with_name(scoresheet.name.replace(" ", "_")).with_suffix(".csv")
    output.parent.mkdir(parents=True, exist_ok=True)
    if by_section:
        # Use SectionedScoresheet to split by section (handles NaN students gracefully)
        sectioned = SectionedScoresheet(name=scoresheet.name, scores=scoresheet.scores)
        sections_dict = sectioned.by_section()
        for section, section_scoresheet in sections_dict.items():
            gradebook = Gradebook.from_gradescope_scoresheet(section_scoresheet)
            section_output = output.with_stem(f"{output.stem}_section_{section}")
            logger.info(
                f"Writing Brightspace gradebook for section {section} to {section_output}"
            )
            gradebook.to_csv(section_output)
    else:
        gradebook = Gradebook.from_gradescope_scoresheet(scoresheet)
        logger.debug(f"Writing Brightspace gradebook to {output}")
        gradebook.to_csv(output)
    return


# Nested Typer app for web client automation
client_app = typer.Typer(help="Automate Gradescope web client interactions")


@client_app.command()
def authenticate(
    base_url: Annotated[
        str | None, typer.Option(help="Override Gradescope base URL")
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
    """Open Gradescope for login and persist authentication state."""
    ok = client_authenticate(
        base_url=base_url,
        auth_state_path=auth_state_path,
        headless=headless,
    )
    if ok:
        typer.echo("Authentication state saved.")
    else:
        raise typer.Exit(code=1)


@client_app.command("sync-roster")
def sync_roster(
    course: Annotated[
        str, typer.Argument(help="Gradescope course ID or URL to the course home page")
    ],
    notify: Annotated[bool, typer.Option(help="Notify added users")] = True,
    headless: Annotated[
        bool,
        typer.Option(
            "--headless/--headed",
            help="Run browser headless (for automation) or headed (for debugging)",
        ),
    ] = True,
    base_url: Annotated[
        str | None, typer.Option(help="Override Gradescope base URL")
    ] = None,
    auth_state_path: Annotated[
        Path | None, typer.Option(help="Path to stored auth state JSON")
    ] = None,
) -> None:
    """Synchronize the course roster with the linked LMS."""
    ok = client_sync_roster(
        course=course,
        notify=notify,
        headless=headless,
        base_url=base_url,
        auth_state_path=auth_state_path,
    )
    if ok:
        typer.echo("Roster sync completed successfully.")
    else:
        raise typer.Exit(code=1)


@client_app.command("fetch-details")
def fetch_class_details(
    course_name: Annotated[str, typer.Argument(help="Course name to match in Gradescope")],
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
        str | None, typer.Option(help="Override Gradescope base URL")
    ] = None,
    auth_state_path: Annotated[
        Path | None, typer.Option(help="Path to stored auth state JSON")
    ] = None,
) -> None:
    """Fetch class details for a course offering and optionally save."""
    import json

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


# Register the gradescope app as a subcommand with the main app
main_app.add_typer(app, name="gradescope")
app.add_typer(client_app, name="client")
