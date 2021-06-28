import math
import os
import asyncio

import json
import re

import gspread
from gspread_formatting import *

from discord.ext import commands

from watcher import utils, checks

"""New season checklist:
    Make sure divisions are up to date 
    Make sure weather types are up to date
    Make sure all team spreadsheet tabs exists
    Make sure all teams are added to name mapping
    Update divisions in generate_per_team_records
    Maybe just automate the update of as much of this as possible
"""

spreadsheet_names_old = {
    'adc5b394-8f76-416d-9ce9-813706877b84': {'schedule': 'Mints Schedule', 'matchups': 'Mints Matchups'},
    '8d87c468-699a-47a8-b40d-cfb73a5660ad': {'schedule': 'Crabs Schedule', 'matchups': 'Crabs Matchups'},
    'b63be8c2-576a-4d6e-8daf-814f8bcea96f': {'schedule': 'Dale Schedule', 'matchups': 'Dale Matchups'},
    'ca3f1c8c-c025-4d8e-8eef-5be6accbeb16': {'schedule': 'Firefighters Schedule', 'matchups': 'Firefighters Matchups'},
    '3f8bbb15-61c0-4e3f-8e4a-907a5fb1565e': {'schedule': 'Flowers Schedule', 'matchups': 'Flowers Matchups'},
    '979aee4a-6d80-4863-bf1c-ee1a78e06024': {'schedule': 'Fridays Schedule', 'matchups': 'Fridays Matchups'},
    '105bc3ff-1320-4e37-8ef0-8d595cb95dd0': {'schedule': 'Garages Schedule', 'matchups': 'Garages Matchups'},
    'a37f9158-7f82-46bc-908c-c9e2dda7c33b': {'schedule': 'Hands Schedule', 'matchups': 'Hands Matchups'},
    'c73b705c-40ad-4633-a6ed-d357ee2e2bcf': {'schedule': 'Lift Schedule', 'matchups': 'Lift Matchups'},
    'b72f3061-f573-40d7-832a-5ad475bd7909': {'schedule': 'Lovers Schedule', 'matchups': 'Lovers Matchups'},
    '7966eb04-efcc-499b-8f03-d13916330531': {'schedule': 'Magic Schedule', 'matchups': 'Magic Matchups'},
    '36569151-a2fb-43c1-9df7-2df512424c82': {'schedule': 'Millennials Schedule', 'matchups': 'Millenials Matchups'},
    'eb67ae5e-c4bf-46ca-bbbc-425cd34182ff': {'schedule': 'Talkers Schedule', 'matchups': 'Talkers Matchups'},
    '23e4cbc1-e9cd-47fa-a35b-bfa06f726cb7': {'schedule': 'Pies Schedule', 'matchups': 'Pies Matchups'},
    'bfd38797-8404-4b38-8b82-341da28b1f83': {'schedule': 'Shoe Schedule', 'matchups': 'Shoes Matchups'},
    '9debc64f-74b7-4ae1-a4d6-fce0144b6ea5': {'schedule': 'Spies Schedule', 'matchups': 'Spies Matchups'},
    'b024e975-1c4a-4575-8936-a3754a08806a': {'schedule': 'Steaks Schedule', 'matchups': 'Steaks Matchups'},
    'f02aeae2-5e6a-4098-9842-02d2273f25c7': {'schedule': 'Sunbeams Schedule', 'matchups': 'Sunbeams Matchups'},
    '878c1bf6-0d21-4659-bfee-916c8314d69c': {'schedule': 'Tacos Schedule', 'matchups': 'Tacos Matchups'},
    '747b8e4a-7e50-4638-a973-ea7950a3e739': {'schedule': 'Tigers Schedule', 'matchups': 'Tigers Matchups'},
    'd9f89a8a-c563-493e-9d64-78e4f9a55d4a': {'schedule': 'Georgias Schedule', 'matchups': 'Georgias Matchups'},
    'bb4a9de5-c924-4923-a0cb-9d1445f1ee5d': {'schedule': 'Worms Schedule', 'matchups': 'Worms Matchups'},
    '46358869-dce9-4a01-bfba-ac24fc56f57e': {'schedule': 'Mechanics Schedule', 'matchups': 'Mechanics Matchups'},
    '57ec08cc-0411-4643-b304-0e80dbc15ac7': {'schedule': 'Wings Schedule', 'matchups': 'Wings Matchups'}
}

spreadsheet_names = {
    'adc5b394-8f76-416d-9ce9-813706877b84': {'schedule': 'Mints Sched', 'matchups': 'Mints M/U'},
    '8d87c468-699a-47a8-b40d-cfb73a5660ad': {'schedule': 'Crabs Sched', 'matchups': 'Crabs M/U'},
    'b63be8c2-576a-4d6e-8daf-814f8bcea96f': {'schedule': 'Dale Sched', 'matchups': 'Dale M/U'},
    'ca3f1c8c-c025-4d8e-8eef-5be6accbeb16': {'schedule': 'Firefighters Sched', 'matchups': 'Firefighters M/U'},
    '3f8bbb15-61c0-4e3f-8e4a-907a5fb1565e': {'schedule': 'Flowers Sched', 'matchups': 'Flowers M/U'},
    '979aee4a-6d80-4863-bf1c-ee1a78e06024': {'schedule': 'Fridays Sched', 'matchups': 'Fridays M/U'},
    '105bc3ff-1320-4e37-8ef0-8d595cb95dd0': {'schedule': 'Garages Sched', 'matchups': 'Garages M/U'},
    'a37f9158-7f82-46bc-908c-c9e2dda7c33b': {'schedule': 'Hands Sched', 'matchups': 'Hands M/U'},
    'c73b705c-40ad-4633-a6ed-d357ee2e2bcf': {'schedule': 'Lift Sched', 'matchups': 'Lift M/U'},
    'b72f3061-f573-40d7-832a-5ad475bd7909': {'schedule': 'Lovers Sched', 'matchups': 'Lovers M/U'},
    '7966eb04-efcc-499b-8f03-d13916330531': {'schedule': 'Magic Sched', 'matchups': 'Magic M/U'},
    '36569151-a2fb-43c1-9df7-2df512424c82': {'schedule': 'Millennials Sched', 'matchups': 'Millenials M/U'},
    'eb67ae5e-c4bf-46ca-bbbc-425cd34182ff': {'schedule': 'Talkers Sched', 'matchups': 'Talkers M/U'},
    '23e4cbc1-e9cd-47fa-a35b-bfa06f726cb7': {'schedule': 'Pies Sched', 'matchups': 'Pies M/U'},
    'bfd38797-8404-4b38-8b82-341da28b1f83': {'schedule': 'Shoe Sched', 'matchups': 'Shoes M/U'},
    '9debc64f-74b7-4ae1-a4d6-fce0144b6ea5': {'schedule': 'Spies Sched', 'matchups': 'Spies M/U'},
    'b024e975-1c4a-4575-8936-a3754a08806a': {'schedule': 'Steaks Sched', 'matchups': 'Steaks M/U'},
    'f02aeae2-5e6a-4098-9842-02d2273f25c7': {'schedule': 'Sunbeams Sched', 'matchups': 'Sunbeams M/U'},
    '878c1bf6-0d21-4659-bfee-916c8314d69c': {'schedule': 'Tacos Sched', 'matchups': 'Tacos M/U'},
    '747b8e4a-7e50-4638-a973-ea7950a3e739': {'schedule': 'Tigers Sched', 'matchups': 'Tigers M/U'},
    'd9f89a8a-c563-493e-9d64-78e4f9a55d4a': {'schedule': 'Georgias Sched', 'matchups': 'Georgias M/U'},
    'bb4a9de5-c924-4923-a0cb-9d1445f1ee5d': {'schedule': 'Worms Sched', 'matchups': 'Worms M/U'},
    '46358869-dce9-4a01-bfba-ac24fc56f57e': {'schedule': 'Mechanics Sched', 'matchups': 'Mechanics M/U'},
    '57ec08cc-0411-4643-b304-0e80dbc15ac7': {'schedule': 'Wings Sched', 'matchups': 'Wings M/U'}
}

