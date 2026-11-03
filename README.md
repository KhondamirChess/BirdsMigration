# Bird–HPAI Risk Simulator

Lab project: **Predicting Migratory Bird–HPAI Risk with an Ecological World Model**.

A map simulator that plays back GPS tracks of birds over time and shows when they come close to
poultry farms (buffer zone around each farm, 3 km by default). The interface is in English and Korean.

## Features

- Play back GPS tracks of many birds on one map: play/pause (<kbd>Space</kbd>), speed, time slider, jump to a date (UTC)
- Route lines and muted arrows along the route, drawn as the bird moves (from its first fix to where it is now)
- A brighter arrow at each bird pointing to its next recorded position
- "Full routes" (off by default) shows the whole season's route as a faint line
- Poultry farms with a buffer zone (selectable radius); a farm is coloured by whether a bird
  has not entered its zone yet, entered earlier, or is inside now
- "Watch bird" to follow a single bird, and a list for showing or hiding individual birds
- Data check: rows read, valid fixes, rows dropped and why (position 0,0, duplicate time)
- Offline base map: relief, rivers and lakes, place names; an optional online topographic layer

## Datasets

Every dataset in the database appears in the simulator under step 1.

| # | Dataset | Birds | Source |
|---|---------|-------|--------|
| 1–3 | Demo scenarios: baseline wintering, cold wave shift, spring departure | the same 20 mallards | **synthetic** (`data/generate_demo_data.py`) |
| 4 | Poultry network China 2022 | 110 mallards | real export, `data/real_data/` |
| 5 | KU 2025 Oriental magpie tracking | 6 magpies | real KU tag export, `data/real_data/` |

The demo tracks and demo farms are synthetic and must not be read as real data.

## Quick start (Docker)

```bash
docker compose up -d --build     # PostgreSQL 16 + backend
```

Open **http://localhost:8000**. On first start the backend loads the demo data into an empty database.

```bash
docker compose ps                # status
docker compose logs -f backend   # backend logs
docker compose down              # stop (the database volume is kept)
```

## Running the backend without Docker

You still need PostgreSQL. You can start only the database with `docker compose up -d db`.

```bash
cd backend
cp .env.example .env             # DATABASE_URL=postgresql+psycopg://hpai:hpai@localhost:5432/hpai
pip install -r requirements.txt
uvicorn app.main:app --reload    # http://localhost:8000
```

## Adding data

Any Movebank-style CSV (individual ID, timestamp, latitude, longitude, optional species) can be imported:

```bash
cd backend
python -m scripts.import_dataset "../data/real_data/Poultry network China 2022.csv"
python -m scripts.import_dataset FILE --name "My dataset" --replace
```

After a page reload the dataset is listed in the simulator.

Other scripts:

```bash
python data/generate_demo_data.py                       # regenerate the synthetic demo CSVs
cd backend && python -m scripts.seed_demo --reset       # reload the demo scenarios and farms
python data/convert_ku_tracking.py data/real_data/ku2025_oriental_magpie_tracking.xls   # KU .xls -> CSV
python data/build_map_layers.py --cache DIR             # rebuild the offline base map (already committed)
```

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | status and counts of datasets, birds and farms |
| GET | `/api/datasets` | list of datasets |
| GET | `/api/datasets/{slug}/tracks` | GPS fixes of one dataset |
| GET | `/api/birds` | list of birds |
| GET | `/api/farms` | poultry farms |

Interactive docs: http://localhost:8000/docs

## Project layout

```
backend/            FastAPI + SQLAlchemy + PostgreSQL
  app/controllers/  HTTP routes
  app/services/     logic (dataset import, track parsing, farms)
  app/repositories/ database access
  app/models/       ORM models: dataset, bird, fix, farm
  app/schemas/      API schemas
  scripts/          import_dataset, seed_demo
frontend/           single-page simulator (index.html), offline map in geo/
data/               demo data generator, converters, demo_data/ and real_data/
agent/              reserved for a later milestone, intentionally empty
docker-compose.yml  db + backend
```

## Progress

See [PROGRESS.md](PROGRESS.md).
