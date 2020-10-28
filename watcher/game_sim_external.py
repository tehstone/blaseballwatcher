import asyncio
import json
import os
import random

import requests
import statistics

from joblib import load
from requests import Timeout

import time

team_names = {
"b72f3061-f573-40d7-832a-5ad475bd7909": "Lovers",
"878c1bf6-0d21-4659-bfee-916c8314d69c": "Tacos",
"b024e975-1c4a-4575-8936-a3754a08806a": "Steaks",
"adc5b394-8f76-416d-9ce9-813706877b84": "Breath Mints",
"ca3f1c8c-c025-4d8e-8eef-5be6accbeb16": "Firefighters",
"bfd38797-8404-4b38-8b82-341da28b1f83": "Shoe Thieves",
"3f8bbb15-61c0-4e3f-8e4a-907a5fb1565e": "Flowers",
"979aee4a-6d80-4863-bf1c-ee1a78e06024": "Fridays",
"7966eb04-efcc-499b-8f03-d13916330531": "Magic",
"36569151-a2fb-43c1-9df7-2df512424c82": "Millennials",
"8d87c468-699a-47a8-b40d-cfb73a5660ad": "Crabs",
"9debc64f-74b7-4ae1-a4d6-fce0144b6ea5": "Spies",
"23e4cbc1-e9cd-47fa-a35b-bfa06f726cb7": "Pies",
"f02aeae2-5e6a-4098-9842-02d2273f25c7": "Sunbeams",
"57ec08cc-0411-4643-b304-0e80dbc15ac7": "Wild Wings",
"747b8e4a-7e50-4638-a973-ea7950a3e739": "Tigers",
"eb67ae5e-c4bf-46ca-bbbc-425cd34182ff": "Moist Talkers",
"b63be8c2-576a-4d6e-8daf-814f8bcea96f": "Dale",
"105bc3ff-1320-4e37-8ef0-8d595cb95dd0": "Garages",
"a37f9158-7f82-46bc-908c-c9e2dda7c33b": "Jazz Hands",
"c73b705c-40ad-4633-a6ed-d357ee2e2bcf": "Lift"
}
team_effects = {"3f8bbb15-61c0-4e3f-8e4a-907a5fb1565e": {"growth": 8}}
blood_effect = {"f02aeae2-5e6a-4098-9842-02d2273f25c7": {"base_instincts": {"season": 8, "blood": 4}}}
base_instincts_procs = {8: {2: 0, 3: 0}, 9: {2: 0, 3: 0}, 10: {2: 0, 3: 0}}
stlat_list = ["anticapitalism", "chasiness", "omniscience", "tenaciousness", "watchfulness", "pressurization",
              "cinnamon", "buoyancy", "divinity", "martyrdom", "moxie", "musclitude", "patheticism", "thwackability",
              "tragicness", "base_thirst", "continuation", "ground_friction", "indulgence", "laserlikeness",
              "coldness", "overpowerment", "ruthlessness", "shakespearianism", "suppression", "unthwackability"]


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


def apply_effect(def_stlats, effect, day):
    if effect == "growth":
        def_stlats = {k: float(v) * (1.0 + (day / 99 * 0.05)) for (k, v) in def_stlats.items() if k in stlat_list}
    return def_stlats


def apply_effect_deep(def_stlats, effect, day):
    if effect == "growth":
        for key, stlats in def_stlats.items():
            def_stlats[key] = {k: float(v) * (1.0 + (day / 99 * 0.05)) for (k, v) in stlats.items() if k in stlat_list}
    return def_stlats