weather_types = {
    0: 'Void',
    1: 'Sun 2',
    2: 'Overcast',
    3: 'Rainy',
    4: 'Sandstorm',
    5: 'Snowy',
    6: 'Acidic',
    7: 'Solar Eclipse',
    8: 'Glitter',
    9: 'Blooddrain',
    10: 'Peanuts',
    11: 'Bird',
    12: 'Feedback',
    13: 'Reverb',
    14: 'Black Hole',
    15: 'Coffee',
    16: 'Coffee 2',
    17: 'Coffee 3s',
    18: 'Flooding',
    19: 'Salmon',
    20: 'Polarity+',
    21: 'Polarity-',
    22: '???',
    23: '???',
    24: 'Sun .1',
}

old_favor_rankings = {
        "Pies": 0,
        "Lovers": 1,
        "Tacos": 2,
        "Steaks": 3,
        "Breath Mints": 4,
        "Firefighters": 5,
        "Shoe Thieves": 6,
        "Flowers": 7,
        "Fridays": 8,
        "Magic": 9,
        "Millennials": 10,
        "Crabs": 11,
        "Sunbeams": 12,
        "Wild Wings": 13,
        "Tigers": 14,
        "Moist Talkers": 15,
        "Spies": 16,
        "Dale": 17,
        "Garages": 18,
        "Jazz Hands": 19
}

favor_rankings = {
        "Firefighters": 0,
        "Jazz Hands": 1,
        "Dale": 2,
        "Fridays": 3,
        "Shoe Thieves": 4,
        "Lovers": 5,
        "Pies": 6,
        "Tigers": 7,
        "Garages": 8,
        "Sunbeams": 9,
        "Millennials": 10,
        "Spies": 11,
        "Breath Mints": 12,
        "Magic": 13,
        "Steaks": 14,
        "Crabs": 15,
        "Wild Wings": 16,
        "Flowers": 17,
        "Moist Talkers": 18,
        "Tacos": 19
}


