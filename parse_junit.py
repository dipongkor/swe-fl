#!/usr/bin/env python3
"""Parse a pytest JUnit XML report into categorized test-name lists.

Usage:
    python parse_junit.py <junit.xml> [output.json]

Output shape:
    {"passed": [...], "failed": [...], "skipped": [...], "xfailed": [...]}

Notes:
- JUnit XML has no distinct xfailed outcome; pytest encodes xfails as
  <skipped message="expected test failure" .../>. We detect them by the
  message string (the `type` attribute is just "pytest.skip").
- <error> is folded into "failed"; xpassed is folded into "passed" to match
  the requested 4-bucket shape.
- Test names use pytest nodeid form ("path/to/test.py::Class::test_name")
  when the testcase has a `file` attribute; otherwise "classname::name".
"""
import json
import sys
from xml.etree.ElementTree import iterparse


def categorize(testcase):
    for child in testcase:
        if child.tag == "failure" or child.tag == "error":
            return "failed"
        if child.tag == "skipped":
            msg = (child.get("message") or "").lower()
            if "expected test failure" in msg or "xfail" in msg:
                return "xfailed"
            if "unexpectedly passing" in msg or "xpass" in msg:
                return "passed"
            return "skipped"
    return "passed"


def nodeid(testcase):
    classname = testcase.get("classname") or ""
    name = testcase.get("name") or ""
    file = testcase.get("file") or ""
    if not file:
        return f"{classname}::{name}" if classname else name
    module = file.replace("/", ".").rsplit(".", 1)[0]
    if not classname or classname == module:
        return f"{file}::{name}" if name else file
    if classname.startswith(module + "."):
        cls = classname[len(module) + 1:]
        return f"{file}::{cls}::{name}"
    return f"{classname}::{name}"


def parse(path):
    buckets = {
        "passed": [],
        "failed": [],
        "skipped": [],
        "xfailed": [],
    }
    for _, elem in iterparse(path, events=("end",)):
        if elem.tag != "testcase":
            continue
        buckets[categorize(elem)].append(nodeid(elem))
        elem.clear()
    return buckets


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: parse_junit.py <junit.xml> [output.json]")
    result = parse(sys.argv[1])
    out = json.dumps(result, indent=2)
    if len(sys.argv) >= 3:
        with open(sys.argv[2], "w") as f:
            f.write(out)
    else:
        sys.stdout.write(out + "\n")


if __name__ == "__main__":
    main()
