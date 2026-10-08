from types import SimpleNamespace

from stadium_atlas import titles


def fake_get(payload, status=200):
    return lambda url, params=None, timeout=None: SimpleNamespace(status_code=status, json=lambda: payload)


def game(date, home, away, home_wins):
    return {"gameDate": f"{date}T00:00:00Z", "officialDate": date,
            "teams": {"home": {"team": {"name": home}, "isWinner": home_wins},
                      "away": {"team": {"name": away}, "isWinner": not home_wins}}}


def test_winner_is_taken_from_the_last_game(monkeypatch):
    payload = {"dates": [{"games": [game("2012-10-24", "San Francisco Giants", "Detroit Tigers", True)]},
                         {"games": [game("2012-10-28", "Detroit Tigers", "San Francisco Giants", False)]}]}
    monkeypatch.setattr(titles.requests, "get", fake_get(payload))
    assert titles.world_series_winner(2012) == ("San Francisco Giants", "2012-10")


def test_no_games_means_no_winner(monkeypatch):
    monkeypatch.setattr(titles.requests, "get", fake_get({"dates": []}))
    assert titles.world_series_winner(1994) is None


def test_export_maps_titles_to_the_venue_of_the_winning_team(monkeypatch, tmp_path):
    winners = {2010: ("San Francisco Giants", "2010-11"), 2011: ("St. Louis Cardinals", "2011-10"), 2012: None}
    monkeypatch.setattr(titles, "world_series_winner", lambda s: winners.get(s))
    out = titles.export_titles(str(tmp_path), first=2010, last=2012)
    assert out["titles"]["oracle-park"] == ["2010-11"]
    assert out["titles"]["busch-stadium"] == ["2011-10"]
    assert out["titles"]["petco-park"] == [] and out["seasons_found"] == 2
