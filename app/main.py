import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, List, Dict, Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .analyzer import (
    analyse_script,
    extract_script_text,
    generate_production_schedule,
    utc_now,
)
from .auth import auth_router, get_current_user, get_optional_user
from .database import (
    connection,
    init_db,
    row_to_project,
    save_project_structured_data,
    IS_POSTGRES,
)
from .services import (
    geocode_location,
    get_market_movies,
    get_movie_details,
    get_comparable_candidates,
    generate_comparative_market_report,
)

logger = logging.getLogger(__name__)

# Load environment variables
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

APP_AUTHOR = os.getenv("APP_AUTHOR", "Ramanand S P")
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Script Analyser started. Engine: %s", "PostgreSQL" if IS_POSTGRES else "SQLite")
    yield


app = FastAPI(
    title="Script Analyser",
    version="2.1.0",
    description="Professional screenplay analysis, character profiling, GIS location mapping, production planning, Supabase auth and comparative market intelligence.",
    lifespan=lifespan,
)

# CORS configuration
origins_env = os.getenv("CORS_ORIGINS", "*").strip()
allowed_origins = [o.strip() for o in origins_env.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if allowed_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount authentication router
app.include_router(auth_router)

# Mount static frontend
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ============================================================
# REQUEST SCHEMAS
# ============================================================

class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    author: str = Field(default="", max_length=180)
    script_text: str = Field(min_length=1)
    budget_settings: dict = Field(default_factory=dict)


class ReanalyseRequest(BaseModel):
    budget_settings: dict = Field(default_factory=dict)


class ManualLocationUpdate(BaseModel):
    name: str = Field(min_length=1)
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    display_name: Optional[str] = ""


class ScheduleUpdateRequest(BaseModel):
    strategy: str = Field(default="sequential")  # "sequential" or "by_location"
    minutes_per_scene: float = Field(default=45.0, ge=1.0, le=300.0)
    shooting_hours_per_day: float = Field(default=8.0, ge=1.0, le=24.0)


class CompareMovieRequest(BaseModel):
    imdb_id: str = Field(min_length=3)


# ============================================================
# HELPER FOR USER-SCOPED PROJECT ACCESS
# ============================================================

def get_user_project(conn, project_id: int, user: dict):
    user_id = user["id"]
    row = conn.execute(
        "SELECT * FROM projects WHERE id = ? AND (user_id = ? OR user_id = 'demo-user-id')",
        (project_id, user_id),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found or access denied.")
    return row_to_project(row)


# ============================================================
# CORE APP ROUTES
# ============================================================

@app.get("/", response_class=HTMLResponse)
def index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.is_file():
        index_file = BASE_DIR / "static" / "index.html"
    if not index_file.is_file():
        raise HTTPException(status_code=404, detail="Dashboard index.html not found")
    return FileResponse(index_file)


@app.get("/api/health")
def health():
    db_status = "ok"
    try:
        with connection() as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception as e:
        db_status = f"error: {e}"

    return {
        "status": "ok",
        "service": "Script Analyser Pro",
        "version": "2.1.0",
        "author": APP_AUTHOR,
        "database": db_status,
        "database_engine": "PostgreSQL (Supabase)" if IS_POSTGRES else "SQLite (Local)",
        "supabase_auth": bool(os.getenv("SUPABASE_URL", "").strip()),
    }


@app.get("/api/config")
def config():
    return {
        "author": APP_AUTHOR,
        "market_provider": "OMDb",
        "market_configured": bool(os.getenv("OMDB_API_KEY", "").strip()),
        "supabase_configured": bool(os.getenv("SUPABASE_URL", "").strip() and os.getenv("SUPABASE_ANON_KEY", "").strip()),
        "supabase_url": os.getenv("SUPABASE_URL", "").strip(),
        "supabase_anon_key": os.getenv("SUPABASE_ANON_KEY", "").strip(),
        "database_backend": "PostgreSQL (Supabase)" if IS_POSTGRES else "SQLite (Local)",
        "demo_email": os.getenv("DEMO_USER_EMAIL", "faculty@scriptanalyser.com"),
    }


@app.get("/api/author")
def author():
    return {"author": APP_AUTHOR}


# ============================================================
# PROJECT MANAGEMENT ROUTES (AUTHENTICATED & USER-SCOPED)
# ============================================================

@app.get("/api/projects")
def list_projects(user: dict = Depends(get_current_user)):
    user_id = user["id"]
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM projects WHERE user_id = ? OR user_id = 'demo-user-id' ORDER BY updated_at DESC",
            (user_id,)
        ).fetchall()
    return [row_to_project(row) for row in rows]


@app.post("/api/projects")
def create_project(payload: ProjectCreate, user: dict = Depends(get_current_user)):
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Project title cannot be empty.")

    script_text = payload.script_text
    if not script_text.strip():
        raise HTTPException(status_code=422, detail="Script text cannot be empty.")

    now = utc_now()
    analysis = analyse_script(title, script_text, payload.budget_settings)

    with connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO projects (title, author, script_text, created_at, updated_at, analysis_json, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (title, payload.author.strip(), script_text, now, now, json.dumps(analysis), user["id"]),
        )
        project_id = cursor.lastrowid
        save_project_structured_data(conn, project_id, analysis)

        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()

    return row_to_project(row)


@app.post("/api/projects/upload")
async def upload_project(
    title: str = Form(...),
    author: str = Form(""),
    budget_settings_json: str = Form("{}"),
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Choose a screenplay file.")

    extension = file.filename.lower().rsplit(".", 1)[-1] if "." in file.filename else "txt"
    if extension not in {"txt", "pdf", "docx"}:
        raise HTTPException(status_code=415, detail="Supported file formats: .txt, .pdf, .docx")

    content = await file.read()
    if len(content) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Maximum screenplay upload size is 15 MB.")

    try:
        script_text = extract_script_text(file.filename, content)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read this file: {exc}") from exc

    if not script_text.strip():
        raise HTTPException(status_code=400, detail="No readable text found. Scanned PDFs need OCR before upload.")

    try:
        settings = json.loads(budget_settings_json or "{}")
        if not isinstance(settings, dict):
            raise ValueError("Budget settings must be a JSON object.")
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid budget settings JSON: {exc}") from exc

    payload = ProjectCreate(
        title=title,
        author=author,
        script_text=script_text,
        budget_settings=settings,
    )
    return create_project(payload, user=user)


@app.get("/api/projects/{project_id}")
def get_project(project_id: int, user: dict = Depends(get_current_user)):
    with connection() as conn:
        return get_user_project(conn, project_id, user)


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: int, user: dict = Depends(get_current_user)):
    with connection() as conn:
        row = conn.execute("SELECT id, user_id FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Project not found.")

        # Check permissions: owner or demo project in demo mode
        if row["user_id"] != user["id"] and row["user_id"] != "demo-user-id":
            raise HTTPException(status_code=403, detail="You do not have permission to delete this project.")

        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        # Cascade cleanup for SQLite if pragma not active
        conn.execute("DELETE FROM scenes WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM characters WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM character_traits WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM character_relationships WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM locations WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM schedules WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM comparisons WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM market_reports WHERE project_id = ?", (project_id,))

    return {"deleted": True, "id": project_id}


@app.post("/api/projects/{project_id}/reanalyze")
def reanalyze_project(project_id: int, payload: ReanalyseRequest, user: dict = Depends(get_current_user)):
    with connection() as conn:
        proj = get_user_project(conn, project_id, user)

        analysis = analyse_script(
            proj["title"],
            proj["script_text"],
            payload.budget_settings,
        )

        save_project_structured_data(conn, project_id, analysis)

        now = utc_now()
        conn.execute(
            "UPDATE projects SET analysis_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(analysis), now, project_id),
        )

        updated = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()

    return row_to_project(updated)


# ============================================================
# STRUCTURED SCENES & CHARACTERS ENDPOINTS
# ============================================================

@app.get("/api/projects/{project_id}/scenes")
def get_project_scenes(project_id: int, user: dict = Depends(get_current_user)):
    with connection() as conn:
        proj = get_user_project(conn, project_id, user)
        rows = conn.execute(
            "SELECT * FROM scenes WHERE project_id = ? ORDER BY scene_order ASC",
            (project_id,)
        ).fetchall()

    if not rows:
        return proj.get("analysis", {}).get("structured_scenes", [])

    scenes = []
    for r in rows:
        d = dict(r)
        d["characters"] = json.loads(d.get("characters_json", "[]"))
        scenes.append(d)
    return scenes


@app.get("/api/projects/{project_id}/characters")
def get_project_characters(project_id: int, user: dict = Depends(get_current_user)):
    with connection() as conn:
        proj = get_user_project(conn, project_id, user)
        rows = conn.execute(
            "SELECT * FROM characters WHERE project_id = ? ORDER BY cue_count DESC",
            (project_id,)
        ).fetchall()

        if not rows:
            return proj.get("analysis", {}).get("characters", [])

        characters = []
        for r in rows:
            d = dict(r)
            d["strengths"] = json.loads(d.get("strengths_json", "[]"))
            d["flaws"] = json.loads(d.get("flaws_json", "[]"))
            d["scenes"] = json.loads(d.get("scenes_json", "[]"))

            t_rows = conn.execute(
                "SELECT * FROM character_traits WHERE project_id = ? AND character_name = ?",
                (project_id, d["name"])
            ).fetchall()
            d["trait_evidence"] = [dict(t) for t in t_rows]
            d["traits"] = [t["trait"] for t in t_rows]
            characters.append(d)

    return characters


@app.get("/api/projects/{project_id}/characters/{name}/evidence")
def get_character_evidence(project_id: int, name: str, user: dict = Depends(get_current_user)):
    with connection() as conn:
        get_user_project(conn, project_id, user)
        traits = conn.execute(
            "SELECT * FROM character_traits WHERE project_id = ? AND character_name = ?",
            (project_id, name)
        ).fetchall()
        rels = conn.execute(
            "SELECT * FROM character_relationships WHERE project_id = ? AND (character_a = ? OR character_b = ?)",
            (project_id, name, name)
        ).fetchall()

    return {
        "character": name,
        "traits": [dict(t) for t in traits],
        "relationships": [dict(r) for r in rels],
    }


@app.get("/api/projects/{project_id}/relationships")
def get_project_relationships(project_id: int, user: dict = Depends(get_current_user)):
    with connection() as conn:
        proj = get_user_project(conn, project_id, user)
        rows = conn.execute(
            "SELECT * FROM character_relationships WHERE project_id = ? ORDER BY shared_scenes_count DESC",
            (project_id,)
        ).fetchall()

    if not rows:
        return proj.get("analysis", {}).get("relationships", [])

    return [dict(r) for r in rows]


# ============================================================
# LOCATIONS & GIS MAP ENDPOINTS
# ============================================================

@app.get("/api/projects/{project_id}/locations")
def get_project_locations(project_id: int, user: dict = Depends(get_current_user)):
    with connection() as conn:
        proj = get_user_project(conn, project_id, user)
        rows = conn.execute(
            "SELECT * FROM locations WHERE project_id = ? ORDER BY scene_count DESC",
            (project_id,)
        ).fetchall()

    if not rows:
        return proj.get("analysis", {}).get("locations", [])

    locations = []
    for r in rows:
        d = dict(r)
        d["sub_locations"] = json.loads(d.get("sub_locations_json", "[]"))
        d["scene_numbers"] = json.loads(d.get("scene_numbers_json", "[]"))
        locations.append(d)
    return locations


@app.post("/api/projects/{project_id}/locations/resolve")
@app.post("/api/projects/{project_id}/geocode")
def resolve_project_locations(project_id: int, user: dict = Depends(get_current_user)):
    with connection() as conn:
        project = get_user_project(conn, project_id, user)
        analysis = project.get("analysis", {})
        locations = analysis.get("locations", [])

        resolved_count = 0
        for loc in locations:
            if loc.get("resolution_status") == "manual":
                continue

            loc_name = loc.get("name", "")
            if loc.get("latitude") is None or loc.get("longitude") is None:
                res = geocode_location(loc_name)
                if res.get("latitude") is not None and res.get("longitude") is not None:
                    loc["latitude"] = res["latitude"]
                    loc["longitude"] = res["longitude"]
                    loc["display_name"] = res.get("display_name", loc_name)
                    loc["resolution_status"] = "resolved"
                    loc["resolution_source"] = "OpenStreetMap Nominatim"
                    resolved_count += 1
                else:
                    loc["resolution_status"] = "unresolved"
                    loc["resolution_source"] = "Unresolved"
                    loc["unresolved_reason"] = "Location not found in public gazetteer; may be fictional or private set."

        save_project_structured_data(conn, project_id, analysis)

        now = utc_now()
        conn.execute(
            "UPDATE projects SET analysis_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(analysis), now, project_id),
        )

        updated_row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()

    return row_to_project(updated_row)


@app.post("/api/projects/{project_id}/locations/manual")
def set_manual_location_coordinates(project_id: int, payload: ManualLocationUpdate, user: dict = Depends(get_current_user)):
    with connection() as conn:
        project = get_user_project(conn, project_id, user)
        analysis = project.get("analysis", {})
        locations = analysis.get("locations", [])

        target_norm = payload.name.strip().upper()
        matched = False

        for loc in locations:
            if loc.get("normalized_name") == target_norm or loc.get("name", "").strip().upper() == target_norm:
                loc["latitude"] = payload.latitude
                loc["longitude"] = payload.longitude
                loc["display_name"] = payload.display_name or f"Manually verified: {loc['name']}"
                loc["resolution_status"] = "manual"
                loc["resolution_source"] = "User verified"
                loc["unresolved_reason"] = ""
                matched = True
                break

        if not matched:
            locations.append({
                "name": payload.name,
                "normalized_name": target_norm,
                "int_ext": "MIXED",
                "sub_locations": [],
                "scene_numbers": [],
                "scene_count": 0,
                "latitude": payload.latitude,
                "longitude": payload.longitude,
                "display_name": payload.display_name or f"Manually verified: {payload.name}",
                "resolution_status": "manual",
                "resolution_source": "User verified",
                "unresolved_reason": "",
            })

        save_project_structured_data(conn, project_id, analysis)

        now = utc_now()
        conn.execute(
            "UPDATE projects SET analysis_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(analysis), now, project_id),
        )

        updated_row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()

    return row_to_project(updated_row)


# ============================================================
# PRODUCTION SCHEDULE ENDPOINTS
# ============================================================

@app.get("/api/projects/{project_id}/schedule")
def get_project_schedule(
    project_id: int,
    strategy: str = Query("sequential", enum=["sequential", "by_location"]),
    user: dict = Depends(get_current_user),
):
    with connection() as conn:
        proj = get_user_project(conn, project_id, user)

    analysis = proj.get("analysis", {})
    structured_scenes = analysis.get("structured_scenes", [])
    budget_assumptions = analysis.get("budget", {}).get("assumptions", {})

    mins_per_scene = float(budget_assumptions.get("minutes_per_scene", 45))
    hrs_per_day = float(budget_assumptions.get("shooting_hours_per_day", 8))

    schedule = generate_production_schedule(
        structured_scenes=structured_scenes,
        minutes_per_scene=mins_per_scene,
        shooting_hours_per_day=hrs_per_day,
        strategy=strategy,
    )
    return {
        "project_id": project_id,
        "strategy": strategy,
        "minutes_per_scene": mins_per_scene,
        "shooting_hours_per_day": hrs_per_day,
        "total_days": max([s["day"] for s in schedule], default=1) if schedule else 1,
        "schedule": schedule,
    }


@app.post("/api/projects/{project_id}/schedule")
def update_project_schedule(project_id: int, payload: ScheduleUpdateRequest, user: dict = Depends(get_current_user)):
    with connection() as conn:
        proj = get_user_project(conn, project_id, user)

    analysis = proj.get("analysis", {})
    structured_scenes = analysis.get("structured_scenes", [])

    schedule = generate_production_schedule(
        structured_scenes=structured_scenes,
        minutes_per_scene=payload.minutes_per_scene,
        shooting_hours_per_day=payload.shooting_hours_per_day,
        strategy=payload.strategy,
    )

    analysis["schedule"] = schedule
    if "budget" in analysis and "assumptions" in analysis["budget"]:
        analysis["budget"]["assumptions"]["minutes_per_scene"] = payload.minutes_per_scene
        analysis["budget"]["assumptions"]["shooting_hours_per_day"] = payload.shooting_hours_per_day

    with connection() as conn:
        conn.execute("DELETE FROM schedules WHERE project_id = ?", (project_id,))
        conn.execute(
            """
            INSERT INTO schedules (project_id, strategy, minutes_per_scene, shooting_hours_per_day, schedule_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (project_id, payload.strategy, payload.minutes_per_scene, payload.shooting_hours_per_day, json.dumps(schedule), utc_now())
        )
        conn.execute(
            "UPDATE projects SET analysis_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(analysis), utc_now(), project_id),
        )

    return {
        "project_id": project_id,
        "strategy": payload.strategy,
        "minutes_per_scene": payload.minutes_per_scene,
        "shooting_hours_per_day": payload.shooting_hours_per_day,
        "total_days": max([s["day"] for s in schedule], default=1) if schedule else 1,
        "schedule": schedule,
    }


# ============================================================
# OMDB COMPARATIVE MARKET ANALYSIS ENDPOINTS
# ============================================================

@app.get("/api/market")
def market_search(query: str = ""):
    return get_market_movies(query=query)


@app.get("/api/market/movie/{imdb_id}")
def movie_details(imdb_id: str):
    details = get_movie_details(imdb_id)
    if not details:
        raise HTTPException(status_code=404, detail="Film record not found on OMDb.")
    return details


@app.get("/api/projects/{project_id}/market/recommendations")
def get_market_recommendations(project_id: int, user: dict = Depends(get_current_user)):
    with connection() as conn:
        proj = get_user_project(conn, project_id, user)
    analysis = proj.get("analysis", {})
    genres = analysis.get("genre_signals", [])
    title = proj.get("title", "")
    candidates = get_comparable_candidates(genres=genres, title=title)
    return {
        "project_title": title,
        "screenplay_genres": genres,
        "candidates": candidates,
    }


@app.get("/api/projects/{project_id}/market/comparisons")
def list_project_comparisons(project_id: int, user: dict = Depends(get_current_user)):
    with connection() as conn:
        get_user_project(conn, project_id, user)
        rows = conn.execute(
            "SELECT * FROM comparisons WHERE project_id = ? ORDER BY added_at DESC",
            (project_id,)
        ).fetchall()

    comparisons = []
    for r in rows:
        d = json.loads(r["data_json"])
        comparisons.append(d)
    return comparisons


@app.post("/api/projects/{project_id}/market/compare")
def add_project_comparison(project_id: int, payload: CompareMovieRequest, user: dict = Depends(get_current_user)):
    movie = get_movie_details(payload.imdb_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie details could not be retrieved from OMDb.")

    with connection() as conn:
        get_user_project(conn, project_id, user)
        conn.execute("DELETE FROM comparisons WHERE project_id = ? AND imdb_id = ?", (project_id, movie["imdb_id"]))
        conn.execute(
            """
            INSERT INTO comparisons (project_id, imdb_id, title, year, data_json, added_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (project_id, movie["imdb_id"], movie["title"], movie["year"], json.dumps(movie), utc_now()),
        )

    return list_project_comparisons(project_id, user=user)


@app.delete("/api/projects/{project_id}/market/compare/{imdb_id}")
def remove_project_comparison(project_id: int, imdb_id: str, user: dict = Depends(get_current_user)):
    with connection() as conn:
        get_user_project(conn, project_id, user)
        conn.execute(
            "DELETE FROM comparisons WHERE project_id = ? AND imdb_id = ?",
            (project_id, imdb_id),
        )
    return list_project_comparisons(project_id, user=user)


@app.post("/api/projects/{project_id}/market/report")
def create_market_report(project_id: int, user: dict = Depends(get_current_user)):
    with connection() as conn:
        proj = get_user_project(conn, project_id, user)

    analysis = proj.get("analysis", {})
    genres = analysis.get("genre_signals", [])

    comparisons = list_project_comparisons(project_id, user=user)
    if not comparisons:
        candidates = get_comparable_candidates(genres=genres, title=proj.get("title", ""))
        for c in candidates:
            with connection() as conn:
                conn.execute("DELETE FROM comparisons WHERE project_id = ? AND imdb_id = ?", (project_id, c["imdb_id"]))
                conn.execute(
                    """
                    INSERT INTO comparisons (project_id, imdb_id, title, year, data_json, added_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (project_id, c["imdb_id"], c["title"], c["year"], json.dumps(c), utc_now()),
                )
        comparisons = list_project_comparisons(project_id, user=user)

    report = generate_comparative_market_report(
        project_title=proj.get("title", "Screenplay"),
        script_genres=genres,
        comp_movies=comparisons,
    )

    with connection() as conn:
        conn.execute(
            "INSERT INTO market_reports (project_id, report_json, created_at) VALUES (?, ?, ?)",
            (project_id, json.dumps(report), utc_now()),
        )

    return report


@app.get("/api/projects/{project_id}/market/report")
def get_latest_market_report(project_id: int, user: dict = Depends(get_current_user)):
    with connection() as conn:
        get_user_project(conn, project_id, user)
        row = conn.execute(
            "SELECT report_json FROM market_reports WHERE project_id = ? ORDER BY id DESC LIMIT 1",
            (project_id,)
        ).fetchone()

    if not row:
        return create_market_report(project_id, user=user)

    return json.loads(row["report_json"])


@app.get("/api/projects/{project_id}/report")
def full_export_report(project_id: int, user: dict = Depends(get_current_user)):
    with connection() as conn:
        proj = get_user_project(conn, project_id, user)
    proj["scenes"] = get_project_scenes(project_id, user=user)
    proj["characters"] = get_project_characters(project_id, user=user)
    proj["locations"] = get_project_locations(project_id, user=user)
    proj["relationships"] = get_project_relationships(project_id, user=user)
    proj["schedule"] = get_project_schedule(project_id, user=user)
    proj["comparisons"] = list_project_comparisons(project_id, user=user)
    try:
        proj["market_report"] = get_latest_market_report(project_id, user=user)
    except Exception:
        proj["market_report"] = None
    return proj
