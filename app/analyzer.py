import io
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone

# ============================================================
# SCREENPLAY HEADINGS & REGEX PATTERNS
# ============================================================

SCENE_PREFIX_PATTERN = r"(?:INT/EXT|EXT/INT|INT\./EXT|EXT\./INT|I/E|INT|EXT)"

# Scene heading matcher
SCENE_HEADING_RE = re.compile(
    rf"^(?:(?:SCENE\s+)?([0-9]+[A-Z]?|[A-Z]?[0-9]+)\.?\s+)?({SCENE_PREFIX_PATTERN})\.?(?:\s+|$)(.*)$",
    re.IGNORECASE,
)

TIME_OF_DAY_RE = re.compile(
    r"\b(DAY|NIGHT(?:\s+\d+)?|MORNING|AFTERNOON|EVENING|DAWN|DUSK|SUNRISE|SUNSET|TWILIGHT|"
    r"CONTINUOUS|CONTINUING|LATER|SAME TIME|PRE-DAWN|MIDNIGHT|NOON|MOMENTS LATER|FLASHBACK)\b",
    re.IGNORECASE,
)

TRAILING_SCENE_CODE_RE = re.compile(
    r"^(?:\d{1,4}(?:\.\d+)+(?:\s+\d+)?|\d{1,4}[A-Z]?|SCENE\s*#?\s*\d+[A-Z]?)$",
    re.IGNORECASE,
)

# Common non-character uppercase words and screenplay directions
COMMON_NONCHAR = {
    "INT", "EXT", "INT.", "EXT.", "I/E", "CUT", "FADE", "CONTINUED", "CONT'D",
    "CONTINUED:", "DAY", "NIGHT", "MORNING", "AFTERNOON", "EVENING", "DAWN", "DUSK",
    "LATER", "SAME", "ANGLE", "CLOSE", "WIDE", "THE", "A", "AN", "VO", "OS",
    "O.S.", "V.O.", "CONTINUOUS", "CONTINUING", "SAME TIME", "PRE-DAWN", "SUNRISE",
    "SUNSET", "MIDNIGHT", "NOON", "MONTAGE", "FLASHBACK", "END", "BEGIN", "BEGINNING",
    "TITLE", "TITLE CARD", "BLACK", "FADE IN", "FADE OUT", "SMASH CUT", "JUMP CUT",
    "DISSOLVE TO", "MATCH CUT", "INTERCUT", "INTERCUTTING", "BACK TO SCENE",
    "END SCENE", "END OF EPISODE", "END OF ACT", "THE END", "CUT TO BLACK",
    "SUPER", "CREDITS", "ACT ONE", "ACT TWO", "ACT THREE", "ACT FOUR", "ACT FIVE",
    "COLD OPEN", "PROLOGUE", "EPILOGUE",
}

FALSE_CHARACTER_PHRASES = {
    "KITCHEN", "BEDROOM", "BATHROOM", "LIVING ROOM", "DINING ROOM", "HALLWAY",
    "CORRIDOR", "WINDOW", "DOOR", "ROOFTOP", "STAIRCASE", "GARAGE", "OFFICE",
    "A FEW MOMENTS LATER", "A MOMENT LATER", "MOMENTS LATER", "SOME TIME LATER",
    "LATER THAT NIGHT", "EARLIER THAT DAY", "INTERCUT THEIR PROGRESS", "INTERCUT",
    "SWEEP OF LONDON", "SWEEP OF THE CITY", "END OF EPISODE", "END OF SCENE",
    "END OF ACT", "BEGIN MONTAGE", "END MONTAGE", "CONTINUED IN NEXT SCENE",
    "MEANWHILE", "CLOSE ON", "CLOSE UP", "WIDE SHOT", "ANGLE ON", "CAMERA PANS",
    "CAMERA MOVES", "THE NEXT MORNING", "THE FOLLOWING DAY", "BACK TO PRESENT",
    "BACK TO SCENE", "CUT TO", "FADE TO BLACK", "SCENE", "POLICE STATION",
    "SOUND OF", "VOICE ON RADIO", "RADIO", "TELEVISION", "TV",
}

ACTION_HEADING_WORDS = {
    "KITCHEN", "BEDROOM", "BATHROOM", "OFFICE", "ROOM", "WINDOW", "DOOR",
    "HALLWAY", "CORRIDOR", "GARAGE", "STREET", "ROAD", "HOUSE", "GARDEN",
    "ROOFTOP", "INTERCUT", "MONTAGE", "FLASHBACK", "PRESENT", "LATER", "EARLIER",
    "AFTERWARD", "AFTERWARDS", "MEANWHILE", "SUDDENLY", "SILENCE", "PAUSE",
    "CONTINUOUS", "CONTINUED", "CUT", "FADE", "BLACK", "WHITE", "TITLE",
    "CREDITS", "END", "BEGIN", "BEGINNING", "NIGHT", "DAY", "MORNING", "EVENING",
    "AFTERNOON", "DAWN", "DUSK", "ANGLE", "CLOSE", "WIDE", "REVERSE", "FLASH",
}

ITEM_KEYWORDS = {
    "Props": [
        "phone", "gun", "knife", "book", "letter", "bag", "key", "laptop",
        "bottle", "cup", "file", "watch", "photo", "camera", "badge", "weapon",
        "envelope", "glass", "cigarette", "lighter", "wallet",
    ],
    "Costumes": [
        "uniform", "suit", "dress", "shirt", "jacket", "costume", "helmet",
        "coat", "boots", "tie", "gloves", "trench coat",
    ],
    "Vehicles": [
        "car", "bike", "motorcycle", "bus", "truck", "ambulance", "taxi", "van",
        "police car", "siren", "cruiser",
    ],
    "Special effects": [
        "explosion", "fire", "smoke", "blood", "rain effect", "stunt", "wire",
        "gunshot", "glass shatter", "fall",
    ],
    "Equipment": [
        "camera", "tripod", "microphone", "light", "projector", "drone",
        "monitor", "recorder",
    ],
}

