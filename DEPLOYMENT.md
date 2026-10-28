# Script Analyser Pro — Supabase Migration & Live Deployment Guide

This guide provides exact, step-by-step instructions to set up **Supabase (Authentication & PostgreSQL)**, migrate your existing screenplay data, and deploy the application live on **Render** for your university faculty demonstration.

---

## Architecture Overview

```
 ┌────────────────────────────────────────────────────────┐
 │                   Web Browser / Client                 │
 │  • Script Analyser UI (DM Sans / Plus Jakarta Sans)    │
 │  • Interactive Leaflet.js OpenStreetMap GIS            │
 │  • Supabase-js Client for Session Management           │
 └───────────────────────────┬────────────────────────────┘
                             │
            HTTPS API Calls  │  Authorization: Bearer <JWT>
                             ▼
 ┌────────────────────────────────────────────────────────┐
 │             FastAPI Backend (Render / Local)           │
 │  • Screenplay NLP Parser & Scene Heading Extractor     │
 │  • Evidence-Grounded Character Profiling Engine        │
 │  • Production Shooting Scheduler & Cost Estimator      │
 │  • OMDb Comparative Film Market Intelligence           │
 │  • Supabase JWT Token Verification Dependency          │
 └─────────────┬────────────────────────────┬─────────────┘
               │                            │
   SQL Queries │ (psycopg2 / SSL)           │ REST API
               ▼                            ▼
 ┌───────────────────────────┐  ┌─────────────────────────┐
 │   Supabase PostgreSQL     │  │        OMDb API         │
 │  • 10 Relational Tables   │  │  • Film Ratings (IMDb,  │
 │  • User-Scoped Isolation  │  │    Rotten Tomatoes, MC) │
 │  • Full Script & Analysis │  │  • Box Office & Genres  │
 └───────────────────────────┘  └─────────────────────────┘
```

---

## 1. Quick Local Demonstration (Zero-Config Mode)

The application includes an automatic local mode that runs out of the box using your SQLite database and built-in session verification:

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run automated test suite (30 passing tests)
pytest

# 3. Start local development server
uvicorn app.main:app --reload
```

- Open `http://127.0.0.1:8000/` in your web browser.
- Click **"🎓 Faculty / Fast Demo Access"** to immediately log in with the pre-authorized demonstration account (`faculty@scriptanalyser.com`).

---

## 2. Setting Up Supabase (Database & Auth)

Follow these steps to create your free Supabase cloud instance:

