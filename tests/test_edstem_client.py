#!/usr/bin/env python
"""Tests for EdSTEM client module."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from dotenv import load_dotenv

load_dotenv()

from edubag.edstem.client import EdstemClient  # noqa: E402


class TestEdstemClient:
    """Test the EdstemClient class."""

    def test_client_initialization(self):
        """Test basic client initialization."""
        client = EdstemClient()
        assert client.base_url == "https://edstem.org/us/"
        assert client.auth_state_path.name == "edstem_auth.json"

    def test_client_custom_base_url(self):
        """Test client initialization with custom base URL."""
        custom_url = "https://edstem.org/au/"
        client = EdstemClient(base_url=custom_url)
        assert client.base_url == custom_url

    def test_client_custom_auth_path(self):
        """Test client initialization with custom auth state path."""
        import tempfile

        custom_path = Path(tempfile.gettempdir()) / "custom_edstem_auth.json"
        client = EdstemClient(auth_state_path=custom_path)
        assert client.auth_state_path == custom_path

    def test_default_auth_state_path(self):
        """Test the default auth state path generation."""
        path = EdstemClient._default_auth_state_path()
        assert path.name == "edstem_auth.json"
        assert "edubag" in str(path)

    def test_save_analytics_with_course_id(self):
        """Test save_analytics constructs correct URL from course ID."""
        client = EdstemClient()

        with patch("pathlib.Path.exists", return_value=True):
            with patch.object(client, "_save_analytics_session", return_value=Path("analytics.csv")) as mock_session:
                result = client.save_analytics(course="12345", headless=True)

                mock_session.assert_called_once_with("12345", None, True)
                assert result == [Path("analytics.csv")]

    def test_save_analytics_with_save_dir(self):
        """Test save_analytics with custom save directory."""
        client = EdstemClient()

        with tempfile.TemporaryDirectory() as tmpdir:
            save_dir = Path(tmpdir)

            with patch("pathlib.Path.exists", return_value=True):
                with patch.object(
                    client,
                    "_save_analytics_session",
                    return_value=save_dir / "analytics.csv",
                ) as mock_session:
                    result = client.save_analytics(course="12345", save_dir=save_dir, headless=True)

                    mock_session.assert_called_once_with("12345", save_dir, True)
                    assert result == [save_dir / "analytics.csv"]

    def test_save_analytics_triggers_auth_when_missing(self):
        """Test that save_analytics calls authenticate when auth state is missing."""
        client = EdstemClient()

        with patch("pathlib.Path.exists", return_value=False):
            with patch.object(client, "authenticate") as mock_auth:
                with patch.object(client, "_save_analytics_session", return_value=Path("analytics.csv")):
                    client.save_analytics(course="12345", headless=True)
                    mock_auth.assert_called_once_with(headless=True)

    def test_save_analytics_retries_on_runtime_error(self):
        """Test that save_analytics retries with re-auth on RuntimeError."""
        client = EdstemClient()

        with patch("pathlib.Path.exists", return_value=True):
            with patch.object(client, "authenticate") as mock_auth:
                with patch.object(
                    client,
                    "_save_analytics_session",
                    side_effect=[RuntimeError("Authentication session expired."), Path("analytics.csv")],
                ) as mock_session:
                    result = client.save_analytics(course="12345", headless=True)

                    assert mock_session.call_count == 2
                    mock_auth.assert_called_once()
                    assert result == [Path("analytics.csv")]

    def test_save_analytics_raises_after_max_retries(self):
        """Test that save_analytics raises RuntimeError after max retries."""
        client = EdstemClient()

        with patch("pathlib.Path.exists", return_value=True):
            with patch.object(client, "authenticate"):
                with patch.object(
                    client,
                    "_save_analytics_session",
                    side_effect=RuntimeError("Authentication session expired."),
                ):
                    with pytest.raises(RuntimeError):
                        client.save_analytics(course="12345", headless=True)

    def test_save_analytics_integration(self):
        """Integration test: download analytics CSV from a real EdSTEM course.

        Requires RUN_EDSTEM_ANALYTICS_TEST=1 and a valid auth state.
        """
        if os.getenv("RUN_EDSTEM_ANALYTICS_TEST") != "1":
            pytest.skip("Set RUN_EDSTEM_ANALYTICS_TEST=1 to run this integration test.")

        client = EdstemClient()

        if not client.auth_state_path.exists():
            pytest.skip("Auth state not found. Run edstem client authenticate first.")

        course_id = os.getenv("EDSTEM_COURSE_ID")
        if not course_id:
            pytest.skip("Set EDSTEM_COURSE_ID to run this integration test.")

        result = client.save_analytics(course=course_id, headless=True)
        assert len(result) == 1
        assert result[0].exists()