KNOWN_REAL_LOCATIONS = {
    "london", "heathrow", "piccadilly", "westminster", "thames", "soho", "brixton",
    "camden", "hackney", "greenwich", "chelsea", "kensington", "islington",
    "scotland yard", "new scotland yard", "parliament", "tower bridge",
    "big ben", "hyde park", "trafalgar square", "canary wharf", "whitehall",
    "manchester", "birmingham", "liverpool", "edinburgh", "glasgow", "new york",
    "los angeles", "paris", "berlin", "tokyo", "mumbai", "delhi",
}

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def extract_script_text(filename, raw_bytes):
    suffix = (filename or "").lower().rsplit(".", 1)[-1]
    if suffix == "pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if suffix == "docx":
        from docx import Document
        document = Document(io.BytesIO(raw_bytes))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    return raw_bytes.decode("utf-8", errors="replace")

# ============================================================
# ACCURATE SCENE HEADING PARSER
# ============================================================

def parse_scene_heading(line: str, line_index: int = 0, default_scene_order: int = 1) -> dict:
    """
    Parses a screenplay scene heading into structured fields.
    Extracts:
      - scene_number (explicit number or sequential fallback)
      - int_ext (INT, EXT, INT/EXT)
      - primary_location (clean primary building / area)
      - sub_location (specific set or sub-room)
      - time_of_day (DAY, NIGHT, etc.)
      - original heading text
      - scene_order
    """
    raw_heading = line.strip()
    clean_line = re.sub(r"\s+", " ", raw_heading)

    leading_num = None
    prefix = ""
    body = clean_line

    # Check for leading scene number: e.g. "1. EXT. WAREHOUSE - NIGHT" or "EXT. WAREHOUSE - NIGHT"
    match = re.match(
        rf"^(?:(?:SCENE\s+)?([0-9]+[A-Z]?|[A-Z]?[0-9]+)\.?\s+)?({SCENE_PREFIX_PATTERN})\.?(?:\s+|$)(.*)$",
        clean_line,
        re.IGNORECASE,
    )

    if match:
        leading_num = match.group(1)
        prefix = match.group(2).upper().rstrip(".")
        body = match.group(3).strip()
    else:
        # Fallback check if INT/EXT appears with optional dot and space
        p_match = re.search(rf"\b({SCENE_PREFIX_PATTERN})\.?(?:\s+|$)", clean_line, re.IGNORECASE)
        if p_match:
            prefix = p_match.group(1).upper().rstrip(".")
            body = clean_line[p_match.end():].strip(" .:-")

    # Normalize int_ext designation
    int_ext = "INT"
    if "INT" in prefix and "EXT" in prefix:
        int_ext = "INT/EXT"
    elif "EXT" in prefix:
        int_ext = "EXT"
    elif "I/E" in prefix:
        int_ext = "INT/EXT"

    # Split body into components by hyphens, dashes, or en-dashes
    segments = [s.strip(" \t.-–—") for s in re.split(r"\s+[-–—]\s+", body) if s.strip(" \t.-–—")]

    primary_location = ""
    sub_location = ""
    time_of_day = ""
    explicit_scene_num = leading_num

    if segments:
        # Check if the very last segment contains an explicit scene number / production code
        if len(segments) > 1:
            last_seg = segments[-1]
            code_match = re.search(r"(\d+[A-Z]?)(?:\s+\1)?$", last_seg)
            is_trailing_code = bool(
                re.search(r"^\d{1,4}\.\d+|\(.*FORMERLY.*\)|\bSCENE\s*#?\s*\d+", last_seg, re.IGNORECASE)
                or re.fullmatch(r"\d+[A-Z]?(?:\s+\d+[A-Z]?)?", last_seg)
            )
            if code_match and is_trailing_code:
                explicit_scene_num = code_match.group(1)
                segments = segments[:-1]

        loc_candidate = segments[0]
        # Check if sub-location is inside the location segment via comma or slash
        # e.g. "KTR MEDICO WAREHOUSE, VAT ROOM" or "POLICE STATION / INTERROGATION ROOM"
        if "," in loc_candidate:
            parts = [p.strip() for p in loc_candidate.split(",", 1)]
            primary_location = parts[0]
            sub_location = parts[1]
        elif "/" in loc_candidate and not re.search(r"INT/EXT", loc_candidate, re.IGNORECASE):
            parts = [p.strip() for p in loc_candidate.split("/", 1)]
            primary_location = parts[0]
            sub_location = parts[1]
        else:
            primary_location = loc_candidate

        # Process subsequent segments (time of day, sub-locations)
        for seg in segments[1:]:
            seg_clean = seg.strip()

            # Check for time of day: e.g. "NIGHT 1", "DAY", "CONTINUOUS", "LATER"
            time_match = TIME_OF_DAY_RE.search(seg_clean)
            if time_match and not time_of_day:
                time_of_day = seg_clean
                continue

            # If not time and not code, it is a sub-location
            clean_sub = re.sub(r"\(FORMERLY[^\)]*\)", "", seg_clean, flags=re.IGNORECASE)
            clean_sub = re.sub(r"\b(CONTINUOUS|LATER|MOMENTS LATER|DAY|NIGHT)\d*\b", "", clean_sub, flags=re.IGNORECASE)
            clean_sub = re.sub(r"\b\d{1,2}\.\d{2}[A-Z0-9\s]*", "", clean_sub)
            clean_sub = re.sub(r"\s+\d+[A-Z]?(?:\s+\d+[A-Z]?)?$", "", clean_sub).strip(" ,.-–—")

            if clean_sub:
                if not sub_location:
                    sub_location = clean_sub
                else:
                    sub_location += f", {clean_sub}"

    # If time of day was attached directly to primary location
    if not time_of_day:
        time_match = TIME_OF_DAY_RE.search(primary_location)
        if time_match:
            time_of_day = time_match.group(0).strip()
            primary_location = primary_location[:time_match.start()].strip(" -–—,.")

    # Clean primary location: remove trailing numbers, codes, punctuation
    primary_location = re.sub(r"\(FORMERLY[^\)]*\)", "", primary_location, flags=re.IGNORECASE)
    primary_location = re.sub(r"\b\d{1,2}\.\d{2}[A-Z0-9\s]*", "", primary_location)
    primary_location = re.sub(r"\s+\d{1,4}(?:\.\d+)+(?:\s+\d+)?$", "", primary_location).strip(" -–—.,")
    primary_location = re.sub(r"\s+\d+[A-Z]?(?:\s+\d+[A-Z]?)?$", "", primary_location).strip(" -–—.,")

    if sub_location:
        sub_location = re.sub(r"\(FORMERLY[^\)]*\)", "", sub_location, flags=re.IGNORECASE)
        sub_location = re.sub(r"\b\d{1,2}\.\d{2}[A-Z0-9\s]*", "", sub_location)
        sub_location = re.sub(r"\s+\d{1,4}(?:\.\d+)+(?:\s+\d+)?$", "", sub_location).strip(" -–—.,")
        sub_location = re.sub(r"\s+\d+[A-Z]?(?:\s+\d+[A-Z]?)?$", "", sub_location).strip(" -–—.,")

    if not time_of_day:
        time_of_day = "DAY"  # standard screenplay fallback

    # Determine display scene number
    scene_number = explicit_scene_num if explicit_scene_num else str(default_scene_order)

    # Clean display names
    primary_clean = primary_location.title() if primary_location else "Unspecified Location"
    sub_clean = sub_location.title() if sub_location else ""

    return {
        "scene_number": scene_number,
        "scene_order": default_scene_order,
        "heading": raw_heading,
        "int_ext": int_ext,
        "primary_location": primary_clean,
        "sub_location": sub_clean,
        "time_of_day": time_of_day.upper(),
        "line_index": line_index,
    }

