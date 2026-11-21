"""All enum types (stored as native PostgreSQL enums; never edit members without /db-change)."""
import enum


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    DATA_ENTRY = "data_entry"
    VIEWER = "viewer"


class EventType(str, enum.Enum):
    PD_TEST = "pd_test"
    SERVICE = "service"
    BIRTH = "birth"
    DEATH = "death"
    SOLD = "sold"
    MISSING = "missing"
    GIFT_IN = "gift_in"
    GIFT_OUT = "gift_out"
    BOUGHT = "bought"
    TRANSFER = "transfer"
    CATEGORY_CHANGE = "category_change"
    ABORTION = "abortion"
    WEANING = "weaning"  # Moving calves from nursing to weaned categories


class SpeciesType(str, enum.Enum):
    CATTLE = "cattle"
    SHEEP = "sheep"
    GOAT = "goat"


class AbortionStage(str, enum.Enum):
    EARLY = "early"      # 0-3 months
    MID = "mid"          # 3-6 months
    LATE = "late"        # 6-9 months


class AnimalSex(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"


class AnimalAcquisitionType(str, enum.Enum):
    BORN = "born"
    BOUGHT = "bought"
    GIFT_IN = "gift_in"


class AnimalStatus(str, enum.Enum):
    ACTIVE = "active"
    SOLD = "sold"
    DEAD = "dead"
    TRANSFERRED = "transferred"
    MISSING = "missing"


class HealthEventType(str, enum.Enum):
    DIPPING = "dipping"
    VACCINATION = "vaccination"
    DEWORMING = "deworming"
    LOG = "log"


class CategoryScope(str, enum.Enum):
    ALL = "all"
    SPECIFIC = "specific"


class ServiceType(str, enum.Enum):
    NATURAL = "natural"
    AI = "ai"


class PDResult(str, enum.Enum):
    PREGNANT = "pregnant"
    OPEN = "open"
    REPEAT = "repeat"


class ReproductiveCycleStatus(str, enum.Enum):
    OPEN = "open"
    SERVED = "served"
    PREGNANT = "pregnant"
    CALVED = "calved"
    ABORTED = "aborted"


class CalvingOutcome(str, enum.Enum):
    LIVE_CALF = "live_calf"
    STILLBIRTH = "stillbirth"
    ABORTION = "abortion"
    ASSISTED_LIVE = "assisted_live"
    ASSISTED_DEAD = "assisted_dead"


class NoteType(str, enum.Enum):
    OBSERVATION = "observation"
    WEIGHT = "weight"
    MEASUREMENT = "measurement"
    INCIDENT = "incident"
    HEALTH = "health"
    OTHER = "other"


class AnimalIdentifierType(str, enum.Enum):
    EID = "eid"
    UHF_TAG = "uhf_tag"
    READER_CODE = "reader_code"
    VISUAL_TAG = "visual_tag"
    BRANDING_MARK = "branding_mark"
    OTHER = "other"


class ReconciliationInputType(str, enum.Enum):
    RFID = "rfid"
    VISUAL = "visual"
    MIXED = "mixed"


class ReproductiveEventType(str, enum.Enum):
    PD_TEST = "pd_test"
    CALVING = "calving"
    ABORTION = "abortion"
    SERVICE = "service"


class CustomerType(str, enum.Enum):
    ABATTOIR = "abattoir"
    FEEDLOT = "feedlot"
    INDIVIDUAL = "individual"
    OTHER = "other"


class TransitionTriggerType(str, enum.Enum):
    AGE = "age"      # trigger when the animal reaches trigger_age_months
    EVENT = "event"  # trigger on a named event (e.g. first_calving)
