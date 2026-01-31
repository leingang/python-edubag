#!/usr/bin/env python
"""
Template script for debugging mark_engaged functionality.

This script demonstrates how to test the mark_engaged method with live Albert data.
To use this template:

1. Copy it to debug_mark_engaged.py
2. Update CLASS_NUMBER and TERM with values from your Albert instance
3. Update TEST_EMAILS with student email addresses from the target class
4. Ensure credentials are available in environment or keychain
5. Run: .venv/bin/python tests/debug_mark_engaged.py

This file is not committed to git. Keep real data in the copied version only.
"""

from pathlib import Path
import os
import sys

from dotenv import load_dotenv
from loguru import logger
import keyring

# Load environment variables from .env file
load_dotenv()

# Import edubag modules
try:
    from edubag.albert.client import AlbertClient
    EDUBAG_AVAILABLE = True
except ImportError as e:
    logger.error(f"edubag module not available: {e}")
    EDUBAG_AVAILABLE = False
    sys.exit(1)

# ============================================================================
# CONFIGURATION - Update these with your test data
# ============================================================================

# Class number from Albert (check Admin > Class Search)
CLASS_NUMBER = 12345

# Academic term (e.g., "Spring 2026", "Fall 2025")
TERM = "Spring 2026"

# Student email addresses to mark as engaged (use a small subset for testing)
TEST_EMAILS = [
    "student1@nyu.edu",
    "student2@nyu.edu",
    "student3@nyu.edu",
]

# ============================================================================


def get_password(service: str, username: str) -> str | None:
    """Get password from macOS Keychain."""
    try:
        logger.debug(f"Attempting to retrieve password from keychain for {service}/{username}")
        password = keyring.get_password(service, username)
        if password:
            logger.debug(f"Successfully retrieved password from keychain for {service}/{username}")
            return password
    except Exception as e:
        logger.error(f"Failed to retrieve password from keychain: {e}")
    return None


def main():
    """Main debug function."""
    logger.remove()  # Remove default handler
    logger.add(sys.stderr, format="{time} | {level: <8} | {name}:{function}:{line} - {message}")

    logger.info("=" * 80)
    logger.info("DEBUG: Testing mark_engaged with specific emails")
    logger.info("=" * 80)

    logger.info(f"Class Number: {CLASS_NUMBER}")
    logger.info(f"Term: {TERM}")
    logger.info(f"Number of emails to test: {len(TEST_EMAILS)}")
    logger.info("Emails:")
    for i, email in enumerate(TEST_EMAILS, 1):
        logger.info(f"  {i}. {email}")

    logger.info("")
    logger.info("Retrieving credentials from environment and keychain...")

    # Get SSO username
    username = os.getenv("SSO_USERNAME")
    if not username:
        logger.error("SSO_USERNAME not found in environment")
        return

    logger.info(f"Using SSO username: {username}")

    # Get password from keychain
    password = get_password("nyu-sso", username)
    if not password:
        logger.error("Password not found in keychain for nyu-sso")
        logger.info("Add it with: security add-generic-password -s nyu-sso -a <username> -w <password>")
        return

    logger.info("")
    logger.info("Creating AlbertClient...")
    albert_client = AlbertClient()
    logger.success("AlbertClient created")

    logger.info("Note: mark_engaged should handle authentication internally")

    logger.info("")
    logger.info("Attempting to mark students as engaged...")
    logger.info("This will open a browser window (headless=False) for debugging")

    try:
        result = albert_client.mark_engaged(
            CLASS_NUMBER,
            TERM,
            TEST_EMAILS,
            headless=False,
            username=username,
            password=password,
        )
        logger.success("mark_engaged completed")
        logger.info(f"Result: {result}")
    except Exception as e:
        logger.error(f"mark_engaged failed: {e}")
        logger.debug(f"Traceback:\n{e.__traceback__}")
        return

    logger.info("")
    logger.info("=" * 80)
    logger.info("Debug script completed")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
