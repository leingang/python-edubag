from pathlib import Path
from typing import Annotated, List

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

from .client import GradescopeClient

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


@app.command("bs2gs")
def add_sections_to_roster_from_brightspace(
    roster_csv: Annotated[
        Path, typer.Argument(help="Path to the Gradescope roster CSV file.")
    ],
    brightspace_csv: Annotated[
        Path, typer.Argument(help="Path to the Brightspace gradebook CSV file.")
    ],
    output_csv: Annotated[
        Path | None,
        typer.Argument(
            help="Path to the output Gradescope roster CSV file with sections added."
        ),
    ] = None,
    skip_constant: Annotated[
        bool,
        typer.Option(
            "--skip-constant/--keep-constant",
            help="Skip columns with only one unique value.",
        ),
    ] = True,
) -> List[Path]:
    """Add section information to a Gradescope roster from a Brightspace gradebook CSV.

    The output CSV file can be specified with `output_csv`. If not provided,
    the output file is created in the same directory as the input roster file,
    with '_with_sections' appended to the stem of the filename.

    Args:
        roster_csv (Path): Path to the Gradescope roster CSV file.
        brightspace_csv (Path): Path to the Brightspace gradebook CSV file.
        output_csv (Path | None): Path to the output Gradescope roster CSV file.
        skip_constant (bool): Skip columns with only one unique value.

    Returns:
        List[Path]: List containing the path to the output CSV file.
    """
    # Load the Gradescope roster
    gs_roster = GradescopeRoster.from_csv(roster_csv)

    # Load the Brightspace gradebook
    bs_gradebook = Gradebook.from_csv(brightspace_csv)

    gs_roster.update_sections_from_brightspace_gradebook(
        bs_gradebook, skip_constant=skip_constant
    )

    # Save the updated roster with sections
    if output_csv is None:
        output_csv = roster_csv.with_stem(f"{roster_csv.stem}_with_sections")
    try:
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        gs_roster.to_csv(output_csv)
        logger.success(f"Saved updated Gradescope roster with sections to {output_csv}")
        return [output_csv]
    except Exception as e:
        logger.error(f"Failed to save updated Gradescope roster: {e}")
        return []


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
    client = GradescopeClient(base_url=base_url, auth_state_path=auth_state_path)
    try:
        client.authenticate(headless=headless)
        typer.echo("Authentication state saved.")
    except Exception as e:
        typer.echo(f"Authentication failed: {e}", err=True)
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
    client = GradescopeClient(base_url=base_url, auth_state_path=auth_state_path)
    try:
        client.sync_roster(
            course=course,
            notify=notify,
            headless=headless,
        )
        typer.echo("Roster sync completed successfully.")
    except Exception as e:
        typer.echo(f"Roster sync failed: {e}", err=True)
        raise typer.Exit(code=1)


@client_app.command("fetch-details")
def fetch_class_details(
    course_name: Annotated[
        str, typer.Argument(help="Course name to match in Gradescope")
    ],
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

    client = GradescopeClient(base_url=base_url, auth_state_path=auth_state_path)
    result = client.fetch_class_details(
        course_name=course_name,
        term=term,
        headless=headless,
        output=output,
    )

    # If output is None, pretty-print to STDOUT
    if output is None:
        typer.echo(json.dumps(result, indent=2))


@client_app.command("save-roster")
def save_roster(
    course: Annotated[
        str, typer.Argument(help="Gradescope course ID or URL to the course home page")
    ],
    save_dir: Annotated[
        Path | None, typer.Option(help="Target directory for the saved roster file")
    ] = None,
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
    """Download the roster for a Gradescope course."""
    client = GradescopeClient(base_url=base_url, auth_state_path=auth_state_path)
    result_paths = client.save_roster(
        course=course,
        save_dir=save_dir,
        headless=headless,
    )
    for p in result_paths:
        typer.echo(f"Roster saved to {p}")


@client_app.command("send-roster")
def send_roster(
    course: Annotated[
        str, typer.Argument(help="Gradescope course ID or URL to the course home page")
    ],
    csv_path: Annotated[Path, typer.Argument(help="Path to the roster CSV file to upload")],
    notify: Annotated[
        bool, typer.Option(help="Notify users by email when added to the course")
    ] = False,
    role: Annotated[
        str,
        typer.Option(help="Role to add users as. Must be one of: Student, Instructor, TA, Reader"),
    ] = "Student",
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
    """Upload a roster CSV file to a Gradescope course.
    
    Users are added or updated based on the contents of the CSV file.
    For example, the file might include additional staff members to add to the course.
    Or it might contain section information to update existing students.    
    """
    client = GradescopeClient(base_url=base_url, auth_state_path=auth_state_path)
    try:
        client.send_roster(
            course=course,
            csv_path=csv_path,
            notify=notify,
            role=role,
            headless=headless,
        )
        typer.echo("Roster upload completed successfully.")
    except Exception as e:
        typer.echo(f"Roster upload failed: {e}", err=True)
        raise typer.Exit(code=1)


# Register the gradescope app as a subcommand with the main app
main_app.add_typer(app, name="gradescope")
app.add_typer(client_app, name="client")
