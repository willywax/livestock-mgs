from models import Category, SpeciesType, User, UserRole, Location
from auth import get_password_hash

# Cattle categories
CATTLE_CATEGORIES = [
    {"name_sw": "Koo", "name_en": "Cows", "sort_order": 1},
    {"name_sw": "Mitamba", "name_en": "Heifers", "sort_order": 2},
    {"name_sw": "Ndama Dume", "name_en": "Bull calves", "sort_order": 3},
    {"name_sw": "Ndama Jike", "name_en": "Heifer calves", "sort_order": 4},
    {"name_sw": "Achishwa Dume", "name_en": "Weaner bulls", "sort_order": 5},
    {"name_sw": "Achishwa Jike", "name_en": "Weaner heifers", "sort_order": 6},
    {"name_sw": "Maksai", "name_en": "Steers", "sort_order": 7},
    {"name_sw": "Dume Mbegu", "name_en": "Breeding bulls", "sort_order": 8},
    {"name_sw": "Dume Wadogo", "name_en": "Young bulls", "sort_order": 9},
]

# Goat and Sheep categories (same for both)
SMALL_STOCK_CATEGORIES = [
    {"name_sw": "Koo", "name_en": "Does/Ewes", "sort_order": 1},
    {"name_sw": "Mitamba", "name_en": "Heifers", "sort_order": 2},
    {"name_sw": "Vichinda Dume", "name_en": "Male kids/lambs", "sort_order": 3},
    {"name_sw": "Vichinda Jike", "name_en": "Female kids/lambs", "sort_order": 4},
    {"name_sw": "Achishwa Dume", "name_en": "Weaners male", "sort_order": 5},
    {"name_sw": "Achishwa Jike", "name_en": "Weaners female", "sort_order": 6},
    {"name_sw": "Dume Mbegu", "name_en": "Breeding males", "sort_order": 7},
    {"name_sw": "Maksai", "name_en": "Castrated males", "sort_order": 8},
    {"name_sw": "Dume Wadogo", "name_en": "Young males", "sort_order": 9},
]

def get_seed_categories():
    categories = []
    
    # Cattle
    for cat in CATTLE_CATEGORIES:
        categories.append(Category(
            name_sw=cat["name_sw"],
            name_en=cat["name_en"],
            species=SpeciesType.CATTLE,
            sort_order=cat["sort_order"]
        ))
    
    # Goats
    for cat in SMALL_STOCK_CATEGORIES:
        categories.append(Category(
            name_sw=cat["name_sw"],
            name_en=cat["name_en"],
            species=SpeciesType.GOAT,
            sort_order=cat["sort_order"]
        ))
    
    # Sheep
    for cat in SMALL_STOCK_CATEGORIES:
        categories.append(Category(
            name_sw=cat["name_sw"],
            name_en=cat["name_en"],
            species=SpeciesType.SHEEP,
            sort_order=cat["sort_order"]
        ))
    
    return categories

def get_default_admin():
    return User(
        phone="255700000000",
        password_hash=get_password_hash("admin123"),
        name="Admin",
        role=UserRole.ADMIN
    )

def get_sample_locations():
    return [
        Location(name="Shamba Kuu", description="Main farm headquarters"),
        Location(name="Shamba Kaskazini", description="Northern branch"),
        Location(name="Shamba Kusini", description="Southern branch"),
    ]