class GameData(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_team_league_division(self, team_id):
        for div in self.bot.divisions:
            for team in div["teams"]:
                if team == team_id:
                    return div["league"], div["name"]

    def get_weather(self, weather_id):
        if weather_id not in weather_types:
            self.bot.logger.warning(f"Unknown weather id: {weather_id}.")
            return "Unknown"
        return weather_types[weather_id]

    async def save_json_range(self, season, fill=False):
        new_season_data = []
        day = -1
        try:
            with open(os.path.join("season_data", f"season{season+1}.json")) as json_file:
                season_data = json.load(json_file)
            for game in season_data:
                if game["gameComplete"]:
                    new_season_data.append(game)
                    day = game["day"]
                else:
                    break
        except FileNotFoundError:
            pass
        day += 1
        done = False
        day_retries = 0
        while True:
            if done:
                break
            # todo remove this and handle better for next season
            if day == 107:
                day += 1
            url = f"https://blaseball.com/database/games?day={day}&season={season}"
            print(f"day: {day}")
            html_response = await utils.retry_request(self.bot.session, url)
            if html_response:
                day_data = await html_response.json()
                if len(day_data) < 1:
                    break
                if len(day_data) < 10:
                    self.bot.logger.warning(f"Fewer than 10 games found for day{day}")
                    if day < 99:
                        day -= 1
                        day_retries += 1
                        if day_retries == 5:
                            self.bot.logger.warning(f"Unable to get 10 games for day{day}")
                            break
                day_games = []
                for game in day_data:
                    if not fill and not game["gameComplete"]:
                        done = True
                        break
                    day_games.append(game)
                new_season_data += day_games
            else:
                print("no response")
            day += 1
        with open(os.path.join("season_data", f"season{season+1}.json"), 'w') as json_file:
            json.dump(new_season_data, json_file)
        success = False
        if fill:
            first = os.path.join('..', 'gamesimsvc', 'season_sim', 'season_data')
            second = os.path.join('..', 'blaseballgamesim', 'season_sim', 'season_data')
            if os.path.exists(first):
                success = True
                file_path = os.path.join(first, f"season{season+1}.json")
                with open(file_path, 'w') as json_file:
                    json.dump(new_season_data, json_file)
            elif os.path.exists(second):
                success = True
                file_path = os.path.join(second, f"season{season + 1}.json")
                with open(file_path, 'w') as json_file:
                    json.dump(new_season_data, json_file)
        return success

    def base_season_parser(self, seasons, fill):
        schedule, teams, odds, weathers, flood_count = {}, {}, {}, {}, {}
        for seas in seasons:
            with open(os.path.join("season_data", f"season{seas+1}.json")) as json_file:
                season_data = json.load(json_file)
            print(f"season: {seas}")
            odds[seas] = {}
            weathers[seas] = {}
            for game in season_data:
                if not fill:
                    if not game["gameComplete"]:
                        break
                    if game['weather'] == 18:
                        if not game['day'] in flood_count:
                            flood_count[game['day']] = []
                        flood_count[game['day']].append(game['id'])
                if game['weather'] not in weathers[seas]:
                    weathers[seas][game['weather']] = 0
                weathers[seas][game['weather']] += 1

                if game['day'] not in odds[seas]:
                    odds[seas][game['day']] = {"results": {"favored": 0, "underdog": 0}, "odds": [], "weathers": []}
                if game["homeScore"] > game["awayScore"]:
                    if game["homeOdds"] > game["awayOdds"]:
                        result = "favored"
                    else:
                        result = "underdog"
                else:
                    if game["awayOdds"] > game["homeOdds"]:
                        result = "favored"
                    else:
                        result = "underdog"
                if result == "favored":
                    odds[seas][game['day']]["odds"].append(max(game["homeOdds"], game["awayOdds"]))
                else:
                    odds[seas][game['day']]["odds"].append(min(game["homeOdds"], game["awayOdds"]))
                odds[seas][game['day']]["weathers"].append(game["weather"])

                odds[seas][game['day']]["results"][result] += 1

                season = schedule.setdefault(game["season"], {})
                home_team = season.setdefault(game["homeTeam"], {})
                away_team = season.setdefault(game["awayTeam"], {})
                if game["homeTeam"] not in teams:
                    league, division = self.get_team_league_division(game["homeTeam"])
                    teams[game["homeTeam"]] = {
                        "name": game["homeTeamNickname"],
                        "league": league,
                        "division": division
                    }
                if game["awayTeam"] not in teams:
                    league, division = self.get_team_league_division(game["awayTeam"])
                    teams[game["awayTeam"]] = {
                        "name": game["awayTeamNickname"],
                        "league": league,
                        "division": division
                    }
                series_count = (game["day"]) // 3
                series_game = (game["day"]) % 3
                h_series = home_team.setdefault(series_count, {})
                a_series = away_team.setdefault(series_count, {})
                if series_game not in h_series:
                    h_series[series_game] = {
                        "id": game["id"],
                        "teamScore": game["homeScore"],
                        "opponentScore": game["awayScore"],
                        "opponent": game["awayTeam"],
                        "teamPitcher": game["homePitcherName"],
                        "opponentPitcher": game["awayPitcherName"],
                        "odds": game["homeOdds"],
                        "home": True,
                        "shame": game["shame"],
                        "weather": game["weather"],
                        "day": game["day"],
                        "outcomes": game["outcomes"]
                    }
                if series_game not in a_series:
                    a_series[series_game] = {
                        "id": game["id"],
                        "opponentScore": game["homeScore"],
                        "teamScore": game["awayScore"],
                        "opponent": game["homeTeam"],
                        "teamPitcher": game["awayPitcherName"],
                        "opponentPitcher": game["homePitcherName"],
                        "odds": game["awayOdds"],
                        "home": False,
                        "shame": game["shame"],
                        "weather": game["weather"],
                        "day": game["day"],
                        "outcomes": game["outcomes"]
                    }
        return schedule, teams, odds, weathers, flood_count

    @staticmethod
    def get_outcome_type(outcome):
        if "reverb" in outcome.lower():
            return "Reverb"
        if "feedback" in outcome.lower():
            return "Feedback"
        if "blooddrain" in outcome.lower():
            return "Blooddrain"
        if "with a pitch" in outcome.lower():
            return "Hit by Pitch"
        if "allergic reaction" in outcome.lower():
            return "Allergic Reaction"
        if "yummy reaction" in outcome.lower():
            return "Yummy Reaction"
        if "is red hot" in outcome.lower():
            return "Red Hot"
        if "no longer red hot" in outcome.lower():
            return "Cooled Down"
        if "incinerated" in outcome.lower():
            return "Incineration"
        if "partying" in outcome.lower():
            return "Partying!"
        if "crashes into the field" in outcome.lower():
            return "Shelled"
        if "tasted the infinite and shelled" in outcome.lower():
            return "Shelled"
        if "sun 2" in outcome.lower():
            return "Sunset"
        if "black hole swallowed" in outcome.lower():
            return "Black Hole"
        if "black hole burped" in outcome.lower():
            return "Black Hole Burp"
        if "was swept elsewhere" in outcome.lower():
            return "Swept Elsewhere"
        if "returned from elsewhere" in outcome.lower():
            return "Returned from Elsewhere"
        if "attack" in outcome.lower() and "defends" in outcome.lower() and "breaks" in outcome.lower():
            return "Defend/Break"
        if "consumers attack" in outcome.lower():
            return "CONSUMERS"
        if "bat broke" in outcome.lower():
            return "Broken Bat"

    async def update_spreadsheets(self, seasons, fill=False):
        agc = await self.bot.authorize_agcm()
        schedule, teams, odds, weathers, flood_count = self.base_season_parser(seasons, fill)
        league_records = {"Wild": {}, "Mild": {}}

        for season in schedule:
            season_outcomes = {}
            if self.bot.config['live_version'] == True:
                sheet = await agc.open_by_key(self.bot.SPREADSHEET_IDS[f"season{season+1}"])
            else:
                sheet = await agc.open_by_key(self.bot.SPREADSHEET_IDS[f"seasontest"])
            print("Updating Team Schedules")
            day = 0
            for team in schedule[season]:
                if season < 12:
                    s_worksheet = await sheet.worksheet(spreadsheet_names_old[team]["schedule"])
                    m_worksheet = await sheet.worksheet(spreadsheet_names_old[team]["matchups"])
                else:
                    s_worksheet = await sheet.worksheet(spreadsheet_names[team]["schedule"])
                    m_worksheet = await sheet.worksheet(spreadsheet_names[team]["matchups"])
                srows = [["Day", "Opponent", "Team Score", "Opp Score", "Winner",
                          "Winning Pitcher", "Losing Pitcher", "Streak", "Record",
                          "Game Type", "Win", "Home",
                          "Odds", "Shame", "Weather", "Outcomes"]]
                mrows = []
                i, j = 3, 2
                team_series = {}
                record = {"total": {"win": 0, "loss": 0},
                          "postseason": {"win": 0, "loss": 0},
                          "home": {"win": 0, "loss": 0},
                          "away": {"win": 0, "loss": 0},
                          "o500": {"win": 0, "loss": 0},
                          "single_run": {"win": 0, "loss": 0},
                          "scored": 0, "given": 0,
                          "shames": 0, "times_shamed": 0,
                          "win_modifier": 0}
                for oteam in teams:
                    if oteam != team:
                        record[teams[oteam]["name"]] = {"win": 0, "loss": 0}
                last_outcome, this_outcome, running_count = None, None, 0
                for sid in schedule[season][team]:
                    series = schedule[season][team][sid]
                    for gid in series:
                        i += 1
                        game = series[gid]
                        day = max(day, game["day"])
                        if game["opponent"] not in team_series:
                            team_series[game["opponent"]] = {
                                "team": teams[team]["name"],
                                "opponent": teams[game["opponent"]]["name"],
                                "wins": 0,
                                "losses": 0,
                                "games": 0,
                                "game_type": "",
                                "home": 0,
                                "away": 0,
                                "season": season + 1
                            }
                        record["scored"] += game["teamScore"]
                        record["given"] += game["opponentScore"]

                        if game["teamScore"] - game["opponentScore"] == 1:
                            record["single_run"]["win"] += 1
                        elif game["teamScore"] - game["opponentScore"] == -1:
                            record["single_run"]["loss"] += 1
                        win = game["teamScore"] > game["opponentScore"]

                        if win:
                            winner = teams[team]["name"]
                            win = game["teamPitcher"]
                            loss = game["opponentPitcher"]
                            if game["day"] < 99:
                                record["total"]["win"] += 1
                            else:
                                record["postseason"]["win"] += 1
                            team_series[game["opponent"]]["wins"] += 1
                            this_outcome = "W"
                            if game["shame"]:
                                record["shames"] += 1
                            if game["home"]:
                                record["home"]["win"] += 1
                                team_series[game["opponent"]]["home"] += 1
                            else:
                                record["away"]["win"] += 1
                                team_series[game["opponent"]]["away"] += 1
                            record[teams[game["opponent"]]["name"]]["win"] += 1
                        else:
                            winner = teams[game["opponent"]]["name"]
                            win = game["opponentPitcher"]
                            loss = game["teamPitcher"]
                            if game["day"] < 99:
                                record["total"]["loss"] += 1
                            else:
                                record["postseason"]["loss"] += 1
                            team_series[game["opponent"]]["losses"] += 1
                            this_outcome = "L"
                            if game["shame"]:
                                record["times_shamed"] += 1
                            if game["home"]:
                                record["home"]["loss"] += 1
                                team_series[game["opponent"]]["home"] += 1
                            else:
                                record["away"]["loss"] += 1
                                team_series[game["opponent"]]["away"] += 1
                            record[teams[game["opponent"]]["name"]]["loss"] += 1
                        if this_outcome != last_outcome:
                            running_count = 1
                            last_outcome = this_outcome
                        else:
                            running_count += 1
                        running_string = f"{this_outcome}-{running_count}"
                        record_str = f"{record['total']['win']}-{record['total']['loss']}"
                        team_league, team_division = teams[team]["league"], teams[team]["division"]
                        opp_league, opp_division = teams[game["opponent"]]["league"], teams[game["opponent"]]["division"]
                        if team_division == opp_division:
                            game_type = team_series[game["opponent"]]["game_type"] = "Division"
                        elif team_league == opp_league:
                            game_type = team_series[game["opponent"]]["game_type"] = "League"
                        else:
                            game_type = team_series[game["opponent"]]["game_type"] = "InterLeague"
                        team_series[game["opponent"]]["games"] += 1
                        if game['weather']:
                            w_str = self.get_weather(game['weather'])
                        else:
                            w_str = "None"
                        if len(game["outcomes"]) > 0:
                            season_outcomes.setdefault(game['day'], {})
                            season_outcomes[game["day"]][game["id"]] = game["outcomes"]

                            for o in game["outcomes"]:
                                outcome_type = self.get_outcome_type(o)
                                team_name = teams[team]['name']
                                if outcome_type == "Sunset":
                                    # this may need changing in the future
                                    match = re.search(r"at the ([a-zA-Z ]+)", o)
                                    if match:
                                        if len(match.groups()) > 0:
                                            target_team = match.groups()[0]
                                            if target_team == team_name:
                                                record["win_modifier"] += 1
                                elif outcome_type == "Black Hole":
                                    match = re.search(r"from the ([a-zA-Z ]+)", o)
                                    if match:
                                        if len(match.groups()) > 0:
                                            target_team = match.groups()[0]
                                            if target_team == team_name:
                                                record["win_modifier"] -= 1
                                elif outcome_type == "Black Hole Burp":
                                    match = re.search(r"at the ([a-zA-Z ]+)", o)
                                    if match:
                                        if len(match.groups()) > 0:
                                            target_team = match.groups()[0]
                                            if target_team == team_name:
                                                record["win_modifier"] += 1

                        game_outcomes = [o.strip() for o in game["outcomes"]]
                        if fill:
                            row = [game["day"] + 1,
                                   teams[game["opponent"]]["name"],
                                   '',
                                   '',
                                   '',
                                   '',
                                   '',
                                   '',
                                   '',
                                   game_type,
                                   '',
                                   game["home"],
                                   '',
                                   '',
                                   w_str,
                                   " | ".join(game_outcomes),
                                   ]
                        else:
                            row = [game["day"] + 1,
                                   teams[game["opponent"]]["name"],
                                   game["teamScore"],
                                   game["opponentScore"],
                                   winner,
                                   win,
                                   loss,
                                   running_string,
                                   record_str,
                                   game_type,
                                   game["teamScore"] > game["opponentScore"],
                                   game["home"],
                                   round(game["odds"]*100),
                                   game["shame"],
                                   w_str,
                                   " | ".join(game_outcomes),
                                   ]
                        srows.append(row)
                summary_row = ["Record", record['total']["win"], record['total']["loss"],
                               round(record['total']["win"] / (
                                           record['total']["win"] + record['total']["loss"]) * 1000) / 1000,
                               "Runs", record["scored"], "Given Up", record["given"],
                               "Diff", record["scored"] - record["given"],
                               "Shames", record["shames"], "Shamed", record["times_shamed"]]
                indices_to_add = len(srows[0]) - len(summary_row)
                summary_row += [''] * indices_to_add
                srows.insert(0, summary_row)
                await s_worksheet.batch_update([{
                    'range': f"A{2}:Q{i+1}",
                    'values': srows
                }])

                if fill:
                    for opp in team_series:
                        row = [team_series[opp]["opponent"], '0', '0',
                               team_series[opp]['games'], team_series[opp]['game_type'],
                               team_series[opp]['home'], team_series[opp]['away']]
                        mrows.append(row)
                        j += 1


                    await m_worksheet.batch_update([{
                        'range': f"A{3}:G{j}",
                        'values': mrows
                    }])

                else:
                    for opp in team_series:
                        row = [team_series[opp]['wins'], team_series[opp]['losses']]
                        mrows.append(row)
                        j += 1
                    await m_worksheet.batch_update([{
                        'range': f"B{3}:C{j}",
                        'values': mrows
                    }])
                league_records[teams[team]['league']][teams[team]["name"]] = record
                if fill:
                    await asyncio.sleep(10)

            print("Updating Weather Events")

            orows, otypes = [], []
            weather_occurrences = {"Black Hole": 0, "Sunset": 0, "Incineration": 0}
            for day in sorted(season_outcomes.keys()):
                for game in season_outcomes[day]:
                    for outcome in season_outcomes[day][game]:
                        outcome_type = self.get_outcome_type(outcome)
                        if outcome_type in weather_occurrences:
                            weather_occurrences[outcome_type] += 1
                        orows.append([day+1, outcome.strip().replace('\n', ' ')])
                        otypes.append([outcome_type])
            o_worksheet = await sheet.worksheet("Blaseball")

            await o_worksheet.batch_update([{
                'range': f"A{9}:B{9 + len(orows)}",
                'values': orows
            }])
            await o_worksheet.batch_update([{
                'range': f"I{9}:I{9 + len(otypes)}",
                'values': otypes
            }])

            if fill:
                weather_rows = []
                for w, count in weathers[season].items():
                    weather_name = self.get_weather(w)
                    w_row = [weather_name, count, f"{round((count/1188)*1000)/10}%"]
                    weather_rows.append(w_row)
                await o_worksheet.batch_update([{
                    'range': f"K{8}:M{8 + len(weather_rows)}",
                    'values': weather_rows
                }])
            else:
                try:
                    with open(os.path.join('data', 'pendant_data', 'statsheets', f's{season}_flood_lookups.json'),
                              'r') as file:
                        flood_lookups = json.load(file)
                except FileNotFoundError:
                    flood_lookups = {}
                for day, floods in flood_count.items():
                    if str(day) not in flood_lookups:
                        flood_lookups[str(day)] = {"lookedup": False, "floods": floods}
                with open(os.path.join('data', 'pendant_data', 'statsheets', f's{season}_flood_lookups.json'),
                          'w') as file:
                    json.dump(flood_lookups, file)

            def generate_per_team_records(team_list, record):
                n_divisions = {"Wild High": ["Tigers", "Lift", "Wild Wings", "Firefighters", "Jazz Hands", "Georgias"],
                             "Wild Low": ["Spies", "Flowers", "Sunbeams", "Dale", "Tacos", "Worms"],
                             "Mild High": ["Lovers", "Pies", "Garages", "Steaks", "Millennials", "Mechanics"],
                             "Mild Low": ["Fridays", "Moist Talkers", "Breath Mints", "Shoe Thieves", "Magic", "Crabs"]
                             }

                div_records = {"Wild High": {"win": 0, "loss": 0},
                               "Wild Low": {"win": 0, "loss": 0},
                               "Mild High": {"win": 0, "loss": 0},
                               "Mild Low": {"win": 0, "loss": 0}
                             }

                team_columns = []

                for division in n_divisions:
                    for team in n_divisions[division]:
                        if team == team_list[0]:
                            team_columns.append("-")
                        else:
                            if team not in record:
                                t_record = '0-0'
                            else:
                                t_record = f'{record[team]["win"]}-{record[team]["loss"]}'
                                div_records[division]["win"] += record[team]["win"]
                                div_records[division]["loss"] += record[team]["loss"]
                            team_columns.append(t_record)
                for division in div_records:
                    d_record = f'{div_records[division]["win"]}-{div_records[division]["loss"]}'
                    team_list.append(d_record)
                team_list += team_columns

            async def update_league(league, start_i):

                sorted_league = {k: v for k, v in
                                 sorted(league.items(),
                                        key=lambda item: item[1]["total"]["win"] + item[1]["win_modifier"],
                                        reverse=True)}
                any_team = list(sorted_league.items())[0]
                games = any_team[1]['total']['win'] + any_team[1]['total']['loss']
                teams = []
                for team, record in sorted_league.items():
                    teams.append([team, record['total']['win'] + record["win_modifier"],
                                  record['total']['loss'], record['total']['win']])
                for i in range(len(teams)):
                    gb_string = ""
                    team, wins, losses = teams[i][0], teams[i][1], teams[i][2]
                    if i >= 4:
                        gb_string = (teams[3][1] - wins) + (losses - teams[3][2]) / 2
                        diff = 100 - teams[3][1] - teams[i][2]
                    else:
                        diff = 100 - teams[i][1] - teams[4][2]
                    teams[i] += round((wins / (wins + losses)) * 1000) / 1000, gb_string, diff
                for i in range(len(teams) - 1):
                    if teams[i][3] == teams[i+1][3]:
                        if self.bot.favor_rankings[teams[i+1][0]] < self.bot.favor_rankings[teams[i][0]]:
                            teams[i], teams[i+1] = teams[i+1], teams[i]
                            if teams[i][5] == 0:
                                teams[i][5] = ""
                            teams[i+1][5] = f"{teams[i+1][5]}*"

                for i in range(len(teams)):
                    teams[i][2] = f"{teams[i][3]}-{teams[i][2]}"
                    teams[i].pop(3)
                    if i <= 3:
                      if teams[i][5] <= 0:
                            teams[i][5] = "Clinched"
                    else:
                        if teams[i][5] <= 0:
                            teams[i][5] = "Party Time!"

                    record = sorted_league[teams[i][0]]
                    home_record = f"{record['home']['win']}-{record['home']['loss']}"
                    away_record = f"{record['away']['win']}-{record['away']['loss']}"
                    teams[i] += home_record, away_record, record["scored"] - record["given"]
                    generate_per_team_records(teams[i], record)
                    teams[i] += [f"{record['single_run']['win']}-{record['single_run']['loss']}"]
                    teams[i] += record["scored"], record["given"], record["shames"], record["times_shamed"]

                await s_worksheet.batch_update([{
                    'range': f"A{start_i-1}:AP{start_i -1}",
                    'values': [["Team", "Wins", "Record", "Pct.", "GB", "Magic #",
                                "Home", "Away", "Run Diff", "WH", "WL", "MH", "ML",
                                "Tigers", "Lift", "Wild Wings", "Firefighters", "Jazz Hands", "Georgias",
                                "Spies", "Flowers", "Sunbeams", "Dale", "Tacos", "Worms",
                                "Lovers", "Pies", "Garages", "Steaks", "Millennials", "Mechanics",
                                "Fridays", "Moist Talkers", "Breath Mints", "Shoe Thieves", "Magic", "Crabs",
                                "1-Run", "R Scored", "R Allowed", "Shames", "Shamed"]]
                }])

                await s_worksheet.batch_update([{
                    'range': f"A{start_i}:AP{start_i + len(teams)}",
                    'values': teams
                }])
                await s_worksheet.batch_update([{
                    'range': "F32",
                    'values': [[99-games]]
                }])
                await s_worksheet.batch_update([{
                    'range': "AR1",
                    'values': [[games]]
                }])

            s_worksheet = await sheet.worksheet("Standings")
            if day <= 98:
                print("Updating Standings")
                await update_league(league_records["Wild"], 4)
                await update_league(league_records["Mild"], 19)

            print("Updating Odds")
            if season in odds:
                odds_rows = []
                header_row = ["Days", "Favored Wins", "Underdog Wins", "Game 1", "Game 2", "Game 3",
                              "Game 4", "Game 5", "Game 6", "Game 7", "Game 8", "Game 9", "Game 10",
                              "Game 11", "Game 12"]

                if season < 11:
                    bet_tiers = [.5, .51, .52, .53, .54, .55, .56, .57, .58, .59, .6, .61, .62]
                else:
                    bet_tiers = [.5, .51, .52, .53, .54, .55, .56, .57, .58, .59,
                                 .6, .61, .62, .63, .64]
                for i in bet_tiers:
                    header_row.append(f"{round(i*100)}%+ payout")
                odds_rows.append(header_row)
                total_betcounts = [0] * len(bet_tiers)
                for day in odds[season]:
                    payouts, bet_counts = self._calculate_payout(odds[season][day], bet_tiers, season)
                    rounded_odds = []
                    for i in range(len(odds[season][day]["odds"])):
                        #if odds[season][day]["weathers"][i] != 1 and odds[season][day]["weathers"][i] != 14:
                        o = odds[season][day]["odds"][i]
                        rounded_odds.append(round(o * 1000)/10)

                    rounded_odds.sort()
                    # need to track total expected number of games better in case it changes again
                    rounded_odds += [''] * (12 - len(rounded_odds))
                    row = [day+1, odds[season][day]["results"]["favored"], odds[season][day]["results"]["underdog"]]
                    row += rounded_odds
                    row += payouts
                    odds_rows.append(row)
                    for c in range(len(bet_counts)):
                        total_betcounts[c] += bet_counts[c]
                snack_sheet = await agc.open_by_key(self.bot.SPREADSHEET_IDS[f"season{season + 1}snacks"])
                od_worksheet = await snack_sheet.worksheet("Daily Results")
                await od_worksheet.batch_update([{
                    'range': f"A{4}:AD{4 + len(odds_rows)}",
                    'values': odds_rows
                }])
                await od_worksheet.batch_update([{
                    'range': f"P{2}:AD{2}",
                    'values': [total_betcounts]
                }])

            await self._save_weather_counts(sheet, season, weather_occurrences)

            print("Updates Complete")
            await asyncio.sleep(5)

    async def _save_weather_counts(self, sheet, season, weather_occurrences):
        flood_count, runner_count = await self._lookup_floods(season)
        # await p_worksheet.batch_update([{
        #     'range': "C2:C2",
        #     'values': [[weather_occurrences["Black Hole"]]]
        # }])
        # await p_worksheet.batch_update([{
        #     'range': "C3:C3",
        #     'values': [[weather_occurrences["Sunset"]]]
        # }])
        # await p_worksheet.batch_update([{
        #     'range': "C4:C4",
        #     'values': [[weather_occurrences["Incineration"]]]
        # }])
        # await p_worksheet.batch_update([{
        #     'range': "C5:C6",
        #     'values': [[flood_count, runner_count]]
        # }])

        weather_occurrences["flooded_runners"] = runner_count
        with open(os.path.join('season_data', 'weather_occurrences.json'), 'w') as file:
            json.dump(weather_occurrences, file)
        try:
            snax_cog = self.bot.cogs.get('SnaxCog')
            snax_cog.refresh_snax_info()
        except Exception as e:
            self.bot.logger.warning(f"Failed to refresh snax cog data: {e}")

    async def _lookup_floods(self, season):
        season_flood_count, season_runner_count = 0, 0
        try:
            with open(os.path.join('data', 'pendant_data', 'statsheets', f's{season}_flood_lookups.json'),
                      'r') as file:
                flood_lookups = json.load(file)
        except FileNotFoundError:
            flood_lookups = {}
            self.bot.logger.warning("No flood lookup data found.")
        for day, day_info in flood_lookups.items():
            if day_info['lookedup'] == False:
                day_flood_count = 0
                day_runner_count = 0
                failed_count = 0
                for game_id in day_info["floods"]:
                    game_feed = await utils.retry_request(self.bot.session,
                        f"https://api.blaseball-reference.com/v1/events?gameId={game_id}&baseRunners=true")
                    if game_feed:
                        feed_json = await game_feed.json()
                        if len(feed_json['results']) > 0:
                            last_event = None
                            for food in feed_json['results']:
                                for text in food['event_text']:
                                    if "Immateria" in text:
                                        day_flood_count += 1
                                        for runner in last_event['base_runners']:
                                            if runner['base_after_play'] != 4:
                                                day_runner_count += 1
                                last_event = food
                        else:
                            failed_count += 1
                    else:
                        failed_count += 1

                if failed_count == 0:
                    day_info['lookedup'] = True
                    day_info['flood_count'] = day_flood_count
                    day_info['runner_count'] = day_runner_count

                    season_flood_count += day_flood_count
                    season_runner_count += day_runner_count
            else:
                if "flood_count" in day_info:
                    season_flood_count += day_info['flood_count']
                if "runner_count" in day_info:
                    season_runner_count += day_info['runner_count']
            flood_lookups[day] = day_info
        with open(os.path.join('data', 'pendant_data', 'statsheets', f's{season}_flood_lookups.json'),
                  'w') as file:
            json.dump(flood_lookups, file)
        return season_flood_count, season_runner_count

    @staticmethod
    def _calculate_payout(odds_dict, bet_tiers, season):
        weathers = odds_dict["weathers"]
        odds = odds_dict["odds"]
        payouts = [0] * len(bet_tiers)
        bet_counts = [0] * len(bet_tiers)
        for i in range(len(bet_tiers)):
            count = 0
            for j in range(len(odds)):
                odd = odds[j]
                if odd >= bet_tiers[i]:
                    if odd == .5:
                        payouts[i] += round(2*1000)
                    if season < 11:
                        payouts[i] += round(1000 * (2 - 0.000335 * math.pow(100 * (odd - 0.5), 2.045)))
                    else:
                        if odd > .5:
                            #payouts[i] += round(1000 * (.571 + 1.429 / (1 + math.pow(3 * (odd - 0.5), .77))))
                            payouts[i] += round(1000 * (3.206 / (1 + math.pow(.443 * (odd - 0.5), .95)) - 1.206))
                    count += 1
                elif odd < 1 - bet_tiers[i]:
                    count += 1
            payouts[i] = payouts[i] - (1000 * count)
            bet_counts[i] = count
        return payouts, bet_counts

    @commands.command(name='update_spreadsheets', aliases=['us'])
    async def _update_spreadsheets(self, ctx, current_season: int, fill: bool = False):
        await ctx.message.add_reaction("⏲️")
        current_season -= 1
        await self.save_json_range(current_season, fill)
        if fill:
            await self._update_tiebreakers()
        await self.update_spreadsheets([current_season], fill)
        await ctx.message.add_reaction(self.bot.success_react)
        await ctx.send("Spreadsheets updated.")

    @commands.command(name="anc")
    async def _anc(self, ctx):
        html_response = await utils.retry_request(self.bot.session, 'https://www.blaseball.com/database/allteams')
        if not html_response:
            return await ctx.send("Failed to acquire team data.")
        team_data = await html_response.json()
        for team in team_data:
            out_str = ""
            players = team['bullpen']
            html_response = await utils.retry_request(self.bot.session,
                                                      f'https://www.blaseball.com/database/players?ids={",".join(players)}')
            if not html_response:
                return await ctx.send("Failed to acquire player data.")
            player_data = await html_response.json()
            for player in player_data:
                out_str += f"{team['nickname']}\t{player['name']}\tbullpen\n"

            players= team['bench']
            html_response = await utils.retry_request(self.bot.session,
                f'https://www.blaseball.com/database/players?ids={",".join(players)}')
            if not html_response:
                return await ctx.send("Failed to acquire player data.")
            player_data = await html_response.json()
            for player in player_data:
                out_str += f"{team['nickname']}\t{player['name']}\tbench\n"
            print(out_str)

    @commands.command(aliases=['tsh'])
    async def _test_spreadsheet(self, ctx):
        agc = await self.bot.authorize_agcm()
        sheet = await agc.open_by_key(self.bot.SPREADSHEET_IDS["season11"])
        s_worksheet = await sheet.worksheet("Blaseball")
        await s_worksheet.batch_update([{
            'range': f"J1:J1",
            'values': "test"
        }])

    @commands.command(name='update_divine_favor', aliases=['update_tie_breakers', 'utb', 'favor', 'divine', 'udf'])
    async def _update_divine_favor(self, ctx):
        updated = await self._update_tiebreakers()
        if updated:
            return await ctx.message.add_reaction(self.bot.success_react)
        return await ctx.message.add_reaction(self.bot.failed_react)

    async def _update_tiebreakers(self):
        try:
            html_response = await utils.retry_request(self.bot.session,
                                                      "https://www.blaseball.com/database/simulationdata")
            if not html_response:
                self.bot.logger.warning('Failed to acquire sim data')
                return
            sim_data = await html_response.json()
            league_id = sim_data['league']
            content = await utils.retry_request_stream(self.bot.session,
                                                       f"https://www.blaseball.com/database/league?id={league_id}")
            if not content:
                self.bot.logger.warning('Failed to acquire league data')
                return
            league_json = json.loads(content.decode('utf-8'))
            html_response = await utils.retry_request(self.bot.session,
                                                      f"https://www.blaseball.com/database/tiebreakers?id={league_json['tiebreakers']}")
            if not html_response:
                self.bot.logger.warning('Failed to acquire tiebreakers data')
                return
            new_ties_json = await html_response.json()
            json_watcher = self.bot.get_cog("JsonWatcher")
            await json_watcher.update_bot_tiebreakers(new_ties_json)
            html_response = await utils.retry_request(self.bot.session,
                                                      'https://www.blaseball.com/database/allteams')
            if not html_response:
                self.bot.logger.warning('Failed to acquire team data')
                return
            team_data = await html_response.json()
            favor_rankings = {}
            count = 0
            for rank in new_ties_json[0]['order']:
                for team in team_data:
                    if team['id'] == rank:
                        favor_rankings[team['nickname']] = count
                        count += 1
            self.bot.config['favor_rankings'] = self.bot.favor_rankings = favor_rankings
        except Exception as e:
            self.bot.logger.warning(f"Failed to update tiebreakers: {e}")
            return False
        return True

    @commands.command(name="apply_conditional_rules", aliases=['acr'])
    async def _apply_conditional_rules(self, ctx, season):
        gc = gspread.service_account(os.path.join("gspread", "service_account.json"))
        sheet = gc.open_by_key(self.bot.SPREADSHEET_IDS[f"season{season}snacks"])
        od_worksheet = sheet.worksheet("Daily Results")
        rules = get_conditional_format_rules(od_worksheet)
        for i in range(6, 106):
            rule = ConditionalFormatRule(
                ranges=[GridRange.from_a1_range(f'AF{i}', od_worksheet),
                        GridRange.from_a1_range(f'AG{i}', od_worksheet),
                        GridRange.from_a1_range(f'AH{i}', od_worksheet),
                        GridRange.from_a1_range(f'AI{i}', od_worksheet),
                        GridRange.from_a1_range(f'AJ{i}', od_worksheet)],
                gradientRule=GradientRule(minpoint=InterpolationPoint(color=Color.fromHex("#e67e75"), type='min'),
                                          midpoint=InterpolationPoint(color=Color.fromHex("#ffffff"),
                                                                      type='NUMBER', value='0'),
                                          maxpoint=InterpolationPoint(color=Color.fromHex("#5bbd8d"), type='max'))
                )
            rules.append(rule)
        rules.save()

    @commands.command(name='test_feed')
    async def _test_feed(self, ctx):
        game_ids = []
        for i in [12, 13]:
            with open(os.path.join("season_data", f"season{i}.json")) as json_file:
                season_data = json.load(json_file)
            for game in season_data:
                if game['weather'] == 18 and game["gameComplete"]:
                    game_ids.append(game['id'])

        total_runners = 0
        floods = 0
        for game_id in game_ids:
            game_feed = await utils.retry_request(self.bot.session,
                                                  f"https://api.blaseball-reference.com/v1/events?gameId={game_id}&baseRunners=true")
            feed_json = await game_feed.json()
            last_event = None
            for food in feed_json['results']:
                for text in food['event_text']:
                    if "Immateria" in text:
                        floods += 1
                        runners = 0
                        for runner in last_event['base_runners']:
                            if runner['base_after_play'] != 4:
                                total_runners += 1
                                runners += 1
                        print(f"{game_id} - event {food['id']} - runners: {runners}")
                last_event = food
            print(f"total runners so far: {total_runners}")
        print(f"total floods: {floods}")

    @commands.command(name='check_for_new_schedules', aliases=['cfns'])
    async def _check_for_new_schedules(self, ctx, check: bool):
        if check == self.bot.config['check_for_new_schedules']:
            return await ctx.message.add_reaction(self.bot.success_react)
        self.bot.config['check_for_new_schedules'] = check
        tasks = self.bot.tasks
        if check:
            event_loop = asyncio.get_event_loop()
            self.bot.tasks.append(event_loop.create_task(self.check_new_schedule_loop()))
        else:
            for t in range(len(tasks)):
                task = tasks[t]
                if task._coro.cr_code.co_name == "check_new_schedule_loop":
                    tasks.pop(t)
                    task.cancel()
                    break
        return await ctx.message.add_reaction(self.bot.success_react)

    async def check_new_schedule_loop(self):
        while not self.bot.is_closed():
            self.bot.logger.info("Checking for new schedules")

            season = self.bot.config['current_season'] - 1
            games = await utils.retry_request(self.bot.session,
                                              f"https://www.blaseball.com/database/games?day=0&season={season}")
            if games:
                games_list = await games.json()
                if len(games_list) > 0:
                    for t in range(len(self.bot.tasks)):
                        task = self.bot.tasks[t]
                        if task._coro.cr_code.co_name == "game_new_schedule_loop":
                            self.bot.tasks.pop(t)
                            task.cancel()
                    self.bot.config['check_for_new_schedules'] = False
                    success = await self.save_json_range(season, True)
                    await self.update_spreadsheets(season, True)
                    await self._update_tiebreakers()
                    if success:
                        file_id = f"s_{season}_season_sim"
                        for day in range(0, 99):
                            data = {"iterations": 501,
                                    "season": season,
                                    "day": day,
                                    "file_id": file_id,
                                    "seg_size": 3
                                    }
                            async with self.bot.session.get(url=f'http://localhost:5555/v1/seasonsim', json=data,
                                                            timeout=75000) as response:
                                await response.json()
                    break

            await asyncio.sleep(120)

    @commands.command(name='copy_and_clear_new_sheet', aliases=['cns'])
    @checks.is_owner()
    async def _copy_and_clear_new_sheet(self, ctx, season):
        client = gspread.authorize(self.bot.get_creds())
        old_snacks_id = self.bot.SPREADSHEET_IDS[f"season{int(season)-1}snacks"]
        new_snacks_sheet = client.copy(old_snacks_id, title=f"Blaseball Season {season} Snacks", copy_permissions=True)
        self.bot.SPREADSHEET_IDS[f"season{int(season)}snacks"] = new_snacks_sheet.id

        old_sheet_id = self.bot.SPREADSHEET_IDS[f"season{int(season) - 1}"]
        new_main_sheet = client.copy(old_sheet_id, title=f"Blaseball Season {season}", copy_permissions=True)
        self.bot.SPREADSHEET_IDS[f"season{int(season)}"] = new_main_sheet.id

        with open(os.path.join("data", "spreadsheet_ids.json"), 'w') as json_file:
            json.dump(self.bot.SPREADSHEET_IDS, json_file)

        await ctx.send(f"Main sheet: {new_main_sheet.url}\nSnacks sheet: {new_snacks_sheet.url}")

        agc = await self.bot.authorize_agcm()

        async def clear_snack_sheet():
            snack_sheet = await agc.open_by_key(new_snacks_sheet.id)
            d_worksheet = await snack_sheet.worksheet("Daily Results")
            empty_rows = []
            for i in range(120):
                empty_rows.append([''] * 14)
            await d_worksheet.batch_update([{
                'range': f"B5:O125",
                'values': empty_rows
            }])
            await d_worksheet.batch_update([{
                'range': f"P2:AD2",
                'values': [[''] * 15]
            }])

            d_worksheet = await snack_sheet.worksheet("Weather Snacks")
            empty_rows = []
            for i in range(5):
                empty_rows.append([''] * 2)
            await d_worksheet.batch_update([{
                'range': f"C2:D6",
                'values': empty_rows
            }])
        await clear_snack_sheet()

        async def clear_main_sheet():
            sheet = await agc.open_by_key(new_main_sheet.id)
            b_worksheet = await sheet.worksheet("Blaseball")
            empty_rows = []
            for i in range(15):
                empty_rows.append([''] * 3)
            await b_worksheet.batch_update([{
                'range': f"K{8}:M{22}",
                'values': empty_rows
            }])

            empty_rows = []
            last_row = b_worksheet.row_count
            weather_rows = last_row - 8
            for i in range(weather_rows):
                empty_rows.append([''] * 9)
            await b_worksheet.batch_update([{
                'range': f"A{9}:I{last_row}",
                'values': empty_rows
            }])

            for team in self.bot.team_names.keys():
                try:
                    s_worksheet = await sheet.worksheet(spreadsheet_names[team]["schedule"])
                    m_worksheet = await sheet.worksheet(spreadsheet_names[team]["matchups"])

                    empty_rows = []
                    for i in range(112):
                        empty_rows.append([''] * 16)
                    await s_worksheet.batch_update([{
                        'range': f"A{2}:Q{2}",
                        'values': [[''] * 16]
                    }])
                    await s_worksheet.batch_update([{
                        'range': f"A{4}:Q{115}",
                        'values': empty_rows
                    }])

                    empty_rows = []
                    for i in range(17):
                        empty_rows.append([''] * 7)
                    await m_worksheet.batch_update([{
                        'range': f"A{3}:G{19}",
                        'values': empty_rows
                    }])
                except KeyError:
                    pass
        await clear_main_sheet()

        await ctx.message.add_reaction(self.bot.success_react)

    @commands.command(name='fix_formulas', aliases=['ffm'])
    async def _fix_formulas(self, ctx, season):
        agc = await self.bot.authorize_agcm()
        sheet = await agc.open_by_key(self.bot.SPREADSHEET_IDS[f"season{season}"])
        for team in self.bot.team_names.keys():
            try:
                m_worksheet = await sheet.worksheet(spreadsheet_names[team]["matchups"])

                formula_rows = [
                    ['=SUM(FILTER(D3:D18,E3:E18="Division"))'],
                    ['=SUM(FILTER(D3:D18,E3:E18="League"))'],
                    ['=SUM(FILTER(D3:D18,E3:E18="InterLeague"))']
                ]
                await m_worksheet.batch_update([{
                    'range': f"B20:B22",
                    'values': formula_rows
                }],
                    value_input_option='USER_ENTERED')

                formula_rows = [
                    ['=sum(F3:F18)'],
                    ['=sum(G3:G18)']
                ]
                await m_worksheet.batch_update([{
                    'range': f"F20:F21",
                    'values': formula_rows
                }],
                    value_input_option='USER_ENTERED')
            except KeyError:
                pass
        await ctx.message.add_reaction(self.bot.success_react)


def setup(bot):
    bot.add_cog(GameData(bot))
