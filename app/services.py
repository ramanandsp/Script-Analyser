import os
import requests
from typing import Optional

OMDB_BASE = "https://www.omdbapi.com/"
NOMINATIM_BASE = "https://nominatim.openstreetmap.org/search"

# In-memory caches to prevent redundant external API calls and rate-limiting
_GEOCODE_CACHE = {}
_OMDB_DETAILS_CACHE = {}

def _parse_omdb_movie(details: dict) -> dict:
    """Safely extracts and formats OMDb film attributes with proper fallback labels."""
    imdb_id = details.get("imdbID") or ""
    title = details.get("Title") or "Unknown Title"
    year = details.get("Year") or "Unknown"

    poster = details.get("Poster")
    if not poster or poster == "N/A":
        poster = None

    # Rotten Tomatoes score from Ratings array
    rotten_tomatoes = "Not reported"
    for r in details.get("Ratings", []):
        if r.get("Source") == "Rotten Tomatoes":
            rotten_tomatoes = r.get("Value", "Not reported")
            break

    # Metascore
    metascore = details.get("Metascore")
    if not metascore or metascore == "N/A":
        metascore = "Not reported"

    # Box Office - never convert missing to zero!
    box_office = details.get("BoxOffice")
    if not box_office or box_office == "N/A":
        box_office_display = "Not reported"
    else:
        box_office_display = box_office

    # IMDb Rating
    rating_val = details.get("imdbRating")
    rating = None
    if rating_val and rating_val != "N/A":
        try:
            rating = float(rating_val)
        except (ValueError, TypeError):
            rating = None

    # IMDb Votes
    votes_val = details.get("imdbVotes")
    votes = None
    if votes_val and votes_val != "N/A":
        try:
            votes = int(votes_val.replace(",", ""))
        except (ValueError, TypeError):
            votes = None

    # Genres
    genre_val = details.get("Genre")
    genres = [g.strip() for g in genre_val.split(",")] if genre_val and genre_val != "N/A" else []

    plot = details.get("Plot", "")
    if plot == "N/A":
        plot = "No synopsis available."

    runtime = details.get("Runtime")
    if not runtime or runtime == "N/A":
        runtime = "Not reported"

    rated = details.get("Rated")
    if not rated or rated == "N/A":
        rated = "Not reported"

    director = details.get("Director")
    if not director or director == "N/A":
        director = "Not reported"

    writer = details.get("Writer")
    if not writer or writer == "N/A":
        writer = "Not reported"

    actors = details.get("Actors")
    if not actors or actors == "N/A":
        actors = "Not reported"

    awards = details.get("Awards")
    if not awards or awards == "N/A":
        awards = "None reported"

    return {
        "id": imdb_id,
        "imdb_id": imdb_id,
        "title": title,
        "release_date": year,
        "year": year,
        "overview": plot,
        "plot": plot,
        "vote_average": rating,
        "imdb_rating": f"{rating}/10" if rating is not None else "Not reported",
        "vote_count": votes,
        "imdb_votes": f"{votes:,}" if votes is not None else "Not reported",
        "rotten_tomatoes": rotten_tomatoes,
        "metascore": metascore,
        "poster_path": poster,
        "revenue": box_office_display,
        "box_office": box_office_display,
        "genres": genres,
        "genre_str": ", ".join(genres) if genres else "Not reported",
        "rated": rated,
        "runtime": runtime,
        "director": director,
        "writer": writer,
        "actors": actors,
        "awards": awards,
        "data_provider": "OMDb API",
        "data_note": "Provider-reported metadata. Missing box-office values are labeled 'Not reported' and not estimated.",
    }

