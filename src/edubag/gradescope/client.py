"""Module to automate interactions with the Gradescope platform."""

import os
from pathlib import Path

import platformdirs
from dotenv import load_dotenv
from loguru import logger
from playwright.sync_api import sync_playwright


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

    def authenticate(self, username: str | None = None, password: str | None = None, headless: bool = False) -> bool:
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

    def sync_roster(self, course_url: str, notify: bool = True, headless: bool = True) -> bool:
        """Synchronize the course roster with the linked LMS.

        Args:
            course_url: URL to the course home page on Gradescope
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
                more_button = page.get_by_role("button", name=" More")
                if more_button.count() > 0:
                    more_button.click()
                    page.wait_for_load_state("networkidle")

                # Click the Sync button (using inexact match on "Sync")
                page.get_by_role("button", name="Sync").first.click()
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

                # Wait for sync to complete
                page.wait_for_load_state("networkidle", timeout=30000)

                logger.info("Roster sync completed successfully")
                browser.close()
                return True

            except Exception as e:
                logger.error(f"Error during roster sync: {e}")
                browser.close()
                return False


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
    course_url: str,
    notify: bool = True,
    headless: bool = True,
    base_url: str | None = None,
    auth_state_path: Path | None = None,
) -> bool:
    """Synchronize the course roster with the linked LMS.

    Args:
        course_url: URL to the course home page on Gradescope
        notify: notify added users
        headless: Run browser headless; default True for automation.
        base_url: Override base URL for Gradescope.
        auth_state_path: Path to stored authentication state JSON.

    Returns:
        True on success, False otherwise.
    """
    client = GradescopeClient(base_url=base_url, auth_state_path=auth_state_path)
    return client.sync_roster(course_url=course_url, notify=notify, headless=headless)
