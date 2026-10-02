"""Every way a consumer can read `.env`, and every setting that has no default.

Two subjects, one file, because both are about the same file being read by
consumers that do not agree with each other.

**Collection settings must survive every read shape.** Docker's `env_file` and
systemd's `EnvironmentFile` hand the raw text over, so JSON works there. A shell
that sources the file (`set -a; . ./.env`) performs quote removal, which used to
leave a value that was neither valid JSON nor a plain list, and the process
aborted at import with an error naming an unrelated field. See TICKET-013.

**A setting whose value differs per environment has no default.** The failure this
exists for is silent and it is the worst kind: a local `.env` that omits
`MINIO_PUBLIC_PORT` resolves it to the internal port, the process starts cleanly,
and every presigned URL points at the wrong origin. A default is a value nobody
chose, and a value nobody chose is a value nobody notices is wrong. The omission
must be loud, at import, naming the key.
"""

import json
import os
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


# ── settings that must be required, not defaulted ─────────────────────────
#
# Every key below has a value that legitimately differs between the developer's
# machine and the VPS. `PRESIGNED_TTL_HOURS` is here for the same reason as the
# rest: it is an hours count, and an hours count that differs per deployment must
# be stated rather than inherited from a constant in the source.
#
# The list is deliberately explicit rather than derived from the Settings class.
# A test that asks pydantic which fields are required is testing pydantic; this
# test states what this project decided, and fails when a decision is reversed
# without a line being changed here.

#: Each required key, and the attribute on the resolved Settings it must reach.
#: Stated rather than inferred: the guard above proves the key is *absent* when
#: missing, and this map proves it is *present* when supplied. A field that is
#: required and mis-aliased satisfies the first and breaks every real deployment.
REQUIRED_KEY_TO_FIELD: dict[str, str] = {
    "DB_PORT": "pg_port",
    "MINIO_PORT": "minio_port",
    "MINIO_SECURE": "minio_secure",
    "MINIO_REGION": "minio_region",
    "MINIO_DEFAULT_BUCKET": "minio_default_bucket",
    "BASE_OBJECT_PATH": "base_object_path",
    "PRESIGNED_TTL_HOURS": "presigned_ttl_hours",
    "PDF_SUFFIX": "pdf_suffix",
    "TEMPLATES_DIR": "templates_dir",
    "CHUNK_DIR": "chunk_dir",
    "MINIO_PUBLIC_ENDPOINT": "minio_public_endpoint",
    "MINIO_PUBLIC_PORT": "minio_public_port",
    "MINIO_PUBLIC_SECURE": "minio_public_secure",
}

REQUIRED_KEYS: tuple[str, ...] = tuple(REQUIRED_KEY_TO_FIELD)

#: A valid value for every required key except the one under test. The point is
#: that the other twelve resolve, so the import fails only if the key under test
#: is the missing one. A filler that were itself invalid would make every case
#: fail for the same unrelated reason, which is a test that asserts nothing.
_FILLER: dict[str, str] = {
    "DB_PORT": "1111",
    "MINIO_PORT": "1111",
    "MINIO_SECURE": "false",
    "MINIO_REGION": "filler-region",
    "MINIO_DEFAULT_BUCKET": "filler-bucket",
    "BASE_OBJECT_PATH": "filler/path",
    "PRESIGNED_TTL_HOURS": "111",
    "PDF_SUFFIX": "Filler",
    "TEMPLATES_DIR": "filler/templates",
    "CHUNK_DIR": "/tmp/filler-chunks",
    "MINIO_PUBLIC_ENDPOINT": "filler.public.test",
    "MINIO_PUBLIC_PORT": "1111",
    "MINIO_PUBLIC_SECURE": "false",
}

#: Keys the rest of this file needs in the ambient environment to be absent, so
#: that stripping one of REQUIRED_KEYS from the env file is actually the only
#: thing removing it. `app.core.settings` builds a module-level singleton from
#: the environment, so an inherited value would mask the omission.
_ALL_RELEVANT = set(REQUIRED_KEYS) | {"PRESIGNED_TTL"}


def _without(keys: set[str]) -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in keys}


