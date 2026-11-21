"""ORM models, grouped by domain. Import everything from here: `from models import Animal, EventType`.

Every module must be imported here so Base.metadata (create_all) and string-based
relationship() targets see all tables. Add new models to the matching module and list them below.
"""
from models.enums import (  # noqa: F401
    UserRole,
    EventType,
    SpeciesType,
    AbortionStage,
    AnimalSex,
    AnimalAcquisitionType,
    AnimalStatus,
    HealthEventType,
    CategoryScope,
    ServiceType,
    PDResult,
    ReproductiveCycleStatus,
    CalvingOutcome,
    NoteType,
    AnimalIdentifierType,
    ReconciliationInputType,
    ReproductiveEventType,
    CustomerType,
    TransitionTriggerType,
)
from models.core import (  # noqa: F401
    User,
    Location,
    Category,
    OpeningBalance,
    DailyLog,
    Disease,
    Event,
    EventAnimalLink,
    StockLevel,
)
from models.animals import (  # noqa: F401
    Animal,
    AnimalPhoto,
    AnimalNote,
    AnimalLocationHistory,
    AnimalIdentifier,
    CategoryTransitionRule,
    CategoryTransition,
)
from models.health import (  # noqa: F401
    HealthInterval,
    FarmHealthEvent,
    VaccineType,
)
from models.reproduction import (  # noqa: F401
    BullAssignment,
    ReproductiveCycle,
    BCSRecord,
    ReproductiveEvent,
)
from models.reconciliation import (  # noqa: F401
    ReconciliationSession,
    ReconciliationEntry,
)
from models.sales import (  # noqa: F401
    Customer,
    SaleDetail,
)
from models.mortality import (  # noqa: F401
    DeathCause,
    MortalityThreshold,
)
from database import Base  # noqa: F401
