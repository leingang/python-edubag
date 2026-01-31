#!/usr/bin/env python
"""Tests for albert client module."""

import inspect

from edubag.albert.client import AlbertClient, _normalize_label


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


class TestAlbertClientMarkEngaged:
    """Test the mark_engaged method exists and has the correct signature."""

    def test_mark_engaged_method_exists(self):
        """Test that mark_engaged method exists on AlbertClient."""
        assert hasattr(AlbertClient, "mark_engaged")
        assert callable(AlbertClient.mark_engaged)

    def test_mark_engaged_signature(self):
        """Test that mark_engaged has the expected parameters."""
        method = AlbertClient.mark_engaged
        sig = inspect.signature(method)
        params = list(sig.parameters.keys())

        # Check required parameters are present
        assert "self" in params
        assert "class_number" in params
        assert "term" in params
        assert "email_addresses" in params

        # Check optional parameters are present
        assert "username" in params
        assert "password" in params
        assert "headless" in params

    def test_private_methods_exist(self):
        """Test that the private helper methods exist."""
        assert hasattr(AlbertClient, "_find_academic_engagement_link")
        assert hasattr(AlbertClient, "_mark_engaged_session")