async def setup_models(games, clf, player_stlats, team_stlats):
    models = {"pitch": {}, "is_hit": {}, "hit_type": {},
              "runner_adv_out": {}, "runner_adv_hit": {},
              "sb_attempt": {}, "sb_success": {}}
    for game in games:
        if game["homePitcher"] not in player_stlats:
            continue
        if game["awayPitcher"] not in player_stlats:
            continue
        home_pitcher = player_stlats[game["homePitcher"]]
        away_pitcher = player_stlats[game["awayPitcher"]]
        home_hitters = home_defense = team_stlats[game['homeTeam']]["lineup"]
        away_hitters = away_defense = team_stlats[game['awayTeam']]["lineup"]
        if game["homeTeam"] in team_effects:
            for effect, start_season in team_effects[game["homeTeam"]].items():
                if game["season"] >= start_season:
                    home_defense = apply_effect_deep(home_defense, effect, game["day"])
                    home_hitters = apply_effect_deep(home_hitters, effect, game["day"])
                    home_pitcher = apply_effect(home_pitcher, effect, game["day"])
        if game["awayTeam"] in team_effects:
            for effect, start_season in team_effects[game["awayTeam"]].items():
                if game["season"] >= start_season:
                    away_defense = apply_effect_deep(away_defense, effect, game["day"])
                    away_hitters = apply_effect_deep(away_hitters, effect, game["day"])
                    away_pitcher = apply_effect(away_pitcher, effect, game["day"])
        h_anticapitalism = statistics.mean([float(d["anticapitalism"]) for d in home_defense.values()])
        h_chasiness = statistics.mean([float(d["chasiness"]) for d in home_defense.values()])
        h_omniscience = statistics.mean([float(d["omniscience"]) for d in home_defense.values()])
        h_tenaciousness = statistics.mean([float(d["tenaciousness"]) for d in home_defense.values()])
        h_watchfulness = statistics.mean([float(d["watchfulness"]) for d in home_defense.values()])
        h_defense_pressurization = statistics.mean([float(d["pressurization"]) for d in home_defense.values()])
        h_defense_cinnamon = statistics.mean([float(d["cinnamon"]) for d in home_defense.values()])
        a_anticapitalism = statistics.mean([float(d["anticapitalism"]) for d in away_defense.values()])
        a_chasiness = statistics.mean([float(d["chasiness"]) for d in away_defense.values()])
        a_omniscience = statistics.mean([float(d["omniscience"]) for d in away_defense.values()])
        a_tenaciousness = statistics.mean([float(d["tenaciousness"]) for d in away_defense.values()])
        a_watchfulness = statistics.mean([float(d["watchfulness"]) for d in away_defense.values()])
        a_defense_pressurization = statistics.mean([float(d["pressurization"]) for d in away_defense.values()])
        a_defense_cinnamon = statistics.mean([float(d["cinnamon"]) for d in away_defense.values()])
        hit_model_arrs = []
        run_model_arrs = []
        sorted_h_hitters = {k: v for k, v in
                            sorted(home_hitters.items(), key=lambda item: item[0])}
        sorted_a_hitters = {k: v for k, v in
                            sorted(away_hitters.items(), key=lambda item: item[0])}
        for __, hitter in sorted_h_hitters.items():
            h_arr = []
            r_arr = []
            for stlat in ["buoyancy", "divinity", "martyrdom", "moxie", "musclitude", "patheticism",
                          "thwackability", "tragicness", "base_thirst", "continuation",
                          "ground_friction", "indulgence", "laserlikeness", "cinnamon", "pressurization"]:
                h_arr.append(float(hitter[stlat]))
            for stlat in ['base_thirst', 'continuation', 'ground_friction', 'indulgence',
                          'laserlikeness', 'cinnamon', 'pressurization']:
                r_arr.append(float(hitter[stlat]))
            for stlat in ["coldness", "overpowerment", "ruthlessness", "shakespearianism",
                          "suppression", "unthwackability", "cinnamon", "pressurization"]:
                h_arr.append(float(away_pitcher[stlat]))
                r_arr.append(float(away_pitcher[stlat]))
            h_arr += [a_anticapitalism, a_chasiness, a_omniscience, a_tenaciousness,
                      a_watchfulness, a_defense_pressurization, a_defense_cinnamon]
            r_arr += [a_anticapitalism, a_chasiness, a_omniscience, a_tenaciousness,
                      a_watchfulness, a_defense_pressurization, a_defense_cinnamon]
            hit_model_arrs.append(h_arr)
            run_model_arrs.append(r_arr)
        for __, hitter in sorted_a_hitters.items():
            h_arr = []
            r_arr = []
            for stlat in ["buoyancy", "divinity", "martyrdom", "moxie", "musclitude", "patheticism",
                          "thwackability", "tragicness", "base_thirst", "continuation",
                          "ground_friction", "indulgence", "laserlikeness", "cinnamon", "pressurization"]:
                h_arr.append(float(hitter[stlat]))
            for stlat in ['base_thirst', 'continuation', 'ground_friction', 'indulgence',
                          'laserlikeness', 'cinnamon', 'pressurization']:
                r_arr.append(float(hitter[stlat]))
            for stlat in ["coldness", "overpowerment", "ruthlessness", "shakespearianism",
                          "suppression", "unthwackability", "cinnamon", "pressurization"]:
                h_arr.append(float(home_pitcher[stlat]))
                r_arr.append(float(home_pitcher[stlat]))
            h_arr += [h_anticapitalism, h_chasiness, h_omniscience, h_tenaciousness,
                      h_watchfulness, h_defense_pressurization, h_defense_cinnamon]
            r_arr += [h_anticapitalism, h_chasiness, h_omniscience, h_tenaciousness,
                      h_watchfulness, h_defense_pressurization, h_defense_cinnamon]
            hit_model_arrs.append(h_arr)
            run_model_arrs.append(r_arr)
        is_hit = clf["is_hit"].predict_proba(hit_model_arrs)
        pitch = clf["pitch"].predict_proba(hit_model_arrs)
        hit_type = clf["hit_type"].predict_proba(hit_model_arrs)

        runner_adv_out = clf["runner_adv_out"].predict_proba(run_model_arrs)
        runner_adv_hit = clf["runner_adv_hit"].predict_proba(run_model_arrs)
        sb_attempt = clf["sb_attempt"].predict_proba(run_model_arrs)
        sb_success = clf["sb_success"].predict_proba(run_model_arrs)
        counter = 0
        for hitter, __ in sorted_h_hitters.items():
            models["is_hit"][hitter] = is_hit[counter]
            models["pitch"][hitter] = pitch[counter]
            models["hit_type"][hitter] = hit_type[counter]
            models["runner_adv_out"][hitter] = runner_adv_out[counter]
            models["runner_adv_hit"][hitter] = runner_adv_hit[counter]
            models["sb_attempt"][hitter] = sb_attempt[counter]
            models["sb_success"][hitter] = sb_success[counter]
            counter += 1
        for hitter, __ in sorted_a_hitters.items():
            models["is_hit"][hitter] = is_hit[counter]
            models["pitch"][hitter] = pitch[counter]
            models["hit_type"][hitter] = hit_type[counter]
            models["runner_adv_out"][hitter] = runner_adv_out[counter]
            models["runner_adv_hit"][hitter] = runner_adv_hit[counter]
            models["sb_attempt"][hitter] = sb_attempt[counter]
            models["sb_success"][hitter] = sb_success[counter]
            counter += 1

    return models


