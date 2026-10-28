# Script Analyser Pro — Screenplay Intelligence & Comparative Market Platform

A full-stack screenplay analysis, production planning, GIS location mapping, and film-market research web application built with **FastAPI**, **Python**, **Supabase (PostgreSQL & Auth)**, **SQLite (Local)**, **Vanilla JavaScript**, **Leaflet + OpenStreetMap**, and the **OMDb API**.

---

## What's New in Version 2.1

1. **Supabase Authentication**:
   - Secure user registration, sign-in, and session persistence using Supabase Auth.
   - FastAPI JWT verification dependency protecting private screenplay endpoints.
   - Multi-tenant data isolation: Each user's projects, scripts, and analyses are isolated and private.
   - Pre-configured 1-click **Faculty Demonstration Access** for university presentations.

2. **Supabase PostgreSQL & SQLite Hybrid Database**:
   - Production PostgreSQL connection pooling with SSL support.
   - Zero-config local SQLite mode for offline testing and development.
   - Multi-table schema: `users`, `projects`, `scenes`, `characters`, `character_traits`, `character_relationships`, `locations`, `schedules`, `comparisons`, `market_reports`.

3. **Safe SQLite to Supabase Migration Tool**:
   - `migrate_to_supabase.py` migrates all existing screenplay projects, scenes, character dossiers, GIS locations, and schedules to Supabase cloud PostgreSQL.
   - Preserves all relational IDs and resets PostgreSQL sequences.

4. **Production Hosting Configurations**:
   - Pre-configured `render.yaml` for 1-click Render Web Service deployment.
   - Containerized `Dockerfile` with automated health check.
   - Detailed walkthrough guide in `DEPLOYMENT.md`.

---

## Core Application Modules

- **Screenplay NLP Parser**: Accurately extracts scene headings, `INT/EXT` tags, locations, sets, times of day, and scene numbers without malformed concatenations.
- **Evidence-Grounded Character Profiling**: Role classifications (`Protagonist`, `Antagonist / Foil`, `Supporting`), personality traits with scene references and verbatim quotation citations, motivations, and story arcs.
- **GIS Location Resolution & Leaflet Map**: Normalized scene sets with OpenStreetMap Nominatim geocoding, interactive pin clustering, and manual filming coordinate editing.
- **Production Scheduling & Cost Estimation**: Sequential narrative vs. location-grouped shooting strategies, day-by-day breakdowns, and customizable budget department rates.
- **Comparative Film Market Intelligence**: Side-by-side OMDb film benchmarking matrix and 9-point commercial intelligence report.

---

## Quick Start (Local Development)

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
```
*(Optionally provide your `OMDB_API_KEY`, `SUPABASE_URL`, and `DATABASE_URL` in `.env`)*

### 3. Run Automated Tests
```bash
pytest
```
*Executes all 30 unit and integration tests across auth, parsing, characters, GIS, and scheduling.*

### 4. Start the Application
```bash
uvicorn app.main:app --reload
```
Open **`http://127.0.0.1:8000`** in your browser.

---

## Fast Faculty Demonstration Mode

To demonstrate the application without manual account registration:
1. Open the website: `http://127.0.0.1:8000` (or your deployed Render URL).
2. The login screen will appear.
3. Click the **"🎓 Faculty / Fast Demo Access"** button.
4. You will immediately be authenticated as the authorized demonstration reviewer (`faculty@scriptanalyser.com`).
5. All screenplay analysis, character profiling, GIS mapping, scheduling, and market comparison features are fully unlocked.
6. Click **"↪" (Sign Out)** in the sidebar footer to demonstrate that unauthenticated visitors are blocked.

---

## Migrating Data to Supabase PostgreSQL

When you have created your Supabase project:
```bash
python migrate_to_supabase.py --target-url "postgresql://postgres:YOUR_PASSWORD@db.YOUR_REF.supabase.co:5432/postgres"
```

For full cloud hosting instructions, see [**`DEPLOYMENT.md`**](DEPLOYMENT.md).