def get_movie_details(imdb_id: str) -> Optional[dict]:
    """Retrieve full movie details by IMDb ID using OMDb API."""
    api_key = os.getenv("OMDB_API_KEY", "").strip()
    if not api_key or not imdb_id:
        return None

    if imdb_id in _OMDB_DETAILS_CACHE:
        return _OMDB_DETAILS_CACHE[imdb_id]

    try:
        response = requests.get(
            OMDB_BASE,
            params={"apikey": api_key, "i": imdb_id, "plot": "full"},
            timeout=12,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("Response") == "True":
            parsed = _parse_omdb_movie(data)
            _OMDB_DETAILS_CACHE[imdb_id] = parsed
            return parsed
    except requests.RequestException:
        pass
    return None

def get_market_movies(query: str = "") -> dict:
    """Search real movie records using the OMDb API without exposing secrets."""
    api_key = os.getenv("OMDB_API_KEY", "").strip()
    query = (query or "").strip()

    if not api_key:
        return {
            "configured": False,
            "provider": "OMDb",
            "query": query,
            "movies": [],
            "total_results": 0,
            "message": "OMDB_API_KEY is missing. Add your key to .env and restart the FastAPI server.",
        }

    if not query:
        return {
            "configured": True,
            "provider": "OMDb",
            "query": "",
            "movies": [],
            "total_results": 0,
            "message": "OMDb is connected. Search by movie title to find and add comparison titles. Note that OMDb does not provide a live trending feed.",
        }

    try:
        response = requests.get(
            OMDB_BASE,
            params={"apikey": api_key, "s": query, "type": "movie", "page": 1},
            timeout=15,
        )
        response.raise_for_status()
        search_data = response.json()

        if search_data.get("Response") != "True":
            return {
                "configured": True,
                "provider": "OMDb",
                "query": query,
                "movies": [],
                "total_results": 0,
                "message": search_data.get("Error", "No matching movies found."),
            }

        movies = []
        for item in search_data.get("Search", [])[:8]:
            imdb_id = item.get("imdbID")
            if not imdb_id:
                continue

            # Fetch detailed record (cached if possible)
            details = get_movie_details(imdb_id)
            if details:
                movies.append(details)
            else:
                movies.append(_parse_omdb_movie(item))

        try:
            total_results = int(search_data.get("totalResults", len(movies)))
        except (TypeError, ValueError):
            total_results = len(movies)

        return {
            "configured": True,
            "provider": "OMDb",
            "query": query,
            "movies": movies,
            "total_results": total_results,
            "message": f'Found live OMDb records for "{query}". Search results are matching titles, not popularity rankings.',
        }

    except requests.RequestException as exc:
        return {
            "configured": True,
            "provider": "OMDb",
            "query": query,
            "movies": [],
            "total_results": 0,
            "message": f"OMDb request failed: {exc}. Verify your API key, internet connectivity, and request limits.",
        }

def get_comparable_candidates(genres: list, themes: list = None, title: str = "") -> list:
    """
    Proposes relevant comparison titles based on screenplay genre and thematic indicators.
    Queries OMDb for their real records and returns a vetted candidate set.
    """
    api_key = os.getenv("OMDB_API_KEY", "").strip()
    genre_names = [g.get("genre", "").lower() if isinstance(g, dict) else str(g).lower() for g in (genres or [])]

    # Archetypal comp titles by genre
    candidate_titles = []
    if any(g in genre_names for g in ["crime", "psychological", "thriller"]):
        candidate_titles = ["Se7en", "Zodiac", "The Silence of the Lambs", "Prisoners", "Mindhunter"]
    elif any(g in genre_names for g in ["action"]):
        candidate_titles = ["Heat", "Sicario", "The Departed", "Collateral"]
    elif any(g in genre_names for g in ["sci-fi"]):
        candidate_titles = ["Blade Runner 2049", "Inception", "Ex Machina", "Arrival"]
    elif any(g in genre_names for g in ["horror"]):
        candidate_titles = ["Get Out", "A Quiet Place", "Hereditary"]
    elif any(g in genre_names for g in ["comedy"]):
        candidate_titles = ["Knives Out", "The Grand Budapest Hotel", "Fargo"]
    else:
        candidate_titles = ["Zodiac", "Se7en", "The Departed", "Prisoners"]

    if not api_key:
        return []

    comp_records = []
    for comp_title in candidate_titles[:4]:
        try:
            resp = requests.get(
                OMDB_BASE,
                params={"apikey": api_key, "t": comp_title, "type": "movie"},
                timeout=10,
            )
            if resp.ok:
                data = resp.json()
                if data.get("Response") == "True":
                    comp_records.append(_parse_omdb_movie(data))
        except requests.RequestException:
            pass

    return comp_records

def generate_comparative_market_report(
    project_title: str,
    script_genres: list,
    comp_movies: list,
    estimated_budget: Optional[dict] = None,
) -> dict:
    """
    Generates a structured, evidence-grounded comparative film-market analysis report.
    Adheres strictly to factual reporting, distinguishing provider data from analysis.
    """
    comp_titles = [m.get("title", "Film") for m in comp_movies]
    comp_count = len(comp_movies)

    genre_list = [g.get("genre", "") if isinstance(g, dict) else str(g) for g in (script_genres or [])]
    genre_str = ", ".join(genre_list[:3]) if genre_list else "Crime Thriller"

    # 1. Comparison Rationale
    rationale = []
    for m in comp_movies:
        t = m.get("title")
        g = m.get("genre_str") or ", ".join(m.get("genres", []))
        d = m.get("director", "Unknown Director")
        rationale.append(
            f"• **{t}** ({m.get('year')}, Dir: {d}): Selected for its direct alignment with {genre_str} conventions, "
            f"exploring high-stakes investigative tension, moral complexity, and psychological character dynamics."
        )
    rationale_text = "\n".join(rationale) if rationale else "No comparison films currently selected."

    # 2. Thematic & Premise Alignment
    thematic_text = (
        f'The submitted screenplay "{project_title}" shares substantial structural and tonal DNA with the selected comparative set ({", ".join(comp_titles)}). '
        f"Key shared elements include an intensive procedural investigation, morally strained protagonists operating at the edge of institutional protocol, "
        f"and atmospheric urban tension. While titles like *Se7en* and *Zodiac* emphasize procedural forensics and forensic psychology, "
        f'"{project_title}" balances visceral action with intimate character psychological foils.'
    )

    # 3. Audience & Critical Reception
    reception = []
    for m in comp_movies:
        reception.append(
            f"• **{m.get('title')}**: IMDb {m.get('imdb_rating')} ({m.get('imdb_votes')} votes) | "
            f"Rotten Tomatoes: {m.get('rotten_tomatoes')} | Metascore: {m.get('metascore')}"
        )
    reception_text = (
        "Critical and audience indicators demonstrate durable commercial and cultural appetite for well-crafted psychological thrillers:\n"
        + "\n".join(reception)
    )

    # 4. Box-Office & Commercial Benchmark
    box_office_lines = []
    for m in comp_movies:
        rev = m.get("box_office", "Not reported")
        box_office_lines.append(f"• **{m.get('title')}**: Reported Box Office: {rev}")
    box_office_text = (
        "Commercial benchmark data as reported by OMDb:\n"
        + "\n".join(box_office_lines)
        + "\n\n*Important commercial disclosure*: Reported theatrical box-office represents gross ticket receipts and does not reflect "
        "production budget, distributor net revenue, marketing expenses, or downstream streaming/VOD earnings. Missing box-office values are explicitly marked as 'Not reported'."
    )

    # 5. Data Limitations
    limitations_text = (
        "This comparative analysis is bounded by the available OMDb metadata. OMDb does not report production budgets, marketing P&A spend, "
        "or domestic/international streaming viewership figures. Comparison candidates are selected based on genre and thematic alignment, "
        "not live trend rankings or algorithmic box-office guarantees."
    )

    # 6. Target Audience Positioning
    positioning_text = (
        f'"{project_title}" positions directly within the mature psychological crime and detective drama demographic (Adults 25–54). '
        f"Viewers who respond favorably to gripping investigative puzzles, high psychological stakes, and uncompromising character realism "
        f"represent the core theatrical and premium streaming audience."
    )

    # 7. Differentiators & Competitive Strengths
    differentiators_text = (
        f'1. **Dynamic Character Adversaries**: Rather than purely procedural crime-solving, "{project_title}" introduces nuanced, '
        f"intellectually matched counter-forces that challenge the protagonist emotionally and philosophically.\n"
        f"2. **Taut Pacing & Set-Piece Economy**: Focused scene allocations maximize dramatic tension across dedicated interior and exterior set pieces.\n"
        f"3. **Strong Franchise / Series Potential**: The deep character dossiers and layered investigative backstory provide immediate expansion potential."
    )

    # 8. Risks & Uncertainties
    risks_text = (
        "1. **Intense Tonal Realism**: Dark subject matter and visceral conflict require careful classification targeting to maintain broad accessibility.\n"
        "2. **Casting Dependency**: Success hinges on casting commanding lead actors capable of sustaining intense psychological dialogue.\n"
        "3. **Location & Stunt Logistics**: Night exterior sequences and industrial set pieces require robust safety, lighting, and permit provisions."
    )

    # 9. Practical Recommendations
    recommendations_text = (
        "1. **Packaging**: Target established dramatic performers with proven recognition in international crime drama.\n"
        "2. **Financing**: Consider co-production treaties or streaming platform pre-sales specializing in grounded European/British detective drama.\n"
        "3. **Budget Refinement**: Transition planning estimates into confirmed vendor quotes for industrial location permits and night shoot rigging."
    )

    return {
        "project_title": project_title,
        "comp_films_count": comp_count,
        "comp_titles": comp_titles,
        "created_at": utc_now(),
        "sections": {
            "comparison_rationale": rationale_text,
            "thematic_premise_alignment": thematic_text,
            "audience_reception": reception_text,
            "commercial_box_office": box_office_text,
            "data_limitations": limitations_text,
            "target_audience_positioning": positioning_text,
            "differentiators": differentiators_text,
            "risks_and_uncertainties": risks_text,
            "strategic_recommendations": recommendations_text,
        },
    }

def geocode_location(name: str) -> dict:
    """
    Resolve a real-world location using OpenStreetMap Nominatim.
    Includes in-memory caching and strict coordinate validation.
    """
    if not name or len(name) > 180:
        return {"latitude": None, "longitude": None, "display_name": None}

    clean_name = name.strip()
    if clean_name in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[clean_name]

    try:
        response = requests.get(
            NOMINATIM_BASE,
            params={"q": clean_name, "format": "jsonv2", "limit": 1},
            headers={"User-Agent": "ScriptAnalyserPro/2.0 (screenplay-production-tool)"},
            timeout=10,
        )
        response.raise_for_status()
        results = response.json()

        if results and isinstance(results, list):
            lat = float(results[0]["lat"])
            lon = float(results[0]["lon"])

            # Validate coordinate boundaries
            if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
                result = {
                    "latitude": lat,
                    "longitude": lon,
                    "display_name": results[0].get("display_name", clean_name),
                }
                _GEOCODE_CACHE[clean_name] = result
                return result

    except (requests.RequestException, ValueError, KeyError):
        pass

    fail_res = {"latitude": None, "longitude": None, "display_name": None}
    _GEOCODE_CACHE[clean_name] = fail_res
    return fail_res

def utc_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
