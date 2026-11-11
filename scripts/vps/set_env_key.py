#!/usr/bin/env python3
"""Replace one KEY=value line in an env file, in place.

Used by the ops wizards (``rotate-cloudflare-token.sh``, ``order-phone-did.sh``)
so the remote step is a file the wizard ships, not a heredoc quoted through ssh.
The value is read from a separate 0600 file so it never appears in a command
line or in process listings on the box.
"""
import argparse
import pathlib
import sys


def replace(path, key, value):
    """Return how many lines were replaced; append the key if it is missing."""
    file = pathlib.Path(path)
    lines = file.read_text().splitlines()
    output, replaced = [], 0
    for line in lines:
        if line.startswith(key + "="):
            output.append(f"{key}={value}")
            replaced += 1
        else:
            output.append(line)
    if replaced == 0:
        output.append(f"{key}={value}")
    file.write_text("\n".join(output) + "\n")
    file.chmod(0o600)
    return replaced


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, help="env file to edit")
    parser.add_argument("--key", required=True, help="variable name")
    parser.add_argument("--value-file", required=True, help="file holding the new value")
    parser.add_argument("--allow-append", action="store_true",
                        help="append the key when it is not already present")
    args = parser.parse_args(argv)
    value = pathlib.Path(args.value_file).read_text().strip()
    if not value:
        print("refusing to write an empty value", file=sys.stderr)
        return 2
    if any(character in value for character in ("\n", "\r", "\0")):
        print("refusing a value containing control characters", file=sys.stderr)
        return 2
    file = pathlib.Path(args.file)
    if not file.exists():
        print(f"{file} does not exist", file=sys.stderr)
        return 2
    if args.key in file.read_text() or args.allow_append:
        replaced = replace(file, args.key, value)
        print(f"updated {args.key} in {file} (replaced {replaced} line(s))")
        return 0
    print(f"{args.key} is not in {file}; pass --allow-append to add it", file=sys.stderr)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