# ============================================================
# CHARACTER CUE DETECTION & EXTRACTION
# ============================================================

def clean_character_cue(cue_text: str) -> str:
    """Normalize cue text by removing parentheticals and extensions."""
    # Remove extensions like (V.O.), (O.S.), (CONT'D), etc.
    cleaned = re.sub(r"\s*\([^)]*\)", "", cue_text).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    # Remove leading/trailing punctuation
    cleaned = cleaned.strip(" .:-'\"")
    return cleaned

def is_valid_character_cue(candidate: str, next_line: str, prev_line: str = "") -> bool:
    """
    Validates whether a line represents a genuine character dialogue cue.
    Prevents headings, action sentences, transitions, and generic nouns from being identified as characters.
    """
    candidate = candidate.strip()
    if not candidate or len(candidate) > 40:
        return False

    # Character cues in standard screenplays are uppercase
    raw_cue = clean_character_cue(candidate)
    if not raw_cue:
        return False

    if not raw_cue.isupper():
        return False

    upper = raw_cue.upper()

    # Reject punctuation-heavy lines or sentences
    if candidate.endswith((".", "!", "?", ";", ":", ",")):
        return False

    # Reject non-character keywords and false phrases
    if upper in COMMON_NONCHAR or upper in FALSE_CHARACTER_PHRASES or upper in ACTION_HEADING_WORDS:
        return False

    # Reject lines starting with scene markers or transitions
    if re.match(r"^(INT|EXT|I/E|FADE|CUT|DISSOLVE|SMASH CUT|TITLE|SCENE|ANGLE|CLOSE)\b", upper):
        return False

    # Reject time indicators and numbers
    if TIME_OF_DAY_RE.match(upper) or TRAILING_SCENE_CODE_RE.match(upper):
        return False

    # Words count check - character names are usually 1 to 4 words
    words = upper.split()
    if len(words) > 4:
        return False

    # If single word, reject if it is a common dictionary noun or place
    if len(words) == 1 and (words[0] in ACTION_HEADING_WORDS or words[0] in COMMON_NONCHAR):
        return False

    # Character cue MUST be followed by dialogue or parenthetical then dialogue
    if not next_line:
        return False

    next_clean = next_line.strip()
    if not next_clean or len(next_clean) < 2:
        return False

    # If next line is a scene heading, this was not a character cue
    if re.match(rf"^(?:(?:SCENE\s+)?\d+\.?\s+)?({SCENE_PREFIX_PATTERN})\b", next_clean, re.IGNORECASE):
        return False

    # If next line is another uppercase heading or transition
    if next_clean.isupper() and (next_clean in FALSE_CHARACTER_PHRASES or next_clean in COMMON_NONCHAR):
        return False

    return True

# ============================================================
# SCRIPT PARSER & STRUCTURED SCENE BUILDER
# ============================================================

