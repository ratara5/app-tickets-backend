from enum import Enum


class UserRole(str, Enum):
    technician = "TECHNICIAN"
    director = "DIRECTOR"
    administrator = "ADMINISTRATOR"