import json
import logging
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Detect Database backend
RAW_DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

def get_clean_database_url() -> str:
    if not RAW_DATABASE_URL:
        return ""
    url = RAW_DATABASE_URL
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url

DATABASE_URL = get_clean_database_url()
IS_POSTGRES = bool(DATABASE_URL and (DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://")))

# SQLite fallback path
DB_PATH = Path(os.getenv("DATABASE_PATH", "script_analyser.db")).resolve()

# Global PostgreSQL connection pool
_pg_pool = None

def get_pg_pool():
    global _pg_pool
    if _pg_pool is None and IS_POSTGRES:
        try:
            import psycopg2
            from psycopg2.pool import ThreadedConnectionPool
            # Ensure sslmode=require for cloud Supabase unless already specified
            dsn = DATABASE_URL
            if "sslmode=" not in dsn and ("supabase.co" in dsn or "pooler.supabase.com" in dsn or "render.com" in dsn):
                separator = "&" if "?" in dsn else "?"
                dsn = f"{dsn}{separator}sslmode=require"

            _pg_pool = ThreadedConnectionPool(minconn=1, maxconn=10, dsn=dsn)
            logger.info("Connected to PostgreSQL database pool (Supabase)")
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL pool: {e}")
            raise
    return _pg_pool


class SQLiteCursorWrapper:
    def __init__(self, cur):
        self._cur = cur

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    @property
    def rowcount(self):
        return self._cur.rowcount


class PGCursorWrapper:
    def __init__(self, cur, lastrowid=None):
        self._cur = cur
        self._lastrowid = lastrowid

    def fetchone(self):
        row = self._cur.fetchone()
        return dict(row) if row else None

    def fetchall(self):
        rows = self._cur.fetchall()
        return [dict(r) for r in rows]

    @property
    def lastrowid(self):
        return self._lastrowid

    @property
    def rowcount(self):
        return self._cur.rowcount


class DBConnectionWrapper:
    def __init__(self, raw_conn, is_postgres: bool = False):
        self.raw_conn = raw_conn
        self.is_postgres = is_postgres

    def execute(self, sql: str, params: tuple = ()):
        if not self.is_postgres:
            return SQLiteCursorWrapper(self.raw_conn.execute(sql, params))

        import psycopg2.extras
        cur = self.raw_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        pg_sql = sql.replace("?", "%s")

        # Automatically translate AUTOINCREMENT in create statements
        pg_sql = re.sub(r'\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b', 'SERIAL PRIMARY KEY', pg_sql, flags=re.IGNORECASE)

        # Check for INSERT without RETURNING
        lastrowid = None
        is_insert = bool(re.search(r'^\s*INSERT\s+INTO\s+', pg_sql, re.IGNORECASE))
        has_returning = 'RETURNING' in pg_sql.upper()

        if is_insert and not has_returning:
            pg_sql_ret = pg_sql.rstrip().rstrip(';') + " RETURNING id;"
            try:
                cur.execute(pg_sql_ret, params)
                row = cur.fetchone()
                if row and "id" in row:
                    lastrowid = row["id"]
                return PGCursorWrapper(cur, lastrowid)
            except Exception:
                # If table does not have 'id' column or RETURNING failed, fallback to plain
                self.raw_conn.rollback()
                cur = self.raw_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute(pg_sql, params)
                return PGCursorWrapper(cur, None)

        cur.execute(pg_sql, params)
        return PGCursorWrapper(cur, None)

    def commit(self):
        self.raw_conn.commit()

    def rollback(self):
        self.raw_conn.rollback()

    def close(self):
        if not self.is_postgres:
            self.raw_conn.close()


@contextmanager
def connection():
    if IS_POSTGRES:
        pool = get_pg_pool()
        raw_conn = pool.getconn()
        wrapper = DBConnectionWrapper(raw_conn, is_postgres=True)
        try:
            yield wrapper
            raw_conn.commit()
        except Exception:
            raw_conn.rollback()
            raise
        finally:
            pool.putconn(raw_conn)
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        wrapper = DBConnectionWrapper(conn, is_postgres=False)
        try:
            yield wrapper
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def init_db():
    """Initializes tables for either PostgreSQL or SQLite with user isolation and index optimizations."""
    with connection() as conn:
        id_type = "SERIAL PRIMARY KEY" if IS_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"

        # Users table for local credentials and cached Supabase identities
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)

        # Projects table (with user_id for multi-tenant isolation)
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS projects (
                id {id_type},
                title TEXT NOT NULL,
                author TEXT DEFAULT '',
                script_text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                analysis_json TEXT NOT NULL,
                user_id TEXT NOT NULL DEFAULT 'demo-user-id'
            )
        """)

                # SQLite compatibility migration.
        # PostgreSQL projects table already defines user_id above.
        if not IS_POSTGRES:
            try:
                conn.execute(
                    "ALTER TABLE projects ADD COLUMN user_id TEXT NOT NULL DEFAULT 'demo-user-id'"
                )
            except Exception:
                pass

        # Structured scenes table
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS scenes (
                id {id_type},
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_number TEXT NOT NULL,
                scene_order INTEGER NOT NULL,
                heading TEXT NOT NULL,
                int_ext TEXT DEFAULT '',
                primary_location TEXT NOT NULL,
                sub_location TEXT DEFAULT '',
                time_of_day TEXT DEFAULT '',
                characters_json TEXT DEFAULT '[]',
                dialogue_count INTEGER DEFAULT 0,
                action_summary TEXT DEFAULT '',
                line_start INTEGER DEFAULT 0,
                line_end INTEGER DEFAULT 0
            )
        """)

        # Structured character profiles table
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS characters (
                id {id_type},
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                role TEXT DEFAULT 'Supporting',
                role_basis TEXT DEFAULT '',
                description TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                motivation TEXT DEFAULT '',
                strengths_json TEXT DEFAULT '[]',
                flaws_json TEXT DEFAULT '[]',
                character_arc TEXT DEFAULT '',
                confidence TEXT DEFAULT 'Moderate',
                cue_count INTEGER DEFAULT 0,
                dialogue_word_count INTEGER DEFAULT 0,
                first_scene TEXT DEFAULT '',
                scenes_json TEXT DEFAULT '[]'
            )
        """)

        # Character trait evidence table
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS character_traits (
                id {id_type},
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                character_name TEXT NOT NULL,
                trait TEXT NOT NULL,
                evidence TEXT NOT NULL,
                scene_ref TEXT DEFAULT '',
                confidence TEXT DEFAULT 'Moderate',
                trait_type TEXT DEFAULT 'inferred'
            )
        """)

        # Character relationships table
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS character_relationships (
                id {id_type},
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                character_a TEXT NOT NULL,
                character_b TEXT NOT NULL,
                relationship_type TEXT NOT NULL,
                description TEXT DEFAULT '',
                shared_scenes_count INTEGER DEFAULT 0,
                evidence TEXT DEFAULT ''
            )
        """)

        # Normalized locations and GIS table
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS locations (
                id {id_type},
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                int_ext TEXT DEFAULT 'MIXED',
                sub_locations_json TEXT DEFAULT '[]',
                scene_numbers_json TEXT DEFAULT '[]',
                scene_count INTEGER DEFAULT 0,
                latitude REAL,
                longitude REAL,
                display_name TEXT DEFAULT '',
                resolution_status TEXT DEFAULT 'unresolved',
                resolution_source TEXT DEFAULT '',
                unresolved_reason TEXT DEFAULT ''
            )
        """)

        # Production schedule presets / settings
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS schedules (
                id {id_type},
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                strategy TEXT DEFAULT 'sequential',
                minutes_per_scene REAL DEFAULT 45,
                shooting_hours_per_day REAL DEFAULT 8,
                schedule_json TEXT DEFAULT '[]',
                updated_at TEXT NOT NULL
            )
        """)

        # Film comparisons table
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS comparisons (
                id {id_type},
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                imdb_id TEXT NOT NULL,
                title TEXT NOT NULL,
                year TEXT DEFAULT '',
                data_json TEXT NOT NULL,
                added_at TEXT NOT NULL,
                UNIQUE(project_id, imdb_id)
            )
        """)

        # Comparative market analysis reports table
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS market_reports (
                id {id_type},
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                report_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

                # Performance Indexes
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_scenes_proj ON scenes(project_id)",
            "CREATE INDEX IF NOT EXISTS idx_chars_proj ON characters(project_id)",
            "CREATE INDEX IF NOT EXISTS idx_traits_proj ON character_traits(project_id)",
            "CREATE INDEX IF NOT EXISTS idx_rel_proj ON character_relationships(project_id)",
            "CREATE INDEX IF NOT EXISTS idx_locs_proj ON locations(project_id)",
        ]

        for sql in indexes:
            try:
                conn.execute(sql)
            except Exception:
                if IS_POSTGRES:
                    raise
                pass

    logger.info("Database initialized successfully (Engine: %s)", "PostgreSQL/Supabase" if IS_POSTGRES else "SQLite")


