"""Module to automate interactions with the Gradescope platform."""

import json
import os
import re
from pathlib import Path

import platformdirs
from dotenv import load_dotenv
from loguru import logger
from playwright.sync_api import Page, sync_playwright

from edubag.albert.term import Term


class GradescopeClient:
    """Client to interact with the Gradescope platform."""

    base_url = "https://gradescope.com"

    @staticmethod
    def _default_auth_state_path() -> Path:
        """Get the platform-appropriate default path for the auth state file."""
        cache_dir = Path(platformdirs.user_cache_dir("edubag", "NYU"))
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / "gradescope_auth.json"

    def __init__(self, base_url: str | None = None, auth_state_path: Path | None = None):
        """Initializes the GradescopeClient."""
        if base_url is not None:
            self.base_url = base_url
        if auth_state_path is not None:
            self.auth_state_path = auth_state_path
        else:
            self.auth_state_path = self._default_auth_state_path()

    def authenticate(
        self,
        username: str | None = None,
        password: str | None = None,
        headless: bool = False,
    ) -> bool:
        """Log into Gradescope and save the authentication state.

        Args:
            username (str | None): NetID to log in with. If None, user must enter manually in browser.
            password (str | None): Password for login. If None, user must enter manually in browser.
            headless (bool): Whether to run the browser in headless mode. Headless mode requires username and password.

        Returns:
            bool: True if authentication was successful, False otherwise.
        """
        # Load environment variables from .env file
        load_dotenv()

        # Try to get username and password from environment if not provided
        if username is None:
            username = os.getenv("GRADESCOPE_USERNAME")
        if password is None:
            password = os.getenv("GRADESCOPE_PASSWORD")

        # If username or password are not specified, browser must not be headless
        if username is None or password is None:
            headless = False

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context()
            page = context.new_page()

            page.goto(self.base_url)

            # Wait for page to load
            page.wait_for_load_state("domcontentloaded", timeout=10000)

            # Click the "Log In" button
            page.get_by_role("button", name="Log In").click()

            # Wait for login form to appear
            page.get_by_role("textbox", name="Email").wait_for(state="visible", timeout=10000)

            if username is not None:
                page.get_by_role("textbox", name="Email").fill(username)
                if password is not None:
                    page.get_by_role("textbox", name="Password").fill(password)
                    page.locator("#session_remember_me_label").click()
                    page.get_by_role("button", name="Log In").click()
                else:
                    print("Please enter your password in the browser window.")
            else:
                print("Please enter your username and password in the browser window.")

            # Wait for successful login (redirect to dashboard or account page)
            page.wait_for_url("**/account", timeout=60000)

            context.storage_state(path=self.auth_state_path)
            logger.debug(f"Authentication state saved at {self.auth_state_path}")

            browser.close()
        return True

    def sync_roster(self, course: str, notify: bool = True, headless: bool = True) -> bool:
        """Synchronize the course roster with the linked LMS.

        Args:
            course: Gradescope course ID or URL to the course home page
            notify: notify added users
            headless: Whether to run the browser in headless mode

        Returns:
            success value
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(storage_state=self.auth_state_path)
            page = context.new_page()

            # Navigate to the course page
            # Determine if course is a full URL or just an ID
            if course.startswith("http://") or course.startswith("https://"):
                course_url = course
            else:
                course_url = f"{self.base_url}/courses/{course}"
            page.goto(course_url)

            # Check if we need to re-login
            if "login" in page.url:
                logger.error("Authentication session expired. Please re-authenticate.")
                browser.close()
                return False

            try:
                # Navigate to Roster page
                page.get_by_role("link", name="Roster").click()
                page.wait_for_load_state("networkidle")

                # Try to click "More" button if it exists
                more_button = page.locator(".js-toggleActionBarCollapsedMenu")
                if more_button.count() > 0:
                    more_button.click()
                    page.wait_for_load_state("networkidle")

                # Click the Sync button (using inexact match on "Sync")
                # It has class js-openSyncLTIv1p3RosterModal
                page.get_by_role("button", name="Sync", exact=False).first.click()
                page.wait_for_load_state("networkidle")

                # Handle the notification checkbox
                sync_dialog = page.get_by_label("Sync with NYU Brightspace")
                notify_checkbox = sync_dialog.get_by_text("Let new users know that they")

                # Check the current state and update if needed
                is_checked = notify_checkbox.is_checked()
                if notify != is_checked:
                    notify_checkbox.click()

                # Click the "Sync Roster" button
                page.get_by_role("button", name="Sync Roster").click()

                # Wait until the dialog disappears
                page.get_by_role("button", name="Sync Roster").wait_for(state="detached", timeout=60000)

                # Check for flash message alert
                flash_alert = page.locator(".alert.alert-flashMessage.alert-success span").first
                if flash_alert.count() > 0:
                    message = flash_alert.text_content()
                    logger.info(message)
                else:
                    logger.info("Roster sync succeeded with no changes.")

                browser.close()
                return True

            except Exception as e:
                logger.error(f"Error during roster sync: {e}")
                browser.close()
                return False

    def _save_roster_session(
        self,
        course: str,
        save_dir: Path | None = None,
        headless: bool = True,
    ) -> Path:
        """Internal method to save roster in a single browser session.

        Raises RuntimeError if authentication has expired.
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(storage_state=self.auth_state_path, accept_downloads=True)
            page = context.new_page()

            # Navigate to the course page
            # Determine if course is a full URL or just an ID
            if course.startswith("http://") or course.startswith("https://"):
                course_url = course
            else:
                course_url = f"{self.base_url}/courses/{course}"

            # Navigate to the memberships (roster) page
            roster_url = course_url.rstrip("/") + "/memberships"
            page.goto(roster_url)

            # Check if we need to re-login
            if "login" in page.url:
                logger.error("Authentication session expired. Please re-authenticate.")
                browser.close()
                raise RuntimeError("Authentication session expired.")

            # Wait for page to load
            page.wait_for_load_state("domcontentloaded", timeout=10000)

            # Find the download roster link
            # It's an <a> element with class containing "tiiBtn" and href ending with "memberships.csv"
            download_link = page.locator('a[href$="/memberships.csv"]').first

            # Wait for the download link to be available
            download_link.wait_for(state="visible", timeout=10000)

            # Set up download expectation and click the link
            with page.expect_download() as download_info:
                download_link.click()
            download = download_info.value

            # Save the download
            if save_dir is not None:
                save_dir.mkdir(parents=True, exist_ok=True)
                download_file_path = save_dir / download.suggested_filename
            else:
                download_file_path = Path(download.suggested_filename)

            logger.info(f"Downloading roster to {download_file_path}")
            download.save_as(download_file_path)

            browser.close()
        return download_file_path

    def save_roster(
        self,
        course: str,
        save_dir: Path | None = None,
        headless: bool = True,
    ) -> Path:
        """Fetch and save the roster for a class on Gradescope.

        Args:
          * course: Gradescope course ID or URL to the course home page
          * save_dir: target directory of the saved roster file (default: current working directory)
          * headless (bool): Whether to run the browser in headless mode.

        Returns:
            Path: path to the output file
        """
        # Ensure authentication state exists; trigger a login flow if missing
        if not self.auth_state_path.exists():
            logger.warning(f"Auth state file not found at {self.auth_state_path}. Running authentication...")
            self.authenticate(headless=headless)

        max_retries = 1
        for attempt in range(max_retries + 1):
            try:
                return self._save_roster_session(course, save_dir, headless)
            except RuntimeError as e:
                if attempt < max_retries:
                    logger.warning(f"RuntimeError: {e} Authentication may have expired.")
                    logger.info("Re-authenticating...")
                    if self.auth_state_path.exists():
                        self.auth_state_path.unlink()
                    self.authenticate(headless=headless)
                    continue
                else:
                    logger.error(f"Max retries exceeded. RuntimeError: {e}")
                raise
        # This should never be reached, but return an empty Path as a fallback
        return Path()

    def _extract_course_details(self, page: Page) -> dict:
        """Extract course details from a Gradescope course page.

        Args:
            page: The Playwright page object for the course home page.

        Returns:
            Dictionary with course detail information.
        """
        course_details = {}

        # Extract course number from the h1.courseHeader--title
        course_number_element = page.locator("h1.courseHeader--title")
        if course_number_element.count() > 0:
            text = course_number_element.text_content()
            if text:
                course_details["course_number"] = text.strip()

        # Extract course name from the sidebar subtitle (format: "MATH-UA 122.006 Calculus II, Spring 2026")
        sidebar_subtitle = page.locator("div.sidebar--subtitle")
        if sidebar_subtitle.count() > 0:
            subtitle_text = sidebar_subtitle.text_content()
            if subtitle_text:
                course_details["course_name"] = subtitle_text.strip()

        # Extract Course ID from div.courseHeader--courseID
        course_id_element = page.locator("div.courseHeader--courseID")
        if course_id_element.count() > 0:
            course_id_text = course_id_element.text_content()
            if course_id_text:
                course_id_text = course_id_text.strip()
                # Extract just the number from "Course ID: 1227665"
                course_id_match = re.search(r"(\d+)", course_id_text)
                if course_id_match:
                    course_details["course_id"] = course_id_match.group(1)

        # Extract instructors from the sidebar roster (aria-label="Instructor: ...")
        instructor_items = page.locator("li[aria-label^='Instructor:']")
        if instructor_items.count() > 0:
            instructors = []
            for item in instructor_items.all():
                aria_label = item.get_attribute("aria-label")
                # Extract name from "Instructor: Name" format
                if aria_label and aria_label.startswith("Instructor:"):
                    name = aria_label.replace("Instructor:", "").strip()
                    instructors.append(name)
            if instructors:
                course_details["instructors"] = instructors

        return course_details

    def _fetch_class_details_session(
        self,
        course_name: str,
        term: str | Term,
        headless: bool = True,
    ) -> list[dict]:
        """Internal method to fetch class details in a single browser session.

        Raises RuntimeError if authentication has expired.
        """
        result = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(storage_state=self.auth_state_path)
            page = context.new_page()

            page.goto(self.base_url)
            if "login" in page.url:
                browser.close()
                raise RuntimeError("Authentication session expired.")

            # Wait for the course list to load
            page.wait_for_load_state("networkidle")

            # Convert term to string representation (e.g., "FALL 2025")
            term_str = str(term)

            # Find all term divs and filter for the exact one we want
            term_divs = page.locator("div.courseList--term")
            term_count = term_divs.count()
            matching_term_index = -1

            # Find the term div that contains our term string
            for i in range(term_count):
                term_div = term_divs.nth(i)
                term_text = term_div.text_content()
                if term_text and term_str in term_text:
                    matching_term_index = i
                    break

            if matching_term_index == -1:
                logger.warning(f"Term '{term_str}' not found on page")
                browser.close()
                return result

            # Get all coursesForTerm containers and find the one after our matching term
            courses_for_term_divs = page.locator("div.courseList--coursesForTerm")
            courses_for_term_count = courses_for_term_divs.count()

            # The courses container should be at the same index as the term (terms and containers alternate)
            if matching_term_index < courses_for_term_count:
                courses_container = courses_for_term_divs.nth(matching_term_index)
            else:
                logger.warning(
                    f"Courses container index {matching_term_index} out of range (only {courses_for_term_count} containers)"
                )
                browser.close()
                return result

            if courses_container.count() == 0:
                logger.warning(f"No courses found for term '{term_str}'")
                browser.close()
                return result

            # Normalize whitespace in course name (handle line breaks, multiple spaces, etc.)
            normalized_course_name = re.sub(r"\s+", " ", course_name).strip()

            # Build a regex once for reuse with locator filters
            course_regex = re.compile(re.escape(normalized_course_name), re.IGNORECASE)
            logger.debug(f"Looking for course matching regex: {course_regex.pattern}")

            # Locate matching course boxes via Playwright locator filters
            course_boxes = courses_container.locator("a.courseBox")
            by_name = course_boxes.filter(has=page.locator("div.courseBox--name", has_text=course_regex))
            # Fallback: match on any text inside the course box
            by_box_text = course_boxes.filter(has_text=course_regex)

            # Combine matches using Playwright's locator union
            matching_courses = by_name.or_(by_box_text).all()
            logger.debug(f"Found {len(matching_courses)} matching course boxes")

            # Now visit each matching course and extract details
            for course_link in matching_courses:
                course_url = course_link.get_attribute("href")
                if course_url:
                    # Validate and construct the full URL safely
                    # Ensure course_url is a relative path starting with /
                    if not course_url.startswith("/"):
                        logger.warning(f"Skipping invalid course URL: {course_url}")
                        continue

                    # Navigate to the course page
                    full_url = f"{self.base_url}{course_url}"
                    page.goto(full_url)
                    page.wait_for_load_state("networkidle")

                    # Extract course details
                    course_details = self._extract_course_details(page)
                    result.append(course_details)
                    logger.info(f"Extracted details for course: {course_details.get('course_name', 'Unknown')}")

                    # Go back to the home page for the next iteration
                    page.goto(self.base_url)
                    page.wait_for_load_state("networkidle")

            browser.close()
        return result

    def fetch_class_details(
        self,
        course_name: str,
        term: str | Term,
        username: str | None = None,
        password: str | None = None,
        headless: bool = True,
        output: Path | None = None,
    ) -> list[dict]:
        """Fetch class details for a course offering and optionally save.

        Args:
          * course_name (str): The name of the course.
          * term (str | Term): The term of the course.
          * username (str | None): NetID to log in with. If None, user must enter manually.
          * password (str | None): Password for login. If None, user must enter manually.
          * headless (bool): Whether to run the browser in headless mode.
          * output (Path | None): Path to save the output JSON. If None, doesn't save.

        Returns:
            list[dict]: List of dictionaries with class details.
        """
        # Check if authentication state exists; if not, authenticate first
        if not self.auth_state_path.exists():
            logger.warning(f"Auth state file not found at {self.auth_state_path}. Running authentication...")
            self.authenticate(username=username, password=password, headless=headless)

        max_retries = 1
        for attempt in range(max_retries + 1):
            try:
                result = self._fetch_class_details_session(course_name, term, headless)

                # Save to output if specified
                if output is not None:
                    output.parent.mkdir(parents=True, exist_ok=True)
                    with output.open("w") as f:
                        json.dump(result, f, indent=2)
                    logger.info(f"Class details saved to {output}")

                return result
            except RuntimeError as e:
                if attempt < max_retries:
                    logger.warning(f"RuntimeError: {e} Authentication may have expired.")
                    logger.info("Re-authenticating...")
                    if self.auth_state_path.exists():
                        self.auth_state_path.unlink()
                    self.authenticate(username=username, password=password, headless=headless)
                else:
                    logger.error(f"Max retries exceeded. RuntimeError: {e}")
                    raise
        return []


