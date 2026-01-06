import re
from typing import List
import pandas as pd
from pathlib import Path

from edubag.brightspace.gradebook import Gradebook
from edubag.albert.roster import AlbertRoster


class GradescopeRoster(object):
    """A class roster fetched from Gradescope"""

    students: pd.DataFrame

    def to_csv(self, path: Path):
        """
        Write the roster to a CSV file.

        Args:
            path (pathlib.Path): Path to the CSV file target.

        Returns: None
        """
        self.students.to_csv(path, index=False)

    @classmethod
    def from_csv(cls, path: Path):
        """
        Parses a CSV file to create a Gradescope roster.

        Args:
            path (pathlib.Path): The path to the HTML file.

        Returns:
            GradescopeRoster: a roster

        To generate the Gradescope roster CSV file:
        1. Go to your course on Gradescope.
        2. Click on "Roster" in the left-hand menu.
        3. Click on the "Download CSV" button to download the roster file.
        4. Save the file (recommended path: `data/raw/gradescope/roster/<date>/`)
        """
        obj = GradescopeRoster()
        obj.students = pd.read_csv(path)
        return obj

    @classmethod
    def from_albert_roster(cls, roster: AlbertRoster, read_section: bool = True):
        obj = GradescopeRoster()
        df = pd.DataFrame()
        for gs_field, albert_field in {
            "First Name": "First Name",
            "Last Name": "Last Name",
            "Email": "Email Address",
            "SID": "Campus ID",
        }.items():
            df[gs_field] = roster.students[albert_field]
        if read_section:
            class_detail = roster.course["Class Detail"]
            pattern = (
                r"^(?P<subject>[A-Z-]+)\s+(?P<catalog>\d+)\s+\(\d+\)-(?P<section>\d+)$"
            )
            m = re.match(pattern, class_detail)
            if m:
                section_code = m.group("section")
            else:
                raise ValueError(
                    f"Could not parse section from Class Detail: {class_detail}"
                )
            df["Section"] = section_code
        obj.students = df
        return obj

    @classmethod
    def merge(cls, rosters: List["GradescopeRoster"]):
        """Merge several rosters into a single one"""
        obj = GradescopeRoster()
        obj.students = pd.concat([r.students for r in rosters], ignore_index=True)
        return obj

    def obscure_emails(self):
        """Obscure the email addresses in the roster

        Prefixes "hidden" to the email address domain name
        For example, "mpl123@example.com" becomes "mpl123@hidden.example.com"
        """
        self.students["Email"] = self.students.apply(
            lambda row: f"{row['Email'].split('@')[0]}@hidden.{row['Email'].split('@')[1]}",
            axis=1,
        )

    def update_sections_from_brightspace_gradebook(
        self, gradebook: Gradebook
    ):
        """
        Update the sections in the roster based on the Brightspace gradebook data.

        Args:
            gradebook (Gradebook): The Brightspace gradebook instance.

        Returns: None
        """
        raise NotImplementedError


if __name__ == "__main__":
    # assume the first argument is a path and try to parse it
    import sys

    path = sys.argv[1]
    roster = GradescopeRoster.from_csv(path)
    if roster:
        print("\n--- Roster DataFrame ---")
        print(roster.students.head())
        print("...")