async def simulate(games, models, team_stlats, player_blood_types, player_names, sim_length):
    a_favored_wins, p_favored_wins, predicted_wins = 0, 0, 0
    day = games[0]['day']
    season = games[0]['season']
    output_text = f"Day: {day}\n"
    strikeouts = {}
    game_statsheets = {}
    for game in games:
        home_scores = []
        away_scores = []
        home_shutout = 0
        home_wins = 0
        away_shutout = 0
        away_wins = 0
        home_struckout = []
        away_struckout = []
        innings = []
        homeTeam, awayTeam = game["homeTeam"], game["awayTeam"]
        home_name = team_names[homeTeam]
        away_name = team_names[awayTeam]
        home_lineup = team_stlats[homeTeam]["lineup"]
        away_lineup = team_stlats[awayTeam]["lineup"]
        for hitter in list(home_lineup.keys()) + list(away_lineup.keys()):
            game_statsheets[hitter] = {"plate_appearances": 0, "at_bats": 0, "struckouts": 0, "walks": 0,
                                       "hits": 0, "doubles": 0, "triples": 0, "quadruples": 0, "homeruns": 0,
                                       "runs": 0, "rbis": 0, "stolen_bases": 0,
                                       "caught_stealing": 0, "double_play": 0,
                                       "wins": 0, "losses": 0, "shutouts": 0, "outs_recorded": 0,
                                       "hits_allowed": 0, "home_runs_allowed": 0, "strikeouts": 0,
                                       "walks_issued": 0, "batters_faced": 0, "runs_allowed": 0}

        game_statsheets[game["homePitcher"]] = {"plate_appearances": 0, "at_bats": 0, "struckouts": 0, "walks": 0,
                                                "hits": 0, "doubles": 0, "triples": 0, "quadruples": 0, "homeruns": 0,
                                                "runs": 0, "rbis": 0, "stolen_bases": 0,
                                                "caught_stealing": 0, "double_play": 0,
                                                "wins": 0, "losses": 0, "shutouts": 0, "outs_recorded": 0,
                                                "hits_allowed": 0, "home_runs_allowed": 0, "strikeouts": 0,
                                                "walks_issued": 0, "batters_faced": 0, "runs_allowed": 0}
        game_statsheets[game["awayPitcher"]] = {"plate_appearances": 0, "at_bats": 0, "struckouts": 0, "walks": 0,
                                                "hits": 0, "doubles": 0, "triples": 0, "quadruples": 0, "homeruns": 0,
                                                "runs": 0, "rbis": 0, "stolen_bases": 0,
                                                "caught_stealing": 0, "double_play": 0,
                                                "wins": 0, "losses": 0, "shutouts": 0, "outs_recorded": 0,
                                                "hits_allowed": 0, "home_runs_allowed": 0, "strikeouts": 0,
                                                "walks_issued": 0, "batters_faced": 0, "runs_allowed": 0}
        shakeup = False
        if len(game["outcomes"]) > 0:
            for outcome in game["outcomes"]:
                if "shuffled in the Reverb" in outcome:
                    shakeup = True
                    break
        if shakeup:
            continue
        log_game = False
        for i in range(sim_length):
            game_log = [f'Day {game["day"]}.',
                        f'{game["homePitcherName"]} pitching for the {game["homeTeamName"]} at home.',
                        f'{game["awayPitcherName"]} pitching for the {game["awayTeamName"]} on the road.']
            home_score, away_score = 0, 0
            home_order, away_order = 0, 0
            home_strikeouts, away_strikeouts = 0, 0
            inning = 0
            while True:
                game_log.append(f'\nTop of the {inning+1}, {game["awayTeamNickname"]} batting.')
                game_log.append(f'{game["homeTeamNickname"]}: {home_score} -  {game["awayTeamNickname"]}: {away_score}')
                a_runs, away_order, a_strikeouts, nlg = await simulate_inning(models, away_lineup, away_order,
                                                                              game_statsheets, player_blood_types,
                                                                              game, True, game_log, player_names,
                                                                              f"Top of the {inning+1}", log_game)
                log_game = nlg
                away_score += a_runs
                away_strikeouts += a_strikeouts
                if inning == 8 and home_score != away_score:
                    break
                game_log.append(f'\nBottom of the {inning + 1}, {game["homeTeamNickname"]} batting.')
                game_log.append(f'{game["homeTeamNickname"]}: {home_score} -  {game["awayTeamNickname"]}: {away_score}')
                h_runs, home_order, h_strikeouts, nlg = await simulate_inning(models, home_lineup, home_order,
                                                                              game_statsheets, player_blood_types,
                                                                              game, False, game_log, player_names,
                                                                              f'bottom of the {inning+1}', log_game)
                log_game = nlg
                home_score += h_runs
                home_strikeouts += h_strikeouts

                if inning >= 8 and home_score != away_score:
                    break
                inning += 1
            innings.append(inning+1)
            home_scores.append(home_score)
            away_scores.append(away_score)
            if home_score == 0:
                home_shutout += 1
                game_statsheets[game["awayPitcher"]]["shutouts"] += 1
            if away_score == 0:
                away_shutout += 1
                game_statsheets[game["homePitcher"]]["shutouts"] += 1
            if home_score > away_score:
                home_wins += 1
                game_statsheets[game["homePitcher"]]["wins"] += 1
                game_statsheets[game["awayPitcher"]]["losses"] += 1
                game_log.append(f'Game Over. {game["homeTeamName"]} win {home_score} - {away_score}')
            else:
                away_wins += 1
                game_statsheets[game["awayPitcher"]]["wins"] += 1
                game_statsheets[game["homePitcher"]]["losses"] += 1
                game_log.append(f'Game Over. {game["awayTeamName"]} win {away_score} - {home_score}')
            home_struckout.append(home_strikeouts)
            away_struckout.append(away_strikeouts)
            if log_game or i == 0:
                if i == 0:
                    filename = os.path.join('season_sim', 'game_logs',
                                            f's{season}-d{day}_{away_name}-at-{home_name}.txt')
                else:
                    filename = os.path.join('season_sim', 'game_logs',
                                            f's{season}-d{day}_{away_name}-at-{home_name}_{i}.txt')
                with open(filename, 'w') as file:
                    for message in game_log:
                        file.write(f"{message}\n")
                log_game = False

        home_scores.sort()
        away_scores.sort()
        home_struckout.sort(reverse=True)
        away_struckout.sort(reverse=True)

        home_odds, away_odds = game["homeOdds"], game["awayOdds"]

        if game['homeScore'] > game['awayScore']:
            if home_odds > away_odds:
                a_favored_wins += 1
        else:
            if away_odds > home_odds:
                a_favored_wins += 1
        if statistics.mean(home_scores) > statistics.mean(away_scores):
            if home_odds > away_odds:
                p_favored_wins += 1
        else:
            if away_odds > home_odds:
                p_favored_wins += 1

        avg_home_score = statistics.mean(home_scores)
        avg_away_score = statistics.mean(away_scores)
        if season == 10:
            avg_home_score = avg_home_score % 10
            avg_away_score = avg_away_score % 10
        if game['homeScore'] > game['awayScore']:
            if avg_home_score > avg_away_score:
                predicted_wins += 1
        else:
            if avg_away_score > avg_home_score:
                predicted_wins += 1

        strikeouts[game["homePitcher"]] = {
            "name": game["homePitcherName"],
            "predicted_strikeouts": statistics.mean(away_struckout),
            "sho_per": away_shutout / sim_length
        }
        strikeouts[game["awayPitcher"]] = {
            "name": game["awayPitcherName"],
            "predicted_strikeouts": statistics.mean(home_struckout),
            "sho_per": home_shutout / sim_length
        }

    with open(os.path.join('season_sim', 'results', 'daily', f"s{season}_d{day}_results.txt"), 'a') as fd:
        fd.write(output_text)
    return predicted_wins, a_favored_wins, strikeouts, game_statsheets


