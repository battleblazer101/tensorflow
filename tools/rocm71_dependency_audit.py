#!/usr/bin/env python3
"""Read-only audit of Bazel undeclared-inclusion diagnostics.

This intentionally reports candidates, not proven fixes. Bazel's configured
C++ action graph remains authoritative for header ownership and visibility.
"""
import argparse
import json
import pathlib
import re
import sys

MISSING = re.compile(r"^\s*'([^']+\.(?:h|hpp|inc))'\s*$", re.MULTILINE)
RULE = re.compile(r"^ERROR: .*? in rule '([^']+)'", re.MULTILINE)
GENERATED = re.compile(r"^(?:bazel-out/[^/]+/bin/)?(?:external/([^/]+)/)?(.+)$")


def candidate_labels(header):
    match = GENERATED.match(header)
    if not match:
        return []
    repo, relative = match.groups()
    if not relative.endswith(".pb.h"):
        return []
    package, _, filename = relative.rpartition("/")
    stem = filename.removesuffix(".pb.h")
    prefix = "@" + repo if repo else ""
    return [
        f"{prefix}//{package}:{stem}_proto_cc",
        f"{prefix}//{package}:{stem}_proto_cc_impl",
    ]


def audit(text):
    problems = []
    for block in re.split(r"(?=^ERROR: )", text, flags=re.MULTILINE):
        if "undeclared inclusion(s)" not in block:
            continue
        rule = RULE.search(block)
        headers = sorted(set(MISSING.findall(block)))
        if headers:
            problems.append({
                "rule": rule.group(1) if rule else "unknown",
                "missing_headers": [
                    {"path": h, "candidate_owners": candidate_labels(h)}
                    for h in headers
                ],
            })
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=pathlib.Path, help="Saved Bazel build output")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    args = parser.parse_args()
    try:
        text = args.log.read_text(errors="replace")
    except OSError as exc:
        parser.error(str(exc))
    problems = audit(text)
    if args.json:
        print(json.dumps(problems, indent=2))
    else:
        for problem in problems:
            print(f"Rule: {problem['rule']}")
            for item in problem["missing_headers"]:
                print(f"  Missing: {item['path']}")
                for label in item["candidate_owners"]:
                    print(f"    Candidate owner (verify with Bazel): {label}")
        print(f"Undeclared-inclusion failures found: {len(problems)}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
