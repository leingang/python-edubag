"""Module to automate interactions with the Albert learning platform."""

from pathlib import Path
import re
from datetime import date

from playwright.sync_api import sync_playwright
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

    def authenticate(self, headless=False) -> bool:
        """Log into Albert and save the authentication state.

        You will need to manually complete the login and MFA process.

        Args:
            headless (bool): Whether to run the browser in headless mode.

        Returns:
            bool: True if authentication was successful, False otherwise.
        """
        # Placeholder for login logic
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context()
            page = context.new_page()

            page.goto(self.base_url)

            print("Log in manually and complete MFA.")
            page.wait_for_url(
                "**/h/?tab=IS_FSA_TAB", timeout=60000
            )  # adjust to post-login URL

            context.storage_state(path=self.auth_state_path)
            logger.debug(f"Authentication state saved at {self.auth_state_path}")

            browser.close()
        return True

    def fetch_and_save_rosters(
        self,
        course_name: str,
        term: str | Term,
        save_path: Path | None = None,
        headless: bool = True,
    ) -> list[Path]:
        """Fetch from the network and save to disk the class rosters for a given
        course offering.

        Args:
          * course_name (str): The name of the course. 
          * term (str | Term): The term of the course. 
          * save_path (Path | None): Directory to save the rosters. If None,
            uses default directory. 
          * headless (bool): Whether to run the browser in headless mode.

        Returns:
            List[Path]: List of paths to the downloaded roster files.
        """
        # Check if authentication state exists; if not, authenticate first
        if not self.auth_state_path.exists():
            logger.warning(f"Auth state file not found at {self.auth_state_path}. Running authentication...")
            self.authenticate(headless=False)
        
        result_paths = []
        with sync_playwright() as p:
            # Change to headless=True for non-UI mode
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(
                storage_state=self.auth_state_path, accept_downloads=True
            )
            page = context.new_page()

            page.goto(self.base_url)
            if "login" in page.url:
                logger.error("Not authenticated. Please run authenticate() first.")
                return []
            page.locator("#IS_FSA_SchWrp").get_by_role("link", name=str(term)).click()
            # https://playwright.dev/python/docs/api/class-page#page-wait-for-load-state
            # says this is discouraged, but I haven't found a better way to ensure the
            # page is loaded
            page.wait_for_load_state("networkidle")

            # Paginate through all course listing pages
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
                    with page.expect_popup() as popup_info:
                        course.get_by_role("link", name="Class Roster").click()
                    roster_page = popup_info.value
                    # Clicking the link opens a page that immediately redirects;
                    # wait for the redirect to complete
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
                    result_paths.append(download_file_path)
                    roster_page.close()
                
                # Check if there's a next page button and click it
                next_button = page.locator(".isFSA_PNext")
                if next_button.count() > 0 and next_button.is_visible():
                    logger.debug("Navigating to next page of courses")
                    next_button.click()
                    page.wait_for_load_state("networkidle")
                else:
                    # No more pages, exit the loop
                    break
            
            browser.close()
        return result_paths


# Convenience module-level functions for CLI and simple scripting
def authenticate(
    base_url: str | None = None,
    auth_state_path: Path | None = None,
    headless: bool = False,
) -> bool:
    """Authenticate to Albert using Playwright and persist session state.

    Args:
        base_url: Override base URL for Albert.
        auth_state_path: Path to save authentication state JSON.
        headless: Run browser headless; default False for interactive login.

    Returns:
        True on success, False otherwise.
    """
    client = AlbertClient(base_url=base_url, auth_state_path=auth_state_path)
    return client.authenticate(headless=headless)


def fetch_and_save_rosters(
    course_name: str,
    term: str | Term,
    save_path: Path | None = None,
    headless: bool = True,
    base_url: str | None = None,
    auth_state_path: Path | None = None,
) -> list[Path]:
    """Fetch rosters and save them to disk using stored auth state.

    Args:
        course_name: The course name to match in Albert.
        term: A term string (e.g., "Fall 2025") or `Term`.
        save_path: Directory to save roster files; defaults to CWD.
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
        headless=headless,
    )
