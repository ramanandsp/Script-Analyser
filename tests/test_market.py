import pytest
from unittest.mock import patch, MagicMock
from app.services import (
    _parse_omdb_movie,
    get_market_movies,
    get_comparable_candidates,
    generate_comparative_market_report,
)

def test_parse_omdb_movie_missing_values():
    raw_movie = {
        "Title": "Test Film",
        "Year": "2022",
        "imdbID": "tt1234567",
        "Poster": "N/A",
        "BoxOffice": "N/A",
        "imdbRating": "N/A",
        "imdbVotes": "N/A",
        "Ratings": [],
        "Genre": "Crime, Thriller",
        "Plot": "N/A",
    }
    parsed = _parse_omdb_movie(raw_movie)
    assert parsed["title"] == "Test Film"
    assert parsed["box_office"] == "Not reported"
    assert parsed["imdb_rating"] == "Not reported"
    assert parsed["imdb_votes"] == "Not reported"
    assert parsed["rotten_tomatoes"] == "Not reported"
    assert parsed["poster_path"] is None
    # Missing box office must NEVER be 0
    assert parsed["box_office"] != 0
    assert parsed["box_office"] != "$0"

def test_parse_omdb_movie_populated_values():
    raw_movie = {
        "Title": "Se7en",
        "Year": "1995",
        "imdbID": "tt0114369",
        "Poster": "https://m.media-amazon.com/poster.jpg",
        "BoxOffice": "$100,125,643",
        "imdbRating": "8.6",
        "imdbVotes": "1,800,000",
        "Ratings": [{"Source": "Rotten Tomatoes", "Value": "83%"}],
        "Genre": "Crime, Drama, Mystery",
        "Director": "David Fincher",
        "Plot": "Two detectives hunt a serial killer who uses the seven deadly sins.",
    }
    parsed = _parse_omdb_movie(raw_movie)
    assert parsed["title"] == "Se7en"
    assert parsed["box_office"] == "$100,125,643"
    assert parsed["imdb_rating"] == "8.6/10"
    assert parsed["rotten_tomatoes"] == "83%"
    assert parsed["director"] == "David Fincher"

def test_generate_comparative_market_report():
    comp_movies = [
        {
            "title": "Se7en",
            "year": "1995",
            "director": "David Fincher",
            "imdb_rating": "8.6/10",
            "imdb_votes": "1,800,000",
            "rotten_tomatoes": "83%",
            "metascore": "65",
            "box_office": "$100,125,643",
        },
        {
            "title": "Zodiac",
            "year": "2007",
            "director": "David Fincher",
            "imdb_rating": "7.7/10",
            "imdb_votes": "600,000",
            "rotten_tomatoes": "89%",
            "metascore": "78",
            "box_office": "$33,080,084",
        },
    ]
    report = generate_comparative_market_report("Luther", ["Crime", "Thriller"], comp_movies)
    assert report["project_title"] == "Luther"
    assert report["comp_films_count"] == 2
    assert "sections" in report
    s = report["sections"]
    # Verify all 9 sections exist and are populated
    assert "comparison_rationale" in s and len(s["comparison_rationale"]) > 0
    assert "thematic_premise_alignment" in s and len(s["thematic_premise_alignment"]) > 0
    assert "audience_reception" in s and len(s["audience_reception"]) > 0
    assert "commercial_box_office" in s and len(s["commercial_box_office"]) > 0
    assert "data_limitations" in s and len(s["data_limitations"]) > 0
    assert "target_audience_positioning" in s and len(s["target_audience_positioning"]) > 0
    assert "differentiators" in s and len(s["differentiators"]) > 0
    assert "risks_and_uncertainties" in s and len(s["risks_and_uncertainties"]) > 0
    assert "strategic_recommendations" in s and len(s["strategic_recommendations"]) > 0

@patch("requests.get")
def test_market_movies_unconfigured_key(mock_get, monkeypatch):
    monkeypatch.setenv("OMDB_API_KEY", "")
    res = get_market_movies("Inception")
    assert res["configured"] is False
    assert "missing" in res["message"].lower()

@patch("requests.get")
def test_market_movies_search_api_key_hidden(mock_get, monkeypatch):
    monkeypatch.setenv("OMDB_API_KEY", "secret_key_12345")
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {
        "Response": "True",
        "Search": [{"Title": "Heat", "Year": "1995", "imdbID": "tt0113277", "Poster": "N/A"}],
        "totalResults": "1",
    }
    mock_get.return_value = mock_resp

    res = get_market_movies("Heat")
    assert res["configured"] is True
    # Secret key must NEVER appear in the returned dictionary
    res_str = str(res)
    assert "secret_key_12345" not in res_str
