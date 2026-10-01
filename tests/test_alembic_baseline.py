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

They were replaced by a baseline derived from `infra/schema.sql`. These tests
hold that arrangement in place. The failure they prevent is not subtle: an
unconnected revision reintroduces a second head, and a long id reintroduces the
column that had to be hand-widened in the first place.

Note what the invariant is and is not. It is a single head reached by one linear
chain, NOT a single revision file. The baseline is an empty anchor so that
forward migrations have something to descend from, and the first one,
`0002_widen_uom_factor`, already exists (TICKET-021). A test that counted files
would have blocked a correct migration, so the count assertions below became
chain assertions.

No database is required, so these run in CI.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VERSIONS_DIR = REPO_ROOT / "alembic" / "versions"
SCHEMA_SQL = REPO_ROOT / "infra" / "schema.sql"
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


def _heads() -> list[str]:
    """Revisions that no other revision descends from. More than one is a fork.

    A head is identified by having no *children*, not by having no parent. Those
    are opposite ends of the chain, and conflating them reports the baseline as
    the head, which is the bug this helper was written to avoid.
    """
    revisions = _revisions()
    parents = set(revisions.values())
    return [rev for rev in revisions if rev not in parents]


def test_the_history_is_a_single_linear_chain_ending_in_one_head() -> None:
    """One head, reached by one unbroken chain. A second head blocks autogenerate.

    This replaced an assertion that exactly one revision file exists. That was
    wrong as a rule: the baseline is deliberately empty so real migrations have
    something to descend from, and asserting a single file would fail the first
    correct migration anyone added. What actually breaks `alembic upgrade head` is
    a fork, not a length.
    """
    revisions = _revisions()
    heads = _heads()
    assert len(heads) == 1, (
        f"expected exactly one head, found {len(heads)}: {heads}. The history was "
        f"replaced by a single baseline because the seven revisions it replaced were "
        f"never applied to any database, and two heads is what made `alembic upgrade "
        f"head` unrunnable and what autogenerate refuses to run against. See TICKET-009."
    )

    # Walk back from the head. Every step must resolve, and the walk must cover
    # every revision: a cycle, or a revision whose down_revision names something
    # that does not exist, would otherwise pass the head count.
    seen: list[str] = []
    cursor = heads[0]
    while cursor in revisions and cursor not in seen:
        seen.append(cursor)
        cursor = revisions[cursor]
    assert len(seen) == len(revisions), (
        f"walking back from head {heads[0]!r} reached {seen} and left "
        f"{sorted(set(revisions) - set(seen))} unvisited. Every revision must be on "
        f"the one chain, otherwise the history branches or dangles."
    )
    assert revisions[seen[-1]] in ("", "None"), (
        f"the walk from head {heads[0]!r} bottoms out at {seen[-1]!r}, which still "
        f"names a parent {revisions[seen[-1]]!r} that is not on the chain. The oldest "
        f"revision must have no down_revision so there is exactly one root."
    )


def test_the_baseline_has_no_down_revision() -> None:
    """The root of the chain is the baseline, and it is a root."""
    revisions = _revisions()
    roots = [rev for rev, down in revisions.items() if down in ("", "None")]
    assert len(roots) == 1, (
        f"expected exactly one root revision with no down_revision, found {roots} "
        f"in {revisions}. A second root is a second head."
    )
    assert "0001_baseline" in roots, (
        f"the root is {roots[0]!r}, not the baseline. The baseline is the anchor "
        f"every forward migration descends from; renaming it silently orphans the "
        f"migrations that point at it."
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
    to do instead, because the schema comes from infra/schema.sql.
    """
    baseline = VERSIONS_DIR / "0001_baseline.py"
    assert baseline.exists(), f"the baseline is missing from {VERSIONS_DIR}"
    text = baseline.read_text(encoding="utf-8")
    for phrase in ("infra/schema.sql", "stamp", "baseline"):
        assert phrase in text, (
            f"alembic/versions/{only.name} never mentions {phrase!r}. The baseline "
            f"creates no tables, so the file must state that the schema comes from "
            f"infra/schema.sql and that an existing database is brought in with "
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
