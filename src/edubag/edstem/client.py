"""Module to automate interactions with the EdSTEM platform."""

import os
from pathlib import Path

import platformdirs
from dotenv import load_dotenv
from loguru import logger
from playwright.sync_api import sync_playwright

from edubag.clients import LMSClient


class EdstemClient(LMSClient):
    """Client to interact with the EdSTEM platform.

    This client provides automated browser-based interactions with EdSTEM
    for downloading analytics files and other course management tasks.

    Note on headless parameter:
        Methods that accept `headless` parameter default to:
        - `False` for `authenticate()` - interactive login may require manual steps
        - `True` for other operations - automated operations benefit from headless mode
    """

    base_url = "https://edstem.org/us/"

    @staticmethod
    def _default_auth_state_path() -> Path:
        """Get the platform-appropriate default path for the auth state file."""
        cache_dir = Path(platformdirs.user_cache_dir("edubag", "NYU"))
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / "edstem_auth.json"

    def __init__(self, base_url: str | None = None, auth_state_path: Path | None = None):
        """Initializes the EdstemClient."""
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
    ) -> None:
        """Log into EdSTEM and save the authentication state.

        EdSTEM uses a two-step login: first enter email and click "Continue",
        then enter password and click "Log in".

        Args:
            username (str | None): Email address to log in with. If None, user must enter manually in browser.
            password (str | None): Password for login. If None, user must enter manually in browser.
            headless (bool): Whether to run the browser in headless mode. Headless mode requires username and password.

        Raises:
            RuntimeError: If authentication fails.
        """
        load_dotenv()

        if username is None:
            username = os.getenv("EDSTEM_USERNAME")
        if password is None:
            password = os.getenv("EDSTEM_PASSWORD")

        if username is None or password is None:
            headless = False

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context()
            page = context.new_page()

            page.goto(self.base_url)
            page.wait_for_load_state("domcontentloaded", timeout=10000)

            if username is not None:
                page.get_by_role("textbox", name="Email").fill(username)
                page.get_by_role("button", name="Continue").click()

                page.get_by_role("textbox", name="Password").wait_for(state="visible", timeout=10000)

                if password is not None:
                    page.get_by_role("textbox", name="Password").fill(password)
                    page.get_by_role("button", name="Log in").click()
                else:
                    print("Please enter your password in the browser window.")
            else:
                print("Please enter your email and password in the browser window.")

            # Wait for successful login (redirect away from login page)
            page.wait_for_url("**/courses**", timeout=60000)

            context.storage_state(path=self.auth_state_path)
            logger.debug(f"Authentication state saved at {self.auth_state_path}")

            browser.close()

    def _save_analytics_session(
        self,
        course: str,
        save_dir: Path | None = None,
        headless: bool = True,
    ) -> Path:
        """Internal method to save analytics CSV in a single browser session.

        Raises RuntimeError if authentication has expired.
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(storage_state=self.auth_state_path, accept_downloads=True)
            page = context.new_page()

            course_url = self.base_url.rstrip("/") + "/courses/" + course
            page.goto(course_url)

            # Check if we need to re-login
            if "login" in page.url:
                logger.error("Authentication session expired. Please re-authenticate.")
                browser.close()
                raise RuntimeError("Authentication session expired.")

            page.wait_for_load_state("domcontentloaded", timeout=10000)

            page.get_by_role("link", name="Analytics").click()
            page.wait_for_load_state("networkidle", timeout=15000)

            with page.expect_download() as download_info:
                page.get_by_role("button", name="Analytics CSV").click()
            download = download_info.value

            if save_dir is not None:
                save_dir.mkdir(parents=True, exist_ok=True)
                download_file_path = save_dir / download.suggested_filename
            else:
                download_file_path = Path(download.suggested_filename)

            logger.info(f"Downloading analytics to {download_file_path}")
            download.save_as(download_file_path)

            browser.close()
        return download_file_path

    def save_analytics(
        self,
        course: str,
        save_dir: Path | None = None,
        headless: bool = True,
    ) -> list[Path]:
        """Fetch and save the analytics CSV for a course on EdSTEM.

        Args:
            course: EdSTEM course ID.
            save_dir: Target directory for the saved analytics file (default: current working directory).
            headless (bool): Whether to run the browser in headless mode.

        Returns:
            list[Path]: List containing the path to the saved analytics file.

        Raises:
            RuntimeError: If analytics download fails or authentication expired.
        """
        if not self.auth_state_path.exists():
            logger.warning(f"Auth state file not found at {self.auth_state_path}. Running authentication...")
            self.authenticate(headless=headless)

        max_retries = 1
        for attempt in range(max_retries + 1):
            try:
                result_path = self._save_analytics_session(course, save_dir, headless)
                return [result_path]
            except RuntimeError as e:
                if attempt < max_retries:
                    logger.warning(f"RuntimeError: {e} Authentication may have expired.")
                    logger.info("Re-authenticating...")
                    self.auth_state_path.unlink(missing_ok=True)
                    self.authenticate(headless=headless)
                    continue
                else:
                    logger.error(f"Max retries exceeded. RuntimeError: {e}")
                    raise
