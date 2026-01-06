"""Aggregator for combining multiple data sources into a unified gradebook."""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from loguru import logger

from edubag.brightspace.gradebook import Gradebook
from edubag.sources import DataSource


class EngagementAggregator:
    """Aggregates multiple DataSource instances into a unified gradebook.
    
    Attributes:
        sources: Dictionary mapping source names to DataSource instances
        config: Configuration dictionary specifying how to compute columns
        base_gradebook: Optional base Gradebook to merge into
        merged_data: The merged DataFrame after aggregation
    """

    def __init__(
        self,
        sources: Optional[Dict[str, DataSource]] = None,
        config: Optional[Dict[str, Any]] = None,
        base_gradebook: Optional[Gradebook] = None,
    ):
        """Initialize the aggregator.
        
        Args:
            sources: Dictionary mapping source names to DataSource instances
            config: Configuration for column computation, e.g.:
                {
                    "Attendance Points": {
                        "source": "attendance",
                        "column": "% Attendance",
                        "scale": 10.0,
                        "weight": 1.0
                    },
                    "EdSTEM Points": {
                        "sources": ["edstem"],
                        "formula": "Posts * 0.5 + Answers * 1.0 + Reactions * 0.1",
                        "scale": 10.0,
                        "clip_upper": 10.0
                    }
                }
            base_gradebook: Existing Gradebook to merge data into
        """
        self.sources = sources or {}
        self.config = config or {}
        self.base_gradebook = base_gradebook
        self.merged_data: Optional[pd.DataFrame] = None
        self.validation_report: Dict[str, Any] = {}

    def add_source(self, name: str, source: DataSource) -> None:
        """Add a data source to the aggregator.
        
        Args:
            name: Identifier for this source (used in config)
            source: DataSource instance with resolved identity
        """
        if "Username" not in source.data.columns:
            raise ValueError(f"Source '{name}' must have 'Username' column. Call resolve_identity() first.")
        self.sources[name] = source
        logger.info(f"Added source '{name}' with {len(source.data)} students")

    def merge_sources(self) -> pd.DataFrame:
        """Merge all sources on Username.
        
        Returns:
            DataFrame with all sources merged on Username
        """
        if not self.sources:
            raise ValueError("No sources to merge. Add sources with add_source().")

        # Start with base gradebook if provided, otherwise first source
        if self.base_gradebook is not None:
            merged = self.base_gradebook.grades.copy()
            logger.info(f"Starting with base gradebook: {len(merged)} students")
        else:
            first_source_name = list(self.sources.keys())[0]
            merged = self.sources[first_source_name].data[["Username"]].copy()
            logger.info(f"Starting with source '{first_source_name}': {len(merged)} students")

        # Merge each source
        for name, source in self.sources.items():
            # Select only Username and metric columns
            source_df = source.data.copy()
            
            # Rename columns to avoid conflicts, except Username
            rename_map = {
                col: f"{name}_{col}" 
                for col in source_df.columns 
                if col != "Username"
            }
            source_df = source_df.rename(columns=rename_map)
            
            # Merge on Username
            before_count = len(merged)
            merged = merged.merge(source_df, on="Username", how="outer")
            after_count = len(merged)
            
            logger.info(
                f"Merged source '{name}': {before_count} → {after_count} students "
                f"(+{after_count - before_count} new)"
            )

        # Filter to only students in base gradebook (if base_gradebook was provided)
        if self.base_gradebook is not None:
            # Normalize usernames by stripping leading # for comparison
            # (Gradebook class strips #, but other sources may have it)
            base_usernames = set(
                u.lstrip("#") for u in self.base_gradebook.grades["Username"].unique()
            )
            merged["_normalized_username"] = merged["Username"].str.lstrip("#")
            
            before_filter = len(merged)
            merged = merged[merged["_normalized_username"].isin(base_usernames)].copy()
            after_filter = len(merged)
            
            # Remove the temporary column
            merged = merged.drop(columns=["_normalized_username"])
            
            if before_filter > after_filter:
                removed_count = before_filter - after_filter
                logger.info(
                    f"Filtered to base gradebook students: {before_filter} → {after_filter} "
                    f"(removed {removed_count} external usernames)"
                )


        # Fill NaN values in numeric columns with 0 to prevent NaN propagation
        # in formula evaluation. Keep Username column as-is.
        numeric_columns = merged.select_dtypes(include=['number']).columns
        merged[numeric_columns] = merged[numeric_columns].fillna(0.0)
        
        self.merged_data = merged
        return merged
    def compute_columns(self) -> pd.DataFrame:
        """Compute configured columns based on source data.
        
        Returns:
            DataFrame with computed columns added
        """
        if self.merged_data is None:
            self.merge_sources()

        df = self.merged_data.copy()
        
        # Log available columns for debugging
        denominator_cols = [c for c in df.columns if 'denominator' in c]
        if denominator_cols:
            logger.debug(f"Available denominator columns: {denominator_cols}")

        for col_name, col_config in self.config.items():
            logger.info(f"Computing column: {col_name}")
            
            if "formula" in col_config:
                # Evaluate formula (e.g., "Posts * 0.5 + Answers * 1.0")
                formula = col_config["formula"]
                
                # Replace column references with actual merged column names
                eval_formula = formula
                
                # First pass: Handle backtick-quoted column names (for columns with special chars)
                # Do this first to avoid double-processing
                for source_name in self.sources.keys():
                    source_cols = [
                        c for c in self.sources[source_name].data.columns 
                        if c != "Username"
                    ]
                    for col in source_cols:
                        backtick_col = f"`{col}`"
                        backtick_replacement = f"`{source_name}_{col}`"
                        eval_formula = eval_formula.replace(backtick_col, backtick_replacement)
                
                # Second pass: Handle bare column names (only those not in backticks)
                # This is trickier - need to avoid replacing already-processed backtick names
                for source_name in self.sources.keys():
                    source_cols = [
                        c for c in self.sources[source_name].data.columns 
                        if c != "Username"
                    ]
                    for col in source_cols:
                        # Only replace if the column name isn't wrapped in backticks
                        # We'll use a regex to check for word boundaries
                        # Pattern: col not preceded/followed by backticks
                        pattern = r"(?<![`\w])" + re.escape(col) + r"(?![\w`])"
                        replacement = f"{source_name}_{col}"
                        eval_formula = re.sub(pattern, replacement, eval_formula)
                
                # Third pass: Replace backticked column names with df['col'] references
                # This handles both source-prefixed and computed denominator columns
                if '`' in eval_formula:
                    eval_formula = re.sub(r"`([^`]+)`", lambda m: f"df['{m.group(1)}']", eval_formula)
                
                # Fourth pass: Replace remaining bare column names (denominators, computed cols)
                # with df['col'] references for any that exist in the dataframe
                # Look for identifier-like names that aren't already wrapped
                for col in df.columns:
                    if col == "Username":
                        continue
                    if re.match(r"^[A-Za-z_]\w*$", col):  # Valid Python identifier
                        # Pattern to match word boundary
                        pattern = r"\b" + re.escape(col) + r"\b"
                        # Check if this column name appears in the formula and isn't already wrapped
                        if re.search(pattern, eval_formula):
                            # Only replace if not already in df[...] or backticks
                            if f"df['{col}']" not in eval_formula and f'df["{col}"]' not in eval_formula:
                                eval_formula = re.sub(pattern, f"df['{col}']", eval_formula)
                
                logger.info(f"  Original formula: {formula}")
                logger.info(f"  After substitution: {eval_formula}")
                
                # Evaluate the formula safely using eval with df in context
                try:
                    df[col_name] = eval(eval_formula, {}, {"df": df})
                except Exception as e:
                    logger.error(f"Failed to evaluate formula for '{col_name}': {e}")
                    df[col_name] = 0.0
                    
            elif "column" in col_config:
                # Simple column mapping from a source
                source_name = col_config["source"]
                source_col = col_config["column"]
                merged_col = f"{source_name}_{source_col}"
                
                if merged_col in df.columns:
                    df[col_name] = df[merged_col]
                else:
                    logger.warning(f"Column '{merged_col}' not found for '{col_name}'")
                    df[col_name] = 0.0
            else:
                logger.warning(f"No formula or column specified for '{col_name}'")
                df[col_name] = 0.0

            # Apply scale if specified
            if "scale" in col_config:
                scale = col_config["scale"]
                df[col_name] = df[col_name] * scale
                
            # Apply upper cap if specified
            if "clip_upper" in col_config:
                clip_upper = col_config["clip_upper"]
                df[col_name] = df[col_name].clip(upper=clip_upper)

            # Apply lower clip/floor if specified
            if "clip_lower" in col_config:
                lower = col_config["clip_lower"]
                df[col_name] = df[col_name].clip(lower=lower)
                
            # Fill NaN with 0
            df[col_name] = df[col_name].fillna(0.0)
            
            logger.info(
                f"  {col_name}: mean={df[col_name].mean():.2f}, "
                f"min={df[col_name].min():.2f}, max={df[col_name].max():.2f}"
            )

        self.merged_data = df
        return df

    def validate(self) -> Dict[str, Any]:
        """Validate the aggregated data and generate a report.
        
        Returns:
            Dictionary containing validation results:
                - missing_students: Students in base but not in sources
                - new_students: Students in sources but not in base
                - column_stats: Statistics for each computed column
                - warnings: List of validation warnings
        """
        report = {
            "missing_students": [],
            "new_students": [],
            "column_stats": {},
            "warnings": []
        }

        if self.merged_data is None:
            report["warnings"].append("No merged data available. Run compute_columns() first.")
            return report

        df = self.merged_data

        # Check for missing/new students if base gradebook exists
        if self.base_gradebook is not None:
            base_usernames = set(self.base_gradebook.grades["Username"])
            merged_usernames = set(df["Username"].dropna())
            
            report["missing_students"] = list(base_usernames - merged_usernames)
            report["new_students"] = list(merged_usernames - base_usernames)
            
            if report["missing_students"]:
                logger.warning(f"Students in base gradebook but not in sources: {len(report['missing_students'])}")
            # Note: new_students should be empty now since we filter to base gradebook

        # Compute statistics for configured columns
        for col_name in self.config.keys():
            if col_name in df.columns:
                col_data = df[col_name].dropna()
                report["column_stats"][col_name] = {
                    "count": len(col_data),
                    "mean": float(col_data.mean()) if len(col_data) > 0 else 0.0,
                    "std": float(col_data.std()) if len(col_data) > 0 else 0.0,
                    "min": float(col_data.min()) if len(col_data) > 0 else 0.0,
                    "max": float(col_data.max()) if len(col_data) > 0 else 0.0,
                    "zeros": int((col_data == 0).sum()),
                }

        # Check for suspicious patterns
        for col_name, stats in report["column_stats"].items():
            if stats["count"] > 0:
                zero_pct = (stats["zeros"] / stats["count"]) * 100
                if zero_pct > 50:
                    report["warnings"].append(
                        f"{col_name}: {zero_pct:.1f}% of students have zero points"
                    )

        self.validation_report = report
        return report

    def to_gradebook(self, keep_source_columns: bool = False) -> Gradebook:
        """Convert the aggregated data to a Brightspace Gradebook.
        
        Args:
            keep_source_columns: If True, keep intermediate source columns
        
        Returns:
            Gradebook instance ready to write to CSV
        """
        if self.merged_data is None:
            self.compute_columns()

        df = self.merged_data.copy()

        # Keep only Username and configured columns (plus base gradebook columns if present)
        if self.base_gradebook is not None:
            # Start with base gradebook columns
            keep_cols = list(self.base_gradebook.grades.columns)
            # Add configured columns that aren't already in base
            for col in self.config.keys():
                if col not in keep_cols and col in df.columns:
                    keep_cols.append(col)
        else:
            # Just Username and configured columns
            keep_cols = ["Username"] + [
                col for col in self.config.keys() if col in df.columns
            ]

        # Optionally keep source columns for debugging
        if keep_source_columns:
            source_cols = [
                col for col in df.columns 
                if any(col.startswith(f"{src}_") for src in self.sources.keys())
            ]
            keep_cols.extend(source_cols)

        # Filter to keep_cols that exist in df
        keep_cols = [col for col in keep_cols if col in df.columns]
        df = df[keep_cols]

        # Create gradebook
        gb = Gradebook()
        gb.grades = df
        
        logger.info(f"Created gradebook with {len(df)} students and {len(df.columns)} columns")
        
        return gb

    def print_report(self) -> None:
        """Print a human-readable validation report."""
        if not self.validation_report:
            self.validate()

        report = self.validation_report
        
        print("\n" + "="*60)
        print("ENGAGEMENT AGGREGATION REPORT")
        print("="*60)
        
        if report.get("missing_students"):
            print(f"\n⚠️  Missing Students ({len(report['missing_students'])}):")
            for username in sorted(report["missing_students"])[:10]:
                print(f"  - {username}")
            if len(report["missing_students"]) > 10:
                print(f"  ... and {len(report['missing_students']) - 10} more")
        
        # Note: new_students should be empty since we filter to base gradebook
        
        if report.get("column_stats"):
            print("\n📊 Column Statistics:")
            for col_name, stats in report["column_stats"].items():
                print(f"\n  {col_name}:")
                print(f"    Count:  {stats['count']}")
                print(f"    Mean:   {stats['mean']:.2f}")
                print(f"    Std:    {stats['std']:.2f}")
                print(f"    Range:  [{stats['min']:.2f}, {stats['max']:.2f}]")
                print(f"    Zeros:  {stats['zeros']} ({stats['zeros']/stats['count']*100:.1f}%)")
        
        if report.get("warnings"):
            print("\n⚠️  Warnings:")
            for warning in report["warnings"]:
                print(f"  - {warning}")
        
        print("\n" + "="*60 + "\n")