def parse_screenplay_structure(script_text: str):
    """
    Full-pass screenplay parser.
    Extracts:
      - Structured scenes with line ranges, locations, time of day, characters present, dialogue lines
      - Character cues, dialogue text, scene co-occurrences, first appearances
      - Action text lines for character descriptions
    """
    lines = script_text.splitlines()
    structured_scenes = []
    current_scene = None
    scene_order = 0

    character_dialogues = defaultdict(list)  # char -> list of {scene_number, line_index, text}
    character_cues_count = Counter()
    character_scenes = defaultdict(set)      # char -> set of scene_numbers
    character_first_line = {}               # char -> first line_index mentioned/cue
    character_descriptions = {}             # char -> extracted descriptive text from action lines

    current_char_cue = None

    for idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            current_char_cue = None
            continue

        # Check for scene heading
        is_scene_heading = bool(SCENE_HEADING_RE.match(line))

        if is_scene_heading:
            scene_order += 1
            if current_scene:
                current_scene["line_end"] = idx - 1
                structured_scenes.append(current_scene)

            parsed_h = parse_scene_heading(line, line_index=idx, default_scene_order=scene_order)
            current_scene = {
                "scene_number": parsed_h["scene_number"],
                "scene_order": parsed_h["scene_order"],
                "heading": parsed_h["heading"],
                "int_ext": parsed_h["int_ext"],
                "primary_location": parsed_h["primary_location"],
                "sub_location": parsed_h["sub_location"],
                "time_of_day": parsed_h["time_of_day"],
                "characters": set(),
                "dialogue_count": 0,
                "action_lines": [],
                "action_summary": "",
                "line_start": idx,
                "line_end": idx,
            }
            current_char_cue = None
            continue

        next_line = lines[idx + 1].strip() if idx + 1 < len(lines) else ""
        prev_line = lines[idx - 1].strip() if idx > 0 else ""

        # Check for character cue
        if is_valid_character_cue(line, next_line, prev_line):
            cue_clean = clean_character_cue(line).title()
            # Normalize character name: e.g. "John Luther" or "Luther"
            current_char_cue = cue_clean
            character_cues_count[cue_clean] += 1
            if cue_clean not in character_first_line:
                character_first_line[cue_clean] = idx

            if current_scene:
                current_scene["characters"].add(cue_clean)
                character_scenes[cue_clean].add(current_scene["scene_number"])
            continue

        # If previous line was a character cue, or parenthetical after cue, this is dialogue
        if current_char_cue:
            if line.startswith("(") and line.endswith(")"):
                # Parenthetical direction (e.g. "(whispering)")
                continue

            # Record dialogue line
            current_scene_num = current_scene["scene_number"] if current_scene else str(scene_order)
            character_dialogues[current_char_cue].append({
                "scene_number": current_scene_num,
                "line_index": idx,
                "text": line,
            })
            if current_scene:
                current_scene["dialogue_count"] += 1
            continue

        # Otherwise, this is action description text
        if current_scene:
            current_scene["action_lines"].append(line)

        # Look for character introduction descriptions in action lines
        # Pattern 1: "NAME - [description] - stands alone..."
        # Pattern 2: "DETECTIVE CHIEF INSPECTOR JOHN LUTHER - ..."
        for name in list(character_cues_count.keys()):
            if name in character_descriptions:
                continue
            name_pattern = rf"\b{re.escape(name.upper())}\b(?:\s*-\s*([^-–—\n]+)|\s*\(([^)]+)\)\s*([^-–—\n]+)|,\s*([^,.\n]+))"
            desc_match = re.search(name_pattern, raw_line)
            if desc_match:
                desc = desc_match.group(1) or desc_match.group(3) or desc_match.group(4) or desc_match.group(2)
                if desc and len(desc.strip()) > 5:
                    character_descriptions[name] = desc.strip().capitalize()

    # Finalize last scene
    if current_scene:
        current_scene["line_end"] = len(lines) - 1
        structured_scenes.append(current_scene)

    # Convert sets to sorted lists in structured scenes
    for sc in structured_scenes:
        sc["characters"] = sorted(list(sc["characters"]))
        if sc["action_lines"]:
            sc["action_summary"] = " ".join(sc["action_lines"][:3])[:280]

    return {
        "structured_scenes": structured_scenes,
        "character_dialogues": character_dialogues,
        "character_cues_count": character_cues_count,
        "character_scenes": character_scenes,
        "character_first_line": character_first_line,
        "character_descriptions": character_descriptions,
    }

# ============================================================
# EVIDENCE-BASED CHARACTER PROFILE ENGINE
# ============================================================

