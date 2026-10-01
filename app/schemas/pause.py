from pydantic import BaseModel


class PauseRequest(BaseModel):
    """Body of PATCH /maintenances/{maintenance_id}/pause.

    Deliberately standalone rather than a subclass of `MaintenanceUpdate`.
    `MaintenanceUpdate` is the mobile form's full-row save and requires
    `maintenance_description`, plus the spares/technicians/pauses collections
    that the save path *replaces*. Inheriting it would have forced the pause
    endpoint to accept — and then silently discard — the entire form payload,
    and made a bare `{"pause_reason": ...}` body a 422.

    The pause is the only thing this endpoint accepts, so it is the only thing
    it models. There is no maintenance status: a pause is observable as this
    row plus the owning ticket's status, never as a field on a maintenance.
    """

    pause_reason: str