def row_to_project(row):
    if not row:
        return None
    result = dict(row)
    if "analysis_json" in result and result["analysis_json"]:
        try:
            if isinstance(result["analysis_json"], dict):
                result["analysis"] = result.pop("analysis_json")
            else:
                result["analysis"] = json.loads(result.pop("analysis_json"))
        except Exception:
            result["analysis"] = {}
    elif "analysis_json" in result:
        result.pop("analysis_json")
        result["analysis"] = {}
    return result


def save_project_structured_data(conn, project_id: int, analysis: dict):
    """Save structured scenes, characters, traits, relationships, locations to relational tables."""
    # 1. Structured scenes
    scenes = analysis.get("structured_scenes", [])
    if scenes:
        conn.execute("DELETE FROM scenes WHERE project_id = ?", (project_id,))
        for sc in scenes:
            conn.execute("""
                INSERT INTO scenes (
                    project_id, scene_number, scene_order, heading, int_ext,
                    primary_location, sub_location, time_of_day, characters_json,
                    dialogue_count, action_summary, line_start, line_end
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                project_id,
                str(sc.get("scene_number", "")),
                int(sc.get("scene_order", 0)),
                sc.get("heading", ""),
                sc.get("int_ext", ""),
                sc.get("primary_location", ""),
                sc.get("sub_location", ""),
                sc.get("time_of_day", ""),
                json.dumps(sc.get("characters", [])),
                int(sc.get("dialogue_count", 0)),
                sc.get("action_summary", ""),
                int(sc.get("line_start", 0)),
                int(sc.get("line_end", 0)),
            ))

    # 2. Characters & traits & relationships
    characters = analysis.get("characters", [])
    if characters:
        conn.execute("DELETE FROM characters WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM character_traits WHERE project_id = ?", (project_id,))
        for c in characters:
            conn.execute("""
                INSERT INTO characters (
                    project_id, name, role, role_basis, description, notes,
                    motivation, strengths_json, flaws_json, character_arc,
                    confidence, cue_count, dialogue_word_count, first_scene, scenes_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                project_id,
                c.get("name", ""),
                c.get("role", "Supporting"),
                c.get("role_basis", ""),
                c.get("description", ""),
                c.get("notes", c.get("note", "")),
                c.get("motivation", ""),
                json.dumps(c.get("strengths", [])),
                json.dumps(c.get("flaws", [])),
                c.get("character_arc", ""),
                c.get("confidence", "Moderate"),
                int(c.get("cue_count", 0)),
                int(c.get("dialogue_word_count", 0)),
                str(c.get("first_scene", "")),
                json.dumps(c.get("scenes", [])),
            ))
            # Save traits evidence
            for tr in c.get("trait_evidence", []) or c.get("evidence", []):
                conn.execute("""
                    INSERT INTO character_traits (
                        project_id, character_name, trait, evidence,
                        scene_ref, confidence, trait_type
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    project_id,
                    c.get("name", ""),
                    tr.get("trait", ""),
                    tr.get("evidence", tr.get("text", "")),
                    str(tr.get("scene", tr.get("scene_ref", ""))),
                    tr.get("confidence", "Moderate"),
                    tr.get("type", tr.get("trait_type", "inferred")),
                ))

    relationships = analysis.get("relationships", [])
    if relationships:
        conn.execute("DELETE FROM character_relationships WHERE project_id = ?", (project_id,))
        for r in relationships:
            conn.execute("""
                INSERT INTO character_relationships (
                    project_id, character_a, character_b, relationship_type,
                    description, shared_scenes_count, evidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                project_id,
                r.get("character_a", ""),
                r.get("character_b", ""),
                r.get("relationship_type", ""),
                r.get("description", ""),
                int(r.get("shared_scenes_count", 0)),
                r.get("evidence", ""),
            ))

    # 3. Locations (preserving any existing manual coordinates)
    existing_coords = {}
    existing_rows = conn.execute(
        "SELECT normalized_name, latitude, longitude, display_name, resolution_status, resolution_source FROM locations WHERE project_id = ?",
        (project_id,)
    ).fetchall()
    for row in existing_rows:
        if row["latitude"] is not None and row["longitude"] is not None:
            existing_coords[row["normalized_name"]] = {
                "latitude": row["latitude"],
                "longitude": row["longitude"],
                "display_name": row["display_name"],
                "resolution_status": row["resolution_status"],
                "resolution_source": row["resolution_source"],
            }

    locations = analysis.get("locations", [])
    if locations:
        conn.execute("DELETE FROM locations WHERE project_id = ?", (project_id,))
        for loc in locations:
            norm_name = loc.get("normalized_name", loc.get("name", "").strip().upper())
            lat = loc.get("latitude")
            lon = loc.get("longitude")
            disp = loc.get("display_name", "")
            status = loc.get("resolution_status", "unresolved")
            source = loc.get("resolution_source", "")

            if lat is None and norm_name in existing_coords:
                lat = existing_coords[norm_name]["latitude"]
                lon = existing_coords[norm_name]["longitude"]
                disp = existing_coords[norm_name]["display_name"]
                status = existing_coords[norm_name]["resolution_status"]
                source = existing_coords[norm_name]["resolution_source"]
                loc["latitude"] = lat
                loc["longitude"] = lon
                loc["display_name"] = disp
                loc["resolution_status"] = status
                loc["resolution_source"] = source

            conn.execute("""
                INSERT INTO locations (
                    project_id, name, normalized_name, int_ext, sub_locations_json,
                    scene_numbers_json, scene_count, latitude, longitude, display_name,
                    resolution_status, resolution_source, unresolved_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                project_id,
                loc.get("name", ""),
                norm_name,
                loc.get("int_ext", "MIXED"),
                json.dumps(loc.get("sub_locations", [])),
                json.dumps(loc.get("scene_numbers", [])),
                int(loc.get("scene_count", len(loc.get("scene_numbers", [])))),
                lat,
                lon,
                disp,
                status,
                source,
                loc.get("unresolved_reason", ""),
            ))