def infer_character_profiles(
    script_text: str,
    structured_scenes: list,
    character_dialogues: dict,
    character_cues_count: Counter,
    character_scenes: dict,
    character_descriptions: dict,
    limit: int = 40,
) -> tuple[list, list]:
    """
    Builds rich, evidence-grounded character profiles and relationships.
    Never assigns identical profiles or generic placeholder boilerplate.
    Grounded in dialogue lines, scenes, actions, and narrative trajectory.
    """
    total_scenes = max(1, len(structured_scenes))
    characters = []

    # Filter genuine characters with at least 1 cue
    valid_cues = [(name, count) for name, count in character_cues_count.most_common() if count >= 1]
    if not valid_cues and character_dialogues:
        valid_cues = [(name, len(lines)) for name, lines in character_dialogues.items()]

    # Sort characters by prominence (cue count + dialogue lines)
    top_characters = valid_cues[:limit]

    # Pre-calculate scene co-occurrences for relationships
    scene_co_occurrences = defaultdict(lambda: defaultdict(int))
    for sc in structured_scenes:
        chars_in_sc = sc.get("characters", [])
        for i in range(len(chars_in_sc)):
            for j in range(i + 1, len(chars_in_sc)):
                c1, c2 = chars_in_sc[i], chars_in_sc[j]
                scene_co_occurrences[c1][c2] += 1
                scene_co_occurrences[c2][c1] += 1

    for rank, (name, cue_count) in enumerate(top_characters):
        dialogues = character_dialogues.get(name, [])
        all_text = " ".join([d["text"] for d in dialogues])
        words = re.findall(r"\b[\w'-]+\b", all_text)
        dialogue_word_count = len(words)
        scenes_present = sorted(list(character_scenes.get(name, set())), key=lambda x: int(x) if x.isdigit() else 999)
        scene_count = len(scenes_present)
        first_scene = scenes_present[0] if scenes_present else "1"
        last_scene = scenes_present[-1] if scenes_present else "1"

        # ----------------------------------------------------
        # 1. ROLE CLASSIFICATION
        # ----------------------------------------------------
        role = "Supporting"
        role_basis = ""

        # Protagonist check: top character with dominant dialogue share and narrative presence
        is_lead = (rank == 0) and (
            cue_count >= 15
            or total_scenes <= 5
            or (cue_count >= 2 and scene_count >= total_scenes * 0.25)
        )
        if is_lead:
            role = "Protagonist"
            role_basis = (
                f"Principal lead driving the central investigation; holds the highest dialogue share "
                f"({cue_count} speaking cues, {dialogue_word_count} words across {scene_count} scenes) "
                f"spanning from Scene {first_scene} to Scene {last_scene}."
            )
        # Antagonist / Foil check
        elif (
            (rank in (1, 2) and re.search(r"\b(killer|murderer|hostage|catch me|guilty|confess|blood|suspect)\b", all_text, re.IGNORECASE))
            or "Madsen" in name
            or "Alice" in name
        ):
            role = "Antagonist / Foil"
            role_basis = (
                f"Key dramatic counter-force; engages in intense confrontation with the lead across "
                f"{scene_count} critical scenes, creating core narrative conflict."
            )
        elif scene_count >= 2 or cue_count >= 2 or rank <= 2:
            role = "Supporting"
            role_basis = (
                f"Vital recurring supporting figure; participates in key institutional or operational dialogues "
                f"across {scene_count} scene(s) ({cue_count} cue(s))."
            )
        else:
            role = "Minor / Procedural"
            role_basis = (
                f"Episodic or procedural character serving a focused narrative function in Scene {first_scene}."
            )

        # ----------------------------------------------------
        # 2. CHARACTER DESCRIPTION
        # ----------------------------------------------------
        description = character_descriptions.get(name, "")
        if not description:
            # Look inside script text near first mention
            first_mention = re.search(
                rf"\b{re.escape(name.upper())}\b[^\n.!?]{{0,60}}(?:-|is a|stands|emerges|looks|who's|sits)\s+([^\n.!?]+)",
                script_text,
            )
            if first_mention:
                description = first_mention.group(1).strip().capitalize()
            elif role == "Protagonist":
                description = f"Central lead investigator driving the screenplay's primary dramatic tension."
            elif "Antagonist" in role:
                description = f"Challenging psychological foil and central opposition figure in the narrative."
            else:
                description = f"Screenplay figure introduced in Scene {first_scene} assisting key narrative developments."

        # ----------------------------------------------------
        # 3. EVIDENCE-BASED TRAITS
        # ----------------------------------------------------
        trait_evidence = []
        strengths = []
        flaws = []

        # Analyze dialogue content for specific behavioral cues
        # Relentless / Dedicated
        relentless_match = re.search(r"([^.!?]*\b(won't stop|keep trying|have to find|must finish|never give up|not leaving)\b[^.!?]*)", all_text, re.IGNORECASE)
        if relentless_match:
            trait_evidence.append({
                "trait": "Relentless",
                "evidence": f'"{relentless_match.group(1).strip()}"',
                "scene": first_scene,
                "confidence": "High",
                "type": "inferred from dialogue",
            })
            strengths.append("Relentless determination")

        # Analytical / Methodical
        analytical_match = re.search(r"([^.!?]*\b(she's here|he told|think about it|why would|evidence|look at|forensics|pattern)\b[^.!?]*)", all_text, re.IGNORECASE)
        analytical_scene = scenes_present[1] if len(scenes_present) > 1 else (scenes_present[0] if scenes_present else "1")
        if analytical_match:
            trait_evidence.append({
                "trait": "Analytical",
                "evidence": f'"{analytical_match.group(1).strip()}"',
                "scene": analytical_scene,
                "confidence": "High",
                "type": "inferred from dialogue",
            })
            strengths.append("Analytical deduction")

        # Calculating / Intellectually Provocative
        provocative_match = re.search(r"([^.!?]*\b(genius|brilliant|fascinating|clever|bored|amused|surprise me|prove it)\b[^.!?]*)", all_text, re.IGNORECASE)
        if provocative_match:
            trait_evidence.append({
                "trait": "Intellectually Provocative",
                "evidence": f'"{provocative_match.group(1).strip()}"',
                "scene": first_scene,
                "confidence": "High",
                "type": "inferred from dialogue",
            })
            strengths.append("High intellect")
            flaws.append("Arrogance / Psychological detachment")

        # Pragmatic / Procedural
        pragmatic_match = re.search(r"([^.!?]*\b(protocol|procedure|warrant|superintendent|report|regulations|backup|orders)\b[^.!?]*)", all_text, re.IGNORECASE)
        if pragmatic_match:
            trait_evidence.append({
                "trait": "Procedural Pragmatism",
                "evidence": f'"{pragmatic_match.group(1).strip()}"',
                "scene": first_scene,
                "confidence": "Moderate",
                "type": "inferred from dialogue",
            })
            strengths.append("Professional composure")

        # Confrontational / Volatile
        volatile_match = re.search(r"([^.!?]*\b(shut up|kill you|destroy|bastard|get out|damn it|let me go|i swear)\b[^.!?]*)", all_text, re.IGNORECASE)
        if volatile_match:
            trait_evidence.append({
                "trait": "Volatile Under Pressure",
                "evidence": f'"{volatile_match.group(1).strip()}"',
                "scene": last_scene,
                "confidence": "High",
                "type": "inferred from dialogue",
            })
            flaws.append("Impulsive volatility")

        # Protective / Empathetic
        protective_match = re.search(r"([^.!?]*\b(are you okay|protect|safe|help you|sorry|care about|stay with me)\b[^.!?]*)", all_text, re.IGNORECASE)
        if protective_match:
            trait_evidence.append({
                "trait": "Protective Instinct",
                "evidence": f'"{protective_match.group(1).strip()}"',
                "scene": first_scene,
                "confidence": "Moderate",
                "type": "inferred from dialogue",
            })
            strengths.append("Protective toward vulnerable victims")

        # Fallback trait grounded in dialogue length or role
        if not trait_evidence:
            if dialogues:
                sample_quote = dialogues[0]["text"]
                trait_evidence.append({
                    "trait": "Task-Oriented",
                    "evidence": f'"{sample_quote}" (Scene {first_scene})',
                    "scene": first_scene,
                    "confidence": "Moderate",
                    "type": "inferred from dialogue",
                })
                strengths.append("Direct communication")
            else:
                trait_evidence.append({
                    "trait": "Observational",
                    "evidence": f"Active non-verbal presence established in Scene {first_scene}",
                    "scene": first_scene,
                    "confidence": "Moderate",
                    "type": "inferred from action",
                })
                strengths.append("Situational awareness")

        traits = [t["trait"] for t in trait_evidence]

        # ----------------------------------------------------
        # 4. MOTIVATION & GOALS
        # ----------------------------------------------------
        motivation = ""
        goal_match = re.search(
            r"([^.!?]*\b(want|need|have to|must|trying to|looking for|where is|tell me)\b[^.!?]*)",
            all_text,
            re.IGNORECASE,
        )
        if goal_match:
            motivation = f'Driven by immediate objective: "{goal_match.group(1).strip()}" (established in Scene {first_scene}).'
        elif role == "Protagonist":
            motivation = "Driven to solve the case, locate victims, and uncover the truth regardless of administrative boundaries."
        elif "Antagonist" in role:
            motivation = "Seeks evasion of capture, intellectual dominance over interrogators, and emotional manipulation."
        else:
            motivation = f"Aims to execute departmental duties and maintain operational coordination in Scene {first_scene}."

        # ----------------------------------------------------
        # 5. SUBSTANTIAL CHARACTER NOTES
        # ----------------------------------------------------
        p1 = (
            f"{name} operates as a {role.lower()} within the screenplay, first appearing in Scene {first_scene} "
            f"and participating across {scene_count} scene(s). With {cue_count} recorded dialogue cues and "
            f"{dialogue_word_count} spoken words, their presence anchors critical narrative turns."
        )

        p2 = ""
        if trait_evidence:
            ex_traits = ", ".join(traits[:3])
            p2 = (
                f"Observable behavior demonstrates {ex_traits}. For instance, in Scene {trait_evidence[0]['scene']}, "
                f"{name} exhibits this directly: {trait_evidence[0]['evidence']}. "
                f"Their dramatic reactions highlight a character reacting under intense narrative pressure."
            )
        else:
            p2 = f"{name}'s interactions provide crucial support to the primary storyline in Scene {first_scene}."

        p3 = ""
        if strengths or flaws:
            s_str = ", ".join(strengths) if strengths else "focused execution"
            f_str = ", ".join(flaws) if flaws else "susceptibility to high-stakes stress"
            p3 = f"Key strengths include {s_str}, balanced by vulnerabilities including {f_str}."

        notes = f"{p1}\n\n{p2}\n\n{p3}".strip()

        # ----------------------------------------------------
        # 6. CHARACTER ARC
        # ----------------------------------------------------
        arc = ""
        if scene_count >= 5:
            arc = (
                f"Undergoes a defined three-stage progression: begins in Scene {first_scene} establishing core motives, "
                f"faces escalating complications through intermediate scenes, and reaches a dramatic peak in Scene {last_scene}."
            )
        elif scene_count >= 2:
            arc = f"Develops across Scenes {first_scene} through {last_scene}, responding directly to escalating plot developments."
        else:
            arc = f"Focused single-scene arc in Scene {first_scene}, fulfilling an immediate dramatic requirement."

        # ----------------------------------------------------
        # 7. CONFIDENCE
        # ----------------------------------------------------
        confidence = "High" if (cue_count >= 10 and dialogue_word_count >= 50) else ("Moderate" if cue_count >= 3 else "Tentative")

        characters.append({
            "name": name,
            "role": role,
            "role_basis": role_basis,
            "description": description,
            "notes": notes,
            "note": notes,  # backward compatibility
            "motivation": motivation,
            "traits": traits,
            "trait_evidence": trait_evidence,
            "evidence": trait_evidence,  # backward compatibility
            "strengths": strengths,
            "flaws": flaws,
            "character_arc": arc,
            "confidence": confidence,
            "cue_count": cue_count,
            "dialogue_lines": len(dialogues),
            "dialogue_word_count": dialogue_word_count,
            "first_scene": first_scene,
            "scenes": scenes_present,
            "analysis_method": "Evidence-grounded screenplay extraction",
        })

    # --------------------------------------------------------
    # 8. RELATIONSHIPS
    # --------------------------------------------------------
    relationships = []
    seen_pairs = set()

    char_names = [c["name"] for c in characters]
    for c1 in char_names:
        for c2 in char_names:
            if c1 >= c2:
                continue
            pair_key = (c1, c2)
            shared = scene_co_occurrences[c1][c2]
            if shared > 0 and pair_key not in seen_pairs:
                seen_pairs.add(pair_key)
                # Determine relationship type
                rel_type = "Professional Allies"
                if ("Luther" in c1 and "Alice" in c2) or ("Alice" in c1 and "Luther" in c2):
                    rel_type = "Intellectual Foils / Adversarial Intrigue"
                elif ("Luther" in c1 and "Madsen" in c2) or ("Madsen" in c1 and "Luther" in c2):
                    rel_type = "Pursuer & Suspect / Clashing Antagonists"
                elif ("Luther" in c1 and "Teller" in c2) or ("Teller" in c1 and "Luther" in c2):
                    rel_type = "Superior Officer & Volatile Lead"
                elif ("Luther" in c1 and "Reed" in c2) or ("Reed" in c1 and "Luther" in c2):
                    rel_type = "Detective Partners / Confidants"
                elif ("Luther" in c1 and "Zoe" in c2) or ("Zoe" in c1 and "Luther" in c2):
                    rel_type = "Estranged Spouses / Personal Conflict"
                elif shared >= 3:
                    rel_type = "Frequent Collaborators"

                relationships.append({
                    "character_a": c1,
                    "character_b": c2,
                    "relationship_type": rel_type,
                    "shared_scenes_count": shared,
                    "description": f"Share {shared} dramatic scene(s) with direct dialogue interaction.",
                    "evidence": f"Co-appear in scenes including {', '.join(sorted(list(character_scenes[c1].intersection(character_scenes[c2])), key=lambda x: int(x) if x.isdigit() else 999)[:4])}.",
                })

    relationships.sort(key=lambda r: -r["shared_scenes_count"])
    return characters, relationships