def _import_without(key: str, env_path: Path) -> subprocess.CompletedProcess:
    """Import `app.core.settings` in a subprocess with `key` absent from the env file.

    The env file is copied to a temporary path and the key is deleted from the
    copy, because the real `.env` is the developer's and must not be modified by a
    test. `ENV_PATH_CORE` is set to the copy before `Settings` is constructed, so
    the omission is real rather than shadowed by the repository file.
    """
    lines = env_path.read_text().splitlines()
    stripped = [
        line
        for line in lines
        if not line.startswith(f"{key}=") and not line.startswith(f"{key} :")
    ]
    temporary = env_path.parent / f".env.without-{key}"
    temporary.write_text("\n".join(stripped) + "\n")

    script = (
        "import pathlib, sys\n"
        f"import app.core.settings as s\n"
        f"s.ENV_PATH_CORE = pathlib.Path({str(temporary)!r})\n"
        "s.Settings.model_config['env_file'] = s.ENV_PATH_CORE\n"
        "s.settings = s.Settings()\n"
        "print('IMPORTED')\n"
    )
    try:
        keep = {
            k: v
            for k, v in os.environ.items()
            if k not in _ALL_RELEVANT
        }
        return subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            cwd=ROOT,
            env={**keep, "PYTHONPATH": str(ROOT)},
        )
    finally:
        temporary.unlink(missing_ok=True)


def _env_file_for(key: str) -> Path:
    """A complete env file to strip `key` from.

    `.env` is the developer's own file, and it is the one every process actually
    reads. `.env.example` is the committed template and may be missing a key the
    developer has added locally, so either can leave a required setting unresolved
    for an unrelated reason and turn a true failure into a false one.
    """
    for candidate in (ROOT / ".env", ROOT / ".env.example"):
        if candidate.exists():
            return candidate
    pytest.fail("neither .env nor .env.example exists, so there is nothing to strip")


@pytest.mark.parametrize("key", REQUIRED_KEYS)
def test_omitting_a_required_setting_aborts_the_import_naming_it(key: str) -> None:
    """The failure is required to be loud, and to say which key.

    Asserting only that the import failed would pass for the wrong reasons - a typo
    in a different field, a missing dependency, a syntax error. The message must
    contain the key, because the person who sees it is a developer whose `.env` is
    incomplete and who has no other way to learn which of thirteen values is absent.
    """
    proc = _import_without(key, _env_file_for(key))

    assert proc.returncode != 0, (
        f"importing app.core.settings succeeded with {key} absent. It has a default, "
        "so a configuration that forgot this key starts successfully against a value "
        "nobody chose. That is the failure this test exists for: for MINIO_PUBLIC_* it "
        "means presigned URLs signed with the internal origin, which no error ever "
        "reports. Remove the default so the omission fails here instead."
    )
    assert key in proc.stderr, (
        f"the validation error for the missing {key} does not name it:\n{proc.stderr}"
    )


@pytest.mark.parametrize("key", REQUIRED_KEYS)
def test_a_supplied_value_reaches_the_field_the_key_names(key: str) -> None:
    """The complement of the guard above, and the reason to keep the list explicit.

    A key that is required is only required if a supplied value actually arrives. A
    field made required and simultaneously mis-aliased still passes the omission
    guard - the import fails either way - while every real deployment silently
    reads nothing. The value is read back off the resolved object, so a validator
    that rewrote it would be caught here too.
    """
    field = REQUIRED_KEY_TO_FIELD[key]
    supplied = {
        "pg_port": "6543",
        "minio_port": "6543",
        "minio_public_port": "6543",
        "presigned_ttl_hours": "6543",
        "minio_secure": "true",
        "minio_public_secure": "true",
    }.get(field, "probe-value-for-required-key")

    values = {name: filler for name, filler in _FILLER.items() if name != key}
    values[key] = supplied
    values.update({"ALLOWED_TYPES": "image/png", "EXT_BY_TYPE": "image/png:.png"})

    proc = _import_with(values, field)

    assert proc.returncode == 0, proc.stderr
    expected: object = json.loads(proc.stdout)["resolved"]
    if field.endswith("_secure"):
        assert expected is True, (
            f"{key}=true resolved to {expected!r}. The boolean settings must receive "
            "the supplied value, not a value inherited from a default."
        )
    else:
        assert str(expected) == supplied, (
            f"{key} was supplied as {supplied!r} but {field!r} resolved to {expected!r}. "
            "A required setting that does not receive its supplied value is required "
            "for no reason except to make the process fail."
        )


def _import_with(values: dict[str, str], attribute: str) -> subprocess.CompletedProcess:
    """Resolve Settings with `values` supplied through the environment, and read
    back one attribute from the module-level singleton.

    Supplied as environment variables rather than as constructor arguments because
    that is the path Docker's `env_file` and a sourced shell both take, and it is
    the only path that exercises the alias. The repository `.env` is not consulted
    for these keys: `_ALL_RELEVANT` is stripped from the ambient environment and the
    constructor is given every one of them explicitly, so nothing leaks in.
    """
    script = (
        "import json\n"
        "from app.core.settings import settings\n"
        f"print(json.dumps({{'resolved': getattr(settings, {attribute!r})}}))\n"
    )
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env={**_without(_ALL_RELEVANT), **values, "PYTHONPATH": str(ROOT)},
    )
