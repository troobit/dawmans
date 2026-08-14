"""Command-line entry point.

`dawmans ingest`, `dawmans validate` and `dawmans inventory` land with
`data/manual-corpus`; only the `serve` stub is registered so far.
"""

import argparse


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="dawmans")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("serve", help="Run the loopback answer-engine API")
    args = parser.parse_args(argv)
    if args.command == "serve":
        parser.exit(2, "dawmans serve: not implemented yet\n")


if __name__ == "__main__":
    main()
