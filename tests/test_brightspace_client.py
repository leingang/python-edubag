#!/usr/bin/env python
"""Tests for brightspace client module."""

from pathlib import Path

from edubag.brightspace.client import BrightspaceClient


class TestBrightspaceClient:
    """Test the BrightspaceClient class."""

    def test_client_initialization(self):
        """Test basic client initialization."""
        client = BrightspaceClient()
        assert client.base_url == "https://brightspace.nyu.edu/"
        assert client.auth_state_path.name == "brightspace_auth.json"

    def test_client_custom_base_url(self):
        """Test client initialization with custom base URL."""
        custom_url = "https://custom.brightspace.com/"
        client = BrightspaceClient(base_url=custom_url)
        assert client.base_url == custom_url

    def test_client_custom_auth_path(self):
        """Test client initialization with custom auth state path."""
        custom_path = Path("/tmp/custom_auth.json")
        client = BrightspaceClient(auth_state_path=custom_path)
        assert client.auth_state_path == custom_path

    def test_default_auth_state_path(self):
        """Test the default auth state path generation."""
        path = BrightspaceClient._default_auth_state_path()
        assert path.name == "brightspace_auth.json"
        assert "edubag" in str(path)
