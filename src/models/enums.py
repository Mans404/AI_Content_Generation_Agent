from enum import Enum
class DoctorLanguage(str, Enum):
    AR = "AR"
    EN = "EN"


class DoctorSpecialization(str, Enum):
    INTERNAL_MEDICINE = "internal_medicine"
    DENTISTRY = "dentistry"
    DERMATOLOGY = "dermatology"
    CARDIOLOGY = "cardiology"
    NEUROLOGY = "neurology"
    PEDIATRICS = "pediatrics"
    ORTHOPEDICS = "orthopedics"
    OPHTHALMOLOGY = "ophthalmology"
    OBSTETRICS_AND_GYNECOLOGY = "obstetrics_and_gynecology"
    UROLOGY = "urology"
    GENERAL_SURGERY = "general_surgery"
    PSYCHIATRY = "psychiatry"
    ENT = "ent"
    PHYSIOTHERAPY = "physiotherapy"
    OTHER = "other"