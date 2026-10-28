import pytest
from app.analyzer import analyse_script

SAMPLE_SCRIPT = """EXT. WAREHOUSE - NIGHT - 1
HENRY MADSEN - a handsome man in suit and tie - stands alone in a VAST FORSAKEN SPACE.
He looks around terrified.

INT. WAREHOUSE - NIGHT - 2
DETECTIVE CHIEF INSPECTOR JOHN LUTHER advances up the steel walkway.
LUTHER
I won't stop until I find her. Tell me where she is!

MADSEN
You have no proof! You can't touch me!

LUTHER
Look at the evidence. The forensics don't lie.

EXT. POLICE STATION - DAY - 3
SUPERINTENDENT ROSE TELLER watches the monitor screen.
TELLER
Follow procedure, John. That's an order.

LUTHER
I am going in now.
"""

def test_character_profiles_grounded_and_distinct():
    res = analyse_script("Luther Test", SAMPLE_SCRIPT)
    characters = res["characters"]
    assert len(characters) >= 3

    char_names = [c["name"] for c in characters]
    assert "Luther" in char_names
    assert "Madsen" in char_names
    assert "Teller" in char_names

    luther = next(c for c in characters if c["name"] == "Luther")
    madsen = next(c for c in characters if c["name"] == "Madsen")
    teller = next(c for c in characters if c["name"] == "Teller")

    # Ensure profiles are distinct
    assert luther["role"] == "Protagonist"
    assert "Antagonist" in madsen["role"] or "Supporting" in madsen["role"]
    assert teller["role"] == "Supporting"

    # Descriptions should not be generic placeholders
    assert "No character description was extracted" not in luther["description"]
    assert "No character description was extracted" not in madsen["description"]

    # Traits should have supporting evidence
    assert len(luther["trait_evidence"]) > 0
    for trait in luther["trait_evidence"]:
        assert "evidence" in trait
        assert "scene" in trait
        assert "confidence" in trait

    # Check distinct notes
    assert luther["notes"] != madsen["notes"]
    assert luther["notes"] != teller["notes"]

def test_relationship_detection():
    res = analyse_script("Luther Test", SAMPLE_SCRIPT)
    relationships = res["relationships"]
    assert len(relationships) > 0

    # Luther and Madsen share scenes
    pair = next((r for r in relationships if (r["character_a"] == "Luther" and r["character_b"] == "Madsen") or (r["character_a"] == "Madsen" and r["character_b"] == "Luther")), None)
    assert pair is not None
    assert pair["shared_scenes_count"] >= 1
    assert "Pursuer & Suspect" in pair["relationship_type"] or "Clashing" in pair["relationship_type"] or "Collaborators" in pair["relationship_type"] or "Allies" in pair["relationship_type"]

def test_no_identical_fallback_profiles():
    res = analyse_script("Luther Test", SAMPLE_SCRIPT)
    chars = res["characters"]
    motivations = [c["motivation"] for c in chars]
    # Motivations must not all be identical boilerplate
    assert len(set(motivations)) > 1