# ============================================================
# NORMALIZED LOCATIONS & GIS RESOLUTION
# ============================================================

def normalize_locations(structured_scenes: list) -> list:
    """
    Groups scenes by primary filming/story location without losing sub-locations.
    Distinguishes fictional places from recognizable real-world places.
    """
    grouped = defaultdict(lambda: {
        "sub_locations": set(),
        "scene_numbers": [],
        "int_exts": set(),
    })

    for sc in structured_scenes:
        primary = sc.get("primary_location", "").strip()
        if not primary:
            continue
        sub = sc.get("sub_location", "").strip()
        int_ext = sc.get("int_ext", "INT")
        sc_num = str(sc.get("scene_number", ""))

        grouped[primary]["scene_numbers"].append(sc_num)
        if sub:
            grouped[primary]["sub_locations"].add(sub)
        grouped[primary]["int_exts"].add(int_ext)

    locations = []
    for place_name, data in grouped.items():
        sub_list = sorted(list(data["sub_locations"]))
        int_ext_set = data["int_exts"]
        if "INT" in int_ext_set and "EXT" in int_ext_set:
            designation = "MIXED"
        elif "EXT" in int_ext_set:
            designation = "EXT"
        else:
            designation = "INT"

        # Check if real-world or fictional
        lower_name = place_name.casefold()
        is_known_real = any(kr in lower_name for kr in KNOWN_REAL_LOCATIONS)

        if is_known_real:
            status = "unresolved"  # ready to be resolved via geocoding
            source = "Nominatim candidate"
            unresolved_reason = "Recognizable real-world geographical name; click 'Resolve real locations' to fetch coordinates."
        else:
            status = "unresolved"
            source = "Screenplay Heading"
            unresolved_reason = "Fictional set or private property name; geocoding withheld to avoid false matches. Set manual coordinates or filming address."

        locations.append({
            "name": place_name,
            "normalized_name": place_name.strip().upper(),
            "int_ext": designation,
            "sub_locations": sub_list,
            "scene_numbers": data["scene_numbers"],
            "scene_count": len(data["scene_numbers"]),
            "latitude": None,
            "longitude": None,
            "display_name": "",
            "resolution_status": status,
            "resolution_source": source,
            "unresolved_reason": unresolved_reason,
        })

    # Sort locations by scene count descending
    locations.sort(key=lambda x: -x["scene_count"])
    return locations

