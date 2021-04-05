import asyncio
import json
import os
from decimal import Decimal
from typing import Dict, Any, List

import requests
from requests import Timeout

from watcher.game_sim.common import enabled_player_buffs
from watcher.game_sim.common import BlaseballStatistics as Stats, blood_name_map
from watcher.game_sim.common import ForbiddenKnowledge as FK
from watcher.game_sim.common import BloodType, Team, blood_id_map, fk_key, PlayerBuff, Weather
from watcher.game_sim.team_state import TeamState, DEF_ID
from watcher.game_sim.game_state import GameState, InningHalf
from watcher.game_sim.stadium import Stadium

lineups_by_team: Dict[str, Dict[int, str]] = {}
stlats_by_team: Dict[str, Dict[str, Dict[FK, float]]] = {}
buffs_by_team: Dict[str, Dict[str, Dict[PlayerBuff, int]]] = {}
game_stats_by_team: Dict[str, Dict[str, Dict[Stats, float]]] = {}
segmented_stats_by_team: Dict[str, Dict[int, Dict[str, Dict[Stats, float]]]] = {}
names_by_team: Dict[str, Dict[str, str]] = {}
blood_by_team: Dict[str, Dict[str, BloodType]] = {}
team_states: Dict[Team, TeamState] = {}
starting_pitchers: Dict[str, str] = {}
default_stadium: Stadium = Stadium(
    "team_id",
    "stadium_id",
    "stadium_name",
    0.5,
    0.5,
    0.5,
    0.5,
    0.5,
    0.5,
    0.5,
)


async def retry_request(url, tries=10):
    headers = {
        'User-Agent': 'sibrGameSim/0.1test (tehstone#8448@sibr)'
    }

    for i in range(tries):
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                return response
        except (Timeout, Exception):
            continue
        finally:
            await asyncio.sleep(.5)
    return None


def get_stlat_dict(player: Dict[str, Any]) -> Dict[FK, float]:
    ret_val: Dict[FK, float] = {}
    for k in fk_key:
        str_name = fk_key[k]
        ret_val[k] = float(player[str_name])
    return ret_val


async def get_current_player_stlats(season, day, team_ids):
    filename = os.path.join('data', 'season_sim', "stlats", f"s{season}_d{day}_stlats.json")
    try:
        with open(filename, 'r', encoding='utf8', ) as json_file:
            stlats_json = json.load(json_file)
        return stlats_json
    except FileNotFoundError:
        stlats_json = {}
        pitchers = {}
        batters = {}
        teams_response = await retry_request("https://www.blaseball.com/database/allteams")
        teams_json = teams_response.json()
        for team in teams_json:
            if team["id"] not in team_ids:
                continue
            p_counter = 1
            b_counter = 1
            for pitcher in team["rotation"]:
                pitchers[pitcher] = {
                    "position_id": p_counter,
                    "position_type": "PITCHER"}
                p_counter += 1
            for batter in team["lineup"]:
                batters[batter] = {
                    "position_id": b_counter,
                    "position_type": "BATTER"
                }
                b_counter += 1
        pitcher_ids = list(pitchers.keys())
        chunked_pitcher_ids = [pitcher_ids[i:i + 50] for i in range(0, len(pitcher_ids), 50)]
        for chunk in chunked_pitcher_ids:
            b_url = f"https://www.blaseball.com/database/players?ids={','.join(chunk)}"
            pitcher_response = await retry_request(b_url)
            pitcher_json = pitcher_response.json()
            for pitcher in pitcher_json:
                pitcher["position_id"] = pitchers[pitcher["id"]]["position_id"]
                pitcher["position_type"] = pitchers[pitcher["id"]]["position_type"]
                stlats_json[pitcher["id"]] = pitcher
        batter_ids = list(batters.keys())
        chunked_batter_ids = [batter_ids[i:i + 50] for i in range(0, len(batter_ids), 50)]
        for chunk in chunked_batter_ids:
            b_url = f"https://www.blaseball.com/database/players?ids={','.join(chunk)}"
            batter_response = await retry_request(b_url)
            batter_json = batter_response.json()
            for batter in batter_json:
                batter["position_id"] = batters[batter["id"]]["position_id"]
                batter["position_type"] = batters[batter["id"]]["position_type"]
                stlats_json[batter["id"]] = batter
        with open(filename, 'w', encoding='utf8') as json_file:
            json.dump(stlats_json, json_file)
        return stlats_json


