#!/usr/bin/env python3
"""Interactive OAuth setup for all Google accounts."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import GOOGLE_ACCOUNTS, GOOGLE_EMAILS
from src.integrations.google_auth import (
    check_all_accounts,
    get_google_token_path,
    revoke_credentials,
    run_oauth_flow,
)


def print_status():
    """Print authentication status for all accounts."""
    print("\n" + "=" * 60)
    print("Google Account Authentication Status")
    print("=" * 60)

    status = check_all_accounts()

    for account in GOOGLE_ACCOUNTS:
        email = GOOGLE_EMAILS.get(account, "unknown")
        token_path = get_google_token_path(account)
        authenticated = status.get(account, False)

        status_str = "✓ Authenticated" if authenticated else "✗ Not authenticated"
        token_exists = "token exists" if token_path.exists() else "no token"

        print(f"\n{account}:")
        print(f"  Email: {email}")
        print(f"  Status: {status_str}")
        print(f"  Token: {token_exists}")


def authenticate_account(account: str) -> bool:
    """Authenticate a single account.

    Returns:
        True if successful.
    """
    if account not in GOOGLE_ACCOUNTS:
        print(f"Unknown account: {account}")
        return False

    try:
        run_oauth_flow(account)
        print(f"\n✓ Successfully authenticated {account}")
        return True
    except Exception as e:
        print(f"\n✗ Failed to authenticate {account}: {e}")
        return False


def authenticate_all():
    """Authenticate all accounts interactively."""
    print("\nStarting OAuth flow for all accounts...")
    print("You will be prompted to sign in to each account in your browser.")
    print("Make sure to select the correct Google account for each!")
    print()

    results = {}
    for account in GOOGLE_ACCOUNTS:
        email = GOOGLE_EMAILS.get(account, "unknown")
        print(f"\n{'=' * 60}")
        print(f"Account: {account} ({email})")
        print(f"{'=' * 60}")

        response = input("Authenticate this account? [Y/n/skip] ").strip().lower()
        if response in ("n", "skip"):
            print("Skipping...")
            results[account] = False
            continue

        results[account] = authenticate_account(account)

    print("\n" + "=" * 60)
    print("Authentication Summary")
    print("=" * 60)
    for account, success in results.items():
        status = "✓" if success else "✗"
        print(f"  {status} {account}")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Google OAuth setup for Hani Replica"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show authentication status for all accounts",
    )
    parser.add_argument(
        "--account",
        type=str,
        choices=GOOGLE_ACCOUNTS,
        help="Authenticate a specific account",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Authenticate all accounts interactively",
    )
    parser.add_argument(
        "--revoke",
        type=str,
        choices=GOOGLE_ACCOUNTS,
        help="Revoke credentials for an account",
    )

    args = parser.parse_args()

    if args.status:
        print_status()
    elif args.account:
        authenticate_account(args.account)
    elif args.revoke:
        if revoke_credentials(args.revoke):
            print(f"Revoked credentials for {args.revoke}")
        else:
            print(f"No credentials found for {args.revoke}")
    elif args.all:
        authenticate_all()
    else:
        # Default: show status and offer to authenticate
        print_status()
        print()

        status = check_all_accounts()
        unauthenticated = [a for a, s in status.items() if not s]

        if unauthenticated:
            print(f"\n{len(unauthenticated)} account(s) need authentication.")
            response = input("Authenticate all unauthenticated accounts? [Y/n] ").strip().lower()
            if response != "n":
                for account in unauthenticated:
                    authenticate_account(account)
                print_status()
        else:
            print("\nAll accounts are authenticated!")


if __name__ == "__main__":
    main()
