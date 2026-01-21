#!/usr/bin/env python
"""Tests for gradescope client module."""

from pathlib import Path

from edubag.gradescope.client import GradescopeClient


class TestGradescopeClient:
    """Test the GradescopeClient class."""

    def test_client_initialization(self):
        """Test basic client initialization."""
        client = GradescopeClient()
        assert client.base_url == "https://gradescope.com"
        assert client.auth_state_path.name == "gradescope_auth.json"

    def test_client_custom_base_url(self):
        """Test client initialization with custom base URL."""
        custom_url = "https://custom.gradescope.com"
        client = GradescopeClient(base_url=custom_url)
        assert client.base_url == custom_url

    def test_client_custom_auth_path(self):
        """Test client initialization with custom auth state path."""
        custom_path = Path("/tmp/custom_auth.json")
        client = GradescopeClient(auth_state_path=custom_path)
        assert client.auth_state_path == custom_path

    def test_default_auth_state_path(self):
        """Test the default auth state path generation."""
        path = GradescopeClient._default_auth_state_path()
        assert path.name == "gradescope_auth.json"
        assert "edubag" in str(path)
