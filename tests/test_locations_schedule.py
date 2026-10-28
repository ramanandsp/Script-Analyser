import pytest
from unittest.mock import patch, MagicMock
from app.analyzer import normalize_locations, generate_production_schedule, parse_scene_heading
from app.services import geocode_location

def test_location_normalization_groups_sublocations():
    scenes = [
        {"scene_number": "1", "primary_location": "Ktr Medico Warehouse", "sub_location": "Exterior", "int_ext": "EXT"},
        {"scene_number": "2", "primary_location": "Ktr Medico Warehouse", "sub_location": "Main Area", "int_ext": "INT"},
        {"scene_number": "4", "primary_location": "Ktr Medico Warehouse", "sub_location": "Vat Room", "int_ext": "INT"},
        {"scene_number": "3", "primary_location": "Madsen House", "sub_location": "Living Room", "int_ext": "INT"},
    ]
    locs = normalize_locations(scenes)
    assert len(locs) == 2

    ktr = next(l for l in locs if l["name"] == "Ktr Medico Warehouse")
    assert ktr["scene_count"] == 3
    assert set(ktr["scene_numbers"]) == {"1", "2", "4"}
    assert "Main Area" in ktr["sub_locations"]
    assert "Vat Room" in ktr["sub_locations"]
    assert ktr["int_ext"] == "MIXED"

    madsen = next(l for l in locs if l["name"] == "Madsen House")
    assert madsen["scene_count"] == 1
    assert "Living Room" in madsen["sub_locations"]

def test_fictional_locations_remain_unresolved():
    scenes = [
        {"scene_number": "1", "primary_location": "Ktr Medico Warehouse", "sub_location": "", "int_ext": "INT"},
    ]
    locs = normalize_locations(scenes)
    assert locs[0]["resolution_status"] == "unresolved"
    assert locs[0]["latitude"] is None
    assert locs[0]["longitude"] is None
    assert "fictional" in locs[0]["unresolved_reason"].lower() or "withheld" in locs[0]["unresolved_reason"].lower()

@patch("requests.get")
def test_real_location_geocoding(mock_get):
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = [{"lat": "51.5074", "lon": "-0.1278", "display_name": "London, Greater London, England"}]
    mock_get.return_value = mock_resp

    res = geocode_location("London")
    assert res["latitude"] == 51.5074
    assert res["longitude"] == -0.1278
    assert "London" in res["display_name"]

def test_shooting_schedule_generation_sequential():
    scenes = [
        {"scene_number": "1", "scene_order": 1, "heading": "EXT. WAREHOUSE - NIGHT", "primary_location": "Warehouse", "sub_location": "", "time_of_day": "NIGHT", "int_ext": "EXT", "characters": ["Luther"], "action_summary": "He runs."},
        {"scene_number": "2", "scene_order": 2, "heading": "INT. WAREHOUSE - NIGHT", "primary_location": "Warehouse", "sub_location": "Vat Room", "time_of_day": "NIGHT", "int_ext": "INT", "characters": ["Luther", "Madsen"], "action_summary": "Stunt on walkway."},
    ]
    sched = generate_production_schedule(scenes, minutes_per_scene=60, shooting_hours_per_day=8, strategy="sequential")
    assert len(sched) == 2
    assert sched[0]["day"] == 1
    assert sched[0]["scene_number"] == "1"
    assert sched[0]["primary_location"] == "Warehouse"
    assert sched[1]["scene_number"] == "2"
    assert "Stunt" in sched[1]["planning_notes"] or "Night" in sched[1]["planning_notes"]

def test_shooting_schedule_generation_by_location():
    scenes = [
        {"scene_number": "1", "scene_order": 1, "heading": "EXT. WAREHOUSE - NIGHT", "primary_location": "Warehouse", "sub_location": "", "time_of_day": "NIGHT", "int_ext": "EXT", "characters": ["Luther"], "action_summary": ""},
        {"scene_number": "2", "scene_order": 2, "heading": "INT. HOUSE - DAY", "primary_location": "House", "sub_location": "Kitchen", "time_of_day": "DAY", "int_ext": "INT", "characters": ["Zoe"], "action_summary": ""},
        {"scene_number": "3", "scene_order": 3, "heading": "INT. WAREHOUSE - NIGHT", "primary_location": "Warehouse", "sub_location": "Vat Room", "time_of_day": "NIGHT", "int_ext": "INT", "characters": ["Madsen"], "action_summary": ""},
    ]
    sched = generate_production_schedule(scenes, minutes_per_scene=45, shooting_hours_per_day=8, strategy="by_location")
    assert len(sched) == 3
    # Warehouse scenes should be grouped together
    warehouse_indices = [i for i, s in enumerate(sched) if s["primary_location"] == "Warehouse"]
    assert warehouse_indices == [0, 1] or warehouse_indices == [1, 2]
