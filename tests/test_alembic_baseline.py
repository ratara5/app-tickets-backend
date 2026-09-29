"""Guards for the migration history.

The history this file describes is not a record of anything that happened. The
live database was built by hand and by the ETL loader, and its `alembic_version`
table was stamped by hand: it held one row, a 48-character revision id, inside a
`varchar(64)` column that Alembic's own DDL creates as `varchar(32)`. No
environment had ever been migrated by Alembic, and `alembic upgrade head` could
not run.

Seven hand-patched revisions described a path nobody walked, and they could not
be executed: two heads, and revision ids too long to store in the table that is
supposed to store them.

They were replaced by a single baseline derived from `deploy/schema.sql`. These
tests hold that arrangement in place. The failure they prevent is not subtle: a
second revision reintroduces a second head, and a long id reintroduces the
column that had to be hand-widened in the first place.

No database is required, so these run in CI.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VERSIONS_DIR = REPO_ROOT / "alembic" / "versions"
SCHEMA_SQL = REPO_ROOT / "deploy" / "schema.sql"
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

# Alembic creates alembic_version.version_num as varchar(32), and the live
# database's copy was hand-widened to varchar(64) to accommodate a 48-character
# id. Any id that needs a widened column will fail to stamp on a fresh database.
MAX_REVISION_ID_LENGTH = 32


def _revision_files() -> list[Path]:
    return sorted(VERSIONS_DIR.glob("*.py"))


def _revisions() -> dict[str, str]:
    """Map revision id -> down_revision, parsed from the file text."""
    result: dict[str, str] = {}
    for path in _revision_files():
        text = path.read_text(encoding="utf-8")
        revision = re.search(r'^revision(?::\s*str)?\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        down = re.search(r'^down_revision(?::[^=]+)?\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        if revision:
            result[revision.group(1)] = down.group(1) if down else ""
    return result


def test_exactly_one_revision_exists() -> None:
    """More than one revision means a second head, which blocks autogenerate."""
    files = _revision_files()
    assert len(files) == 1, (
        f"expected exactly one revision in alembic/versions/, found {len(files)}: "
        f"{[p.name for p in files]}. The history was replaced by a single baseline "
        f"because the seven revisions it replaced were never applied to any "
        f"database. Adding a second revision reintroduces the two-heads failure "
        f"that made `alembic upgrade head` unrunnable. See TICKET-009."
    )


def test_the_baseline_has_no_down_revision() -> None:
    """A down_revision would make the single revision a second head again."""
    revisions = _revisions()
    assert len(revisions) == 1, f"expected one revision id, parsed {revisions}"
    revision_id, down = next(iter(revisions.items()))
    assert down in ("", "None"), (
        f"the baseline {revision_id!r} declares down_revision={down!r}. A chain of "
        f"two or more is a history again, and two heads is what autogenerate "
        f"refuses to run against."
    )


def test_the_revision_id_fits_the_table_that_stores_it() -> None:
    """A long id cannot be stamped, which is why the live column was widened by hand."""
    for revision_id in _revisions():
        assert len(revision_id) <= MAX_REVISION_ID_LENGTH, (
            f"revision id {revision_id!r} is {len(revision_id)} characters, over the "
            f"{MAX_REVISION_ID_LENGTH} that alembic_version.version_num holds. It cannot "
            f"be stamped on a fresh database, and stamping the live one required "
            f"widening the column to varchar(64) by hand. See TICKET-010."
        )


def test_the_baseline_says_it_creates_nothing_and_how_to_stamp() -> None:
    """The baseline is an anchor, not a schema. That must be discoverable in the file.

    A reader who finds only `upgrade()` / `downgrade()` with empty bodies will
    assume the migration is broken. The file has to say what it is for and what
    to do instead, because the schema comes from deploy/schema.sql.
    """
    (only,) = _revision_files()
    text = only.read_text(encoding="utf-8")
    for phrase in ("deploy/schema.sql", "stamp", "baseline"):
        assert phrase in text, (
            f"alembic/versions/{only.name} never mentions {phrase!r}. The baseline "
            f"creates no tables, so the file must state that the schema comes from "
            f"deploy/schema.sql and that an existing database is brought in with "
            f"`alembic stamp`, or the next reader will think the migration is empty "
            f"by mistake."
        )


def test_alembic_ini_creates_the_version_column_at_its_normal_width() -> None:
    """Guard the assumption behind MAX_REVISION_ID_LENGTH.

    Alembic's own DDL makes version_num varchar(32). Nothing widens it. If that
    ever changes here, the width the live database was patched to is not evidence
    of anything.
    """
    text = ALEMBIC_INI.read_text(encoding="utf-8")
    assert "version_num" not in text, (
        "alembic.ini references version_num. The live database's version_num was "
        "hand-widened to varchar(64) to fit a 48-character revision id; do not "
        "encode that workaround into configuration. Keep ids short instead."
    )