# Convenience module-level functions for CLI and simple scripting
def authenticate(
    username: str | None = None,
    password: str | None = None,
    base_url: str | None = None,
    auth_state_path: Path | None = None,
    headless: bool = False,
) -> bool:
    """Authenticate to Gradescope using Playwright and persist session state.

    Args:
        username: Username to log in with. If None, attempts to load from environment.
        password: Password for login. If None, attempts to load from environment.
        base_url: Override base URL for Gradescope.
        auth_state_path: Path to save authentication state JSON.
        headless: Run browser headless; default False for interactive login.

    Returns:
        True on success, False otherwise.
    """
    client = GradescopeClient(base_url=base_url, auth_state_path=auth_state_path)
    return client.authenticate(username=username, password=password, headless=headless)


def sync_roster(
    course: str,
    notify: bool = True,
    headless: bool = True,
    base_url: str | None = None,
    auth_state_path: Path | None = None,
) -> bool:
    """Synchronize the course roster with the linked LMS.

    Args:
        course: Gradescope course ID or URL to the course home page
        notify: notify added users
        headless: Run browser headless; default True for automation.
        base_url: Override base URL for Gradescope.
        auth_state_path: Path to stored authentication state JSON.

    Returns:
        True on success, False otherwise.
    """
    client = GradescopeClient(base_url=base_url, auth_state_path=auth_state_path)
    return client.sync_roster(course=course, notify=notify, headless=headless)


