"""Both collection settings must survive every way a consumer can read `.env`.

Docker's `env_file` and systemd's `EnvironmentFile` hand the raw text over, so
JSON works there. A shell that sources the file (`set -a; . ./.env`) performs
quote removal, which used to leave a value that was neither valid JSON nor a
plain list, and the process aborted at import with an error naming an unrelated
field. See TICKET-013.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

JSON_LIST = '["image/jpeg","image/png","application/pdf"]'
JSON_MAP = '{"image/jpeg":".jpg","image/png":".png","application/pdf":".pdf"}'


_REPORT = (
    "import json, sys\n"
    "from app.core.settings import settings\n"
    "print(json.dumps({'allowed_types': settings.allowed_types,"
    " 'ext_by_type': settings.ext_by_type}))\n"
)


def _run(field: str, value: str) -> subprocess.CompletedProcess:
    """Import settings in a subprocess with one env var overridden."""
    return subprocess.run(
        [sys.executable, "-c", _REPORT],
        capture_output=True,
        text=True,
        env={**_clean_env(), field: value, "PYTHONPATH": str(ROOT)},
        cwd=ROOT,
    )


def _parse(field: str, value: str) -> dict:
    """Same, but assert the import succeeded and return the parsed result.

    Subprocess because `app.core.settings` builds a module-level singleton from
    the ambient environment at import.
    """
    proc = _run(field, value)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _clean_env() -> dict:
    import os

    keep = {
        k: v
        for k, v in os.environ.items()
        if k not in {"ALLOWED_TYPES", "EXT_BY_TYPE", "PRESIGNED_TTL", "PRESIGNED_TTL_HOURS"}
    }
    return keep


# ── allowed_types ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(JSON_LIST, id="json-array"),
        pytest.param("image/jpeg,image/png,application/pdf", id="comma-list"),
        pytest.param("[image/jpeg,image/png,application/pdf]", id="brackets-lost-quotes"),
        pytest.param('["image/jpeg", "image/png", "application/pdf"]', id="json-with-spaces"),
    ],
)
def test_allowed_types_parses_every_shape(raw: str) -> None:
    assert _parse("ALLOWED_TYPES", raw)["allowed_types"] == [
        "image/jpeg",
        "image/png",
        "application/pdf",
    ]


def test_allowed_types_trims_stray_whitespace() -> None:
    parsed = _parse("ALLOWED_TYPES", " image/jpeg , image/png ")
    assert parsed["allowed_types"] == ["image/jpeg", "image/png"]


# ── ext_by_type ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(JSON_MAP, id="json-object"),
        pytest.param("image/jpeg:.jpg,image/png:.png,application/pdf:.pdf", id="kv-list"),
        pytest.param(
            "{image/jpeg:.jpg,image/png:.png,application/pdf:.pdf}", id="braces-lost-quotes"
        ),
    ],
)
def test_ext_by_type_parses_every_shape(raw: str) -> None:
    assert _parse("EXT_BY_TYPE", raw)["ext_by_type"] == {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "application/pdf": ".pdf",
    }


def test_a_mangled_mapping_does_not_silently_corrupt_the_first_key() -> None:
    """A shell strips the quotes but leaves the braces behind.

    Keeping them turned the first key into "{image/jpeg" — a value that parses
    cleanly and is quietly wrong, which is worse than the crash it replaced.
    """
    parsed = _parse("EXT_BY_TYPE", "{image/jpeg:.jpg,image/png:.png}")
    assert "image/jpeg" in parsed["ext_by_type"]
    assert not any(k.startswith("{") for k in parsed["ext_by_type"])


def test_a_kv_pair_without_a_colon_is_rejected_rather_than_half_parsed() -> None:
    proc = _run("EXT_BY_TYPE", "image/jpeg")
    assert proc.returncode != 0, "a bare token must not be silently accepted"


# ── the shipped files must themselves be sourceable ───────────────────────


@pytest.mark.parametrize("env_file", [".env.example", ".env"])
def test_shipped_env_files_carry_no_json_that_a_shell_can_mangle(env_file: str) -> None:
    """The tolerant parser is a safety net, not the plan.

    Shipping the flat forms means the value never has to survive quote removal,
    so the documented `set -a; . ./.env` path produces the right values rather
    than merely not crashing.
    """
    text = (ROOT / env_file).read_text()
    for key in ("ALLOWED_TYPES", "EXT_BY_TYPE"):
        line = next(l for l in text.splitlines() if l.startswith(f"{key}="))
        value = line.split("=", 1)[1]
        assert not value.startswith(("{", "[")), (
            f"{env_file}: {key} ships JSON, which a sourcing shell mangles; "
            f"use the flat comma form"
        )


def test_sourcing_the_example_env_yields_the_same_values_as_reading_it_raw() -> None:
    """The two consumers must not disagree about the configuration.

    `set -a; . .env` is the documented shell path; Docker's env_file is the raw
    one. Both have to end up with the same allow-list and extension map.
    """
    script = "set -a\n. ./.env.example\nset +a\npython - <<'PY'\n" + _REPORT + "PY"
    proc = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, cwd=ROOT,
        env={**_clean_env(), "PYTHONPATH": str(ROOT), "PATH": _clean_env()["PATH"]},
    )
    assert proc.returncode == 0, proc.stderr
    sourced = json.loads(proc.stdout)

    text = (ROOT / ".env.example").read_text()

    def field(name: str) -> str:
        return next(
            l.split("=", 1)[1] for l in text.splitlines() if l.startswith(f"{name}=")
        ).strip()

    raw_types = _parse("ALLOWED_TYPES", field("ALLOWED_TYPES"))["allowed_types"]
    raw_map = _parse("EXT_BY_TYPE", field("EXT_BY_TYPE"))["ext_by_type"]

    assert sourced["allowed_types"] == raw_types
    assert sourced["ext_by_type"] == raw_map
    assert "{" not in "".join(raw_map) and "[" not in "".join(raw_types)
