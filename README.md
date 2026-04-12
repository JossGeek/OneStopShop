# OneStopShop

The SUNRISE One Stop Shop application.

## Database Bootstrap (PostgreSQL + Django migrations)

This branch bootstraps the data layer for Task 1/2/3 with:

- Dockerized PostgreSQL
- Dedicated `content` schema
- Django ORM models + migrations
- Deterministic seed commands

### What is included

- Core Task 1 entities:
	- `offer`, `offer_type`, `organization`, `contact`, `domain`, `oss_user`, `user_organization`, `user_role`, `source_type`, `target_profile`
- Task 2 decisions:
	- D-01: `contact.contact_approved` (default `false`)
	- D-02: `offer_contact` junction table
- Lookup/reference seeding from Task 2 (`OSS_Mapping_Seed.json`)
- Task 3 offer seeding from sample data (`OSS_Sample_Offers.json`)
	- Inserts only real + illustrative records
	- Skips fictional offers

## Quick Start

### 1) Install dependencies

```powershell
"d:/Masters/UNIBZ/Semester 2/GDSD - Sweden/.venv/Scripts/python.exe" -m pip install -r requirements.txt
```

### 2) Start PostgreSQL

```powershell
docker compose up -d postgres
```

### 3) Configure environment

Create a local `.env` from `.env.example` and adjust values if needed.

Default values:

- `POSTGRES_DB=oss_db`
- `POSTGRES_USER=oss_user`
- `POSTGRES_PASSWORD=oss_password`
- `POSTGRES_HOST=localhost`
- `POSTGRES_PORT=5432`
- `POSTGRES_SCHEMA=content`
- `DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,testserver`

### 4) Run migrations

```powershell
"d:/Masters/UNIBZ/Semester 2/GDSD - Sweden/.venv/Scripts/python.exe" manage.py migrate
```

### 5) Seed lookup data and offers

```powershell
"d:/Masters/UNIBZ/Semester 2/GDSD - Sweden/.venv/Scripts/python.exe" manage.py seed_lookups
"d:/Masters/UNIBZ/Semester 2/GDSD - Sweden/.venv/Scripts/python.exe" manage.py seed_offers
```

## Seed Sources

- `seed_data/task2/OSS_Mapping_Seed.json`
- `seed_data/task3/OSS_Sample_Offers.json`

The offer seeder excludes fictional Task 3 records by design:

- `{offer_006}`
- `{offer_015}`
- `{offer_016}`
- `{offer_017}`
