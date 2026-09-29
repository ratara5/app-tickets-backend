"""Guards that the ORM models still describe the live database.

`tests/test_alembic_env.py` explains why the suite cannot catch models that
disagree with the database: `conftest.py` builds the test schema with
`Base.metadata.create_all`, so the tests agree with the models by construction.
TICKET-019 measured that disagreement with `alembic check` against a database
built from `deploy/schema.sql` and found roughly sixty operations, of which the
largest groups were audit columns that the model typed as naive `DateTime` and
declared `NOT NULL` while live stores `timestamptz` and allows NULL.

The rules below therefore assert the reconciled declarations directly against
`Base.metadata`, so no database is required and the checks run in CI. Each
expectation is a value measured from live; reverting one of these edits to the
value it had before TICKET-019 makes its test fail.
"""
import importlib
import pkgutil

import pytest
from sqlalchemy import Date, DateTime, Enum as SAEnum, Text, Uuid
from sqlalchemy import Integer, String
from sqlalchemy.types import Variant

import app.models
from app.models.base import Base

# Tables whose audit columns come from AuditMixin, plus `pauses`, which declares
# its own copy. `fsm_users` is excluded on purpose: it stores a naive timestamp
# that is genuinely NOT NULL, and does not use the mixin.
AUDITED_TABLES = (
    "adticketswkd",
    "cancellations",
    "maintenances",
    "maintenances_spares",
    "maintenances_technicians",
    "pauses",
    "photos",
    "tickets",
)


def _import_every_model() -> None:
    for module in pkgutil.iter_modules(app.models.__path__):
        importlib.import_module(f"app.models.{module.name}")


_import_every_model()


def _column(table_name: str, column_name: str):
    return Base.metadata.tables[table_name].columns[column_name]


def _base_type(column) -> object:
    """Unwrap the SQLite variant so the Postgres type can be asserted.

    `Enum(...).with_variant(String(), "sqlite")` yields a `Variant` holding the
    Enum as its `impl`; the test database must keep VARCHAR while live keeps the
    enum, so the interesting type is the wrapped one.
    """
    return column.type.impl if isinstance(column.type, Variant) else column.type


@pytest.mark.parametrize("table_name", AUDITED_TABLES)
def test_audit_timestamps_are_timezone_aware_and_nullable(table_name: str) -> None:
    for name in ("created_at", "updated_at"):
        column = _column(table_name, name)
        assert isinstance(_base_type(column), DateTime), (
            f"{table_name}.{name} must stay a DateTime"
        )
        assert column.type.timezone is True, (
            f"{table_name}.{name} must stay timezone=True to match live timestamptz"
        )
        assert column.nullable is True, (
            f"{table_name}.{name} must stay nullable to match live"
        )


@pytest.mark.parametrize("table_name", AUDITED_TABLES)
def test_audit_actor_columns_are_nullable(table_name: str) -> None:
    for name in ("created_by", "updated_by"):
        assert _column(table_name, name).nullable is True, (
            f"{table_name}.{name} must stay nullable; live rows carry NULL there"
        )


@pytest.mark.parametrize(
    "table_name,column_name",
    (
        ("adticketswkd", "observations_wkd"),
        ("cancellations", "cancellation_reason"),
        ("maintenances", "initial_photo_path"),
        ("maintenances", "maintenance_description"),
        ("maintenances", "observations"),
        ("pauses", "pause_reason"),
        ("photos", "photo_path"),
        ("uploads_sessions", "col_name"),
        ("uploads_sessions", "content_type"),
        ("uploads_sessions", "parent_tab"),
        ("uploads_sessions", "tab_name"),
    ),
)
def test_text_columns_stay_text(table_name: str, column_name: str) -> None:
    assert isinstance(_base_type(_column(table_name, column_name)), Text), (
        f"{table_name}.{column_name} is a text column in live, not varchar"
    )


@pytest.mark.parametrize(
    "table_name,column_name",
    (("tickets", "ticket_date"), ("maintenances", "maintenance_date")),
)
def test_date_columns_stay_date(table_name: str, column_name: str) -> None:
    assert isinstance(_base_type(_column(table_name, column_name)), Date), (
        f"{table_name}.{column_name} is a date column in live, not a timestamp"
    )


