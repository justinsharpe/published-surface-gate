# published-surface-gate

A regex fence that keeps specific strings — misspellings, wrong names, one-letter neighbours — off the surfaces you publish.

## Why this exists

A product name's highest-frequency typo is usually a spelling that is itself a *different word*: a one-letter neighbour. It reads as valid language, so a spellchecker never flags it — but on a published surface it means the wrong thing (in real cases, often a competitor's product).

This tool makes that typo class impossible to miss: you write a fence as a plain regex in a JSON rules file, run the gate on the surfaces you publish (site source, public README/docs, release copy), and any hit fails the build. Records that legitimately discuss a fenced string are allowlisted by glob; product surfaces never are.

The fence is deliberately over-broad on purpose: the regex is cheap to write, and the typo class it prevents is expensive to ship.

## Rules schema

The gate reads every fence from a JSON rules file (default: `published-surface-rules.json` next to the script; override with `--rules`).

```json
{
  "version": 1,
  "rules": [
    {
      "id": "near-miss-gliph",
      "pattern": "\\b[gG]liph(s)?\\b",
      "reason": "One-letter-neighbour fence (example): the product name is `Glyph`; `Gliph` is a different word with a different root. Zero instances on published surfaces — rewrite to the correct name."
    }
  ],
  "allowlist": ["**/analysis/**", "**/competitor-intel/**"]
}
```

Top-level keys:

| Key | Type | Required | Meaning |
|-----|------|----------|---------|
| `version` | int | no | Schema version (informational). |
| `rules` | array | yes | The fences. Must be non-empty. |
| `allowlist` | array of glob strings | no | Paths (relative, `/`-separated) that may discuss a fenced string without failing. |

Each rule:

| Key | Type | Required | Meaning |
|-----|------|----------|---------|
| `id` | string | yes | Unique, stable identifier for this fence (reported in findings). |
| `pattern` | string | yes | Python regex, matched per line. Compile failures exit 2. |
| `reason` | string | yes | Why this fence exists and what to write instead (shown in findings). |

The gate fail-fasts (exit 2) on: a missing rules file, an empty `rules` list, a rule missing a required key, a duplicate `id`, an invalid regex, or a non-string allowlist entry.

## Usage

```sh
# enforce (default): exit 1 on any finding — wire into CI
python3 published-surface-gate.py --paths src/ docs/ README.md

# report: list findings, always exit 0 — audits
python3 published-surface-gate.py --paths . --mode report

# machine-readable findings
python3 published-surface-gate.py --paths . --json

# custom rules file + explicit relative-path root
python3 published-surface-gate.py --paths . --rules my-rules.json --root .
```

The gate scans text files only (a broad suffix list) and skips vendor/venv/build directories.

## Self-test

```sh
python3 test_published_surface_gate.py            # fixture cases (offline, deterministic)
python3 test_published_surface_gate.py --audit .  # plus a report-mode audit of a real tree
```

## License

MIT — see [LICENSE](LICENSE).
