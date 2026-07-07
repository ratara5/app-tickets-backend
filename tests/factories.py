from decimal import Decimal
from datetime import datetime

import factory
from factory.alchemy import SQLAlchemyModelFactory

from app.core.security import hash_password
from app.models.fsm_user import FSMUser
from app.models.master import Technician, Spare, Market, Equipment, Labsdl
from app.models.ticket import Ticket, AddWkd
from app.models.maintenance import Maintenance, MaintenanceTechnician, MaintenanceSpare
from app.models.photo import Photo
from app.models.worksheet import Worksheet
from app.models.cancellation import Cancellation
from app.models.pause import Pause
from app.models.upload import UploadSession
from app.models.token_blacklist import TokenBlacklist


class FSMUserFactory(SQLAlchemyModelFactory):
    class Meta:
        model = FSMUser

    user_id = None
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    user_name = factory.Sequence(lambda n: f"User {n}")
    passwd = factory.LazyFunction(lambda: hash_password("password123"))
    user_role = "TECHNICIAN"
    photo_path = ""


class TechnicianFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Technician

    technician_id = None
    user_id = 0


class SpareFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Spare

    spare_id = None
    spare_name = factory.Sequence(lambda n: f"Spare {n}")
    unit = "pcs"
    price = Decimal("10.00")


class MarketFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Market

    market_id = None
    market_name = factory.Sequence(lambda n: f"Market {n}")
    city = "City"
    transport_cost = Decimal("100.00")


class EquipmentFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Equipment

    equipment_id = None
    equipment_name = factory.Sequence(lambda n: f"Equipment {n}")


class LabsdlFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Labsdl

    labsdl_id = None
    labsdl_name = factory.Sequence(lambda n: f"Labsdl {n}")
    labsdl_description = ""
    hourly_rate = Decimal("50.00")


class TicketFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Ticket

    ticket_id = None
    ticket_date = factory.LazyFunction(datetime.now)
    ticket_description = "Test ticket"
    priority = "NORMAL"
    status = "OPEN"
    market_id = 0
    equipment_id = 0
    assigned_to = None
    created_by = 0
    updated_by = 0


class AddWkdFactory(SQLAlchemyModelFactory):
    class Meta:
        model = AddWkd

    ticket_id = 0
    operation_percentage = Decimal("50.00")
    market_temperature = Decimal("25.00")
    operation_damage = False
    completed = False
    observations_wkd = ""
    created_by = 0
    updated_by = 0


class MaintenanceFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Maintenance

    maintenance_id = None
    ticket_id = 0
    maintenance_date = factory.LazyFunction(datetime.now)
    maintenance_description = "Test maintenance"
    labsdl_id = 0
    initial_photo_path = ""
    observations = ""
    created_by = 0
    updated_by = 0


class CancellationFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Cancellation

    ticket_id = 0
    cancellation_reason = "Test cancellation"
    created_by = 0
    updated_by = 0


class PauseFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Pause

    pause_id = None
    maintenance_id = None
    pause_reason = "Test pause"
    created_by = 0
    updated_by = 0


class PhotoFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Photo

    photo_id = None
    maintenance_id = 0
    photo_path = ""
    processed = False
    created_by = 0
    updated_by = 0


class WorksheetFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Worksheet

    worksheet_id = None
    maintenance_id = None
    receiver_name = ""
    receiver_doc_id = ""
    receiver_position = ""
    receiver_sap = ""
    receiver_signature = None
    receiver_signature_timestamp = None
    sheet_number = None
    pdf_path = ""
    generated_at = None
    closed = False


class UploadSessionFactory(SQLAlchemyModelFactory):
    class Meta:
        model = UploadSession

    upload_id = None
    user_id = 0
    parent_tab = "maintenances"
    parent_id = None
    tab_name = "photos"
    col_name = "photo_file"
    content_type = "image/jpeg"
    total_size = 1024
    total_chunks = 1
    received_chunks = 0
    expires_at = factory.LazyFunction(lambda: datetime.now())
    completed = False


class TokenBlacklistFactory(SQLAlchemyModelFactory):
    class Meta:
        model = TokenBlacklist

    jti = factory.Sequence(lambda n: f"jti-{n}")
    expires_at = factory.LazyFunction(lambda: datetime.now())


class MaintenanceTechnicianFactory(SQLAlchemyModelFactory):
    class Meta:
        model = MaintenanceTechnician

    maintenance_id = None
    technician_id = 0
    start_hour = factory.LazyFunction(lambda: datetime.now().time())
    end_hour = factory.LazyFunction(lambda: datetime.now().time())
    created_by = 0
    updated_by = 0


class MaintenanceSpareFactory(SQLAlchemyModelFactory):
    class Meta:
        model = MaintenanceSpare

    maintenance_id = None
    spare_id = 0
    qty = Decimal("1.00")
    created_by = 0
    updated_by = 0