@pytest.mark.parametrize(
    "column_name,enum_name",
    (("priority", "priority_type"), ("status", "status_type")),
)
def test_ticket_enum_columns_stay_enums(column_name: str, enum_name: str) -> None:
    column_type = _base_type(_column("tickets", column_name))
    assert isinstance(column_type, SAEnum), (
        f"tickets.{column_name} is an enum column in live, not varchar"
    )
    assert column_type.name == enum_name


def test_priority_enum_keeps_live_values() -> None:
    assert list(_base_type(_column("tickets", "priority")).enums) == [
        "LOW",
        "MEDIUM",
        "HIGH",
    ]


def test_status_enum_keeps_live_values() -> None:
    assert list(_base_type(_column("tickets", "status")).enums) == [
        "OPEN",
        "ASSIGNED",
        "CANCELLED",
        "IN PROGRESS",
        "PAUSED",
        "CLOSED",
        "SIGNED",
    ]


def test_token_blacklist_jti_is_a_uuid() -> None:
    column_type = _base_type(_column("token_blacklist", "jti"))
    assert isinstance(column_type, Uuid), (
        "token_blacklist.jti is a uuid column in live, not varchar(36)"
    )
    assert column_type.as_uuid is False, (
        "jti must keep as_uuid=False so the raw JWT string can be bound"
    )


def test_worksheet_pdf_path_keeps_live_length() -> None:
    column_type = _base_type(_column("worksheets", "pdf_path"))
    assert isinstance(column_type, String)
    assert column_type.length == 100, "live stores worksheets.pdf_path as varchar(100)"


@pytest.mark.parametrize(
    "column_name", ("receiver_signature_timestamp", "generated_at")
)
def test_worksheet_timestamps_are_timezone_aware(column_name: str) -> None:
    assert _column("worksheets", column_name).type.timezone is True


def test_fsm_user_identity_columns_are_not_nullable() -> None:
    for name in ("email", "user_name", "passwd", "user_role"):
        assert _column("fsm_users", name).nullable is False, (
            f"fsm_users.{name} is NOT NULL in live"
        )


def test_fsm_user_created_at_stays_a_naive_timestamp() -> None:
    column = _column("fsm_users", "created_at")
    assert column.type.timezone is not True, (
        "fsm_users.created_at is timestamp without time zone in live"
    )
    assert column.nullable is False


@pytest.mark.parametrize(
    "column_name",
    (
        "parent_tab",
        "parent_id",
        "tab_name",
        "col_name",
        "content_type",
        "total_size",
        "total_chunks",
        "received_chunks",
        "expires_at",
    ),
)
def test_upload_session_columns_are_not_nullable(column_name: str) -> None:
    assert _column("uploads_sessions", column_name).nullable is False, (
        f"uploads_sessions.{column_name} is NOT NULL in live"
    )


def test_upload_session_optional_columns_stay_nullable() -> None:
    for name in ("completed", "replaces_photo_id"):
        assert _column("uploads_sessions", name).nullable is True


def test_technician_user_id_constraint_and_index_keep_live_names() -> None:
    table = Base.metadata.tables["technicians"]
    names = {getattr(item, "name", None) for item in table.constraints}
    assert "technicians_user_id_unique" in names, (
        "live names the unique constraint on technicians.user_id; Alembic compares "
        "constraints by name, so an unnamed one is reported as a difference"
    )
    assert "fki_technicians_user_id_fkey" in {index.name for index in table.indexes}


def test_photo_id_stays_text() -> None:
    assert isinstance(_base_type(_column("photos", "photo_id")), Text)


def test_integer_typed_identifiers_stay_integers() -> None:
    for table_name, column_name in (
        ("tickets", "ticket_id"),
        ("maintenances", "ticket_id"),
        ("technicians", "technician_id"),
        ("fsm_users", "user_id"),
    ):
        assert isinstance(_base_type(_column(table_name, column_name)), Integer)
