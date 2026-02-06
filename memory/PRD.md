# ShambaManager - Livestock Stock Management System

## Original Problem Statement
Build a multi-location livestock stock management web app for a farm business in Tanzania. Animals are tracked as COUNTS (not individual IDs). The farm has multiple LOCATIONS and multiple SPECIES: CATTLE, SHEEP, GOAT.

## User Choices
- **Authentication**: Phone number + password (JWT-based)
- **Categories**: Displayed in Swahili
- **Export Reports**: Not needed for MVP
- **Notifications**: Not needed for MVP
- **Branding**: Earthy green theme (ShambaManager)

## User Personas
1. **Admin** - Full system access, manage users/locations/categories/opening balances
2. **Data Entry (Office)** - Enter daily logs and events
3. **Manager/Viewer** - Read-only access to reports and dashboard

## Core Requirements (Static)
- Track livestock as counts per Location + Species + Category
- Record daily events: Birth, Death, Sold, Missing, Gift In, Gift Out, Bought, Transfer, Category Change, Abortion
- Opening balances per period
- Daily logs with "No events" option
- Transfer: subtract from source, add to destination (atomic)
- Category Change: same location, different category (atomic)
- Prevent negative stock (warn non-admins, admin can override)
- Audit fields on all records

## Technical Architecture
- **Backend**: FastAPI + SQLAlchemy ORM + SQLite (async with aiosqlite)
- **Frontend**: React + Tailwind CSS + Shadcn UI + Phosphor Icons
- **Authentication**: JWT with phone/password
- **Database**: SQLite (shamba.db)

## What's Been Implemented (Feb 5, 2026)
### Backend
- [x] User authentication (phone + password, JWT tokens)
- [x] User management CRUD (admin only)
- [x] Location management CRUD
- [x] Category seeding (Swahili names for Cattle, Sheep, Goat)
- [x] Opening balances management
- [x] Daily logs with enhanced events including WEANING event type
- [x] Stock level calculations
- [x] Dashboard API with location filter, herd performance, weaning rate, net changes
- [x] Reports API (daily consolidated, date range)
- [x] Analytics API with detailed death analysis (by disease), abortion analysis (by stage), sales analysis
- [x] Disease management (CRUD for diseases, default diseases seeded)
- [x] Abortion stage tracking (early, mid, late)
- [x] Role-based access control
- [x] Event edit/delete API (admin only, works on locked logs too)
- [x] CSV Import for Locations and Opening Balances

### Event Fields Enhanced
- [x] Animal tags for all events
- [x] Death events: cause of death, days sick, attending vet/DK
- [x] Birth events: mother tag, offspring tags
- [x] Sale events: buyer name, phone, address, sale price

### Frontend
- [x] Login page with earthy theme
- [x] Dashboard with herd performance (calving, weaning, mortality rates), net changes, location filter
- [x] Locations list + detail view with CSV Import dialog
- [x] Daily Logs list + detail view
- [x] New Daily Log form with enhanced event fields including weaning
- [x] Edit/Delete events (admin only, including locked logs)
- [x] Opening Balances management with CSV Import dialog
- [x] Reports with Herd Analytics, Death Analysis tabs, location filter
- [x] User management (admin)
- [x] Responsive sidebar navigation

### Categories Seeded (Swahili)
**Cattle**: Koo, Mitamba, Ndama Dume, Ndama Jike, Achishwa Dume, Achishwa Jike, Maksai, Dume Mbegu, Dume Wadogo
**Sheep/Goat**: Koo, Mitamba, Vichinda Dume, Vichinda Jike, Achishwa Dume, Achishwa Jike, Dume Mbegu, Maksai, Dume Wadogo

## Prioritized Backlog

### P0 (Critical) - DONE
- [x] Authentication
- [x] Dashboard
- [x] Locations
- [x] Daily Logs with Events
- [x] Opening Balances
- [x] Stock Calculations

### P1 (Important) - Next
- [ ] Add sample/demo locations (Shamba Kuu, Shamba Kaskazini, Shamba Kusini)
- [ ] Negative stock warning modal
- [ ] Lock daily log after manager review
- [ ] Edit existing daily log (before lock)

### P2 (Nice to Have)
- [ ] Export reports (PDF/CSV)
- [ ] Dashboard charts (recharts)
- [ ] Date range picker component
- [ ] Email/SMS notifications
- [ ] Offline mode support

### Completed (Feb 5, 2026)
- [x] Bulk opening balance import via CSV
- [x] Bulk locations import via CSV
- [x] Dashboard herd performance indicators (calving/weaning/mortality rates per species)
- [x] Location filter on Dashboard and Analytics
- [x] Enhanced Analytics with sold/bought counts, sales summary, death causes analysis
- [x] Detailed death analysis (by species, category, cause, vet attendance, days sick)
- [x] Weaning rate calculation and weaning event type
- [x] Net change in animals tracking (births, deaths, bought, sold, gifts, missing)
- [x] Disease management - specify disease when cause of death is "disease"
- [x] Abortion stage tracking (early, mid, late) with analytics
- [x] Enhanced sales analytics (by species, by category, top buyers, price range)

## Next Tasks
1. Update frontend forms to capture disease selection for deaths
2. Update frontend forms to capture abortion stage
3. Update Reports page to show new abortion and sales analytics
4. Add sample demo locations
