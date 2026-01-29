#!/usr/bin/env python3
"""
Generate .env file with Calibre library paths for testing.

Run via: calibre-debug scripts/build_env.py
"""

import os
import sys


def main():
    env_lines = []

    # Get Calibre library path
    library_path = os.environ.get("CALIBRE_LIBRARY_PATH", "")
    if library_path:
        env_lines.append(f"CALIBRE_LIBRARY_PATH={library_path}")

    # Get Calibre resources path
    resources_path = getattr(sys, "resources_location", "")
    if resources_path:
        env_lines.append(f"CALIBRE_RESOURCES_PATH={resources_path}")

    # Get Calibre extensions path
    extensions_path = getattr(sys, "extensions_location", "")
    if extensions_path:
        env_lines.append(f"CALIBRE_EXTENSIONS_PATH={extensions_path}")

    if env_lines:
        with open(".env", "w") as f:
            f.write("\n".join(env_lines) + "\n")
        print(f"Wrote .env with {len(env_lines)} variables")
    else:
        print("No Calibre paths found - run with calibre-debug")


if __name__ == "__main__":
    main()
