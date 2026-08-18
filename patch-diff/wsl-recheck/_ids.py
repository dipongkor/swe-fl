#!/usr/bin/env python3
"""Print space-separated instance_ids from a predictions file, optionally filtered by repo.
Usage: python3 _ids.py <preds.jsonl> [repo]"""
import json, sys
f = sys.argv[1]
repo = sys.argv[2] if len(sys.argv) > 2 else ""
ids = [json.loads(l)["instance_id"] for l in open(f) if l.strip()]
if repo:
    ids = [i for i in ids if i.split("__")[0] == repo]
print(" ".join(ids))