async def simulate_inning(models, lineup, order, stat_sheets, player_blood_types,
                          game, top_of_inning, game_log, player_names, descriptor, log_game):
    season = game["season"]
    if top_of_inning:
        pitcher_id, hit_team_id, hit_team_name = game["homePitcher"], game["awayTeam"], game["awayTeamName"]
    else:
        pitcher_id, hit_team_id, hit_team_name = game["awayPitcher"], game["homeTeam"], game["homeTeamName"]
    bases = {1: None, 2: None, 3: None}
    inning_outs = 0
    score = 0
    strikeouts = 0
    while True:
        hitter_id = list(lineup.keys())[order]

        game_log.append(f'{player_names[hitter_id]} batting for the {hit_team_name}')
        outs, runs, bases, in_strikeouts, advance_order = await simulate_at_bat(bases, models, stat_sheets,
                                                                                player_blood_types,
                                                                                pitcher_id, hitter_id,
                                                                                hit_team_id, season,
                                                                                game_log, player_names,
                                                                                inning_outs)
        inning_outs += outs
        strikeouts += in_strikeouts
        if advance_order:
            order += 1
            if order == len(lineup):
                order = 0
        if inning_outs >= 3:
            if inning_outs > 3:
                print("WHY ARE THERE MORE THAN 3 OUTS!!!!")
                print(f"day {game['day']} h_team {game['homeTeamNickname']} "
                      f"a_team {game['awayTeamNickname']} {descriptor}")
                log_game = True
            break
        score += runs

    return score, order, strikeouts, log_game


