#!/usr/bin/env python3
"""AI Morning Brief — entry point."""
import argparse
import logging

from src.orchestrator import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Morning Brief")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run pipeline but print digest instead of sending to Discord",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    run_pipeline(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
