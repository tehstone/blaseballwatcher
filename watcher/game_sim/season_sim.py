from decimal import Decimal
from os import path
from typing import Any, Dict
import os
import json
import time

import requests
from requests import Timeout

from watcher.game_sim.common import get_stlats_for_season, blood_name_map, PlayerBuff, enabled_player_buffs, convert_keys
from watcher.game_sim.common import BlaseballStatistics as Stats
from watcher.game_sim.common import ForbiddenKnowledge as FK
from watcher.game_sim.common import BloodType, Team, team_id_map, blood_id_map, fk_key, Weather, team_name_map
from watcher.game_sim.stadium import Stadium
from watcher.game_sim.team_state import TeamState, DEF_ID
from watcher.game_sim.game_state import GameState, InningHalf

lineups_by_team: Dict[str, Dict[int, str]] = {}
stlats_by_team: Dict[str, Dict[str, Dict[FK, float]]] = {}
buffs_by_team: Dict[str, Dict[str, Dict[PlayerBuff, int]]] = {}
game_stats_by_team: Dict[str, Dict[str, Dict[Stats, float]]] = {}
segmented_stats_by_team: Dict[str, Dict[int, Dict[str, Dict[Stats, float]]]] = {}
names_by_team: Dict[str, Dict[str, str]] = {}
blood_by_team: Dict[str, Dict[str, BloodType]] = {}
team_states: Dict[Team, TeamState] = {}
rotations_by_team: Dict[str, Dict[int, str]] = {}
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

day_lineup = {}
day_stlats = {}
day_buffs = {}
day_names = {}
day_blood = {}
day_rotations = {}
stadiums = {}


