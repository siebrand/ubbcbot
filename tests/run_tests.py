#!/usr/bin/env python3

"""
Test runner for UBBC Bot
Executes all test modules in parallel using pytest-xdist
"""

import subprocess
import sys


def main():
    """Run all tests using pytest with parallel execution"""
    print("🧪 Running UBBC Bot Tests (Parallel)\n")

    # Check if pytest-xdist is installed
    import importlib.util

    if importlib.util.find_spec("xdist") is None:
        print("⚠️  pytest-xdist not found. Running sequentially.")
        cmd = [sys.executable, "-m", "pytest", "tests/"]
    else:
        # Use -n auto for all cores, loadscope for better distribution
        cmd = [sys.executable, "-m", "pytest", "-n", "auto", "--dist", "loadscope", "tests/"]

    try:
        # Run pytest
        result = subprocess.run(cmd, text=True)
        return result.returncode
    except KeyboardInterrupt:
        print("\n🛑 Tests interrupted.")
        return 130
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