### Step 2.1 — Create a Supabase Project
1. Go to [https://supabase.com](https://supabase.com) and sign in or create a free account.
2. Click **"New project"**.
3. Fill in:
   - **Name**: `script-analyser`
   - **Database Password**: Choose a strong password and save it securely.
   - **Region**: Choose the region closest to you (e.g., *Central India / Mumbai*, *North America*, or *Europe*).
4. Click **"Create new project"** (it takes about 1–2 minutes to provision).

### Step 2.2 — Obtain Supabase API Credentials
1. In your Supabase dashboard, navigate to **Project Settings** (gear icon at bottom left) -> **API**.
2. Copy the following:
   - **Project URL** (e.g., `https://abcdefghijklm.supabase.co`) $\rightarrow$ `SUPABASE_URL`
   - **Project API Keys `anon` `public`** $\rightarrow$ `SUPABASE_ANON_KEY`
   - **JWT Secret** (under JWT Settings) $\rightarrow$ `SUPABASE_JWT_SECRET`

### Step 2.3 — Obtain the PostgreSQL Connection String
1. In Project Settings, navigate to **Database**.
2. Scroll to **Connection string** and select **URI**.
3. Choose the **Transaction pooler** or **Direct connection** string:
   ```text
   postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres
   ```
4. Replace `[YOUR-PASSWORD]` with the database password you chose in Step 2.1.
5. This is your `DATABASE_URL`.

---

## 3. One-Command SQLite to Supabase Migration

We have prepared a dedicated migration tool: [`migrate_to_supabase.py`](migrate_to_supabase.py).

This tool:
- Connects to your existing `script_analyser.db`.
- Creates all 10 relational tables in Supabase PostgreSQL (`SERIAL` primary keys, foreign key constraints with `ON DELETE CASCADE`, and indexes).
- Migrates all existing projects (*Luther*, *Book Worm*, etc.), scenes (173+), characters (38+), traits, relationships, locations, and schedules.
- Preserves all IDs and foreign key integrity.
- Resets PostgreSQL identity sequences (`setval`) so newly created scripts continue seamlessly without ID collisions.
- Prints a row-by-row verification summary.

### Run the Migration:
```bash
python migrate_to_supabase.py --target-url "postgresql://postgres:YOUR_PASSWORD@db.YOUR_REF.supabase.co:5432/postgres"
```

*Example Output:*
```text
=================================================================
SCRIPT ANALYSER — SQLITE TO SUPABASE POSTGRESQL MIGRATION
=================================================================
[1/5] Initializing target schema in Supabase PostgreSQL...
[2/5] Migrating records...
  ✓ projects                  3 records migrated
  ✓ scenes                    173 records migrated
  ✓ characters                38 records migrated
  ✓ character_traits          53 records migrated
  ✓ character_relationships   94 records migrated
  ✓ locations                 58 records migrated
[3/5] Resetting PostgreSQL serial sequences...
[4/5] Changes committed successfully.
[5/5] Verification Summary:
-----------------------------------------------------------------
Table                      SQLite Rows    Postgres Rows  Status
-----------------------------------------------------------------
projects                   3              3              OK
scenes                     173            173            OK
characters                 38             38             OK
character_traits           53             53             OK
character_relationships    94             94             OK
locations                  58             58             OK
=================================================================
MIGRATION COMPLETED SUCCESSFULLY!
```

---

## 4. Live Deployment to Render

You can host the application on [Render](https://render.com) for free.

### Step 4.1 — Push Code to GitHub
```bash
git init
git add .
git commit -m "Script Analyser Pro with Supabase Auth and PostgreSQL"
git branch -M main
git remote add origin https://github.com/your-username/script-analyser-pro.git
git push -u origin main
```

### Step 4.2 — Deploy as a Web Service on Render
1. Go to [https://dashboard.render.com](https://dashboard.render.com).
2. Click **"New +"** $\rightarrow$ **"Web Service"**.
3. Select your GitHub repository (`script-analyser-pro`).
4. Configure the settings:
   - **Name**: `script-analyser-pro`
   - **Region**: Choose closest to your database (e.g., Oregon or Frankfurt)
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: `Free`

### Step 4.3 — Configure Environment Variables on Render
Under **Environment Variables**, add:

| Key | Value | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql://postgres:...` | Your Supabase connection URI |
| `SUPABASE_URL` | `https://....supabase.co` | Supabase Project URL |
| `SUPABASE_ANON_KEY` | `eyJhbGci...` | Supabase Anonymous Public Key |
| `SUPABASE_JWT_SECRET` | `your-jwt-secret` | Supabase JWT Secret |
| `SECRET_KEY` | `random_secure_key_here` | 32+ char session secret |
| `OMDB_API_KEY` | `your_omdb_key` | OMDb API key |
| `APP_AUTHOR` | `Ramanand S P` | Application Author Name |
| `DEMO_USER_EMAIL` | `faculty@scriptanalyser.com`| Demo presentation account |
| `DEMO_USER_PASSWORD` | `FacultyDemo2026!` | Demo presentation password |
| `CORS_ORIGINS` | `*` | Allowed web origins |

5. Click **"Create Web Service"**.
6. Render will build and deploy your app. When finished, your public URL will look like:
   `https://script-analyser-pro.onrender.com`

---

## 5. University Faculty Demonstration Walkthrough

Follow this step-by-step presentation script to showcase your project to faculty members:

### Step 1: Open the Public Website
- Open your public URL (`https://script-analyser-pro.onrender.com` or `http://127.0.0.1:8000`).
- The login modal immediately appears, demonstrating that unauthenticated visitors cannot access screenplay data or private project records.

### Step 2: Demonstrate Authentication
- Point out the **Script Analyser Pro** brand, the **Sign In** and **Create Account** tabs, and the **Show/Hide password** button.
- Click **"🎓 Faculty / Fast Demo Access"** (or type `faculty@scriptanalyser.com` / `FacultyDemo2026!`).
- The dashboard unlocks smoothly with a session confirmation toast.
- Highlight the user chip in the sidebar footer and topbar showing the verified session and user credentials.

### Step 3: Screenplay Analysis & Project Selection
- Select an existing project from the **RECENT SCRIPTS** list (e.g. *Luther* or *Book Worm*).
- Demonstrate the **Overview** dashboard:
  - Total scenes, dialogue-to-action ratio, detected genres with signal strengths, and cast breakdown.
  - Notice the transparent planning warnings stating that estimates are baseline planning assumptions.

### Step 4: Evidence-Grounded Character Profiling
- Click **"Characters"** in the sidebar.
- Show the faculty that characters are not generic templates:
  - Role classification badges: `PROTAGONIST`, `ANTAGONIST`, `SUPPORTING`.
  - Specific extracted personality traits, each accompanied by direct screenplay dialogue quotes and scene references.
  - Substantive character notes explaining motivation, behavior, and character arc.

### Step 5: GIS Location Resolution & Leaflet Map
- Click **"Locations"** in the sidebar.
- Point out the distinction between real-world places and fictional sets:
  - Real places resolved via OpenStreetMap Nominatim with live coordinates and interactive pins on the Leaflet map.
  - Fictional/private sets properly classified as "Unresolved" rather than fabricating fake coordinates.
  - Click **"Set Location"** to show the manual coordinate override dialog that permanently persists verified coordinates.

### Step 6: Production Scheduling & Cost Estimation
- Click **"Schedule"**: Show sequential narrative vs. location-grouped shooting strategies, day-by-day scene breakdowns, and duration estimates.
- Click **"Budget"**: Show department cost distribution (Cast, Crew, Equipment, Locations, Transport, Post-Production) with configurable day-rate assumptions.

### Step 7: Comparative Film Market Intelligence
- Click **"Market"**:
  - Live side-by-side comparison matrix with comparable films retrieved via OMDb API.
  - Transparent box-office metrics (missing values reported as "Not reported", never zero).
  - 9-point structured market report including target demographic, festival positioning, budget tiers, and distribution channels.

### Step 8: Multi-Tenant Security & Logout
- Click **"Export report"** to download the complete structured JSON analysis.
- Click **"↪" (Sign Out)** in the sidebar footer.
- The session is cleared, the dashboard locks, and unauthorized access is blocked.
- Show the faculty that attempting to call `/api/projects` without a token returns `401 Unauthorized`.
