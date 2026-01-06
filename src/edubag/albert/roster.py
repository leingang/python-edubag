import io
import re
import sys

from bs4 import BeautifulSoup
import pandas as pd
from pathlib import Path

from edubag.albert.term import Term


class AlbertRoster(object):
    """A class roster fetched from Albert"""

    course: dict[str, str]
    students: pd.DataFrame

    @classmethod
    def from_xls(cls, path: Path):
        """
        Parses an HTML file to extract a class roster table into a pandas
        DataFrame and class metadata into a dictionary.

        Args:
            file_path (str): The path to the HTML file.

        Returns:
            AlbertRoster: a roster
        """
        # Debated about whether this should be a module function
        # or a class method. Opted for the latter after reading
        # https://softwareengineering.stackexchange.com/a/166715/149470
        # Dictionary to store the extracted data
        parsed_data = {"metadata": {}, "dataframe": None}

        # Read the HTML content from the file
        with open(path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Parse the HTML with BeautifulSoup
        soup = BeautifulSoup(html_content, "html.parser")

        # --- Extract Metadata ---
        # The metadata is in custom tags with 'b' elements inside them.
        # Find all 'b' tags to get the key-value pairs.
        for tag in soup.find_all("b"):
            # The key is the text of the 'b' tag, stripped of the colon
            key = tag.get_text().strip(": ")
            # The value is the text of the parent tag, with the key text removed
            parent_text = tag.parent.get_text()
            value = parent_text.replace(tag.get_text(), "").strip()
            # Store in the metadata dictionary
            if key and value:
                parsed_data["metadata"][key] = value

        # --- Further parse metadata ---
        # The "Class Detail" field is a string like "MATH-UA 122 (0)-001"
        # The substring "MATH-UA" is the subject code
        # The substring "122" is the catalog number
        # The substring "001" is the section number
        class_detail = parsed_data["metadata"].get("Class Detail", "")
        if class_detail:
            # Parse "MATH-UA 122 (0)-001" format: subject code, catalog number, section
            match = re.match(r"(.+?)\s+(\d+)\s*\(.*?\)-(.+)", class_detail)
            if match:
                parsed_data["metadata"]["Subject Code"] = match.group(1)
                parsed_data["metadata"]["Catalog Number"] = match.group(2)
                parsed_data["metadata"]["Section"] = match.group(3)

        # --- Extract DataFrame ---
        # pandas.read_html can directly parse the table into a DataFrame.
        # It returns a list of DataFrames, so we take the first one.
        tables = pd.read_html(io.StringIO(html_content))
        if tables:
            parsed_data["dataframe"] = tables[0]

        obj = AlbertRoster()
        obj.course = parsed_data["metadata"]
        obj.students = parsed_data["dataframe"]
        return obj

    @property
    def pathstem(self) -> str:
        """A string serializing the course metatdata for use in file paths."""
        subject = self.course.get("Subject Code", "UNKNOWN")
        catalog = self.course.get("Catalog Number", "000")
        section = self.course.get("Section", "000")
        term = Term.from_name(self.course.get("Semester", "Fall 2025")).code
        return f"{subject}_{catalog}_{section}_{term}"

    def to_csv(self, path_or_buf):
        """Saves the roster DataFrame to CSV format.

        Args:
            path_or_buf (Path | file-like): The file path or buffer to write the CSV data to.
            See `pandas.DataFrame.to_csv`_ for details.

        Warning:
            This method only saves the students DataFrame to CSV format. The course metadata
            is not saved. Use the `pathstem` property to get a string representation of the course
            metadata for use in file paths.

        .. _pandas.DataFrame.to_csv: https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.to_csv
        """
        self.students.to_csv(path_or_buf, index=False)


if __name__ == "__main__":
    # assume the first argument is a path and try to parse it
    import sys

    path = sys.argv[1]
    roster = AlbertRoster.from_xls(path)
    if roster:
        print("--- Course Dictionary ---")
        for key, value in roster.course.items():
            print(f"{key}: {value}")

        print("\n--- Roster DataFrame ---")
        print(roster.students.head())
        print("...")
