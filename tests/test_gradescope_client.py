#!/usr/bin/env python
"""Tests for gradescope client module."""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from edubag.albert.term import Season, Term
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

    def test_extract_course_details(self):
        """Test extracting course details from a page."""
        client = GradescopeClient()

        # Mock page object
        mock_page = Mock()

        # Mock course name element
        mock_course_name = Mock()
        mock_course_name.count.return_value = 1
        mock_course_name.text_content.return_value = "Calculus II"
        mock_page.locator.side_effect = lambda selector: (
            mock_course_name
            if selector == "h1.courseHeader--title"
            else Mock(count=lambda: 0)
        )

        details = client._extract_course_details(mock_page)
        assert "course_name" in details
        assert details["course_name"] == "Calculus II"

    def test_extract_course_details_with_instructors(self):
        """Test extracting course details including instructors."""
        client = GradescopeClient()

        # Mock page object
        mock_page = Mock()

        # Mock instructor list
        mock_instructor1 = Mock()
        mock_instructor1.text_content.return_value = "John Doe"
        mock_instructor2 = Mock()
        mock_instructor2.text_content.return_value = "Jane Smith"

        mock_instructor_list = Mock()
        mock_instructor_list.count.return_value = 2
        mock_instructor_list.all.return_value = [mock_instructor1, mock_instructor2]

        def locator_side_effect(selector):
            if selector == "div.instructorList button.rosterCell--primaryLink":
                return mock_instructor_list
            return Mock(count=lambda: 0)

        mock_page.locator.side_effect = locator_side_effect

        details = client._extract_course_details(mock_page)
        assert "instructors" in details
        assert details["instructors"] == ["John Doe", "Jane Smith"]

    def test_fetch_class_details_with_term_object(self):
        """Test that fetch_class_details accepts Term objects."""
        client = GradescopeClient()
        term = Term(2025, Season.FALL)

        # Mock authentication state path to exist
        with patch("pathlib.Path.exists", return_value=True):
            # Mock the session method
            with patch.object(
                client, "_fetch_class_details_session", return_value=[]
            ) as mock_session:
                result = client.fetch_class_details(
                    course_name="Calculus II", term=term, headless=True
                )

                # Verify the session method was called with the term
                mock_session.assert_called_once_with("Calculus II", term, True)
                assert result == []

    def test_fetch_class_details_with_output(self):
        """Test that fetch_class_details saves to output file."""
        client = GradescopeClient()
        output_path = Path("/tmp/test_output.json")

        # Mock authentication state path to exist
        with patch("pathlib.Path.exists", return_value=True):
            # Mock the session method
            with patch.object(
                client,
                "_fetch_class_details_session",
                return_value=[{"course_name": "Test Course"}],
            ):
                # Mock file operations
                with patch("builtins.open", create=True) as mock_open:
                    with patch("pathlib.Path.mkdir"):
                        result = client.fetch_class_details(
                            course_name="Test Course",
                            term="Fall 2025",
                            headless=True,
                            output=output_path,
                        )

                        assert result == [{"course_name": "Test Course"}]
