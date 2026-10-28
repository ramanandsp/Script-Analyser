import pytest
from app.analyzer import (
    parse_scene_heading,
    is_valid_character_cue,
    clean_character_cue,
    parse_screenplay_structure,
    analyse_script,
)

def test_scene_heading_parsing_standard():
    h = parse_scene_heading("INT. HOSPITAL ROOM - NIGHT", default_scene_order=1)
    assert h["int_ext"] == "INT"
    assert h["primary_location"] == "Hospital Room"
    assert h["sub_location"] == ""
    assert h["time_of_day"] == "NIGHT"
    assert h["scene_number"] == "1"

def test_scene_heading_parsing_with_sublocation_and_code():
    h = parse_scene_heading("INT. KTR MEDICO WAREHOUSE, VAT ROOM - NIGHT 1 - 00.034 4", default_scene_order=4)
    assert h["int_ext"] == "INT"
    assert h["primary_location"] == "Ktr Medico Warehouse"
    assert h["sub_location"] == "Vat Room"
    assert "NIGHT 1" in h["time_of_day"]
    assert h["scene_number"] == "4"

def test_scene_heading_parsing_with_alphanumeric_code():
    h = parse_scene_heading("INT. SCU, BULLPEN - DAY 3 - 10.12 (FORMERLY SC 31)35A 35A", default_scene_order=35)
    assert h["int_ext"] == "INT"
    assert h["primary_location"] == "Scu"
    assert h["sub_location"] == "Bullpen"
    assert "DAY 3" in h["time_of_day"]
    assert h["scene_number"] == "35A"

def test_scene_heading_mixed_int_ext():
    h = parse_scene_heading("INT./EXT. CAR - MOVING - DAY", default_scene_order=5)
    assert h["int_ext"] == "INT/EXT"
    assert "Car" in h["primary_location"]
    assert h["time_of_day"] == "DAY"

def test_scene_headings_not_classified_as_characters():
    assert not is_valid_character_cue("INT. HOSPITAL ROOM - NIGHT", next_line="He sits quietly.")
    assert not is_valid_character_cue("EXT. CITY STREET - DAY", next_line="Cars rush by.")
    assert not is_valid_character_cue("FADE IN:", next_line="Blackness.")
    assert not is_valid_character_cue("CUT TO:", next_line="Scene change.")
    assert not is_valid_character_cue("A FEW MOMENTS LATER", next_line="John enters.")
    assert not is_valid_character_cue("KITCHEN", next_line="The pot boils.")
    assert not is_valid_character_cue("WINDOW", next_line="Rain pours.")

def test_character_cue_normalization():
    assert clean_character_cue("JOHN (V.O.)") == "JOHN"
    assert clean_character_cue("JOHN (CONT'D)") == "JOHN"
    assert clean_character_cue("ALICE (O.S.)") == "ALICE"
    assert clean_character_cue("REED (ON PHONE)") == "REED"

def test_valid_character_cues():
    assert is_valid_character_cue("LUTHER", next_line="Where is she?")
    assert is_valid_character_cue("ALICE (O.S.)", next_line="Right behind you, John.")
    assert is_valid_character_cue("TELLER", next_line="Take the team with you.")
    assert is_valid_character_cue("DR. SMITH", next_line="The patient is ready.")

def test_empty_or_malformed_script_handling():
    res1 = analyse_script("Empty", "")
    assert res1["scene_count"] == 0
    assert res1["character_count"] == 0
    assert isinstance(res1["structured_scenes"], list)

    res2 = analyse_script("Malformed", "   \n\n   --- random string ---   ")
    assert res2["scene_count"] == 0
    assert len(res2["analysis_warnings"]) > 0

def test_screenplay_structure_dialogue_association():
    script = """EXT. ROOFTOP - NIGHT - 1
Cold wind sweeps across the ledge.

LUTHER
Tell me where Madsen is.

ALICE
Why would I spoil the surprise?

INT. POLICE CAR - CONTINUOUS - 2
Ripley drives through traffic.
"""
    parsed = parse_screenplay_structure(script)
    scenes = parsed["structured_scenes"]
    assert len(scenes) == 2
    assert scenes[0]["scene_number"] == "1"
    assert "Luther" in scenes[0]["characters"]
    assert "Alice" in scenes[0]["characters"]
    assert scenes[1]["scene_number"] == "2"