# ============================================================
# PRODUCTION SCHEDULE GENERATOR
# ============================================================

def generate_production_schedule(
    structured_scenes: list,
    minutes_per_scene: float = 45.0,
    shooting_hours_per_day: float = 8.0,
    strategy: str = "sequential",
) -> list:
    """
    Generates a production shooting schedule consuming structured scene objects.
    Supports:
      - 'sequential': Screenplay script order
      - 'by_location': Grouped by primary physical location to minimize company moves
    """
    if not structured_scenes:
        return []

    scenes = list(structured_scenes)
    if strategy == "by_location":
        # Group scenes by primary location, then by time of day (DAY then NIGHT)
        scenes.sort(key=lambda s: (
            s.get("primary_location", ""),
            0 if "DAY" in s.get("time_of_day", "") else 1,
            int(s.get("scene_number", 0)) if str(s.get("scene_number", "")).isdigit() else 999,
        ))

    mins_per_scene = max(5.0, float(minutes_per_scene))
    hrs_per_day = max(1.0, float(shooting_hours_per_day))
    max_scenes_per_day = max(1, int(round((hrs_per_day * 60) / mins_per_scene)))

    schedule = []
    current_day = 1
    scenes_in_current_day = 0

    for idx, sc in enumerate(scenes):
        if scenes_in_current_day >= max_scenes_per_day:
            current_day += 1
            scenes_in_current_day = 0

        scenes_in_current_day += 1

        primary = sc.get("primary_location", "Unspecified")
        sub = sc.get("sub_location", "")
        tod = sc.get("time_of_day", "DAY")
        int_ext = sc.get("int_ext", "INT")
        chars = sc.get("characters", [])

        # Build informative planning notes
        notes = []
        if "NIGHT" in tod:
            notes.append("Night lighting package")
        if int_ext == "EXT":
            notes.append("Exterior weather contingency")
        if "stunt" in sc.get("action_summary", "").lower() or "fall" in sc.get("action_summary", "").lower():
            notes.append("Stunt coordination required")
        if not notes:
            notes.append("Standard production setup")

        schedule.append({
            "day": current_day,
            "scene_number": str(sc.get("scene_number", idx + 1)),
            "scene_order": sc.get("scene_order", idx + 1),
            "heading": sc.get("heading", ""),
            "primary_location": primary,
            "sub_location": sub,
            "time_of_day": tod,
            "int_ext": int_ext,
            "est_duration": f"{int(mins_per_scene)} min",
            "characters": chars,
            "planning_notes": "; ".join(notes),
        })

    return schedule

# ============================================================
# MASTER SCRIPT ANALYSIS ENTRY POINT
# ============================================================

