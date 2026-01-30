import re
from typing import List
import pandas as pd
from pathlib import Path
from loguru import logger

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
        self, gradebook: Gradebook, skip_constant: bool = True
    ):
        """
        Update the sections in the roster based on the Brightspace gradebook data.

        Args:
            gradebook (Gradebook): The Brightspace gradebook instance.
            skip_constant (bool): If True, skip columns with only one unique value.
                Defaults to True.

        Returns: None
        """
        if "Email" not in self.students.columns:
            raise ValueError("Roster must have an 'Email' column")

        if "Email" not in gradebook.grades.columns:
            raise ValueError("Gradebook must have an 'Email' column")

        sections_col = None
        for candidate in ["Sections", "Section Membership", "Section Memberships"]:
            if candidate in gradebook.grades.columns:
                sections_col = candidate
                break

        if sections_col is None:
            raise ValueError(
                "Gradebook must have a 'Sections' or 'Section Membership' column"
            )

        bs_sections = gradebook.grades[["Email", sections_col]].rename(
            columns={sections_col: "_brightspace_sections"}
        )

        merged_df = pd.merge(self.students, bs_sections, on="Email", how="left")

        def extract_and_pad_sections(sections_string):
            """Extract section codes from a sections string (comma-separated or single)."""
            if pd.isna(sections_string):
                return []

            entries = [s.strip() for s in str(sections_string).split(",") if s.strip()]
            codes = []
            for entry in entries:
                match = re.search(r"(\d{1,3})\s*$", entry)
                if match:
                    codes.append(match.group(1))
                    continue
                match = re.search(r"Section\s*(\d+)", entry)
                if match:
                    codes.append(match.group(1))

            if not codes:
                return []

            padded_codes = [code.zfill(3) for code in codes]
            sorted_codes = sorted(padded_codes)
            return sorted_codes

        # Extract and pad sections
        section_data = merged_df["_brightspace_sections"].apply(
            lambda x: pd.Series(extract_and_pad_sections(x))
        )

        # Determine which columns to keep
        if skip_constant:
            # First, try to keep only columns with varying values
            varying_columns = [col for col in section_data.columns 
                               if len(section_data[col].dropna().unique()) > 1]
            # If all columns are constant, keep the first non-empty column instead
            if varying_columns:
                columns_to_keep = varying_columns
            else:
                # All columns are constant; keep columns that have at least some non-null values
                columns_to_keep = [col for col in section_data.columns 
                                   if section_data[col].notna().any()]
        else:
            # Keep all columns with at least some non-null values
            columns_to_keep = [col for col in section_data.columns 
                               if section_data[col].notna().any()]

        if len(columns_to_keep) == 0:
            # No columns to add, emit warning and skip update
            logger.warning(
                "No section data found to add to the roster. self.students was not modified."
            )
            return

        # Drop old section columns if they exist
        cols_to_drop = [col for col in ["Section", "Section 2"] if col in merged_df.columns]
        if cols_to_drop:
            merged_df = merged_df.drop(columns=cols_to_drop)

        # Only use the columns we want to keep
        section_data_filtered = section_data[columns_to_keep]

        if len(columns_to_keep) == 1:
            # Only one column, rename it to "Section"
            merged_df["Section"] = section_data_filtered.iloc[:, 0]
        else:
            # Multiple columns, use generic names
            for i, col in enumerate(columns_to_keep):
                col_name = "Section" if i == 0 else f"Section {i + 1}"
                merged_df[col_name] = section_data_filtered.iloc[:, i]

        self.students = merged_df.drop(columns=["_brightspace_sections"])


if __name__ == "__main__":
    # assume the first argument is a path and try to parse it
    import sys

    path = Path(sys.argv[1])
    roster = GradescopeRoster.from_csv(path)
    if roster:
        print("\n--- Roster DataFrame ---")
        print(roster.students.head())
        print("...")
