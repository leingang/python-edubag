"""Module to automate interactions with the Brightspace learning platform."""

from pathlib import Path

import platformdirs
from loguru import logger
from playwright.sync_api import sync_playwright


class BrightspaceClient:
    """Client to interact with the Brightspace learning platform."""

    @staticmethod
    def _default_auth_state_path() -> Path:
        """Get the platform-appropriate default path for the auth state file."""
        cache_dir = Path(platformdirs.user_cache_dir("edubag", "NYU"))
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / "brightspace_auth.json"

    def __init__(self, base_url: str | None = None, auth_state_path: Path | None = None):
        """Initializes the BrightspaceClient."""
        if base_url is not None:
            self.base_url = base_url
        else:
            self.base_url = "https://brightspace.nyu.edu/"
        if auth_state_path is not None:
            self.auth_state_path = auth_state_path
        else:
            self.auth_state_path = self._default_auth_state_path()

    def authenticate(self, username: str | None = None, password: str | None = None, headless: bool = False) -> bool:
        """Log into Brightspace and save the authentication state.

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
            username_field = page.locator("input[type='email']")

            if username is not None:
                username_field.fill(username)
                page.get_by_role("button", name="Next").click()
                page.wait_for_load_state("domcontentloaded", timeout=10000)
                page.locator("input[type='password']").wait_for(state="visible", timeout=10000)
                password_field = page.locator("input[type='password']")

                if password is not None:
                    # Wait for password field to appear
                    password_field.fill(password)
                    page.get_by_role("button", name="Sign in").click()
                    page.get_by_role("button", name="Approve with MFA (Duo)‎ You").click()
                else:
                    # interactive mode: focus password field and wait for user to enter password
                    password_field.click()
                    print("Please enter your password in the browser window and complete MFA.")
            else:
                # interactive mode: focus username field and wait for user to enter credentials
                username_field.click()
                print("Please enter your username and password in the browser window, then complete MFA.")

            # Wait for the Brightspace home page to load after successful login
            page.wait_for_url("**/d2l/home**", timeout=60000)

            context.storage_state(path=self.auth_state_path)
            logger.debug(f"Authentication state saved at {self.auth_state_path}")

            browser.close()
        return True

    def _save_gradebook_session(
        self,
        course: str,
        save_dir: Path | None = None,
        headless: bool = True,
    ) -> list[Path]:
        """Internal method to save gradebook in a single browser session.

        Raises RuntimeError if authentication has expired.
        """
        result_paths = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(storage_state=self.auth_state_path, accept_downloads=True)
            page = context.new_page()

            # Navigate to the course page
            # Determine if course is a full URL or just an ID
            if course.startswith("http://") or course.startswith("https://"):
                course_url = course
            else:
                course_url = f"{self.base_url}d2l/home/{course}"
            page.goto(course_url)

            # Check if we need to re-login
            if "login" in page.url:
                logger.error("Authentication session expired. Please re-authenticate.")
                browser.close()
                raise RuntimeError("Authentication session expired.")

            # Navigate to Grades
            page.get_by_role("link", name="Grades").click()
            page.get_by_role("link", name="Enter Grades  selected").click()

            # Export gradebook
            page.get_by_role("button", name="Export").click()
            page.get_by_role("checkbox", name="Points grade").check()
            page.get_by_role("checkbox", name="Last Name").check()
            page.get_by_role("checkbox", name="First Name").check()
            page.get_by_role("checkbox", name="Email").check()
            page.get_by_role("checkbox", name="Section Membership").check()
            page.get_by_role("checkbox", name="Select all rows").check()
            page.get_by_role("button", name="Export to CSV").click()

            with page.expect_download() as download_info:
                page.get_by_role("button", name="Download").click()
            download = download_info.value

            # Save the download
            if save_dir is not None:
                save_dir.mkdir(parents=True, exist_ok=True)
                download_file_path = save_dir / download.suggested_filename
            else:
                download_file_path = Path(download.suggested_filename)
            logger.info(f"Downloading gradebook to {download_file_path}")
            download.save_as(download_file_path)
            result_paths.append(download_file_path)

            page.get_by_role("button", name="Close").click()

            browser.close()
        return result_paths

    def save_gradebook(
        self,
        course: str,
        save_dir: Path | None = None,
        headless: bool = True,
    ) -> list[Path]:
        """Fetch from the network and save to disk the complete gradebook for a given
        course offering.

        Args:
          * course: The course ID or full URL to the course
          * save_dir: directory to save the file in (default: current working directory)
          * headless: Whether to run the browser in headless mode

        Returns:
            list[Path]: Paths to the downloaded gradebook files.
        """
        # Ensure authentication state exists; trigger a login flow if missing
        if not self.auth_state_path.exists():
            logger.warning(
                f"Auth state file not found at {self.auth_state_path}. Running authentication..."
            )
            self.authenticate(headless=headless)

        max_retries = 1
        for attempt in range(max_retries + 1):
            try:
                return self._save_gradebook_session(course, save_dir, headless)
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
        return []

    def _save_attendance_session(
        self,
        course: str,
        save_dir: Path | None = None,
        headless: bool = True,
    ) -> list[Path]:
        """Internal method to save attendance in a single browser session.

        Raises RuntimeError if authentication has expired.
        """
        result_paths = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(storage_state=self.auth_state_path, accept_downloads=True)
            page = context.new_page()

            # Navigate to the course page
            # Determine if course is a full URL or just an ID
            if course.startswith("http://") or course.startswith("https://"):
                course_url = course
            else:
                course_url = f"{self.base_url}d2l/home/{course}"
            page.goto(course_url)

            # Check if we need to re-login
            if "login" in page.url:
                logger.error("Authentication session expired. Please re-authenticate.")
                browser.close()
                raise RuntimeError("Authentication session expired.")

            # Navigate to Attendance
            page.get_by_role("button", name="More Tools").click()
            page.get_by_role("link", name="Attendance").click()
            page.wait_for_load_state("domcontentloaded", timeout=10000)

            # Exit early if there are no attendance registers available
            empty_state = page.locator(".empty-state-container").first
            if empty_state.is_visible():
                logger.info("No attendance registers available; nothing to download.")
                browser.close()
                return result_paths

            # Process each attendance register
            attendance_links = page.get_by_title("View attendance data in ").all()
            if not attendance_links:
                logger.info("No attendance registers found; nothing to download.")
                browser.close()
                return result_paths
            for loc in attendance_links:
                loc.click()
                page.wait_for_load_state("domcontentloaded", timeout=10000)
                # Get the attendance name from the h1 heading
                attendance_name = page.locator("h1").inner_text()
                logger.info(f"Processing {attendance_name}")
                logger.debug(f"Processing attendance register at {page.url}")
                page.get_by_role("button", name="Export All Data").click()

                with page.expect_download() as download2_info:
                    # Download link lives inside the export dialog iframe; target it directly
                    iframe = page.frame_locator("iframe[title='Export Attendance Data']").first
                    download_link = iframe.locator(".dfl a").first
                    download_link.wait_for(state="visible", timeout=10000)
                    download_link.click()
                download2 = download2_info.value

                # Save the download
                if save_dir is not None:
                    save_dir.mkdir(parents=True, exist_ok=True)
                    download_file_path = save_dir / download2.suggested_filename
                else:
                    download_file_path = Path(download2.suggested_filename)
                logger.info(f"Downloading attendance register to {download_file_path}")
                download2.save_as(download_file_path)
                result_paths.append(download_file_path)

                page.get_by_role("button", name="Close").click()
                page.get_by_role("button", name="Done").click()

            browser.close()
        return result_paths

    def save_attendance(
        self,
        course: str,
        save_dir: Path | None = None,
        headless: bool = True,
    ) -> list[Path]:
        """Fetch from the network and save to disk the attendance registers for a given
        course offering.

        Args:
          * course: The course ID or full URL to the course
          * save_dir: directory to save the file in (default: current working directory)
          * headless: Whether to run the browser in headless mode

        Returns:
            list[Path]: Paths to the downloaded attendance register files.
        """
        # Ensure authentication state exists; trigger a login flow if missing
        if not self.auth_state_path.exists():
            logger.warning(
                f"Auth state file not found at {self.auth_state_path}. Running authentication..."
            )
            self.authenticate(headless=headless)

        max_retries = 1
        for attempt in range(max_retries + 1):
            try:
                return self._save_attendance_session(course, save_dir, headless)
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
        return []


# Convenience module-level functions for CLI and simple scripting
def authenticate(
    username: str | None = None,
    password: str | None = None,
    base_url: str | None = None,
    auth_state_path: Path | None = None,
    headless: bool = False,
) -> bool:
    """Authenticate to Brightspace using Playwright and persist session state.

    Args:
        username: NetID to log in with. If None, user must enter manually in browser.
        password: Password for login. If None, user must enter manually in browser.
        base_url: Override base URL for Brightspace.
        auth_state_path: Path to save authentication state JSON.
        headless: Run browser headless; default False for interactive login.

    Returns:
        True on success, False otherwise.
    """
    client = BrightspaceClient(base_url=base_url, auth_state_path=auth_state_path)
    return client.authenticate(username=username, password=password, headless=headless)


def save_gradebook(
    course: str,
    save_dir: Path | None = None,
    headless: bool = True,
    base_url: str | None = None,
    auth_state_path: Path | None = None,
) -> list[Path]:
    """Fetch and save the gradebook for a course using stored auth state.

    Args:
        course: The course ID or full URL to the course
        save_dir: directory to save the file in (default: current working directory)
        headless: Run browser headless; default True for automation.
        base_url: Override base URL for Brightspace.
        auth_state_path: Path to stored authentication state JSON.

    Returns:
        List of saved file paths.
    """
    client = BrightspaceClient(base_url=base_url, auth_state_path=auth_state_path)
    return client.save_gradebook(course=course, save_dir=save_dir, headless=headless)


def save_attendance(
    course: str,
    save_dir: Path | None = None,
    headless: bool = True,
    base_url: str | None = None,
    auth_state_path: Path | None = None,
) -> list[Path]:
    """Fetch and save the attendance registers for a course using stored auth state.

    Args:
        course: The course ID or full URL to the course
        save_dir: directory to save the file in (default: current working directory)
        headless: Run browser headless; default True for automation.
        base_url: Override base URL for Brightspace.
        auth_state_path: Path to stored authentication state JSON.

    Returns:
        List of saved file paths.
    """
    client = BrightspaceClient(base_url=base_url, auth_state_path=auth_state_path)
    return client.save_attendance(course=course, save_dir=save_dir, headless=headless)