async def simulate_at_bat(bases, models, stat_sheets, player_blood_types,
                          pitcher_id, hitter_id, hit_team_id, season,
                          game_log, player_names, inning_outs):
    stat_sheets[pitcher_id]["batters_faced"] += 1
    stat_sheets[hitter_id]["plate_appearances"] += 1

    outs, strikeouts, runs = 0, 0, 0
    at_bat_count = {"balls": 0, "strikes": 0, "outs": inning_outs}
    advance_order = True
    # ['single %', 'double %', 'triple %', 'hr %']
    while True:
        play, bases, at_bat_count, inc_order, p_runs, p_outs = await simulate_pitch(models, bases, at_bat_count,
                                                                                    hitter_id, game_log, player_names)
        outs += p_outs
        if at_bat_count["outs"] == 3:
            advance_order = inc_order
            break
        if not play:
            runs += p_runs
            if at_bat_count["strikes"] == 3:
                outs += 1
                strikeouts += 1
                stat_sheets[hitter_id]["struckouts"] += 1
                stat_sheets[pitcher_id]["strikeouts"] += 1
                stat_sheets[hitter_id]["at_bats"] += 1
                game_log.append(f'{player_names[hitter_id]} struck out.')
                break
            elif at_bat_count["balls"] == 4:
                base_instincts = False
                if hit_team_id in blood_effect:
                    if "base_instincts" in blood_effect[hit_team_id]:
                        if season >= blood_effect[hit_team_id]["base_instincts"]["season"]:
                            if hitter_id in player_blood_types:
                                if player_blood_types[hitter_id] == blood_effect[hit_team_id]["base_instincts"]["blood"]:
                                    base_instincts = True
                complete = False
                base_msg = ""
                if base_instincts:
                    complete = True
                    walk_chance = random.random()
                    if walk_chance < .035:
                        advance = 3
                        base_msg = " Base Instincts takes them to 3rd base."
                        base_instincts_procs[season][3] += 1
                    elif walk_chance < .19:
                        advance = 2
                        base_msg = " Base Instincts takes them to 2nd base."
                        base_instincts_procs[season][2] += 1
                    else:
                        advance = 1
                    if advance == 3:
                        if bases[3]:
                            runs += 1
                            bases[3] = None
                        if bases[2]:
                            runs += 1
                            bases[2] = None
                        if bases[1]:
                            runs += 1
                            bases[1] = None
                        bases[3] = hitter_id
                    elif advance == 2:
                        if bases[3]:
                            if bases[2] or bases[1]:
                                runs += 1
                                bases[3] = None
                        if bases[2]:
                            if bases[1]:
                                runs += 1
                            else:
                                bases[3] = bases[2]
                            bases[2] = None
                        if bases[1]:
                            bases[1] = None
                            bases[3] = bases[1]
                        bases[2] = hitter_id
                    else:
                        complete = False

                if not complete:
                    if bases[3]:
                        if bases[2] and bases[1]:
                            runs += 1
                            bases[3] = None
                    if bases[2]:
                        if bases[1]:
                            bases[2] = None
                            bases[3] = bases[2]
                    if bases[1]:
                        bases[1] = None
                        bases[2] = bases[1]
                    bases[1] = hitter_id
                stat_sheets[hitter_id]["walks"] += 1
                stat_sheets[pitcher_id]["walks_issued"] += 1
                game_log.append(f'{player_names[hitter_id]} drew a walk.{base_msg}')
                break
            else:
                continue
        stat_sheets[hitter_id]["at_bats"] += 1
        # field_out
        if play == -1:
            return outs, runs, bases, strikeouts, advance_order
        # single
        elif play == 0:
            if bases[3]:
                runs += 1
                bases[3] = None
            if bases[2]:
                run_adv_model = models["runner_adv_hit"][bases[2]]
                result = await simulate_event(run_adv_model)
                if result == 1:
                    runs += 1
                else:
                    bases[3] = bases[2]
                bases[2] = None
            if bases[1]:
                run_adv_model = models["runner_adv_hit"][bases[1]]
                result = await simulate_event(run_adv_model)
                if result == 1:
                    bases[3] = bases[1]
                else:
                    bases[2] = bases[1]
                bases[1] = None
            bases[1] = hitter_id
            stat_sheets[hitter_id]["hits"] += 1
            stat_sheets[pitcher_id]["hits_allowed"] += 1

            run_msg = ""
            if runs > 0:
                run_msg = f" {runs} scores."
            game_log.append(f'{player_names[hitter_id]} hit a single.{run_msg}')
            break
        # double
        elif play == 1:
            if bases[3]:
                runs += 1
                bases[3] = None
            if bases[2]:
                runs += 1
                bases[2] = None
            if bases[1]:
                run_adv_model = models["runner_adv_hit"][bases[1]]
                result = await simulate_event(run_adv_model)
                if result == 1:
                    runs += 1
                else:
                    bases[3] = bases[1]
                bases[1] = None
            bases[2] = hitter_id
            stat_sheets[hitter_id]["hits"] += 1
            stat_sheets[hitter_id]["doubles"] += 1
            stat_sheets[pitcher_id]["hits_allowed"] += 1
            run_msg = ""
            if runs > 0:
                run_msg = f" {runs} scores."
            game_log.append(f'{player_names[hitter_id]} hit a double.{run_msg}')
            break
        # triple or hr
        elif play >= 2:
            stat_sheets[hitter_id]["hits"] += 1
            stat_sheets[pitcher_id]["hits_allowed"] += 1
            if bases[3]:
                runs += 1
                bases[3] = None
            if bases[2]:
                runs += 1
                bases[2] = None
            if bases[1]:
                runs += 1
                bases[1] = None
            # if triple
            if play == 2:
                bases[3] = hitter_id
                stat_sheets[hitter_id]["triples"] += 1
                run_msg = ""
                if runs > 0:
                    run_msg = f" {runs} scores."
                game_log.append(f'{player_names[hitter_id]} hit a triple.{run_msg}')
                break
            else:
                runs += 1
                stat_sheets[hitter_id]["homeruns"] += 1
                stat_sheets[pitcher_id]["home_runs_allowed"] += 1
                run_msg = ""
                if runs > 0:
                    run_msg = f" {runs} scores."
                game_log.append(f'{player_names[hitter_id]} hit a home run.{run_msg}')
                break

    stat_sheets[hitter_id]["rbis"] += runs
    stat_sheets[pitcher_id]["outs_recorded"] += outs
    stat_sheets[pitcher_id]["runs_allowed"] += runs

    return outs, runs, bases, strikeouts, advance_order


async def simulate_pitch(models, bases, at_bat_count, hitter_id, game_log, player_names):
    p_runs = 0
    p_outs = 0
    # check for steal attempt & result
    bases, runs, outs = await simulate_stolen_base(models, bases, game_log, player_names)
    p_runs += runs
    p_outs += outs
    at_bat_count["outs"] += outs

    if outs > 0:
        return None, bases, at_bat_count, False, p_runs, p_outs

    # ['ball %', 'strike %', 'foul %', 'in_play %']
    pitch_model = models["pitch"][hitter_id]
    result = await simulate_event(pitch_model)
    if result == 0:
        at_bat_count["balls"] += 1
        return None, bases, at_bat_count, True, p_runs, p_outs
    if result == 1:
        at_bat_count["strikes"] += 1
        return None, bases, at_bat_count, True, p_runs, p_outs
    if result == 2:
        if at_bat_count["strikes"] < 2:
            at_bat_count["strikes"] += 1
        return None, bases, at_bat_count, True, p_runs, p_outs

    inplay_model = models["is_hit"][hitter_id]
    result = await simulate_event(inplay_model)
    # ['flyout %', 'groundout %', 'hit %']
    if result == 0 or result == 1:
        at_bat_count["outs"] += 1
        p_outs += 1
        if at_bat_count["outs"] < 3:
            lead_run_id, cur = None, 0
            # only lead runner can advance
            if bases[3]:
                lead_run_id = bases[3]
                cur = 3
            elif bases[2]:
                lead_run_id = bases[2]
                cur = 2
            elif bases[1]:
                lead_run_id = bases[1]
                cur = 1
            if lead_run_id:
                r_out_adv = models["runner_adv_out"][lead_run_id]
                result = await simulate_event(r_out_adv)
                if result == 1:
                    if cur == 3:
                        runs += 1
                        bases[3] = None
                    else:
                        bases[cur+1] = bases[cur]
                        bases[cur] = None
        if result == 0:
            game_log.append(f'{player_names[hitter_id]} hit a flyout.')
        if result == 1:
            game_log.append(f'{player_names[hitter_id]} hit a ground out.')
        return -1, bases, at_bat_count, True, p_runs, p_outs
    else:
        hit_type_model = models["hit_type"][hitter_id]
        result = await simulate_event(hit_type_model)
        return result, bases, at_bat_count, True, p_runs, p_outs


