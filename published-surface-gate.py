#!/usr/bin/env python3
"""published-surface-gate — regex fences for the surfaces you publish.

A fence is a "zero instances" rule over a class of string that must never reach
published copy. The canonical case is the one-letter-neighbour misspelling: a
product name's highest-frequency typo is a spelling that is itself a different
word (often another company's product), so a deliberate, over-broad regex fence
is cheap insurance against the typo class that is most expensive when it slips
through.

Two modes:
  enforce (default) — any finding exits 1 (wire this into a build or CI step)
  report            — list findings, always exit 0 (audits, reconnaissance)

Rules are fully data-driven: every fence lives in a JSON rules file (see
README.md for the schema). Point the gate at the surfaces you publish — site
source, public README/docs, release copy. Records that legitimately discuss a
fenced string (analysis docs, competitor intel, session logs) are allowlisted by
glob in the rules file; product surfaces never are.

Usage:
  python3 published-surface-gate.py --paths <file-or-dir> [...]
  python3 published-surface-gate.py --paths . --mode report
  python3 published-surface-gate.py --paths . --json
  python3 published-surface-gate.py --paths . --rules my-rules.json
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
RULES = HERE / "published-surface-rules.json"
TEXT_SUFFIXES = {".md", ".mdx", ".markdown", ".txt", ".rst", ".json", ".jsonl", ".yml", ".yaml",
                 ".toml", ".py", ".sh", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".html",
                 ".css", ".xml", ".svg", ".svelte", ".vue", ".astro"}
# Coverage note: .mdx/.markdown/.mjs/.cjs/.svelte/.vue/.astro/.svg are included because a fence
# that silently skips the format the copy will move to next is worse than no fence — it reads green.
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".worktrees",
             "dist", "build", ".next", "renders", "site-packages"}


def load_rules(path: pathlib.Path = RULES) -> dict:
    if not path.exists():
        print(f"ERROR: rules file missing: {path}")
        sys.exit(2)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("rules"), list) or not data["rules"]:
        print("ERROR: rules file carries no rules")
        sys.exit(2)
    seen = set()
    for r in data["rules"]:
        for key in ("id", "pattern", "reason"):
            if not r.get(key):
                print(f"ERROR: rule missing `{key}`: {r}")
                sys.exit(2)
        if r["id"] in seen:
            print(f"ERROR: duplicate rule id `{r['id']}`")
            sys.exit(2)
        seen.add(r["id"])
        try:
            re.compile(r["pattern"])
        except re.error as e:
            print(f"ERROR: rule `{r['id']}` has an invalid pattern: {e}")
            sys.exit(2)
    allowlist = data.get("allowlist", [])
    if not isinstance(allowlist, list) or not all(isinstance(g, str) for g in allowlist):
        print("ERROR: `allowlist` must be a list of glob strings")
        sys.exit(2)
    return data


def allowlisted(rel: str, rules: dict) -> bool:
    rel = rel.replace("\\", "/")
    for glob in rules.get("allowlist", []):
        if fnmatch.fnmatch(rel, glob) or fnmatch.fnmatch("/" + rel, glob):
            return True
    return False


def iter_files(paths) -> list:
    out = []
    for raw in paths:
        p = pathlib.Path(raw)
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if not f.is_file() or f.suffix.lower() not in TEXT_SUFFIXES:
                    continue
                if any(part in SKIP_DIRS for part in f.parts):
                    continue
                out.append(f)
        else:
            print(f"warn: path not found, skipped: {raw}")
    return out


def scan(files, rules, root_hint: pathlib.Path):
    compiled = [(r, re.compile(r["pattern"])) for r in rules["rules"]]
    findings, scanned, skipped = [], 0, 0
    for f in files:
        rel = str(f.relative_to(root_hint)) if str(f).startswith(str(root_hint)) else str(f)
        if allowlisted(rel, rules):
            skipped += 1
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        scanned += 1
        for lineno, line in enumerate(text.splitlines(), 1):
            for r, rx in compiled:
                m = rx.search(line)
                if m:
                    findings.append({"rule": r["id"], "path": rel, "line": lineno,
                                     "match": m.group(0),
                                     "excerpt": line.strip()[:160],
                                     "reason": r["reason"]})
    return findings, scanned, skipped


def main() -> int:
    ap = argparse.ArgumentParser(prog="published-surface-gate",
                                 description="Regex fences for the surfaces you publish "
                                             "(data-driven; see published-surface-rules.json)")
    ap.add_argument("--paths", nargs="+", required=True, help="files or directories to scan")
    ap.add_argument("--mode", choices=["enforce", "report"], default="enforce")
    ap.add_argument("--json", action="store_true", help="machine-readable findings")
    ap.add_argument("--root", default=None, help="base for relative paths in output (default: first dir given)")
    ap.add_argument("--rules", default=str(RULES),
                    help="path to the JSON rules file (default: published-surface-rules.json next to this script)")
    args = ap.parse_args()

    rules = load_rules(pathlib.Path(args.rules))
    files = iter_files(args.paths)
    root_hint = pathlib.Path(args.root) if args.root else pathlib.Path(args.paths[0])
    if root_hint.is_file():
        root_hint = root_hint.parent
    findings, scanned, skipped = scan(files, rules, root_hint)

    if args.json:
        print(json.dumps({"rules_version": rules.get("version"), "mode": args.mode,
                          "scanned": scanned, "allowlisted_skipped": skipped,
                          "findings": findings}, indent=2))
    else:
        print(f"published-surface-gate — {len(rules['rules'])} rule(s) | mode {args.mode} | "
              f"scanned {scanned} file(s) | allowlisted {skipped}")
        for f in findings:
            print(f"{'FAIL' if args.mode == 'enforce' else 'FIND'}: {f['rule']}  {f['path']}:{f['line']}"
                  f"  «{f['match']}»  — {f['excerpt']}")
        print(f"{len(findings)} finding(s)")
        if not findings:
            print("clean: no fenced string on the scanned surfaces")

    if args.mode == "enforce" and findings:
        if not args.json:
            print("\nfix: rewrite the fenced string to the correct spelling, then re-run.")
        else:
            print("fix: rewrite the fenced string to the correct spelling, then re-run.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