async def setup_stlats(season: int, day: int, team_ids: List):
    player_stlats_list = await get_current_player_stlats(season, day, team_ids)
    for player_id, player in player_stlats_list.items():
        team_id = player["leagueTeamId"]
        pos = int(player["position_id"])
        if "position_type_id" in player:
            if player["position_type_id"] == "0":
                if team_id not in lineups_by_team:
                    lineups_by_team[team_id] = {}
                lineups_by_team[team_id][pos] = player_id
            else:
                if team_id not in starting_pitchers:
                    starting_pitchers[team_id] = player_id
        else:
            if player["position_type"] == "BATTER":
                if team_id not in lineups_by_team:
                    lineups_by_team[team_id] = {}
                lineups_by_team[team_id][pos] = player_id
            else:
                if team_id not in starting_pitchers:
                    starting_pitchers[team_id] = player_id

        if team_id not in stlats_by_team:
            stlats_by_team[team_id] = {}
        stlats_by_team[team_id][player_id] = get_stlat_dict(player)

        mods = player["permAttr"]
        cur_mod_dict = {}
        if mods:
            for mod in mods:
                if mod in enabled_player_buffs:
                    cur_mod_dict[PlayerBuff[mod]] = 1
            if player_id == "4b3e8e9b-6de1-4840-8751-b1fb45dc5605":
                cur_mod_dict[PlayerBuff.BLASERUNNING] = 1
        if team_id not in buffs_by_team:
            buffs_by_team[team_id] = {}
        buffs_by_team[team_id][player_id] = cur_mod_dict

        if team_id not in game_stats_by_team:
            game_stats_by_team[team_id] = {}
            game_stats_by_team[team_id][DEF_ID] = {}
        game_stats_by_team[team_id][player_id] = {}

        if team_id not in buffs_by_team:
            buffs_by_team[team_id] = {}
        buffs_by_team[team_id][player_id] = {}

        if team_id not in segmented_stats_by_team:
            segmented_stats_by_team[team_id] = {}

        if team_id not in names_by_team:
            names_by_team[team_id] = {}
        names_by_team[team_id][player_id] = player["name"]

        if team_id not in blood_by_team:
            blood_by_team[team_id] = {}
        try:
            blood_by_team[team_id][player_id] = blood_id_map[int(player["blood"])]
        except ValueError:
            blood_by_team[team_id][player_id] = blood_name_map[player["blood"]]
        except TypeError:
            blood_by_team[team_id][player_id] = BloodType.A


def make_team_state(team, pitcher, ballparks, season, day):
    if team in ballparks.keys():
        park = ballparks[team]
        stadium = Stadium.from_ballpark_json(park)
    else:
        stadium = default_stadium
    return TeamState(
        team_id=team,
        season=season,
        day=day,
        stadium=stadium,
        weather=Weather.SUN2,
        is_home=True,
        num_bases=4,
        balls_for_walk=4,
        strikes_for_out=3,
        outs_for_inning=3,
        lineup=lineups_by_team[team],
        rotation={1: "starting_pitcher"},
        starting_pitcher=pitcher,
        cur_pitcher_pos=0,
        stlats=stlats_by_team[team],
        buffs=buffs_by_team[team],
        game_stats=game_stats_by_team[team],
        segmented_stats=segmented_stats_by_team[team],
        blood=blood_by_team[team],
        player_names=names_by_team[team],
        cur_batter_pos=1,
    )