async def simulate_stolen_base(models, bases, game_log, player_names):
    runs, outs = 0, 0
    if bases[3]:
        runner_model = models["sb_attempt"][bases[3]]
        result = await simulate_event(runner_model)
        # ['no_sba %', 'sba %']
        if result == 0:
            return bases, runs, outs
        else:
            runner_model = models["sb_success"][bases[3]]
            result = await simulate_event(runner_model)
            # ['cs %', 'sb %']
            if result == 0:
                outs += 1
                game_log.append(f'{player_names[bases[3]]} caught stealing 4th base.')
            else:
                runs += 1
                game_log.append(f'{player_names[bases[3]]} steals 4th base and scores.')
            bases[3] = None
            return bases, runs, outs
    elif bases[2] and not bases[3]:
        runner_model = models["sb_attempt"][bases[2]]
        result = await simulate_event(runner_model)
        if result == 0:
            return bases, runs, outs
        else:
            runner_model = models["sb_success"][bases[2]]
            result = await simulate_event(runner_model)
            if result == 0:
                outs += 1
                game_log.append(f'{player_names[bases[2]]} caught stealing 3rd base.')
            else:
                bases[3] = bases[2]
                game_log.append(f'{player_names[bases[2]]} steals 3rd base.')
            bases[2] = None
            return bases, runs, outs
    elif bases[1] and not bases[2]:
        runner_model = models["sb_attempt"][bases[1]]
        result = await simulate_event(runner_model)
        if result == 0:
            return bases, runs, outs
        else:
            runner_model = models["sb_success"][bases[1]]
            result = await simulate_event(runner_model)
            if result == 0:
                outs += 1
                game_log.append(f'{player_names[bases[1]]} caught stealing 2nd base.')
            else:
                bases[2] = bases[1]
                game_log.append(f'{player_names[bases[1]]} steals 2nd base.')
            bases[1] = None
            return bases, runs, outs
    return bases, runs, outs


async def simulate_event(outputs, roll=None):
    if not roll:
        # generate random float between 0-1
        roll = random.random()
    total = 0
    # hitter is an array of probabilities for 7 outcomes
    # ['field_out %', 'strike_out %', 'walk %', 'single %', 'double %', 'triple %', 'hr %']
    for i in range(len(outputs)):
        # add the odds of the next outcome to the running total
        total += outputs[i]
        # if the random roll is less than the new total, return this outcome
        if roll < total:
            return i


async def setup(sim_length):
    start_time = time.time()
    print(f"Start time: {start_time}")
    clf = {
           # old
           "at_bat": load(os.path.join("season_sim", "models", "ab.joblib")),

           "pitch": load(os.path.join("season_sim", "models", "pitch_v1.joblib")),
           "is_hit": load(os.path.join("season_sim", "models", "is_hit_v1.joblib")),
           "hit_type": load(os.path.join("season_sim", "models", "hit_type_v1.joblib")),
           "runner_adv_out": load(os.path.join("season_sim", "models", "runner_advanced_on_out_v1.joblib")),
           "runner_adv_hit": load(os.path.join("season_sim", "models", "extra_base_on_hit_v1.joblib")),
           "sb_attempt": load(os.path.join("season_sim", "models", "sba_v1.joblib")),
           "sb_success": load(os.path.join("season_sim", "models", "sb_success_v1.joblib"))
    }

    #for season in range(10, 11):
    for season in range(7, 11):
        print(f"season {season}")
        outcome_text = ""
        daily_strikeouts = {}
        with open(os.path.join('season_sim', 'season_data', f"season{season+1}.json"), 'r',
                  encoding='utf8') as json_file:
            raw_season_data = json.load(json_file)
        s_predicted_wins, s_a_favored_wins = 0, 0
        season_data = {}
        season_statsheets = {}
        for game in raw_season_data:
            if game['day'] not in season_data:
                season_data[game['day']] = []
            season_data[game['day']].append(game)
        for day in range(0, 99):
            games = season_data[day]
            if day % 25 == 0:
                print(f"day {day}")
            with open(os.path.join('season_sim', 'stlats', f"s{season}_d{day}_stlats.json"), 'r', encoding='utf8') as json_file:
                player_stlats_list = json.load(json_file)
            player_stlats = {}
            team_stlats = {}
            player_blood_types = {}
            player_names = {}
            for player in player_stlats_list:
                player_stlats[player["player_id"]] = player
                player_blood_types[player["player_id"]] = player["blood"]
                player_names[player["player_id"]] = player["player_name"]
                if player["team_id"] not in team_stlats:
                    team_stlats[player["team_id"]] = {"lineup": {}}
                if player["position_type_id"] == '0':
                    player_id = player["player_id"]
                    team_stlats[player["team_id"]]["lineup"][player_id] = player
            for team in team_stlats:
                us_lineup = team_stlats[team]["lineup"]
                sorted_lineup = {k: v for k, v in
                                 sorted(us_lineup.items(), key=lambda item: item[1]["position_id"])}
                team_stlats[team]["lineup"] = sorted_lineup

            models = await setup_models(games, clf, player_stlats, team_stlats)

            predicted_wins, a_favored_wins, strikeouts, stat_sheets = await simulate(games, models,
                                                                                     team_stlats,
                                                                                     player_blood_types,
                                                                                     player_names, sim_length)

            daily_strikeouts[day] = strikeouts
            s_predicted_wins += predicted_wins
            s_a_favored_wins += a_favored_wins

            for player in stat_sheets:
                if player not in season_statsheets:
                    season_statsheets[player] = {"plate_appearances": 0, "at_bats": 0, "struckouts": 0, "walks": 0,
                                          "hits": 0, "doubles": 0, "triples": 0, "quadruples": 0, "homeruns": 0,
                                          "runs": 0, "rbis": 0, "stolen_bases": 0,
                                          "caught_stealing": 0, "double_play": 0,
                                          "wins": 0, "losses": 0, "shutouts": 0, "outs_recorded": 0,
                                          "hits_allowed": 0, "home_runs_allowed": 0, "strikeouts": 0,
                                          "walks_issued": 0, "batters_faced": 0, "runs_allowed": 0}
                adjust_gs = {k: v / sim_length for k, v in stat_sheets[player].items()}
                for key in adjust_gs:
                    season_statsheets[player][key] += adjust_gs[key]
        for player in season_statsheets:
            season_statsheets[player] = {k: round(v) for k, v in season_statsheets[player].items()}
        with open(os.path.join('season_sim', 'results', f"{season}_outcomes_{sim_length}.txt"), 'w', encoding='utf8') as fd:
            fd.write(outcome_text)
        s_predicted_wins_per = round((s_predicted_wins / 990) * 1000) / 10
        s_a_favored_wins_per = round((s_a_favored_wins / 990) * 1000) / 10
        print(f"{s_predicted_wins} ({s_predicted_wins_per}%) favored wins predicted - "
              f"{s_a_favored_wins} ({s_a_favored_wins_per}%) actual favored wins. ")

        with open(os.path.join('season_sim', 'results', f"{season}_k_sho_results_{sim_length}.json"), 'w',
                  encoding='utf8') as json_file:
            json.dump(daily_strikeouts, json_file)
        with open(os.path.join('season_sim', 'results', f"{season}_statsheets_{sim_length}.json"), 'w',
                  encoding='utf8') as json_file:
            json.dump(season_statsheets, json_file)
    print(base_instincts_procs)
    end_time = time.time() - start_time
    print(f"End time: {time.time()}\nElapsed: {end_time}")


