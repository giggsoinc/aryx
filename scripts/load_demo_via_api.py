#!/usr/bin/env python3
"""Load support demo data via Aryx API endpoint.

Usage:
  python3 scripts/load_demo_via_api.py --api-url http://localhost:8000 --tickets 200
"""
from __future__ import annotations

import argparse
import json
import sys

import requests


def main():
    """Load demo data via the API."""
    parser = argparse.ArgumentParser(description="Load Aryx support demo data")
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="Base URL of Aryx API (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--tickets",
        type=int,
        default=200,
        help="Number of tickets to generate (default: 200)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        default=True,
        help="Clean existing demo data before loading (default: True)",
    )
    args = parser.parse_args()

    url = f"{args.api_url}/api/demo/load"
    payload = {
        "ticket_count": args.tickets,
        "clean_first": args.clean,
    }

    print(f"📤 Loading demo data...")
    print(f"   URL: {url}")
    print(f"   Tickets: {args.tickets}")
    print(f"   Clean first: {args.clean}")

    try:
        response = requests.post(url, json=payload, timeout=300)
        response.raise_for_status()
        data = response.json()

        print(f"\n✅ Success!")
        print(f"\nLoaded data:")
        for table, count in data.get("rows_created", {}).items():
            print(f"   {table:20s} {count:4d}")

        print(f"\n📝 Message: {data.get('message', '')}")
        print(f"⏰ Timestamp: {data.get('timestamp', '')}")

        return 0

    except requests.exceptions.RequestException as e:
        print(f"\n❌ Error: {e}")
        if hasattr(e, "response") and e.response is not None:
            try:
                print(f"   Response: {e.response.json()}")
            except Exception:
                print(f"   Response text: {e.response.text}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
