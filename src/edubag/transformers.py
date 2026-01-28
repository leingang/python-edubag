"""Transformers for applying intermediate calculations to DataSources."""

import re
from typing import Dict, List, Optional

import pandas as pd
from loguru import logger

from edubag.brightspace.gradebook import Gradebook
from edubag.sources import DataSource


class GradebookTransformer:
    """Apply transformations and intermediate calculations to a Brightspace gradebook.
    
    Parses category information from column headers and computes per-category metrics:
    - Count of positive scores (non-zero, non-Exempt)
    - Count of exemptions
    - Total items in category (stored in metadata)
    """

    def __init__(self, gradebook: Gradebook):
        """Initialize transformer.
        
        Args:
            gradebook: A Brightspace Gradebook instance
        """
        self.gradebook = gradebook
        self.df = gradebook.grades
        self.category_columns: Dict[str, List[str]] = {}
        self.category_metadata: Dict[str, dict] = {}
        self._parse_category_columns()

    def _parse_category_columns(self) -> None:
        """Parse column headers to extract category and item information.
        
        Expected format: `"Item Name <Numeric MaxPoints:5 Category:Pre-Quizzes ...>"`
        Stores mapping of category -> list of column names.
        """
        for col in self.df.columns:
            # Skip non-grade columns (Username, etc.)
            if col in ["Username", "First Name", "Last Name", "Email", "Sections"]:
                continue

            # Try to extract category from <...> suffix
            # Format: "Name <...Category:CategoryName...>"
            match = re.search(r"Category:(\w+[\w\s-]*?)\s+(?:CategoryWeight|>)", col)
            if match:
                try:
                    category = match.group(1).strip()
                    if category not in self.category_columns:
                        self.category_columns[category] = []
                    self.category_columns[category].append(col)
                except Exception as e:
                    logger.debug(f"Failed to parse category from column '{col}': {e}")

        logger.info(f"Parsed categories: {list(self.category_columns.keys())}")
        for category, cols in self.category_columns.items():
            logger.info(f"  {category}: {len(cols)} items")

    def add_category_metrics(self, categories: Optional[List[str]] = None) -> "GradebookTransformer":
        """Add metrics for specified categories to the gradebook data.
        
        For each category, adds columns:
        - {category}_positive: Count of non-zero, non-Exempt scores
        - {category}_exemptions: Count of "Exempt" values
        
        Stores in metadata:
        - {category}_total_items: Total number of items in category
        
        Args:
            categories: List of category names to process. If None, processes all found.
        
        Returns:
            self (for method chaining)
        """
        if categories is None:
            categories = list(self.category_columns.keys())

        for category in categories:
            if category not in self.category_columns:
                logger.warning(f"Category '{category}' not found in parsed columns")
                continue

            cols = self.category_columns[category]
            logger.info(f"Computing metrics for '{category}' ({len(cols)} items)...")

            # Count positive scores (non-zero, non-Exempt, non-NaN)
            positive_count = self._count_positive(cols)
            self.df[f"{category}_positive"] = positive_count

            # Count exemptions
            exemption_count = self._count_exemptions(cols)
            self.df[f"{category}_exemptions"] = exemption_count

            # Store total items in metadata (constant across students)
            if "category_metadata" not in self.gradebook.__dict__:
                self.gradebook.category_metadata = {}
            
            self.gradebook.category_metadata[category] = {
                "total_items": len(cols),
                "columns": cols,
            }

            logger.info(
                f"  Added '{category}_positive' and '{category}_exemptions' columns; "
                f"stored total_items={len(cols)} in metadata"
            )

        return self

    def _count_positive(self, columns: List[str]) -> pd.Series:
        """Count positive scores in a list of columns.
        
        A score is positive if:
        - It's numeric and `> 0`
        - It's not "Exempt"
        - It's not NaN or empty string
        
        Args:
            columns: List of column names
        
        Returns:
            Series with count for each row
        """
        def count_row(row: pd.Series) -> int:
            count = 0
            for val in row:
                val_str = str(val).strip().lower()
                # Skip NaN, empty, "exempt", and non-numeric zero
                if val_str in ["nan", "", "exempt"]:
                    continue
                try:
                    num_val = float(val)
                    if num_val > 0:
                        count += 1
                except ValueError:
                    # Not a number and not "Exempt", skip
                    pass
            return count

        return self.df[columns].apply(count_row, axis=1)

    def _count_exemptions(self, columns: List[str]) -> pd.Series:
        """Count exemption values in a list of columns.
        
        Args:
            columns: List of column names
        
        Returns:
            Series with exemption count for each row
        """
        def count_row(row: pd.Series) -> int:
            return sum(1 for val in row if str(val).strip().lower() == "exempt")

        return self.df[columns].apply(count_row, axis=1)

    def compute_ratio(
        self,
        numerator_col: str,
        denominator_col: str,
        target_col: str,
        fill_value: float = 0.0,
    ) -> "GradebookTransformer":
        """Compute ratio of two columns.
        
        Args:
            numerator_col: Column with numerator values
            denominator_col: Column with denominator values
            target_col: Name for the result column
            fill_value: Value to use when denominator is 0
        
        Returns:
            self (for method chaining)
        """
        self.df[target_col] = (
            self.df[numerator_col] / self.df[denominator_col]
        ).fillna(fill_value).replace([float("inf"), float("-inf")], fill_value)
        
        logger.info(f"Computed {target_col} = {numerator_col} / {denominator_col}")
        return self

    def get_metadata(self) -> Dict:
        """Get the category metadata (total items per category).
        
        Returns:
            Dictionary mapping category names to metadata dicts
        """
        return getattr(self.gradebook, "category_metadata", {})


class SourceTransformer:
    """Apply transformations to a generic DataSource."""

    def __init__(self, source: DataSource):
        """Initialize transformer.
        
        Args:
            source: A DataSource instance
        """
        self.source = source
        self.df = source.data

    def count_positive_values(
        self,
        columns: List[str],
        target_col: str,
        threshold: float = 0.0,
    ) -> "SourceTransformer":
        """Count values above a threshold in specified columns.
        
        Args:
            columns: List of column names
            target_col: Name for the result column
            threshold: Values `> threshold` count as positive
        
        Returns:
            self (for method chaining)
        """
        def count_row(row: pd.Series) -> int:
            count = 0
            for val in row:
                try:
                    if float(val) > threshold:
                        count += 1
                except (ValueError, TypeError):
                    pass
            return count

        self.source.data[target_col] = self.df[columns].apply(count_row, axis=1)
        logger.info(f"Computed {target_col}: count of values > {threshold}")
        return self

    def compute_ratio(
        self,
        numerator_col: str,
        denominator_col: str,
        target_col: str,
        fill_value: float = 0.0,
    ) -> "SourceTransformer":
        """Compute ratio of two columns.
        
        Args:
            numerator_col: Column with numerator values
            denominator_col: Column with denominator values
            target_col: Name for the result column
            fill_value: Value to use when denominator is 0
        
        Returns:
            self (for method chaining)
        """
        self.source.data[target_col] = (
            self.df[numerator_col] / self.df[denominator_col]
        ).fillna(fill_value).replace([float("inf"), float("-inf")], fill_value)

        logger.info(f"Computed {target_col} = {numerator_col} / {denominator_col}")
        return self