def setup_season(season:int, stats_segment_size:int, iterations:int):
    with open(os.path.join('data', 'season_sim', 'season_data', f"season{season + 1}.json"), 'r', encoding='utf8') as json_file:
        raw_season_data = json.load(json_file)
        failed = 0
        for game in raw_season_data:
            home_team_name = game["homeTeamName"]
            away_team_name = game["awayTeamName"]
            try:
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
                update_team_states(season, day, home_team, home_pitcher, weather, True, stats_segment_size)
                home_team_state = team_states[team_id_map[home_team]]
                update_team_states(season, day, away_team, away_pitcher, weather, False, stats_segment_size)
                away_team_state = team_states[team_id_map[away_team]]
                home_pitcher_name = day_names[day][home_team][home_team_state.starting_pitcher]
                away_pitcher_name = day_names[day][away_team][away_team_state.starting_pitcher]
                print(f'Day {day}, Weather {weather.name}: {away_team_name} ({away_pitcher_name}) at {home_team_name} ({home_pitcher_name})')
                game = GameState(
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
                home_wins, away_wins = 0, 0
                for x in range(0, iterations):
                    home_win = game.simulate_game()
                    if home_win:
                        home_wins += 1
                    else:
                        away_wins += 1
                    game.reset_game_state()
                home_odds_str = round(home_odds * 1000) / 10
                away_odds_str = round(away_odds * 1000) / 10
                print(f"{home_team_name}: {home_wins} ({home_wins/iterations}) - {home_odds_str}% "
                      f"{away_team_name}: {away_wins} ({away_wins/iterations}) - {away_odds_str}%")
            except KeyError:
                failed += 1
                print(f"failed to sim day {day} {home_team_name} vs {away_team_name} game")
        print(f"{failed} games failed to sim")


def load_all_state(season: int, future=False):
    if not future:
        if not path.exists(os.path.join('..', 'season_sim', 'stlats', f"s{season}_d98_stlats.json")):
            get_stlats_for_season(season)

    with open(os.path.join('data', 'season_sim', "ballparks.json"), 'r', encoding='utf8') as json_file:
        ballparks = json.load(json_file)
    for team in ballparks.keys():
        stadium = Stadium.from_ballpark_json(ballparks[team])
        stadiums[team] = stadium

    for day in range(0, 99):
        reset_daily_cache()
        if future:
            filename = os.path.join('data', 'season_sim', 'stlats', f"s{season}_d0_stlats.json")
            with open(filename, 'r', encoding='utf8') as json_file:
                player_stlats_list = json.load(json_file)
        else:
            filename = os.path.join('data', 'season_sim', 'stlats', f"s{season}_d{day}_stlats.json")
            with open(filename, 'r', encoding='utf8') as json_file:
                player_stlats_list = json.load(json_file)
        for player in player_stlats_list:
            if day == 6 and player["team_id"] == "105bc3ff-1320-4e37-8ef0-8d595cb95dd0":
                x = 1
            team_id = player["team_id"]
            player_id = player["player_id"]
            pos = int(player["position_id"]) + 1
            if "position_type_id" in player:
                if player["position_type_id"] == "0":
                    if team_id not in lineups_by_team:
                        lineups_by_team[team_id] = {}
                    lineups_by_team[team_id][pos] = player_id
                else:
                    if team_id not in rotations_by_team:
                        rotations_by_team[team_id] = {}
                    rotations_by_team[team_id][pos] = player_id
            else:
                if player["position_type"] == "BATTER":
                    if team_id not in lineups_by_team:
                        lineups_by_team[team_id] = {}
                    lineups_by_team[team_id][pos] = player_id
                else:
                    if team_id not in rotations_by_team:
                        rotations_by_team[team_id] = {}
                    rotations_by_team[team_id][pos] = player_id
            if team_id not in stlats_by_team:
                stlats_by_team[team_id] = {}
            stlats_by_team[team_id][player_id] = get_stlat_dict(player)

            mods = player["modifications"]
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

            if team_id not in segmented_stats_by_team:
                segmented_stats_by_team[team_id] = {}

            if team_id not in names_by_team:
                names_by_team[team_id] = {}
            names_by_team[team_id][player_id] = player["player_name"]

            if team_id not in blood_by_team:
                blood_by_team[team_id] = {}
            try:
                blood_by_team[team_id][player_id] = blood_id_map[int(player["blood"])]
            except ValueError:
                blood_by_team[team_id][player_id] = blood_name_map[player["blood"]]
            except TypeError:
                blood_by_team[team_id][player_id] = BloodType.A

        if day > 0 and (len(lineups_by_team) != len(day_lineup[day - 1]) or (len(rotations_by_team) != len(day_rotations[day - 1]))):
            day_lineup[day] = day_lineup[day-1]
            day_stlats[day] = day_stlats[day-1]
            day_buffs[day] = day_buffs[day-1]
            day_names[day] = day_names[day-1]
            day_blood[day] = day_blood[day-1]
            day_rotations[day] = day_rotations[day - 1]
        else:
            day_lineup[day] = lineups_by_team
            day_stlats[day] = stlats_by_team
            day_buffs[day] = buffs_by_team
            day_names[day] = names_by_team
            day_blood[day] = blood_by_team
            day_rotations[day] = rotations_by_team


def reset_daily_cache():
    global lineups_by_team
    global rotations_by_team
    global game_stats_by_team
    global segmented_stats_by_team
    global stlats_by_team
    global names_by_team
    global blood_by_team
    lineups_by_team = {}
    rotations_by_team = {}
    stlats_by_team = {}
    names_by_team = {}
    blood_by_team = {}


def get_stlat_dict(player: Dict[str, Any]) -> Dict[FK, float]:
    ret_val: Dict[FK, float] = {}
    for k in fk_key:
        str_name = fk_key[k]
        ret_val[k] = float(player[str_name])
    return ret_val


def update_team_states(season: int, day: int, team: str, starting_pitcher: str,
                       weather: Weather, is_home: bool, stats_segment_size: int):
    if team_id_map[team] not in team_states:
        if team in stadiums:
            stadium = stadiums[team]
        else:
            stadium = default_stadium
        if not starting_pitcher:
            starting_pitcher = day_rotations[day][team][1]
        team_states[team_id_map[team]] = TeamState(
            team_id=team,
            season=season,
            day=day,
            stadium=stadium,
            weather=weather,
            is_home=is_home,
            num_bases=4,
            balls_for_walk=4,
            strikes_for_out=3,
            outs_for_inning=3,
            lineup=day_lineup[day][team],
            rotation=day_rotations[day][team],
            starting_pitcher=starting_pitcher,
            cur_pitcher_pos=1,
            stlats=day_stlats[day][team],
            buffs=day_buffs[day][team],
            game_stats=game_stats_by_team[team],
            segmented_stats=segmented_stats_by_team[team],
            blood=day_blood[day][team],
            player_names=day_names[day][team],
            cur_batter_pos=1,
            segment_size=stats_segment_size,
        )
    else:
        team_states[team_id_map[team]].day = day
        team_states[team_id_map[team]].weather = weather
        team_states[team_id_map[team]].is_home = is_home
        # lineup_changed = False
        # if team_states[team_id_map[team]].lineup != day_lineup[day][team]:
        #     lineup_changed = True
        team_states[team_id_map[team]].lineup = day_lineup[day][team]
        team_states[team_id_map[team]].rotation = day_rotations[day][team]
        rotation_idx = team_states[team_id_map[team]].next_pitcher()
        team_states[team_id_map[team]].cur_pitcher_pos = rotation_idx
        if starting_pitcher:
            team_states[team_id_map[team]].starting_pitcher = starting_pitcher
        else:
            team_states[team_id_map[team]].starting_pitcher = team_states[team_id_map[team]].rotation[rotation_idx]
        team_states[team_id_map[team]].stlats = day_stlats[day][team]
        team_states[team_id_map[team]].player_buffs = day_buffs[day][team]
        team_states[team_id_map[team]].blood = day_blood[day][team]
        #team_states[team_id_map[team]].player_names = day_names[day][team]
        team_states[team_id_map[team]].update_player_names(day_names[day][team])
        team_states[team_id_map[team]].reset_team_state(lineup_changed=True)


def print_leaders(iterations):
    strikeouts = []
    hrs = []
    avg = []
    all_segmented_stats = {}
    for cur_team in team_states.keys():
        for player in team_states[cur_team].game_stats.keys():
            if Stats.PITCHER_STRIKEOUTS in team_states[cur_team].game_stats[player]:
                player_name = team_states[cur_team].player_names[player]
                value = team_states[cur_team].game_stats[player][Stats.PITCHER_STRIKEOUTS] / float(iterations)
                strikeouts.append((value, player_name))
            if Stats.BATTER_HRS in team_states[cur_team].game_stats[player]:
                player_name = team_states[cur_team].player_names[player]
                value = team_states[cur_team].game_stats[player][Stats.BATTER_HRS] / float(iterations)
                hrs.append((value, player_name))
            if Stats.BATTER_HITS in team_states[cur_team].game_stats[player]:
                player_name = team_states[cur_team].player_names[player]
                hits = team_states[cur_team].game_stats[player][Stats.BATTER_HITS]
                abs = team_states[cur_team].game_stats[player][Stats.BATTER_AT_BATS]
                value = hits / abs
                avg.append((value, player_name))
        for day, stats in team_states[cur_team].segmented_stats.items():
            if day not in all_segmented_stats:
                all_segmented_stats[day] = {}
            for player_id, player_stats in stats.items():
                if player_id not in team_states[cur_team].player_names:
                    continue
                all_segmented_stats[day][player_id] = {"name": team_states[cur_team].player_names[player_id]}
                for stat in [Stats.PITCHER_STRIKEOUTS, Stats.BATTER_HITS, Stats.BATTER_HRS, Stats.STOLEN_BASES]:
                    if stat in player_stats:
                        all_segmented_stats[day][player_id][stat] = player_stats[stat] / float(iterations)
    filename = os.path.join("data", "season_sim", "results", f"{round(time.time())}_all_segmented_stats.json")
    with open(filename, 'w') as f:
        json.dump(convert_keys(all_segmented_stats), f)

    print("STRIKEOUTS")
    count = 0
    for value, name in reversed(sorted(strikeouts)):
        if count == 10:
            break
        print(f'\t{name}: {value}')
        count += 1
    print("HRS")
    count = 0
    for value, name in reversed(sorted(hrs)):
        if count == 10:
            break
        print(f'\t{name}: {value}')
        count += 1
    print("avg")
    count = 0
    for value, name in reversed(sorted(avg)):
        if count == 10:
            break
        print(f'\t{name}: {value:.3f}')
        count += 1
    return all_segmented_stats


def leader_per_segment(stats, segment_size):
    all_season = {}
    all_stats_by_segment = {}
    day = 0
    total_hits_coins = 0
    total_hrs_coins = 0
    total_sb_coins = 0
    total_pd_best_coins = 0
    valentine_games_coins = 0
    don_mitchell_coins = 0
    goodwin_morin_coins = 0
    payouts = {
        "Batter hrs coins": 1645,
        "Batter hits coins": 935,
        "Stolen bases coins": 2640,
        "Pitcher Strikeouts coins": 81
    }

    for i in range(0, 99//segment_size):
        segment = (i * segment_size)
        seg_stats = {}
        for j in range(0, segment_size):
            day = str(segment + j)
            for player_id, day_stats in stats[day].items():
                if player_id not in all_season:
                    all_season[player_id] = {
                        "name": day_stats["name"],
                        "Pitcher Strikeouts": 0,
                        "Pitcher Strikeouts coins": 0,
                        "Batter hits": 0,
                        "Batter hits coins": 0,
                        "Batter hrs": 0,
                        "Batter hrs coins": 0,
                        "Stolen bases": 0,
                        "Stolen bases coins": 0
                    }
                if player_id not in seg_stats:
                    seg_stats[player_id] = {
                        "name": day_stats["name"],
                        "Pitcher Strikeouts": 0,
                        "Pitcher Strikeouts coins": 0,
                        "Batter hits": 0,
                        "Batter hits coins": 0,
                        "Batter hrs": 0,
                        "Batter hrs coins": 0,
                        "Stolen bases": 0,
                        "Stolen bases coins": 0
                    }
                for stat in day_stats:
                    if stat != "name":
                        c_stat = stat + " coins"
                        seg_stats[player_id][stat] += day_stats[stat]
                        seg_stats[player_id][c_stat] += payouts[c_stat] * day_stats[stat]

                        all_season[player_id][stat] += round(day_stats[stat])
                        all_season[player_id][c_stat] += round(payouts[c_stat]) * day_stats[stat]
        all_stats_by_segment[segment] = seg_stats
    day = int(day)
    day += 1
    if day < 98:
        seg_stats = {}
        for d in range(day, 99):
            d = str(d)
            for player_id, day_stats in stats[d].items():
                if player_id not in all_season:
                    all_season[player_id] = {
                        "name": day_stats["name"],
                        "Pitcher Strikeouts": 0,
                        "Pitcher Strikeouts coins": 0,
                        "Batter hits": 0,
                        "Batter hits coins": 0,
                        "Batter hrs": 0,
                        "Batter hrs coins": 0,
                        "Stolen bases": 0,
                        "Stolen bases coins": 0
                    }
                if player_id not in seg_stats:
                    seg_stats[player_id] = {
                        "name": day_stats["name"],
                        "Pitcher Strikeouts": 0,
                        "Pitcher Strikeouts coins": 0,
                        "Batter hits": 0,
                        "Batter hits coins": 0,
                        "Batter hrs": 0,
                        "Batter hrs coins": 0,
                        "Stolen bases": 0,
                        "Stolen bases coins": 0
                    }
                for stat in day_stats:
                    if stat != "name":
                        c_stat = stat + " coins"
                        seg_stats[player_id][stat] += day_stats[stat]
                        seg_stats[player_id][c_stat] += payouts[c_stat] * day_stats[stat]

                        all_season[player_id][stat] += round(day_stats[stat])
                        all_season[player_id][c_stat] += round(payouts[c_stat]) * day_stats[stat]
            all_stats_by_segment[day] = seg_stats
    sorted_hits = {k: v for k, v in
                   sorted(all_season.items(), key=lambda item: item[1]["Batter hits"], reverse=True)}
    sorted_hrs = {k: v for k, v in
                  sorted(all_season.items(), key=lambda item: item[1]["Batter hrs"], reverse=True)}
    sorted_stolen_bases = {k: v for k, v in
                  sorted(all_season.items(), key=lambda item: item[1]["Stolen bases"], reverse=True)}
    top_str = f"Season Leaders\n"
    for key in list(sorted_hits.keys())[:10]:
        top_str += f"{sorted_hits[key]['name']} - {round(sorted_hits[key]['Batter hits'])} hits\n"
    for key in list(sorted_hrs.keys())[:10]:
        top_str += f"{sorted_hrs[key]['name']} - {round(sorted_hrs[key]['Batter hrs'])} hrs\n"
    for key in list(sorted_stolen_bases.keys())[:10]:
        top_str += f"{sorted_stolen_bases[key]['name']} - {round(sorted_stolen_bases[key]['Stolen bases'])} sbs\n"
    print(top_str)
    #return
    top_hrs = ""
    top_hits = ""
    top_sbs = ""
    for segment, segment_stats in all_stats_by_segment.items():
        sorted_hits = {k: v for k, v in sorted(segment_stats.items(), key=lambda item: item[1]["Batter hits"], reverse=True)}
        sorted_hrs = {k: v for k, v in
                       sorted(segment_stats.items(), key=lambda item: item[1]["Batter hrs"], reverse=True)}
        sorted_stolen_bases = {k: v for k, v in
                       sorted(segment_stats.items(), key=lambda item: item[1]["Stolen bases"], reverse=True)}
        top_str = f"Days {segment}-{segment + segment_size - 1}\n"

        for key in list(sorted_hits.keys())[:1]:
            top_hits += f"{sorted_hits[key]['name']}\t{round(sorted_hits[key]['Batter hits'])}\n"
            top_str += f"{sorted_hits[key]['name']} - {round(sorted_hits[key]['Batter hits'])} hits\n"
        for key in list(sorted_hrs.keys())[:1]:
            top_hrs += f"{sorted_hrs[key]['name']}\t{round(sorted_hrs[key]['Batter hrs'])}\n"
            top_str += f"{sorted_hrs[key]['name']} - {round(sorted_hrs[key]['Batter hrs'])} hrs\n"
        for key in list(sorted_stolen_bases.keys())[:1]:
            top_sbs += f"{sorted_stolen_bases[key]['name']}\t{round(sorted_stolen_bases[key]['Stolen bases'])}\n"
            top_str += f"{sorted_stolen_bases[key]['name']} - {round(sorted_stolen_bases[key]['Stolen bases'])} sbs\n"
        print(top_str)
    with open(os.path.join('data', 'season_sim', 'results', "1616749629_top_hits.txt"), 'w',
              encoding='utf8') as json_file:
        json_file.write(top_hits)

    with open(os.path.join('data', 'season_sim', 'results', "1616749629_top_hrs.txt"), 'w',
              encoding='utf8') as json_file:
        json_file.write(top_hrs)
    with open(os.path.join('data', 'season_sim', 'results', "1616749629_top_sbs.txt"), 'w',
              encoding='utf8') as json_file:
        json_file.write(top_sbs)

def retry_request(day=0):
    headers = {
        'User-Agent': 'sibrDataWatcher/0.5test (tehstone#8448@sibr)'
    }
    url = f"https://www.blaseball.com/database/games?day={day}&season=14"
    for i in range(5):
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                return response
        except (Timeout, Exception):
            continue
        finally:
            time.sleep(.5)
    return None

def sim_season(iterations, season):
    # iterations = 25
    # season = 13
    stats_segment_size = 3
    #print_info()
    t1 = time.time()
    print(f"Starting at {t1}")
    load_all_state(season)
    setup_season(season, stats_segment_size, iterations)
    all_segmented_stats = print_leaders(iterations)
    # with open(os.path.join('..', 'season_sim', 'results', "1617527985_all_segmented_stats.json"), 'r',
    #           encoding='utf8') as json_file:
    #     all_segmented_stats = json.load(json_file)
    t2 = time.time()
    print(f"Finished at {t2}, total runtime: {round(t2 - t1)}")
    leader_per_segment(all_segmented_stats, stats_segment_size)


# while True:
#     season_schedule = []
#     games = retry_request()
#     if games:
#         games_list = games.json()
#         if len(games_list) > 0:
#             for g in games_list:
#                 season_schedule.append(g)
#             for i in range(1, 99):
#                 day_games = retry_request(i)
#                 games_list = games.json()
#                 for g in games_list:
#                     season_schedule.append(g)
#             with open(os.path.join('..', 'season_sim', 'season_data', f"season15.json"), 'w',
#                       encoding='utf8') as json_file:
#                 json.dump(season_schedule, json_file)
#             break
#     sleep_delay = 300
#     print(f"No games found yet at {time.time()}. Retrying in {sleep_delay} seconds.")
#     time.sleep(sleep_delay)

sim_season(100, 14)