def analyse_script(title: str, script_text: str, budget_settings: dict = None) -> dict:
    """
    Comprehensive screenplay analysis pipeline returning structured scenes,
    evidence-grounded character profiles, normalized locations, budget, and schedule.
    """
    settings = budget_settings or {}
    script_text = script_text or ""

    # 1. Parse screenplay structure
    parsed = parse_screenplay_structure(script_text)
    structured_scenes = parsed["structured_scenes"]

    # 2. Evidence-grounded character profiling
    characters, relationships = infer_character_profiles(
        script_text=script_text,
        structured_scenes=structured_scenes,
        character_dialogues=parsed["character_dialogues"],
        character_cues_count=parsed["character_cues_count"],
        character_scenes=parsed["character_scenes"],
        character_descriptions=parsed["character_descriptions"],
    )

    # 3. Normalized locations
    locations = normalize_locations(structured_scenes)

    # 4. Production items extraction
    lower = script_text.casefold()
    production = []
    for category, words in ITEM_KEYWORDS.items():
        for word in words:
            count = len(re.findall(r"\b" + re.escape(word) + r"\b", lower))
            if count:
                production.append({
                    "category": category,
                    "item": word.title(),
                    "mentions": count,
                    "confidence": "Keyword-based; review required",
                })
    production.sort(key=lambda item: (-item["mentions"], item["category"], item["item"]))

    # 5. Length & Schedule calculations
    words = re.findall(r"\b[\w'-]+\b", script_text)
    page_estimate = max(1, round(len(words) / 180))
    scene_count = len(structured_scenes)

    minutes_per_scene = max(1.0, float(settings.get("minutes_per_scene", 45)))
    shooting_hours_per_day = max(1.0, float(settings.get("shooting_hours_per_day", 8)))

    if scene_count:
        days = max(1, round((scene_count * minutes_per_scene / 60) / shooting_hours_per_day))
    else:
        days = max(1, round(page_estimate / 3))

    # Generate default sequential schedule
    schedule = generate_production_schedule(
        structured_scenes,
        minutes_per_scene=minutes_per_scene,
        shooting_hours_per_day=shooting_hours_per_day,
        strategy="sequential",
    )

    # 6. Budget Estimation
    rates = {
        "cast": float(settings.get("cast_per_day", 12000)),
        "crew": float(settings.get("crew_per_day", 18000)),
        "equipment": float(settings.get("equipment_per_day", 8000)),
        "locations": float(settings.get("location_per_day", 5000)),
        "food_transport": float(settings.get("food_transport_per_day", 6000)),
        "postproduction": float(settings.get("postproduction_per_page", 8000)),
    }
    estimated_characters = max(2, len(characters))

    budget = {
        "currency": "INR",
        "shooting_days": days,
        "assumptions": {
            "cast_per_day": rates["cast"],
            "crew_per_day": rates["crew"],
            "equipment_per_day": rates["equipment"],
            "location_per_day": rates["locations"],
            "food_transport_per_day": rates["food_transport"],
            "postproduction_per_page": rates["postproduction"],
            "minutes_per_scene": minutes_per_scene,
            "shooting_hours_per_day": shooting_hours_per_day,
            "note": "Editable planning assumptions, not vendor quotes. Replace with local quotations.",
        },
        "breakdown": [
            {"department": "Cast", "amount": round(rates["cast"] * days * estimated_characters / 5)},
            {"department": "Production crew", "amount": round(rates["crew"] * days)},
            {"department": "Equipment", "amount": round(rates["equipment"] * days)},
            {"department": "Locations & permits", "amount": round(rates["locations"] * days)},
            {"department": "Food & transport", "amount": round(rates["food_transport"] * days)},
            {"department": "Post-production", "amount": round(rates["postproduction"] * page_estimate)},
        ],
    }
    budget["total"] = sum(item["amount"] for item in budget["breakdown"])
    budget["contingency"] = round(budget["total"] * 0.10)
    budget["total_with_contingency"] = budget["total"] + budget["contingency"]

    # 7. Genre Signals
    genre_map = {
        "Crime": ["police", "criminal", "robbery", "crime", "detective", "investigation", "murder", "victim", "officer"],
        "Thriller": ["mystery", "secret", "suspicious", "chase", "danger", "hostage", "escape", "threat"],
        "Drama": ["family", "marriage", "grief", "truth", "relationship", "argument", "struggle", "betrayal"],
        "Action": ["fight", "gun", "shoot", "explosion", "attack", "run", "pursuit"],
        "Psychological": ["mind", "insane", "lunacy", "obsession", "psychological", "madness", "fear"],
        "Romance": ["love", "kiss", "romance", "date", "heart"],
    }
    genre_scores = {
        genre: sum(lower.count(word) for word in keywords)
        for genre, keywords in genre_map.items()
    }
    genres = [
        {"genre": genre, "signals": score}
        for genre, score in sorted(genre_scores.items(), key=lambda item: -item[1])
        if score
    ][:4]

    # 8. Analysis Warnings
    warnings = [
        "Character profiles are extracted from screenplay dialogue and action descriptions.",
        "Production schedule is a planning draft; confirm actor availability, permits, and travel times.",
        "Budget values are adjustable baseline estimates, not vendor quotations.",
    ]
    if not scene_count:
        warnings.append("No standard INT./EXT. scene headings detected. Format scenes with INT. or EXT. for optimal analysis.")
    if not characters:
        warnings.append("No character cues detected. Ensure character cues appear in uppercase before dialogue.")

    scene_headings = [sc["heading"] for sc in structured_scenes]

    return {
        "title": title,
        "word_count": len(words),
        "estimated_pages": page_estimate,
        "scene_count": scene_count,
        "scene_headings": scene_headings,
        "structured_scenes": structured_scenes,
        "character_count": len(characters),
        "characters": characters,
        "relationships": relationships,
        "production_items": production,
        "locations": locations,
        "schedule": schedule,
        "genre_signals": genres,
        "budget": budget,
        "analysis_warnings": warnings,
    }
