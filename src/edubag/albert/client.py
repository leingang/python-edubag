"""Module to automate interactions with the Albert learning platform."""

from pathlib import Path
import re
from datetime import date
from typing import Generator

from playwright.sync_api import sync_playwright, Page, Locator
from loguru import logger
import platformdirs

from edubag.albert.term import Term


class AlbertClient:
    """Client to interact with the Albert learning platform."""

    base_url = "https://sis.portal.nyu.edu/psp/ihprod/EMPLOYEE/EMPL/?cmd=start"
    
    @staticmethod
    def _default_auth_state_path() -> Path:
        """Get the platform-appropriate default path for the auth state file."""
        cache_dir = Path(platformdirs.user_cache_dir("edubag", "NYU"))
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / "albert_auth.json"

    def __init__(
        self, base_url: str | None = None, auth_state_path: Path | None = None
    ):
        """Initializes the AlbertClient."""
        if base_url is not None:
            self.base_url = base_url
        if auth_state_path is not None:
            self.auth_state_path = auth_state_path
        else:
            self.auth_state_path = self._default_auth_state_path()

    def authenticate(self, username: str | None = None, password: str | None = None, headless=False) -> bool:
        """Log into Albert and save the authentication state.

        Args:
            username (str | None): NetID to log in with. If None, user must enter manually in browser.
            password (str | None): Password for login. If None, user must enter manually in browser.
            headless (bool): Whether to run the browser in headless mode. Headless mode requires username and password.

        Returns:
            bool: True if authentication was successful, False otherwise.
        """
        if username is None or password is None:
            headless = False
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context()
            page = context.new_page()

            page.goto(self.base_url)

            # Wait for page to load and form to appear instead of URL (SAML can redirect)
            page.wait_for_load_state("domcontentloaded", timeout=10000)
            # Wait for the username input field to appear and be visible
            page.locator("input[type='email']").wait_for(state="visible", timeout=10000)
            
            if username is not None:
                page.locator("input[type='email']").fill(username)
                page.get_by_role("button", name="Next").click()
                
                if password is not None:
                    # Wait for password field to appear
                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                    page.locator("input[type='password']").wait_for(state="visible", timeout=10000)
                    page.locator("input[type='password']").fill(password)
                    page.get_by_role("button", name="Sign in").click()
                    page.get_by_role("button", name="Approve with MFA (Duo)‎ You").click()
                else:
                    print("Please enter your password in the browser window and complete MFA.")
            else:
                print("Please enter your username and password in the browser window, then complete MFA.")
            
            page.wait_for_url(
                "**/h/?tab=IS_FSA_TAB", timeout=60000
            )  # adjust to post-login URL

            context.storage_state(path=self.auth_state_path)
            logger.debug(f"Authentication state saved at {self.auth_state_path}")

            browser.close()
        return True

    def _get_courses_paginated(self, page: Page, course_name: str) -> Generator[Locator, None, None]:
        """Iterator that yields course locators across all pages with pagination.
        
        Args:
            page: The Playwright page object.
            course_name: The name of the course to filter by.
            
        Yields:
            Course locators matching the course name across all pages.
        """
        while True:
            courses = (
                page.locator(
                    "div.isFSA_SchCrsWrp",
                    has=page.get_by_role("heading", name=course_name),
                )
                .locator("visible=true")
                .all()
            )
            for course in courses:
                yield course
            
            # Check if there's a next page button and click it
            next_button = page.locator(".isFSA_PNext")
            if next_button.count() > 0 and next_button.is_visible():
                logger.debug("Navigating to next page of courses")
                next_button.click()
                page.wait_for_load_state("networkidle")
            else:
                break

    def _save_roster_for_course(self, course: Locator, save_path: Path | None = None) -> Path:
        """Process a course and save its roster.
        
        Args:
            course: A course locator element.
            save_path: Directory to save the roster. If None, saves to current directory.
            
        Returns:
            Path to the saved roster file.
        """
        with course.page.expect_popup() as popup_info:
            course.get_by_role("link", name="Class Roster").click()
        roster_page = popup_info.value
        roster_page.wait_for_url(re.compile(r".*PortalActualURL=.*"))
        section_name = roster_page.locator("#DERIVED_SSR_FC_CLASS_SECTION").text_content()
        section_name = section_name.strip() if section_name else ""
        logger.info(f"Processing roster for section: {section_name}")
        roster_page.get_by_label("Print/Download Options").select_option("EXL")
        with roster_page.expect_download() as download_info:
            with roster_page.expect_popup():
                roster_page.get_by_role("button", name="Generate").click()
        download = download_info.value
        if save_path is not None:
            save_path.mkdir(parents=True, exist_ok=True)
            download_file_path = save_path / download.suggested_filename
        else:
            download_file_path = Path(download.suggested_filename)
        logger.info(f"Downloading roster to {download_file_path}")
        download.save_as(download_file_path)
        roster_page.close()
        return download_file_path

    def _fetch_rosters_session(
        self,
        course_name: str,
        term: str | Term,
        save_path: Path | None = None,
        headless: bool = True,
    ) -> list[Path]:
        """Internal method to fetch rosters in a single browser session.
        
        Raises TimeoutError if the session times out.
        Raises RuntimeError if authentication has expired.
        """
        result_paths = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(
                storage_state=self.auth_state_path, accept_downloads=True
            )
            page = context.new_page()

            page.goto(self.base_url)
            if "login" in page.url or "errorCode" in page.url:
                browser.close()
                raise RuntimeError("Authentication session expired.")
            
            try:
                page.locator("#IS_FSA_SchWrp").get_by_role("link", name=str(term)).click()
            except Exception as e:
                # The click failed - check if we got redirected to login
                error_message = str(e)
                current_url = page.url
                logger.debug(f"Click failed. Current URL: {current_url}")
                logger.debug(f"Error message: {error_message}")
                # Check both the current URL and the error message for login/auth failures
                if ("login" in current_url or "errorCode" in current_url or 
                    "errorCode=105" in error_message or "cmd=login" in error_message):
                    logger.info("Detected authentication failure in error message")
                    browser.close()
                    raise RuntimeError("Authentication session expired during navigation.") from e
                # If not a login redirect, re-raise the original exception
                logger.debug("Not an auth error, re-raising original exception")
                browser.close()
                raise
            
            page.wait_for_load_state("networkidle")

            # Process all courses across all pages
            for course in self._get_courses_paginated(page, course_name):
                download_path = self._save_roster_for_course(course, save_path)
                result_paths.append(download_path)
            
            browser.close()
        return result_paths

    def fetch_and_save_rosters(
        self,
        course_name: str,
        term: str | Term,
        save_path: Path | None = None,
        username: str | None = None,
        password: str | None = None,
        headless: bool = True,
    ) -> list[Path]:
        """Fetch from the network and save to disk the class rosters for a given
        course offering.

        Args:
          * course_name (str): The name of the course. 
          * term (str | Term): The term of the course. 
          * save_path (Path | None): Directory to save the rosters. If None,
            uses default directory.
          * username (str | None): NetID to log in with. If None, user must enter manually.
          * password (str | None): Password for login. If None, user must enter manually.
          * headless (bool): Whether to run the browser in headless mode.

        Returns:
            List[Path]: List of paths to the downloaded roster files.
        """
        # Check if authentication state exists; if not, authenticate first
        if not self.auth_state_path.exists():
            logger.warning(f"Auth state file not found at {self.auth_state_path}. Running authentication...")
            self.authenticate(username=username, password=password, headless=headless)
        
        max_retries = 1
        for attempt in range(max_retries + 1):
            try:
                return self._fetch_rosters_session(course_name, term, save_path, headless)
            except (TimeoutError, RuntimeError) as e:
                if attempt < max_retries:
                    logger.warning(f"{type(e).__name__}: {e} Authentication may have expired.")
                    logger.info("Re-authenticating...")
                    if self.auth_state_path.exists():
                        self.auth_state_path.unlink()
                    self.authenticate(username=username, password=password, headless=headless)
                else:
                    logger.error(f"Max retries exceeded. {type(e).__name__}: {e}")
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
    """Authenticate to Albert using Playwright and persist session state.

    Args:
        username: NetID to log in with. If None, user must enter manually in browser.
        password: Password for login. If None, user must enter manually in browser.
        base_url: Override base URL for Albert.
        auth_state_path: Path to save authentication state JSON.
        headless: Run browser headless; default False for interactive login.

    Returns:
        True on success, False otherwise.
    """
    client = AlbertClient(base_url=base_url, auth_state_path=auth_state_path)
    return client.authenticate(username=username, password=password, headless=headless)


def fetch_and_save_rosters(
    course_name: str,
    term: str | Term,
    save_path: Path | None = None,
    username: str | None = None,
    password: str | None = None,
    headless: bool = True,
    base_url: str | None = None,
    auth_state_path: Path | None = None,
) -> list[Path]:
    """Fetch rosters and save them to disk using stored auth state.

    Args:
        course_name: The course name to match in Albert.
        term: A term string (e.g., "Fall 2025") or `Term`.
        save_path: Directory to save roster files; defaults to CWD.
        username: NetID to log in with. If None, user must enter manually.
        password: Password for login. If None, user must enter manually.
        headless: Run browser headless; default True for automation.
        base_url: Override base URL for Albert.
        auth_state_path: Path to stored authentication state JSON.

    Returns:
        List of saved file paths.
    """
    client = AlbertClient(base_url=base_url, auth_state_path=auth_state_path)
    return client.fetch_and_save_rosters(
        course_name=course_name,
        term=term,
        save_path=save_path,
        username=username,
        password=password,
        headless=headless,
    )
