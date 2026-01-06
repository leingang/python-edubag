from pathlib import Path
from typing import List

import pandas as pd
from loguru import logger

from edubag.sources import DataSource


class EdstemAnalytics(DataSource):
    """EdSTEM analytics data source."""

    @classmethod
    def from_file(cls, path: Path) -> "EdstemAnalytics":
        """Load an EdSTEM analytics CSV.

        Expects columns like: Email, Posts, Answers, Reactions, etc.
        Engagement metrics (Posts, Answers, Reactions) are automatically
        converted to numeric types with NaN filled as 0.
        """
        # Define converters for engagement metrics
        def to_numeric_or_zero(x):
            try:
                return int(x) if pd.notna(x) else 0.0
            except (ValueError, TypeError):
                return 0.0
        
        converters = {
            "Posts": to_numeric_or_zero,
            "Answers": to_numeric_or_zero,
            "Reactions": to_numeric_or_zero,
            "Questions": to_numeric_or_zero,
            "Announcements": to_numeric_or_zero,
            "Comments": to_numeric_or_zero,
            "Accepted Answers": to_numeric_or_zero,
            "Hearts": to_numeric_or_zero,
            "Endorsements": to_numeric_or_zero,
        }
        
        df = pd.read_csv(path, converters=converters)
        df.columns = [c.strip() for c in df.columns]

        # keep only users with 'student' role
        if "Role" in df.columns:
            df = df[df["Role"].str.lower() == "student"]

        obj = cls()
        obj.data = df
        obj.metadata = {
            "source": str(path),
            "type": "edstem",
            "original_columns": list(df.columns),
        }
        return obj

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
                    "EdSTEM data must have 'Username' or 'Email' column"
                )
        self.metadata["username_col"] = username_col
