import math
import os
import asyncio

import json
import re

import gspread

from discord.ext import commands

from watcher import utils

"""New season checklist:
    Make sure divisions are up to date 
    Make sure weather types are up to date
    Make sure all team spreadsheet tabs exists
    Make sure all teams are added to name mapping
    Update divisions in generate_per_team_records
    Maybe just automate the update of as much of this as possible
"""

spreadsheet_names = {
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
    '57ec08cc-0411-4643-b304-0e80dbc15ac7': {'schedule': 'Wings Schedule', 'matchups': 'Wings Matchups'}
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
    9: 'Bloodwind',
    10: 'Peanuts',
    11: 'Bird',
    12: 'Feedback',
    13: 'Reverb',
    14: 'Black Hole',
    15: 'Coffee',
    16: 'Coffee 2',
    17: 'Coffee 3s',
    18: 'Flooding',
    19: '???',
    20: '???',
    21: '???',
    22: '???'
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

    @staticmethod
    def get_team_league_division(divisions, teamID):
        for div in divisions:
            for team in div["teams"]:
                if team == teamID:
                    return div["league"], div["name"]

    def get_weather(self, weather_id):
        if weather_id not in weather_types:
            self.bot.logger.warn(f"Unknown weather id: {weather_id}.")
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
            url = f"https://blaseball.com/database/games?day={day}&season={season}"
            print(f"day: {day}")
            html_response = await utils.retry_request(url)
            if html_response:
                day_data = html_response.json()
                if len(day_data) < 1:
                    break
                if len(day_data) < 10:
                    self.bot.logger.warn(f"Fewer than 10 games found for day{day}")
                    if day < 99:
                        day -= 1
                        day_retries += 1
                        if day_retries == 5:
                            self.bot.logger.warn(f"Unable to get 10 games for day{day}")
                            break
                for game in day_data:
                    if not fill and not game["gameComplete"]:
                        done = True
                        break
                    new_season_data.append(game)
            else:
                print("no response")
            day += 1
        with open(os.path.join("season_data", f"season{season+1}.json"), 'w') as json_file:
            json.dump(new_season_data, json_file)

    def base_season_parser(self, seasons, fill):
        schedule, teams, odds, weathers = {}, {}, {}, {}
        with open(os.path.join("data", "divisions.json")) as json_file:
            divisions = json.load(json_file)
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
                    league, division = self.get_team_league_division(divisions, game["homeTeam"])
                    teams[game["homeTeam"]] = {
                        "name": game["homeTeamNickname"],
                        "league": league,
                        "division": division
                    }
                if game["awayTeam"] not in teams:
                    league, division = self.get_team_league_division(divisions, game["awayTeam"])
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
        return schedule, teams, odds, weathers

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
        if "set a win" in outcome.lower():
            return "Sunset"
        if "black hole swallowed" in outcome.lower():
            return "Black Hole"

    async def update_spreadsheets(self, seasons=[1, 2, 3, 4, 5, 6], fill=False):
        gc = gspread.service_account(os.path.join("gspread", "service_account.json"))
        schedule, teams, odds, weathers = self.base_season_parser(seasons, fill)
        league_records = {"Wild": {}, "Mild": {}}

        for season in schedule:
            season_outcomes = {}
            if self.bot.config['live_version']:
                sheet = gc.open_by_key(self.bot.SPREADSHEET_IDS[f"season{season}"])
            else:
                sheet = gc.open_by_key(self.bot.SPREADSHEET_IDS[f"seasontest"])
            print("Updating Team Schedules")
            day = 0
            for team in schedule[season]:
                s_worksheet = sheet.worksheet(spreadsheet_names[team]["schedule"])
                m_worksheet = sheet.worksheet(spreadsheet_names[team]["matchups"])
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
                            for o in game["outcomes"]:
                                if game["day"] not in season_outcomes:
                                    season_outcomes[game["day"]] = [o]
                                else:
                                    if o not in season_outcomes[game["day"]]:
                                        season_outcomes[game["day"]].append(o)
                                outcome_type = self.get_outcome_type(o)
                                team_name = teams[team]['name']
                                if outcome_type == "Sunset":
                                    match = re.search(r"upon the ([a-zA-Z ]+)", o)
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
                s_worksheet.update(f"A{2}:Q{i+1}", srows)

                if fill:
                    for opp in team_series:
                        row = [team_series[opp]["opponent"], '0', '0',
                               team_series[opp]['games'], team_series[opp]['game_type'],
                               team_series[opp]['home'], team_series[opp]['away']]
                        mrows.append(row)
                        j += 1
                    m_worksheet.update(f"A{3}:G{j}", mrows)

                    k = 16
                    if j >= 16:
                        k = j + 1
                    m_worksheet.update(f"B{k}:B{k+2}",
                                       [[f'=SUM(FILTER(D3:D{j},E3:E{j}="Division"))'],
                                        [f'=SUM(FILTER(D3:D{j},E3:E{j}="League"))'],
                                        [f'=SUM(FILTER(D3:D{j},E3:E{j}="InterLeague"))']
                                        ], raw=False)
                    m_worksheet.update(f"F{k}:F{k+1}", [[f'=sum(F3:F{j})'], [f'=sum(G3:G{j})']], raw=False)
                else:
                    for opp in team_series:
                        row = [team_series[opp]['wins'], team_series[opp]['losses']]
                        mrows.append(row)
                        j += 1
                    m_worksheet.update(f"B{3}:C{j}", mrows)
                league_records[teams[team]['league']][teams[team]["name"]] = record
                if fill:
                    await asyncio.sleep(10)

            print("Updating Weather Events")
            orows, otypes = [], []
            for day in sorted(season_outcomes.keys()):
                for outcome in season_outcomes[day]:
                    outcome_type = self.get_outcome_type(outcome)
                    orows.append([day+1, outcome.strip()])
                    otypes.append([outcome_type])
            o_worksheet = sheet.worksheet("Blaseball")

            o_worksheet.merge_cells(f"B{9}:H{9 + len(orows)}", merge_type="MERGE_ROWS")
            o_worksheet.update(f"A{9}:B{9 + len(orows)}", orows)
            o_worksheet.update(f"I{9}:I{9 + len(otypes)}", otypes)

            if fill:
                weather_rows = []
                for w, count in weathers[season].items():
                    weather_name = weather_types[w]
                    w_row = [weather_name, count, f"{round((count/990)*1000)/10}%"]
                    weather_rows.append(w_row)
                o_worksheet.update(f"K{9}:M{9 + len(weather_rows)}", weather_rows)

            def generate_per_team_records(team_list, record):
                n_divisions = {"Wild High": ["Tigers", "Lift", "Wild Wings", "Firefighters", "Jazz Hands"],
                             "Wild Low": ["Spies", "Flowers", "Sunbeams", "Dale", "Tacos"],
                             "Mild High": ["Lovers", "Pies", "Garages", "Steaks", "Millennials"],
                             "Mild Low": ["Fridays", "Moist Talkers", "Breath Mints", "Shoe Thieves", "Magic"]
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
                            t_record = f'{record[team]["win"]}-{record[team]["loss"]}'
                            div_records[division]["win"] += record[team]["win"]
                            div_records[division]["loss"] += record[team]["loss"]
                            team_columns.append(t_record)
                for division in div_records:
                    d_record = f'{div_records[division]["win"]}-{div_records[division]["loss"]}'
                    team_list.append(d_record)
                team_list += team_columns

            def update_league(league, start_i):
                sorted_league = {k: v for k, v in
                                 sorted(league.items(),
                                        key=lambda item: item[1]["total"]["win"] + item[1]["win_modifier"],
                                        reverse=True)}
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
                    teams[i] += record["scored"], record["given"]

                s_worksheet.update(f"A{start_i-1}:AJ{start_i -1}",
                                   [["Team", "Wins", "Record", "Pct.", "GB", "Magic #",
                                    "Home", "Away", "Run Diff", "WH", "WL", "MH", "ML",
                                    "Lovers", "Crabs", "Millennials", "Firefighters", "Jazz Hands", "Spies",
                                     "Flowers", "Sunbeams", "Dale", "Tacos", "Tigers", "Moist Talkers",
                                     "Garages", "Steaks", "Breath Mints", "Fridays", "Pies", "Wild Wings",
                                     "Shoe Thieves", "Magic", "1-Run", "R Scored", "R Allowed"]])
                s_worksheet.update(f"A{start_i}:AJ{start_i + len(teams)}", teams)
                s_worksheet.update(f"C28", [[99-day]])

            s_worksheet = sheet.worksheet("Standings")
            if day <= 98:
                print("Updating Standings")
                update_league(league_records["Wild"], 4)
                update_league(league_records["Mild"], 17)

            print("Updating Odds")
            if season in odds:
                odds_rows = []
                header_row = ["Days", "Favored Wins", "Underdog Wins", "Game 1", "Game 2", "Game 3",
                              "Game 4", "Game 5", "Game 6", "Game 7", "Game 8", "Game 9", "Game 10"]
                bet_tiers = [.56, .57, .58, .59, .6, .61, .62, .63, .64, .65, .66, .67, .68]
                for i in bet_tiers:
                    header_row.append(f"{round(i*100)}%+ payout")
                odds_rows.append(header_row)
                total_betcounts = [0] * len(bet_tiers)
                for day in odds[season]:
                    payouts, bet_counts = self._calculate_payout(odds[season][day], bet_tiers)
                    rounded_odds = []
                    for i in range(len(odds[season][day]["odds"])):
                        #if odds[season][day]["weathers"][i] != 1 and odds[season][day]["weathers"][i] != 14:
                        o = odds[season][day]["odds"][i]
                        rounded_odds.append(round(o * 1000)/10)

                    rounded_odds.sort()
                    rounded_odds += [''] * (10 - len(rounded_odds))
                    row = [day+1, odds[season][day]["results"]["favored"], odds[season][day]["results"]["underdog"]]
                    row += rounded_odds
                    row += payouts
                    odds_rows.append(row)
                    for c in range(len(bet_counts)):
                        total_betcounts[c] += bet_counts[c]
                od_worksheet = sheet.worksheet("Daily Results")
                od_worksheet.update(f"A{4}:Z{4 + len(odds_rows)}", odds_rows)
                od_worksheet.update(f"N{2}:Z{2}", [total_betcounts])

            print("Updates Complete")
            await asyncio.sleep(5)

    @staticmethod
    def _calculate_payout(odds_dict, bet_tiers):
        weathers = odds_dict["weathers"]
        odds = odds_dict["odds"]
        payouts = [0] * len(bet_tiers)
        bet_counts = [0] * len(bet_tiers)
        for i in range(len(bet_tiers)):
            count = 0
            for j in range(len(odds)):
                odd = odds[j]
                if odd >= bet_tiers[i]:
                    #payouts[i] += round(1000 * (2 - 0.000335 * math.pow(100 * (odd - 0.5), 2.045)))
                    payouts[i] += round(1000 * (.571 + 1.429 / (1 + math.pow(3 * (odd - 0.5), .77))))
                    count += 1
                elif odd < 1 - bet_tiers[i]:
                    count += 1
            payouts[i] = payouts[i] - (1000 * count)
            bet_counts[i] = count
        return payouts, bet_counts

    @commands.command(name='update_divine_favor', aliases=['favor', 'divine', 'udf'])
    async def _update_divine_favor(self, ctx):
        url = 'https://www.blaseball.com/database/simulationdata'
        html_response = await utils.retry_request(url)
        if not html_response:
            return await ctx.send("Failed to acquire simulation data, cannot find league id.")
        league_id = html_response.json()['league']
        url = f"https://www.blaseball.com/database/league?id={league_id}"
        html_response = await utils.retry_request(url)
        if not html_response:
            return await ctx.send("Failed to acquire league data, cannot find tiebreaker id.")
        tiebreaker_id = html_response.json()['tiebreakers']
        url = f'https://www.blaseball.com/database/tiebreakers?id={tiebreaker_id}'
        html_response = await utils.retry_request(url)
        if not html_response:
            return await ctx.send("Failed to acquire tiebreaker data.")
        favor_data = html_response.json()
        html_response = await utils.retry_request('https://www.blaseball.com/database/allteams')
        if not html_response:
            return await ctx.send("Failed to acquire team data.")
        team_data = html_response.json()
        favor_rankings = {}
        count = 0
        for rank in favor_data[0]['order']:
            for team in team_data:
                if team['id'] == rank:
                    favor_rankings[team['nickname']] = count
                    count += 1
        self.bot.config['favor_rankings'] = self.bot.favor_rankings = favor_rankings

    @commands.command(name='update_spreadsheets', aliases=['us'])
    async def _update_spreadsheets(self, ctx, current_season: int, fill: bool = False):
        current_season -= 1
        await self.save_json_range(current_season, fill)
        await self.update_spreadsheets([current_season], fill)
        await ctx.send("Spreadsheets updated.")

    @commands.command(name="anc")
    async def _anc(self, ctx):
        html_response = await utils.retry_request('https://www.blaseball.com/database/allteams')
        if not html_response:
            return await ctx.send("Failed to acquire team data.")
        team_data = html_response.json()
        for team in team_data:
            out_str = ""
            players = team['bullpen']
            html_response = await utils.retry_request(f'https://www.blaseball.com/database/players?ids={",".join(players)}')
            if not html_response:
                return await ctx.send("Failed to acquire player data.")
            player_data = html_response.json()
            for player in player_data:
                out_str += f"{team['nickname']}\t{player['name']}\tbullpen\n"

            players= team['bench']
            html_response = await utils.retry_request(
                f'https://www.blaseball.com/database/players?ids={",".join(players)}')
            if not html_response:
                return await ctx.send("Failed to acquire player data.")
            player_data = html_response.json()
            for player in player_data:
                out_str += f"{team['nickname']}\t{player['name']}\tbench\n"
            print(out_str)

    @commands.command(aliases=['tsh'])
    async def _test_spreadsheet(self, ctx):
        gc = gspread.service_account(os.path.join("gspread", "service_account.json"))
        sheet = gc.open_by_key(self.bot.SPREADSHEET_IDS["season11"])
        s_worksheet = sheet.worksheet("Blaseball")
        s_worksheet.update(f"J1:J1", "test")

    @commands.command(aliases=['utb'])
    async def _update_tie_breakers(self, ctx):
        try:
            html_response = await utils.retry_request("https://www.blaseball.com/database/simulationdata")
            if not html_response:
                self.bot.logger.warn('Failed to acquire sim data')
                return
            sim_data = html_response.json()
            league_id = sim_data['league']
            html_response = await utils.retry_request(f"https://www.blaseball.com/database/league?id={league_id}")
            if not html_response:
                self.bot.logger.warn('Failed to acquire league data')
                return
            league_json = json.loads(html_response.content.decode('utf-8'))
            html_response = await utils.retry_request(f"https://www.blaseball.com/database/tiebreakers?id={league_json['tiebreakers']}")
            if not html_response:
                self.bot.logger.warn('Failed to acquire tiebreakers data')
                return
            new_ties_json = html_response.json()
            json_watcher = self.bot.get_cog("JsonWatcher")
            await json_watcher.update_bot_tiebreakers(new_ties_json)
        except Exception as e:
            self.bot.logger.warn(f"Failed to update tiebreakers: {e}")
            return await ctx.message.add_reaction(self.bot.failed_react)
        await ctx.message.add_reaction(self.bot.success_react)


def setup(bot):
    bot.add_cog(GameData(bot))
