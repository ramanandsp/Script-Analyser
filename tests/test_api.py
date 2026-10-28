import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
AUTH_HEADERS = {"Authorization": "Bearer demo-faculty-session-token"}

def test_dashboard_index_route():
    r = client.get("/")
    assert r.status_code == 200
    assert "Script Analyser" in r.text
    assert "<!DOCTYPE html>" in r.text

def test_health_and_config():
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "author" in data
    assert "database_engine" in data

    r2 = client.get("/api/config")
    assert r2.status_code == 200
    cfg = r2.json()
    assert "market_provider" in cfg
    assert "database_backend" in cfg
    assert "demo_email" in cfg

def test_project_crud_and_endpoints():
    script_content = """EXT. PARK - DAY - 1
JOHN sits on a bench.
JOHN
I will protect this city no matter what.

INT. CAFE - NIGHT - 2
SARAH approaches.
SARAH
The files are ready.
"""
    # 1. Create project with auth headers
    create_payload = {
        "title": "API Test Project",
        "author": "Test Author",
        "script_text": script_content,
        "budget_settings": {"minutes_per_scene": 40},
    }
    r = client.post("/api/projects", json=create_payload, headers=AUTH_HEADERS)
    assert r.status_code == 200
    proj = r.json()
    p_id = proj["id"]
    assert proj["title"] == "API Test Project"
    assert proj["analysis"]["scene_count"] == 2

    # 2. Get project
    r_get = client.get(f"/api/projects/{p_id}", headers=AUTH_HEADERS)
    assert r_get.status_code == 200
    assert r_get.json()["id"] == p_id

    # 3. Get scenes
    r_scenes = client.get(f"/api/projects/{p_id}/scenes", headers=AUTH_HEADERS)
    assert r_scenes.status_code == 200
    scenes = r_scenes.json()
    assert len(scenes) == 2

    # 4. Get characters
    r_chars = client.get(f"/api/projects/{p_id}/characters", headers=AUTH_HEADERS)
    assert r_chars.status_code == 200
    chars = r_chars.json()
    assert len(chars) >= 2

    # 5. Get locations
    r_locs = client.get(f"/api/projects/{p_id}/locations", headers=AUTH_HEADERS)
    assert r_locs.status_code == 200
    locs = r_locs.json()
    assert len(locs) >= 2

    # 6. Manual location update
    man_payload = {
        "name": locs[0]["name"],
        "latitude": 51.5074,
        "longitude": -0.1278,
        "display_name": "Regent's Park, London",
    }
    r_man = client.post(f"/api/projects/{p_id}/locations/manual", json=man_payload, headers=AUTH_HEADERS)
    assert r_man.status_code == 200
    upd_locs = r_man.json()["analysis"]["locations"]
    target = next(l for l in upd_locs if l["name"] == locs[0]["name"])
    assert target["latitude"] == 51.5074
    assert target["resolution_status"] == "manual"

    # 7. Get schedule
    r_sched = client.get(f"/api/projects/{p_id}/schedule?strategy=sequential", headers=AUTH_HEADERS)
    assert r_sched.status_code == 200
    assert len(r_sched.json()["schedule"]) == 2

    # 8. Reanalyze
    r_re = client.post(f"/api/projects/{p_id}/reanalyze", json={"budget_settings": {"minutes_per_scene": 50}}, headers=AUTH_HEADERS)
    assert r_re.status_code == 200

    # 9. Export report
    r_rep = client.get(f"/api/projects/{p_id}/report", headers=AUTH_HEADERS)
    assert r_rep.status_code == 200
    rep_data = r_rep.json()
    assert "scenes" in rep_data
    assert "characters" in rep_data
    assert "locations" in rep_data

    # 10. Delete project
    r_del = client.delete(f"/api/projects/{p_id}", headers=AUTH_HEADERS)
    assert r_del.status_code == 200
    assert r_del.json()["deleted"] is True

    # 11. Confirm 404 after deletion
    r_404 = client.get(f"/api/projects/{p_id}", headers=AUTH_HEADERS)
    assert r_404.status_code == 404

def test_upload_file_endpoint():
    txt_content = b"EXT. ROOFTOP - NIGHT - 1\nJOHN stands tall.\nJOHN\nI'm ready.\n"
    files = {"file": ("script.txt", txt_content, "text/plain")}
    data = {"title": "Upload Script Test", "author": "Uploader"}
    r = client.post("/api/projects/upload", data=data, files=files, headers=AUTH_HEADERS)
    assert r.status_code == 200
    p_id = r.json()["id"]

    # Clean up
    client.delete(f"/api/projects/{p_id}", headers=AUTH_HEADERS)
