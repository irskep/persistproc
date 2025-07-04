#!/usr/bin/env python3
"""Simple counter script for e2e tests.

Prints incrementing integers (starting at 1) once per 0.1 seconds.
Odd numbers -> stdout, even numbers -> stderr.

CLI options:
  --num-iterations N  If N >= 1, stop after printing N numbers. If N <= 0,
                      run forever.
  --exit-code CODE    Process exit code when finishing (default 0).
"""

from __future__ import annotations

import argparse
import sys
import time


def parse_args() -> argparse.Namespace:  # noqa: D401 – simple wrapper
    parser = argparse.ArgumentParser(description="Counter test script")
    parser.add_argument(
        "--num-iterations",
        type=int,
        default=10,
        help="Number of iterations before exiting (<=0 means run forever).",
    )
    parser.add_argument(
        "--exit-code",
        type=int,
        default=0,
        help="Exit code to use when the script terminates.",
    )
    return parser.parse_args()


def main() -> None:  # noqa: D401
    args = parse_args()

    iteration = 1
    try:
        while args.num_iterations <= 0 or iteration <= args.num_iterations:
            target = sys.stdout if iteration % 2 == 1 else sys.stderr
            print(iteration, file=target, flush=True)
            iteration += 1
            time.sleep(0.1)
    except KeyboardInterrupt:
        # Allow graceful termination via Ctrl+C or signals in tests.
        pass
    finally:
        sys.exit(args.exit_code)


if __name__ == "__main__":
    main()
