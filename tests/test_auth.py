import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.auth import create_access_token

client = TestClient(app)

def test_unauthenticated_request_rejected():
    """Private endpoints must reject requests lacking Authorization header."""
    r = client.get("/api/projects")
    assert r.status_code == 401
    assert "detail" in r.json()

    r2 = client.post("/api/projects", json={"title": "Test", "script_text": "INT. ROOM - DAY\nHi."})
    assert r2.status_code == 401

def test_faculty_demo_login():
    """Faculty 1-click demo login returns a valid token."""
    r = client.post("/api/auth/demo-login")
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["id"] == "demo-user-id"

    # Use the token to fetch /api/auth/me
    token = data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    me_resp = client.get("/api/auth/me", headers=headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["user"]["id"] == "demo-user-id"

def test_user_registration_and_login_flow():
    """Test user signup, duplicate prevention, and login."""
    test_email = f"writer_{id(app)}@scriptstudio.io"
    test_pwd = "ScreenplaySecret2026!"
    test_name = "Jane Screenwriter"

    # 1. Register
    reg_resp = client.post("/api/auth/register", json={
        "email": test_email,
        "password": test_pwd,
        "full_name": test_name,
    })
    assert reg_resp.status_code == 200
    reg_data = reg_resp.json()
    assert "access_token" in reg_data
    assert reg_data["user"]["email"] == test_email

    # 2. Duplicate registration rejected
    dup_resp = client.post("/api/auth/register", json={
        "email": test_email,
        "password": test_pwd,
    })
    assert dup_resp.status_code == 400

    # 3. Login with wrong password rejected
    bad_login = client.post("/api/auth/login", json={
        "email": test_email,
        "password": "WrongPassword123",
    })
    assert bad_login.status_code == 401

    # 4. Login with correct password
    good_login = client.post("/api/auth/login", json={
        "email": test_email,
        "password": test_pwd,
    })
    assert good_login.status_code == 200
    assert "access_token" in good_login.json()

def test_cross_user_isolation():
    """User A must NOT be able to view, edit, or delete User B's project."""
    token_a = create_access_token("user_alpha_uuid", "alpha@film.com", "User Alpha")
    token_b = create_access_token("user_beta_uuid", "beta@film.com", "User Beta")

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User A creates a private script
    create_res = client.post("/api/projects", json={
        "title": "Alpha Confidential Script",
        "author": "User Alpha",
        "script_text": "INT. VAULT - NIGHT\nALPHA opens the safe.\n",
    }, headers=headers_a)
    assert create_res.status_code == 200
    project_a = create_res.json()
    p_id = project_a["id"]

    # User A can access it
    get_res_a = client.get(f"/api/projects/{p_id}", headers=headers_a)
    assert get_res_a.status_code == 200
    assert get_res_a.json()["id"] == p_id

    # User B CANNOT access it (must return 404 access denied)
    get_res_b = client.get(f"/api/projects/{p_id}", headers=headers_b)
    assert get_res_b.status_code == 404

    # User B CANNOT delete it
    del_res_b = client.delete(f"/api/projects/{p_id}", headers=headers_b)
    assert del_res_b.status_code in (403, 404)

    # User A deletes their own project cleanly
    del_res_a = client.delete(f"/api/projects/{p_id}", headers=headers_a)
    assert del_res_a.status_code == 200
