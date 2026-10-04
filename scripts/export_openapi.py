"""Export the OpenAPI specification to `docs/`.

Both outputs are generated artifacts: `docs/api-spec.json` is written first and
`docs/api-spec.yml` is converted from it, so the YAML is only ever as fresh as the
JSON.

Run without arguments to regenerate. Run with `--check` to fail when the
committed files differ from what the code currently produces, which is what a gate
should do — a gate that rewrites the artifact and exits zero has no way to fail,
and a generated file that only gets refreshed when someone remembers is the
failure mode `.opencode/skills/update-docs` describes.
"""

import json
import sys
from pathlib import Path

import yaml

from app.main import app

SPEC_DIR = Path("docs")
JSON_PATH = SPEC_DIR / "api-spec.json"
YAML_PATH = SPEC_DIR / "api-spec.yml"


def render() -> tuple[str, str]:
    """The JSON and YAML forms of the current specification."""
    payload = json.dumps(app.openapi(), indent=2)
    return payload, yaml.dump(json.loads(payload), sort_keys=False)


def committed(path: Path) -> str | None:
    """A file's contents, or None when it has never been generated."""
    return path.read_text(encoding="utf-8") if path.exists() else None


def main() -> int:
    check_only = "--check" in sys.argv[1:]
    expected_json, expected_yaml = render()
    written: list[Path] = []

    for path, expected in ((JSON_PATH, expected_json), (YAML_PATH, expected_yaml)):
        if not check_only:
            path.write_text(expected, encoding="utf-8")
            written.append(path)
            continue
        actual = committed(path)
        if actual != expected:
            reason = "missing" if actual is None else "stale"
            print(f"  {path} is {reason}. Run: python scripts/export_openapi.py", file=sys.stderr)
            return 1

    if check_only:
        print("OpenAPI specification is up to date.")
    else:
        print(f"Wrote {', '.join(str(p) for p in written)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
