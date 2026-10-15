#!/usr/bin/env python3
"""Test battery for published-surface-gate.

    python3 test_published_surface_gate.py            # fixture cases (offline, deterministic)
    python3 test_published_surface_gate.py --audit .  # plus a report-mode audit of a real tree

Cases run the gate as a subprocess and assert on its exit code and JSON output.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
GATE = HERE / "published-surface-gate.py"
results = []


def run(*args):
    return subprocess.run([sys.executable, str(GATE), *args], capture_output=True, text=True,
                          check=False)  # returncode is asserted, never raised


def case(name, ok, detail=""):
    results.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not ok else ""))


def main() -> int:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="psg-tests-"))
    try:
        # 1. a violating published file ⇒ exit 1, finding reported with line number
        clean = tmp / "clean.md"; clean.write_text("# Shipping notes\n\nThe correct name is Glyph.\n")
        bad = tmp / "bad.md"; bad.write_text("# Docs\n\nLine one.\nThis is Gliph, not Glyph.\n")
        r = run("--paths", str(tmp), "--json")
        data = json.loads(r.stdout)
        case("violation ⇒ exit 1 with the file, line, and rule id",
             r.returncode == 1 and data["findings"] and data["findings"][0]["path"].endswith("bad.md")
             and data["findings"][0]["line"] == 4 and data["findings"][0]["rule"] == "near-miss-gliph",
             r.stdout + r.stderr)

        # 2. clean tree ⇒ exit 0
        only_clean = tmp / "only-clean"; only_clean.mkdir()
        (only_clean / "a.md").write_text("The correct spelling is Glyph.\n")
        r = run("--paths", str(only_clean))
        case("clean surface ⇒ exit 0", r.returncode == 0 and "clean" in r.stdout, r.stdout + r.stderr)

        # 3. case-insensitive + plural forms are caught
        mixed = tmp / "mixed"; mixed.mkdir()
        (mixed / "b.md").write_text("Two Gliphs walk in.\n")
        r = run("--paths", str(mixed), "--json")
        case("case/plural variants caught", r.returncode == 1 and len(json.loads(r.stdout)["findings"]) == 1,
             r.stdout + r.stderr)

        # 4. report mode never fails the build
        r = run("--paths", str(tmp), "--mode", "report")
        case("report mode ⇒ exit 0 even with findings", r.returncode == 0 and "FIND:" in r.stdout,
             r.stdout + r.stderr)

        # 5. allowlisted record files are skipped
        allow = tmp / "analysis"; allow.mkdir()
        (allow / "log.md").write_text("We discussed Gliph as a competitor's product.\n")
        r = run("--paths", str(tmp), "--mode", "report", "--json")
        data = json.loads(r.stdout)
        case("allowlist: discussion records skipped by glob",
             r.returncode == 0 and not any(f["path"].startswith("analysis/") for f in data["findings"])
             and data["allowlisted_skipped"] >= 1, r.stdout + r.stderr)

        # 6. the rules file itself stays valid (fail fast on a broken rule)
        broken = tmp / "broken-rules.json"
        broken.write_text(json.dumps({"version": 1, "rules": [{"id": "x", "pattern": "([", "reason": "bad regex"}]}))
        r = run("--paths", str(only_clean), "--rules", str(broken))
        case("invalid rule pattern ⇒ exit 2 with a stated reason",
             r.returncode == 2 and "invalid pattern" in (r.stdout + r.stderr), r.stdout + r.stderr)

        # 7. binary/vendor trees are not scanned
        big = tmp / "site" / "node_modules"; big.mkdir(parents=True)
        (big / "vendored.md").write_text("gliph gliph gliph\n")
        r = run("--paths", str(tmp / "site"), "--json")
        case("node_modules skipped (no vendor false positives)",
             r.returncode == 0 and json.loads(r.stdout)["findings"] == [], r.stdout + r.stderr)

        # 8. duplicate rule ids are rejected up front
        dup = tmp / "dup-rules.json"
        dup.write_text(json.dumps({"version": 1, "rules": [
            {"id": "a", "pattern": "x", "reason": "one"},
            {"id": "a", "pattern": "y", "reason": "two"}]}))
        r = run("--paths", str(only_clean), "--rules", str(dup))
        case("duplicate rule id ⇒ exit 2 with a stated reason",
             r.returncode == 2 and "duplicate rule id" in (r.stdout + r.stderr), r.stdout + r.stderr)

        # 9. optional: report-mode audit of a real tree
        if "--audit" in sys.argv:
            target = sys.argv[sys.argv.index("--audit") + 1]
            r = run("--paths", target, "--mode", "report", "--root", target)
            print("\n--- audit (report mode) of", target, "---")
            print(r.stdout.strip()[:2000])
            case(f"audit completed on {target}", r.returncode == 0, r.stdout + r.stderr)
        else:
            print("SKIP  real-tree audit (pass --audit <dir>)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    if failed:
        print("FAILED: " + ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