def fetch_class_details(
    course_name: str,
    term: str | Term,
    username: str | None = None,
    password: str | None = None,
    headless: bool = True,
    output: Path | None = None,
    base_url: str | None = None,
    auth_state_path: Path | None = None,
) -> list[dict]:
    """Fetch class details for a course offering and optionally save.

    Args:
        course_name: The course name to match in Gradescope.
        term: A term string (e.g., "Fall 2025") or `Term`.
        username: Username to log in with. If None, attempts to load from environment.
        password: Password for login. If None, attempts to load from environment.
        headless: Run browser headless; default True for automation.
        output: Path to save output JSON; if None, doesn't save.
        base_url: Override base URL for Gradescope.
        auth_state_path: Path to stored authentication state JSON.

    Returns:
        List of dictionaries with class details.
    """
    client = GradescopeClient(base_url=base_url, auth_state_path=auth_state_path)
    return client.fetch_class_details(
        course_name=course_name,
        term=term,
        username=username,
        password=password,
        headless=headless,
        output=output,
    )


def save_roster(
    course: str,
    save_dir: Path | None = None,
    headless: bool = True,
    base_url: str | None = None,
    auth_state_path: Path | None = None,
) -> Path:
    """Fetch and save the roster for a class on Gradescope.

    Args:
        course: Gradescope course ID or URL to the course home page
        save_dir: target directory of the saved roster file (default: current working directory)
        headless: Run browser headless; default True for automation.
        base_url: Override base URL for Gradescope.
        auth_state_path: Path to stored authentication state JSON.

    Returns:
        Path to the saved roster file.
    """
    client = GradescopeClient(base_url=base_url, auth_state_path=auth_state_path)
    return client.save_roster(course=course, save_dir=save_dir, headless=headless)
