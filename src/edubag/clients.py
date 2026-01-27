"""Base classes and protocols for LMS client implementations.

This module defines the common interface that all LMS clients should implement,
ensuring consistency across different learning management system integrations.
"""

from abc import ABC, abstractmethod
from pathlib import Path


class LMSClient(ABC):
    """Abstract base class for LMS (Learning Management System) clients.

    All client implementations (Albert, Brightspace, Gradescope, etc.) should
    inherit from this class and implement the required abstract methods.

    Attributes:
        base_url: The base URL for the LMS platform
        auth_state_path: Path to the authentication state file for session persistence

    Note on `headless` parameter:
        Most methods accept a `headless` parameter that controls browser visibility:
        - `authenticate()`: defaults to `False` (headed mode) because authentication
          typically requires interactive steps like MFA, password entry, or CAPTCHA
        - Other operations (save_*, fetch_*, etc.): default to `True` (headless mode)
          because these are typically automated operations that benefit from running
          in the background without a visible browser window
    """

    base_url: str
    auth_state_path: Path

    @abstractmethod
    def authenticate(
        self,
        username: str | None = None,
        password: str | None = None,
        headless: bool = False,
    ) -> bool:
        """Authenticate to the LMS platform and save session state.

        Args:
            username: Username/NetID for login. If None, user must enter manually.
            password: Password for login. If None, user must enter manually.
            headless: Run browser in headless mode. Defaults to False because
                authentication typically requires interactive steps (MFA, etc.).

        Returns:
            True if authentication was successful, False otherwise.

        Note:
            Authentication state is persisted to `self.auth_state_path` for reuse
            in subsequent operations without requiring re-authentication.
        """
        ...

    @staticmethod
    @abstractmethod
    def _default_auth_state_path() -> Path:
        """Get the platform-appropriate default path for the auth state file.

        Returns:
            Path to the default authentication state file location.
        """
        ...
