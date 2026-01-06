from edubag import config  # noqa: F401

from pathlib import Path
from typing import List, Annotated
import typer

from loguru import logger
from rich.progress import track


from edubag.albert.roster import AlbertRoster
from edubag.gradescope.roster import GradescopeRoster
from edubag.gradescope.scoresheet import (
    Scoresheet,
    VersionedScoresheet,
    SectionedScoresheet,
)
from edubag.brightspace.gradebook import Gradebook

from edubag import app as main_app

# Create a local Typer app for gradescope subcommands
app = typer.Typer(help="Gradescope management commands")


@app.command("gs2bs")
def gradescope_scores_file_to_brightspace_gradebook_csv(
    input: Annotated[
        Path, typer.Argument(help="Path to the Gradescope scores zip or CSV file.")
    ],
    output: Annotated[
        Path, typer.Argument(help="Path to the output Brightspace gradebook CSV file.")
    ] = None,
    by_section: Annotated[
        bool, typer.Option(help="Save separate files for each section.")
    ] = False,
):
    """Convert a Gradescope scores file to a Brightspace gradebook CSV file.

    `input` can be either a zip file containing versioned assignment scores
    or a CSV file for unversioned assignments.

    If no `output` path is provided, it is derived from the `input` path
    by replacing `config.RAW_DATA_DIR/gradescope/grades` with
    `config.INTERIM_DATA_DIR/brightspace/grades`

    If `by_section` is True, separate gradebook files are created for each section.

    """
    if input.name.endswith("_Version_Set_Scores.zip"):
        scoresheet = VersionedScoresheet.from_zip(input)
    elif input.name.endswith("_scores.csv"):
        scoresheet = Scoresheet.from_csv(input)
    else:
        raise ValueError("Input file must be a Gradescope scores zip or CSV file.")
    if output is None:
        relative_path = input.resolve().relative_to(
            config.RAW_DATA_DIR / "gradescope" / "grades"
        )
        output = (
            config.INTERIM_DATA_DIR
            / "brightspace"
            / "grades"
            / relative_path.with_stem(scoresheet.name.replace(" ", "_"))
            .with_suffix(".csv")        
        )
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


# Register the gradescope app as a subcommand with the main app
main_app.add_typer(app, name="gradescope")
