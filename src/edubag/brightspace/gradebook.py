import io
from pathlib import Path

import pandas as pd
from loguru import logger

from edubag.gradescope.scoresheet import Scoresheet as GradescopeScoresheet
from edubag.sources import DataSource

USERNAME_COLNAME = "Username"
EOL_COLNAME = "End-of-Line Indicator"
_LINE_DELIMITER = "#"


def strip_line_indicators(df: pd.DataFrame):
    """
    Strip the end-of-line indicators from a pandas DataFrame
    read from a Brightspace CSV gradebook.

    Brightspace prepends a pound symbol to the first entry
    in the CSV file, and an extra column to the end.
    This functions removes both.

    Args:
        df (pd.DataFrame): The DataFrame

    Returns: pd.DataFrame
    """
    df[df.columns[0]] = df[df.columns[0]].str.lstrip(_LINE_DELIMITER)
    del df[EOL_COLNAME]
    return df


def add_line_indicators(df: pd.DataFrame):
    """
    Add the Brightspace end-of-line indicators
    to prepare for writing to a file.

    Args:
        df (pd.DataFrame): The DataFrame

    Returns: None
    """
    df[df.columns[0]] = _LINE_DELIMITER + df[df.columns[0]].astype(str)
    df[EOL_COLNAME] = _LINE_DELIMITER


class Gradebook(DataSource):
    """A class gradebook fetched from Brightspace."""

    course: dict[str, str]
    grades: pd.DataFrame

    def __init__(self):
        # Initialize DataSource base and keep backward-compatible attributes
        super().__init__()
        self.grades = pd.DataFrame()

    def to_csv(self, path: Path):
        """
        Write a gradebook to a CSV file

        Args:
            path (pathlib.Path): Path to the file

        Returns: None
        """
        # Brightspace expects each line to start and end
        # with a '#'.
        df = self.grades
        add_line_indicators(df)
        df.to_csv(path, index=False)
        strip_line_indicators(df)

    @classmethod
    def from_csv(cls, path: Path) -> "Gradebook":
        """
        Create a gradebook from a downloaded CSV file.

        Args:
            path (pathlib.Path): Path to the file

        Returns:
            Gradebook: the gradebook object.

        To generate the Brightspace gradebook export CSV file:
        1. Go to your course on Brightspace.
        2. Click on "Grades" and "Enter Grades" if the gradebook is not already open.
        3. Click on the "Export" button.
        4. In the "User Details" block, make sure "Email" and "Section Membership" are checked.
           Check whatever grades you want exported.
        5. Click the "Export to CSV" button at the bottom of the page.
        6. Save the file (recommended path: `data/raw/brightspace/grades/<date>/`).
        """
        gb = cls()
        gb.grades = strip_line_indicators(pd.read_csv(path))
        # Keep DataSource.data in sync for aggregator/source usage
        gb.data = gb.grades.copy()
        gb.metadata = {
            "source": str(path),
            "type": "brightspace_gradebook_csv",
            "original_columns": list(gb.grades.columns),
        }
        return gb

    # DataSource interface: allow using Gradebook as a DataSource directly
    @classmethod
    def from_file(cls, path: Path) -> "Gradebook":
        return cls.from_csv(path)

    def resolve_identity(self, username_col: str = USERNAME_COLNAME) -> None:
        """Ensure Username column exists and set metadata.

        Brightspace export already contains `Username` and we strip leading '#'.
        """
        if USERNAME_COLNAME not in self.grades.columns:
            raise ValueError("Gradebook must have a 'Username' column")
        # Ensure DataSource.data stays aligned with grades
        self.data = self.grades.copy()
        self.metadata["username_col"] = username_col

    @classmethod
    def from_xls(cls, path: Path):
        """
        Create a gradebook from a downloaded XLS file.

        Args:
            path (pathlib.Path): Path to the file

        Returns:
            Gradebook: the gradebook object.
        """
        raise NotImplementedError

    @classmethod
    def from_gradescope_scoresheet(
        cls, scoresheet: GradescopeScoresheet, item_name: str | None = None
    ):
        """
        Create a  Gradebook from a Gradescope scoresheet.

        Args:
            scoresheet (gradescope.scoresheet.Scoresheet): The Gradescope scoresheet.
            item_name (str): The name of the grade item in Brightspace to add scores to.

        Returns:
            Gradebook: the gradebook object.
        """
        gb = cls()
        # Map the Gradescope scoresheet columns to Brightspace gradebook columns.
        # This mapping may need to be adjusted based on the actual column names.
        default_name = (
            f"{scoresheet.name} Points Grade <MaxScore: {scoresheet.scores['Max Points'].iloc[0]}>"
        )
        column_mapping = {
            "Email": "Username",
            "Total Score": item_name if item_name else default_name,
        }
        logger.debug(f"{column_mapping=}")
        gb.grades = scoresheet.scores[column_mapping.keys()].rename(columns=column_mapping) # type: ignore
        # drop the "@domain" part of the email addresses to match Brightspace usernames
        gb.grades["Username"] = gb.grades["Username"].str.split("@").str[0]
        # Keep DataSource.data in sync
        gb.data = gb.grades.copy()
        gb.metadata = {
            "source": "gradescope_scoresheet",
            "type": "brightspace_gradebook_from_gradescope",
            "item_name": item_name or default_name,
        }
        return gb


if __name__ == "__main__":
    # assume the first argument is a path and try to parse it
    import sys

    path = sys.argv[1]
    gb = Gradebook.from_csv(Path(path))
    if gb:
        print("\n--- Grades DataFrame ---")
        print(gb.grades.head())
        print("...")