async def run_daily_sim(iterations=250):
    html_response = await retry_request("https://www.blaseball.com/database/simulationdata")
    if not html_response:
        print('Bet Advice daily message failed to acquire sim data and exited.')
        return
    sim_data = html_response.json()
    season = sim_data['season']
    day = sim_data['day'] + 1
    games = await retry_request(f"https://www.blaseball.com/database/games?day={day}&season={season}")
    games_json = games.json()
    team_ids = []
    [team_ids.append(g['homeTeam']) for g in games_json]
    [team_ids.append(g['awayTeam']) for g in games_json]
    await setup_stlats(season, day, team_ids)
    with open(os.path.join('data', 'season_sim', "ballparks.json"), 'r', encoding='utf8') as json_file:
        ballparks = json.load(json_file)
    results = {}
    for game in games_json:
        home_team_name = game["homeTeamName"]
        away_team_name = game["awayTeamName"]
        game_id = game["id"]
        day = int(game["day"])
        home_pitcher = game["homePitcher"]
        away_pitcher = game["awayPitcher"]
        home_team = game["homeTeam"]
        away_team = game["awayTeam"]
        home_odds = game["homeOdds"]
        away_odds = game["awayOdds"]

        weather = Weather(game["weather"])

        if day == 99:
            break

        home_team_state = make_team_state(home_team, home_pitcher, ballparks, season, day)
        away_team_state = make_team_state(away_team, away_pitcher, ballparks, season, day)

        game_sim = GameState(
            game_id=game_id,
            season=season,
            day=day,
            stadium=home_team_state.stadium,
            home_team=home_team_state,
            away_team=away_team_state,
            home_score=Decimal("0"),
            away_score=Decimal("0"),
            inning=1,
            half=InningHalf.TOP,
            outs=0,
            strikes=0,
            balls=0,
            weather=weather
        )
        home_scores, away_scores = [], []
        for x in range(0, iterations):
            home_score, away_score = game_sim.simulate_game()
            home_scores.append(home_score)
            away_scores.append(away_score)
            game_sim.reset_game_state()

        home_wins = home_team_state.game_stats["TEAM"].get(Stats.TEAM_WINS, 0)
        away_wins = away_team_state.game_stats["TEAM"].get(Stats.TEAM_WINS, 0)
        home_odds_str = round(home_odds * 1000) / 10
        away_odds_str = round(away_odds * 1000) / 10
        print(f"{home_team_name}: {home_wins} ({home_wins / iterations}) - {home_odds_str}% "
              f"{away_team_name}: {away_wins} ({away_wins / iterations}) - {away_odds_str}%")
        home_win_per = round((home_wins / iterations) * 1000) / 10
        away_win_per = round((away_wins / iterations) * 1000) / 10

        home_ks = 0
        for player_id, stats in home_team_state.game_stats.items():
            if Stats.BATTER_STRIKEOUTS in stats:
                home_ks += stats[Stats.BATTER_STRIKEOUTS]
        away_ks = 0
        for player_id, stats in away_team_state.game_stats.items():
            if Stats.BATTER_STRIKEOUTS in stats:
                away_ks += stats[Stats.BATTER_STRIKEOUTS]
        home_k_per = round((home_ks / iterations) * 100) / 100
        away_k_per = round((away_ks / iterations) * 100) / 100

        away_shutouts = 0
        for player_id, stats in home_team_state.game_stats.items():
            if Stats.PITCHER_SHUTOUTS in stats:
                away_shutouts += stats[Stats.PITCHER_SHUTOUTS]
        home_shutouts = 0
        for player_id, stats in away_team_state.game_stats.items():
            if Stats.PITCHER_SHUTOUTS in stats:
                home_shutouts += stats[Stats.PITCHER_SHUTOUTS]
        home_shutout_per = round((home_shutouts / iterations) * 1000) / 10
        away_shutout_per = round((away_shutouts / iterations) * 1000) / 10

        home_big_scores = sum(1 for x in home_scores if x > 10) / iterations
        away_big_scores = sum(1 for x in away_scores if x > 10) / iterations
        home_xbig_scores = sum(1 for x in home_scores if x > 20) / iterations
        away_xbig_scores = sum(1 for x in away_scores if x > 20) / iterations

        upset = False
        home_odds = game["homeOdds"]
        away_odds = game["awayOdds"]
        if home_odds > away_odds:
            if away_wins > home_wins:
                upset = True
        else:
            if home_wins > away_wins:
                upset = True

        results[game['homeTeam']] = {
            "game_info": {
                "id": game["id"],
                "homeOdds": game["homeOdds"],
                "awayOdds": game["awayOdds"],
                "homeTeam": game["homeTeam"],
                "awayTeam": game["awayTeam"],
                "homeTeamName": game["homeTeamName"],
                "awayTeamName": game["awayTeamName"]
            },
            "upset": upset,
            "shutout_percentage": home_shutout_per,
            "win_percentage": home_win_per,
            "strikeout_avg": home_k_per,
            "over_ten": home_big_scores,
            "over_twenty": home_xbig_scores,
            "weather": game['weather'],
            "opp_pitcher": {
                "pitcher_id": away_pitcher,
                "pitcher_name": game["awayPitcherName"],
                "p_team_id": away_team,
                "p_team_name": game["awayTeamName"]
                }
             }
        results[game['awayTeam']] = {
            "game_info": {
                "id": game["id"],
                "homeOdds": game["homeOdds"],
                "awayOdds": game["awayOdds"],
                "homeTeam": game["homeTeam"],
                "awayTeam": game["awayTeam"],
                "homeTeamName": game["homeTeamName"],
                "awayTeamName": game["awayTeamName"]
            },
            "upset": upset,
            "shutout_percentage": away_shutout_per,
            "win_percentage": away_win_per,
            "strikeout_avg": away_k_per,
            "over_ten": away_big_scores,
            "over_twenty": away_xbig_scores,
            "weather": game['weather'],
            "opp_pitcher": {
                "pitcher_id": home_pitcher,
                "pitcher_name": game["homePitcherName"],
                "p_team_id": home_team,
                "p_team_name": game["homeTeamName"]
            }
        }
    return results, day
