"""Data source classes for Brightspace gradebook aggregation.

Each DataSource wraps a DataFrame and metadata, providing a consistent interface
for loading, validating, and normalizing student identity across different sources.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import pandas as pd
from loguru import logger
from html.parser import HTMLParser
import zipfile


class DataSource(ABC):
    """Base class for grade/engagement data sources.

    Attributes:
        data (pd.DataFrame): The source data.
        metadata (dict): Source metadata (file path, parse date, column mappings, etc.).
    """

    def __init__(self):
        self.data: pd.DataFrame = pd.DataFrame()
        self.metadata: dict = {}

    @classmethod
    @abstractmethod
    def from_file(cls, path: Path) -> "DataSource":
        """Load a single file into a DataSource instance.

        Args:
            path (Path): Path to the file.

        Returns:
            DataSource: An instance with data and metadata populated.

        Raises:
            ValueError: If the file format is invalid or data is missing.
        """
        raise NotImplementedError

    @classmethod
    def from_dir(cls, dir_path: Path) -> "DataSource":
        """Load and aggregate all relevant files from a directory.

        Default implementation finds all .csv files and calls from_file on each,
        concatenating results. Subclasses may override for custom logic.

        Args:
            dir_path (Path): Directory containing data files.

        Returns:
            DataSource: An instance with aggregated data and metadata.
        """
        if not dir_path.exists() or not dir_path.is_dir():
            raise ValueError(f"Directory not found or not a directory: {dir_path}")

        csv_files = sorted(dir_path.glob("*.csv"))
        if not csv_files:
            raise ValueError(f"No CSV files found in {dir_path}")

        frames = []
        for path in csv_files:
            try:
                source = cls.from_file(path)
                frames.append(source.data)
            except Exception as e:
                logger.warning(f"Failed to load {path}: {e}")
                continue

        if not frames:
            raise ValueError(f"No valid data loaded from {dir_path}")

        # Concatenate by column union; missing columns filled with NaN
        combined = pd.concat(frames, axis=0, ignore_index=True, sort=False)
        logger.info(
            f"Loaded {len(combined)} rows from {len(frames)} files in {dir_path}"
        )

        obj = cls()
        obj.data = combined
        obj.metadata = {
            "source": str(dir_path),
            "type": cls.__name__,
            "files_loaded": len(frames),
        }
        return obj

    @abstractmethod
    def resolve_identity(self, username_col: str = "Username") -> None:
        """Normalize student identity to a canonical key.

        Updates self.data in-place to ensure the username_col exists and contains
        normalized student identifiers.

        Args:
            username_col (str): Name of the column to normalize to. Defaults to "Username".

        Raises:
            ValueError: If identity cannot be resolved.
        """
        raise NotImplementedError

    def get_students(self) -> set:
        """Return the set of unique student identifiers in this source.

        Assumes resolve_identity() has been called.

        Returns:
            set: Unique usernames.
        """
        username_col = self.metadata.get("username_col", "Username")
        if username_col not in self.data.columns:
            return set()
        return set(self.data[username_col].dropna().unique())


class OfficeHoursData(DataSource):
    """Office hours visit log data source."""

    @classmethod
    def from_html_file(cls, path: Path) -> "OfficeHoursData":
        """Load an office hours log from an HTML file.

        Parses anchor tags with href="mailto:..." and counts occurrences per user.

        Args:
            path (Path): Path to the HTML file.

        Returns:
            OfficeHoursData: Instance with Username and visit_count columns.
        """

        class MailtoParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.emails = []

            def handle_starttag(self, tag, attrs):
                if tag != "a":
                    return
                for k, v in attrs:
                    if k == "href" and v and v.startswith("mailto:"):
                        email = v[7:].split("?")[0].strip()
                        if email:
                            self.emails.append(email)

        try:
            html_text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            html_text = path.read_text(errors="replace")

        parser = MailtoParser()
        parser.feed(html_text)

        # Derive usernames and count occurrences
        usernames = [e.split("@")[0] for e in parser.emails if "@" in e]
        counts = (
            pd.Series(usernames, name="Username")
            .value_counts()
            .rename_axis("Username")
            .reset_index(name="visit_count")
        )

        obj = cls()
        obj.data = counts
        obj.metadata = {
            "source": str(path),
            "type": "office_hours_html",
            "format": "html",
            "total_anchors": len(parser.emails),
        }
        return obj

    @classmethod
    def from_zip_file(cls, path: Path) -> "OfficeHoursData":
        """Load an office hours log from a ZIP file containing an HTML file.

        Extracts the first .html/.htm file from the zip and calls from_html_file.

        Args:
            path (Path): Path to the ZIP file.

        Returns:
            OfficeHoursData: Instance with Username and visit_count columns.
        """
        with zipfile.ZipFile(path) as zf:
            html_names = [
                n for n in zf.namelist() if n.lower().endswith((".html", ".htm"))
            ]
            if not html_names:
                raise ValueError(f"No HTML file found in zip: {path}")
            inner_name = html_names[0]

            # Extract to a temporary location and load via from_html_file
            import tempfile

            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)
                inner_path = tmpdir_path / inner_name.split("/")[-1]
                inner_path.write_bytes(zf.read(inner_name))
                obj = cls.from_html_file(inner_path)

        # Update metadata to reflect the zip source
        obj.metadata["source"] = str(path)
        obj.metadata["type"] = "office_hours_html_zip"
        obj.metadata["format"] = "zip(html)"
        obj.metadata["inner_file"] = inner_name
        return obj

    @classmethod
    def from_csv_file(cls, path: Path) -> "OfficeHoursData":
        """Load an office hours log from a CSV file.

        Expects columns like: Username, Email, Date, Duration, etc.

        Args:
            path (Path): Path to the CSV file.

        Returns:
            OfficeHoursData: Instance with CSV data.
        """
        df = pd.read_csv(path, dtype=str)
        df.columns = [c.strip() for c in df.columns]

        obj = cls()
        obj.data = df
        obj.metadata = {
            "source": str(path),
            "type": "office_hours",
            "format": "csv",
            "original_columns": list(df.columns),
        }
        return obj

    @classmethod
    def from_file(cls, path: Path) -> "OfficeHoursData":
        """Load an office hours visit log file.

        Dispatches based on file extension:
        - .zip: calls from_zip_file
        - .html, .htm: calls from_html_file
        - otherwise: calls from_csv_file

        Args:
            path (Path): Path to the file.

        Returns:
            OfficeHoursData: Instance with aggregated data.
        """
        suffix = path.suffix.lower()
        if suffix == ".zip":
            return cls.from_zip_file(path)
        elif suffix in {".html", ".htm"}:
            return cls.from_html_file(path)
        else:
            return cls.from_csv_file(path)

    def resolve_identity(self, username_col: str = "Username") -> None:
        """Normalize to Username; derive from Email if needed.

        Args:
            username_col (str): Target column name (default "Username").
        """
        if username_col not in self.data.columns:
            if "Email" in self.data.columns:
                self.data[username_col] = (
                    self.data["Email"].astype(str).str.split("@").str[0]
                )
            else:
                raise ValueError(
                    "Office hours data must have 'Username' or 'Email' column"
                )
        self.metadata["username_col"] = username_col

    def count_visits(self, visit_col: str = "Username") -> pd.DataFrame:
        """Count visits per student.

        Returns:
            pd.DataFrame: DataFrame with Username and visit_count columns.
        """
        username_col = self.metadata.get("username_col", "Username")
        visits = self.data.groupby(username_col, as_index=False).size()
        visits.columns = [username_col, "visit_count"]
        return visits