async def sum_strikeouts(length):
    print(f"strikeout avgs at sim length {length}")
    for season in range(7, 11):
        print(season)
        strikeouts = {}
        with open(os.path.join('season_sim', 'results', f"{season}_k_sho_results_{length}.json"), 'r',
                  encoding='utf8') as json_file:
            daily_strikeouts = json.load(json_file)
        for day in daily_strikeouts:
            for pid in daily_strikeouts[day]:
                if pid not in strikeouts:
                    strikeouts[pid] = {"name": daily_strikeouts[day][pid]["name"], "strikeouts": 0}
                strikeouts[pid]["strikeouts"] += daily_strikeouts[day][pid]["predicted_strikeouts"]
        sorted_strikeouts = {k: v for k, v in
                            sorted(strikeouts.items(), key=lambda item: item[1]["strikeouts"], reverse=True)}
        print(sorted_strikeouts.values())


async def compare_stats(length):
    for season in range(7, 11):
        with open(os.path.join('season_sim', 'results', f"{season}_statsheets_{length}.json"), 'r',
                  encoding='utf8') as json_file:
            predicted_statsheets = json.load(json_file)
        with open(os.path.join('season_sim', 'results', 'actual_stats', f"{season}_actual_stats.json"), 'r',
                  encoding='utf8') as json_file:
            actual_statsheets = json.load(json_file)
        hitting_diffs = {"below": {}, "above": {}}
        pitching_diffs = {"below": {}, "above": {}}
        for pid, values in predicted_statsheets.items():
            if values["plate_appearances"] > 0 and pid in actual_statsheets["hitting"]:
                hitting_diffs["below"][pid] = {}
                hitting_diffs["above"][pid] = {}
                for key in ["plate_appearances", "at_bats", "struckouts", "walks",
                            "hits", "doubles", "triples", "homeruns", "rbis"]:
                    okey = key
                    if key == "struckouts":
                        okey = "strikeouts"
                    if key == "rbis":
                        okey = "runs_batted_in"
                    if key == "homeruns":
                        okey = "home_runs"
                    actual = float(actual_statsheets["hitting"][pid][okey])
                    predicted = values[key]
                    if actual > predicted:
                        percent_diff = 1 - (predicted / actual)
                        hitting_diffs["below"][pid][key] = percent_diff
                    else:
                        percent_diff = 1 - (actual / predicted)
                        hitting_diffs["above"][pid][key] = percent_diff
            if values["outs_recorded"] > 0 and pid in actual_statsheets["pitching"]:
                pitching_diffs["below"][pid] = {}
                pitching_diffs["above"][pid] = {}
                for key in ["outs_recorded", "hits_allowed",
                            "home_runs_allowed", "strikeouts", "walks_issued"]:
                    okey = key
                    if key == "home_runs_allowed":
                        okey = "hrs_allowed"
                    if key == "walks_issued":
                        okey = "walks"
                    actual = float(actual_statsheets["pitching"][pid][okey])
                    predicted = values[key]
                    if actual > predicted:
                        percent_diff = 1 - (predicted / actual)
                        pitching_diffs["below"][pid][key] = percent_diff
                    else:
                        percent_diff = 1 - (actual / predicted)
                        pitching_diffs["above"][pid][key] = percent_diff

        with open(os.path.join('season_sim', 'results', 'stats', f"{season}_hitting_stat_diffs.json"), 'w',
                  encoding='utf8') as json_file:
            json.dump(hitting_diffs, json_file)
        with open(os.path.join('season_sim', 'results', 'stats', f"{season}_pitching_stat_diffs.json"), 'w',
                  encoding='utf8') as json_file:
            json.dump(pitching_diffs, json_file)


