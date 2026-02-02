#!/usr/bin/env python3
"""Entry point for running the Slack bot."""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import LOG_FILE, LOG_LEVEL, ensure_directories, validate_config


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run the Hani Replica Slack bot")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate configuration, don't start bot",
    )

    args = parser.parse_args()

    # Ensure directories exist
    ensure_directories()

    # Configure logging
    log_level = logging.DEBUG if args.debug else getattr(logging, LOG_LEVEL)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_FILE),
        ],
    )
    logger = logging.getLogger(__name__)

    # Validate configuration
    issues = validate_config()
    if issues:
        logger.warning("Configuration issues:")
        for issue in issues:
            logger.warning(f"  - {issue}")

        # Check for critical issues (Slack tokens)
        critical = [i for i in issues if "SLACK" in i]
        if critical:
            logger.error("Cannot start bot: Slack tokens are required")
            sys.exit(1)

    if args.validate_only:
        if issues:
            print("Configuration has issues (see above)")
            sys.exit(1)
        else:
            print("Configuration is valid!")
            sys.exit(0)

    # Import and run bot
    from src.bot.app import run_bot

    logger.info("Starting Hani Replica Slack bot...")
    logger.info(f"Log file: {LOG_FILE}")

    try:
        run_bot()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
