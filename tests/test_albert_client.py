#!/usr/bin/env python
"""Tests for albert client module."""

import pytest
from edubag.albert.client import _normalize_label


class TestNormalizeLabel:
    """Test the _normalize_label helper function."""

    def test_basic_label(self):
        """Test basic label normalization."""
        assert _normalize_label("Class Number") == "class_number"

    def test_multiple_words(self):
        """Test label with multiple words."""
        assert _normalize_label("Full Class Detail") == "full_class_detail"

    def test_special_characters(self):
        """Test label with special characters."""
        assert _normalize_label("Class Number (Test)") == "class_number_test"

    def test_leading_trailing_spaces(self):
        """Test label with leading/trailing spaces."""
        assert _normalize_label("  Class Number  ") == "class_number"

    def test_multiple_spaces(self):
        """Test label with multiple spaces."""
        assert _normalize_label("Class  Number  Detail") == "class_number_detail"

    def test_all_lowercase(self):
        """Test label that's already lowercase."""
        assert _normalize_label("class number") == "class_number"

    def test_mixed_case(self):
        """Test label with mixed case."""
        assert _normalize_label("ClassNumber") == "classnumber"