async def summarize_diffs():
    all_diffs = {"hitting": {"above": {"plate_appearances": [], "at_bats": [], "struckouts": [],
                                       "walks": [], "hits": [], "doubles": [], "triples": [],
                                       "homeruns": [], "rbis": []},
                             "below": {"plate_appearances": [], "at_bats": [], "struckouts": [],
                                       "walks": [], "hits": [], "doubles": [], "triples": [],
                                       "homeruns": [], "rbis": []}},
                 "pitching": {"above": {"outs_recorded": [], "hits_allowed": [], "home_runs_allowed": [],
                                        "strikeouts": [], "walks_issued": []},
                              "below": {"outs_recorded": [], "hits_allowed": [], "home_runs_allowed": [],
                                        "strikeouts": [], "walks_issued": []}}}

    def summary_message(stat_dict):
        summary_msg = ""
        for stat, stat_list in stat_dict.items():
            stat_list.sort()
            if len(stat_list) < 4:
                if len(stat_list) == 0:
                    summary_msg += f"{stat} has no occurrences.\n"
                else:
                    summary_msg += f"{stat} has only {len(stat_list)} occurrences.\n"
            else:
                p_stat_list = score_percentiles(stat_list)
                p_stat_list = [str(round(float(p) * 100000) / 100000) for p in p_stat_list]
                min_d, max_d = round(stat_list[0] * 100000) / 100000, round(stat_list[-1] * 100000) / 100000
                summary_msg += f"{stat} min diff: {min_d}, max diff: {max_d}, avg: {round(statistics.mean(stat_list) * 100000) / 100000}, " \
                               f"(50, 75, 90, 99)th percentiles: {', '.join(p_stat_list)}\n"
        return summary_msg

    for season in range(7, 11):
        with open(os.path.join('season_sim', 'results', 'stats', f"{season}_hitting_stat_diffs.json"), 'r',
                  encoding='utf8') as json_file:
            hitting_diffs = json.load(json_file)
        with open(os.path.join('season_sim', 'results', 'stats', f"{season}_pitching_stat_diffs.json"), 'r',
                  encoding='utf8') as json_file:
            pitching_diffs = json.load(json_file)
        season_diffs = {"hitting": {"above": {"plate_appearances": [], "at_bats": [], "struckouts": [],
                                              "walks": [], "hits": [], "doubles": [], "triples": [],
                                              "homeruns": [], "rbis": []},
                                    "below": {"plate_appearances": [], "at_bats": [], "struckouts": [],
                                              "walks": [], "hits": [], "doubles": [], "triples": [],
                                              "homeruns": [], "rbis": []}},
                        "pitching": {"above": {"outs_recorded": [], "hits_allowed": [], "home_runs_allowed": [],
                                               "strikeouts": [], "walks_issued": []},
                                     "below": {"outs_recorded": [], "hits_allowed": [], "home_runs_allowed": [],
                                               "strikeouts": [], "walks_issued": []}}}
        for diff in hitting_diffs["above"].values():
            for key in diff:
                season_diffs["hitting"]["above"][key].append(diff[key])
                all_diffs["hitting"]["above"][key].append(diff[key])
        for diff in hitting_diffs["below"].values():
            for key in diff:
                season_diffs["hitting"]["below"][key].append(diff[key])
                all_diffs["hitting"]["below"][key].append(diff[key])
        for diff in pitching_diffs["above"].values():
            for key in diff:
                season_diffs["pitching"]["above"][key].append(diff[key])
                all_diffs["pitching"]["above"][key].append(diff[key])
        for diff in pitching_diffs["below"].values():
            for key in diff:
                season_diffs["pitching"]["below"][key].append(diff[key])
                all_diffs["pitching"]["below"][key].append(diff[key])
        p_idxs = [.50, .75, .90, .99]

        def score_percentiles(scores):
            count = len(scores)
            prob_vals = []
            for p in p_idxs:
                idx = round((p * count) - 1)
                try:
                    prob_vals.append(scores[idx])
                except IndexError:
                    print(1)
            return [str(v) for v in prob_vals]

        hitting_msg_a = summary_message(season_diffs["hitting"]["above"])
        hitting_msg_b = summary_message(season_diffs["hitting"]["below"])
        pitching_msg_a = summary_message(season_diffs["pitching"]["above"])
        pitching_msg_b = summary_message(season_diffs["pitching"]["below"])

        print(f"Season {season} stat diffs above actual\n{hitting_msg_a}\n{pitching_msg_a}")
        print(f"Season {season} stat diffs below actual\n{hitting_msg_b}\n{pitching_msg_b}")

    hitting_msg_a = summary_message(all_diffs["hitting"]["above"])
    hitting_msg_b = summary_message(all_diffs["hitting"]["below"])
    pitching_msg_a = summary_message(all_diffs["pitching"]["above"])
    pitching_msg_b = summary_message(all_diffs["pitching"]["below"])
    print(f"Seasons 8-11 cumulative stat diffs above actual\n{hitting_msg_a}\n{pitching_msg_a}")
    print(f"Seasons 8-11 cumulative stat diffs below actual\n{hitting_msg_b}\n{pitching_msg_b}")


loop = asyncio.get_event_loop()

iterations = 1000
loop.run_until_complete(setup(iterations))
loop.run_until_complete(sum_strikeouts(iterations))
loop.run_until_complete(compare_stats(iterations))
loop.run_until_complete(summarize_diffs())
loop.close()