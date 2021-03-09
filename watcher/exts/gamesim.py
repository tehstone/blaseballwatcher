import asyncio
import json
import os
import random

import requests
import statistics

from discord.ext import commands
from joblib import load
from requests import Timeout


class GameSim(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
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

    async def get_player_stlats(self):
        print("Getting current player stlats")
        batters = {}
        pitcher_ids = []
        pitcher_stlats = {}
        team_stlats = {}
        teams_response = await self.retry_request("https://www.blaseball.com/database/allteams")
        teams_json = teams_response.json()
        for team in teams_json:
            team_stlats[team["id"]] = {"lineup": {}}
            pitcher_ids += team["rotation"]
            counter = 0
            for batter in team["lineup"]:
                batters[batter] = {"team": team["id"],
                                   "order": counter}
                counter += 1
        chunked_pitcher_ids = [pitcher_ids[i:i + 50] for i in range(0, len(pitcher_ids), 50)]
        for chunk in chunked_pitcher_ids:
            b_url = f"https://www.blaseball.com/database/players?ids={','.join(chunk)}"
            pitcher_response = await self.retry_request(b_url)
            pitcher_json = pitcher_response.json()
            for pitcher in pitcher_json:
                pitcher_stlats[pitcher["id"]] = pitcher
        batter_ids = list(batters.keys())
        chunked_batter_ids = [batter_ids[i:i + 50] for i in range(0, len(batter_ids), 50)]
        for chunk in chunked_batter_ids:
            b_url = f"https://www.blaseball.com/database/players?ids={','.join(chunk)}"
            batter_response = await self.retry_request(b_url)
            batter_json = batter_response.json()
            for batter in batter_json:
                team_id = batters[batter["id"]]["team"]
                batter["order"] = batters[batter["id"]]["order"]
                team_stlats[team_id]["lineup"][batter["id"]] = batter
        return pitcher_stlats, team_stlats

    @staticmethod
    async def setup_model(games, clf, pitcher_stlats, team_stlats):
        hitter_models = {}
        for game in games:
            if game["homePitcher"] not in pitcher_stlats:
                continue
            if game["awayPitcher"] not in pitcher_stlats:
                continue
            home_pitcher = pitcher_stlats[game["homePitcher"]]
            away_pitcher = pitcher_stlats[game["awayPitcher"]]
            home_hitters = home_defense = team_stlats[game['homeTeam']]["lineup"]
            away_hitters = away_defense = team_stlats[game['awayTeam']]["lineup"]
            h_anticapitalism = statistics.mean([d["anticapitalism"] for d in home_defense.values()])
            h_chasiness = statistics.mean([d["chasiness"] for d in home_defense.values()])
            h_omniscience = statistics.mean([d["omniscience"] for d in home_defense.values()])
            h_tenaciousness = statistics.mean([d["tenaciousness"] for d in home_defense.values()])
            h_watchfulness = statistics.mean([d["watchfulness"] for d in home_defense.values()])
            h_defense_pressurization = statistics.mean([d["pressurization"] for d in home_defense.values()])
            h_defense_cinnamon = statistics.mean([d["cinnamon"] for d in home_defense.values()])
            a_anticapitalism = statistics.mean([d["anticapitalism"] for d in away_defense.values()])
            a_chasiness = statistics.mean([d["chasiness"] for d in away_defense.values()])
            a_omniscience = statistics.mean([d["omniscience"] for d in away_defense.values()])
            a_tenaciousness = statistics.mean([d["tenaciousness"] for d in away_defense.values()])
            a_watchfulness = statistics.mean([d["watchfulness"] for d in away_defense.values()])
            a_defense_pressurization = statistics.mean([d["pressurization"] for d in away_defense.values()])
            a_defense_cinnamon = statistics.mean([d["cinnamon"] for d in away_defense.values()])
            model_arrs = []
            sorted_h_hitters = {k: v for k, v in
                                sorted(home_hitters.items(), key=lambda item: item[0])}
            sorted_a_hitters = {k: v for k, v in
                                sorted(away_hitters.items(), key=lambda item: item[0])}
            for __, hitter in sorted_h_hitters.items():
                m_arr = []
                for stlat in ["buoyancy", "divinity", "martyrdom", "moxie", "musclitude", "patheticism",
                              "thwackability", "tragicness", "baseThirst", "continuation",
                              "groundFriction", "indulgence", "laserlikeness", "cinnamon", "pressurization"]:
                    m_arr.append(hitter[stlat])
                for stlat in ["coldness", "overpowerment", "ruthlessness", "shakespearianism",
                              "suppression", "unthwackability", "cinnamon", "pressurization"]:
                    m_arr.append(away_pitcher[stlat])
                m_arr += [a_anticapitalism, a_chasiness, a_omniscience, a_tenaciousness,
                          a_watchfulness, a_defense_pressurization, a_defense_cinnamon]
                model_arrs.append(m_arr)
            for __, hitter in sorted_a_hitters.items():
                m_arr = []
                for stlat in ["buoyancy", "divinity", "martyrdom", "moxie", "musclitude", "patheticism",
                              "thwackability", "tragicness", "baseThirst", "continuation",
                              "groundFriction", "indulgence", "laserlikeness", "cinnamon", "pressurization"]:
                    m_arr.append(hitter[stlat])
                for stlat in ["coldness", "overpowerment", "ruthlessness", "shakespearianism",
                              "suppression", "unthwackability", "cinnamon", "pressurization"]:
                    m_arr.append(home_pitcher[stlat])
                m_arr += [h_anticapitalism, h_chasiness, h_omniscience, h_tenaciousness,
                          h_watchfulness, h_defense_pressurization, h_defense_cinnamon]
                model_arrs.append(m_arr)
            probs = clf.predict_proba(model_arrs)
            counter = 0
            for hitter, __ in sorted_h_hitters.items():
                hitter_models[hitter] = probs[counter]
                counter += 1
            for hitter, __ in sorted_a_hitters.items():
                hitter_models[hitter] = probs[counter]
                counter += 1
        return hitter_models

    async def simulate(self, games, model, team_stlats, sim_length):
        print("Beginning Simulation")
        a_favored_wins, p_favored_wins, predicted_wins = 0, 0, 0
        day = games[0]['day']
        season = games[0]['season']
        output_text = f"Day: {day}\n"
        results = {}
        for game in games:
            home_scores = []
            away_scores = []
            home_shutout = 0
            home_wins = 0
            away_shutout = 0
            away_wins = 0
            home_struckout = []
            away_struckout = []
            homeTeam, awayTeam = game["homeTeam"], game["awayTeam"]
            home_name = self.bot.team_names[homeTeam]
            away_name = self.bot.team_names[awayTeam]
            home_lineup = {k: v for k, v in
                           sorted(team_stlats[homeTeam]["lineup"].items(), key=lambda item: item[1]["order"])}
            away_lineup = {k: v for k, v in
                           sorted(team_stlats[awayTeam]["lineup"].items(), key=lambda item: item[1]["order"])}
            for i in range(sim_length):
                home_score, away_score = 0, 0
                home_order, away_order = 0, 0
                home_strikeouts, away_strikeouts = 0, 0
                inning = 0
                while True:
                    a_runs, away_order, a_strikeouts = await self.simulate_inning(model, away_lineup, away_order)
                    away_score += a_runs
                    away_strikeouts += a_strikeouts
                    if inning == 8 and home_score != away_score:
                        break
                    h_runs, home_order, h_strikeouts = await self.simulate_inning(model, home_lineup, home_order)
                    home_score += h_runs
                    home_strikeouts += h_strikeouts
                    if inning >= 8 and home_score != away_score:
                        break
                    inning += 1
                home_scores.append(home_score)
                away_scores.append(away_score)
                if home_score == 0:
                    home_shutout += 1
                if away_score == 0:
                    away_shutout += 1
                if home_score > away_score:
                    home_wins += 1
                else:
                    away_wins += 1
                home_struckout.append(home_strikeouts)
                away_struckout.append(away_strikeouts)
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

            if game['homeScore'] > game['awayScore']:
                if statistics.mean(home_scores) > statistics.mean(away_scores):
                    predicted_wins += 1
            else:
                if statistics.mean(away_scores) > statistics.mean(home_scores):
                    predicted_wins += 1
            if statistics.mean(home_scores) > statistics.mean(away_scores):
                predicted_winner = home_name
            else:
                predicted_winner = away_name

            p_idxs = [.50, .75, .90, .99]

            def score_percentiles(scores):
                count = len(scores)
                prob_vals = []
                for p in p_idxs:
                    idx = round((p * count) - 1)
                    prob_vals.append(scores[idx])
                return prob_vals

            home_p_scores = score_percentiles(home_scores)
            away_p_scores = score_percentiles(away_scores)
            home_big_scores = len(list(filter(lambda s: s >= 10, home_scores))) / sim_length
            away_big_scores = len(list(filter(lambda s: s >= 10, away_scores))) / sim_length
            home_xbig_scores = len(list(filter(lambda s: s >= 20, home_scores))) / sim_length
            away_xbig_scores = len(list(filter(lambda s: s >= 20, away_scores))) / sim_length
            home_p_result = [(item[0], item[1]) for item in zip(p_idxs, home_p_scores)]
            away_p_result = [(item[0], item[1]) for item in zip(p_idxs, away_p_scores)]
            home_p_strs = [str(y) for y in sorted(home_p_result, key=lambda x: x[0], reverse=True)]
            away_p_strs = [str(y) for y in sorted(away_p_result, key=lambda x: x[0], reverse=True)]
            home_so_per = round((home_shutout / sim_length)*1000)/10
            away_so_per = round((away_shutout / sim_length) * 1000) / 10
            home_win_per = round((home_wins / sim_length) * 1000) / 10
            away_win_per = round((away_wins / sim_length) * 1000) / 10
            output_text += (
                  f"Predicted Score: {home_name} {statistics.mean(home_scores)} - {', '.join(home_p_strs)}\n"
                  f"Predicted Score: {away_name} {statistics.mean(away_scores)} - {', '.join(away_p_strs)}\n"
                  f"Predicted winner: {predicted_winner}\n"
                  f"{home_name} predicted Ks: {statistics.mean(home_struckout)} - "
                  f"{away_name} predicted Ks: {statistics.mean(away_struckout)}\n"
                  f"{home_name} shutout %: {home_so_per}% - "
                  f"{away_name} shutout %: {away_so_per}%\n"
                  f"{home_name} win %: {home_win_per}% - Odds: {game['homeOdds']}\n"
                  f"{away_name} win %: {away_win_per}% - Odds: {game['awayOdds']}\n\n"
                  )
            results[game['homeTeam']] = {"shutout_percentage": home_so_per,
                                         "win_percentage": home_win_per,
                                         "strikeout_percentage": statistics.mean(home_struckout),
                                         "over_ten": home_big_scores,
                                         "over_twenty": home_xbig_scores,
                                         "weather": game['weather']}
            results[game['awayTeam']] = {"shutout_percentage": away_so_per,
                                         "win_percentage": away_win_per,
                                         "strikeout_percentage": statistics.mean(away_struckout),
                                         "over_ten": away_big_scores,
                                         "over_twenty": away_xbig_scores,
                                         "weather": game['weather']}
        with open(os.path.join('data', 'pendant_data', 'results', f"s{season}_d{day}_results.txt"), 'a') as fd:
            fd.write((output_text))
        return f"Day: {games[0]['day']} Predicted wins: {predicted_wins} - favored wins: {a_favored_wins}", results

    async def simulate_inning(self, model, lineup, order):
        bases = {1: 0, 2: 0, 3: 0}
        outs = 0
        score = 0
        strikeouts = 0
        while True:
            hitter_id = list(lineup.keys())[order]
            if hitter_id not in model:
                order += 1
                if order == len(lineup):
                    order = 0
                continue
            hitter = model[hitter_id]
            out, runs, bases, strikeout = await self.simulate_at_bat(bases, hitter)
            outs += out
            strikeouts += strikeout
            if outs == 3:
                break
            score += runs
            order += 1
            if order == len(lineup):
                order = 0
        return score, order, strikeouts

    async def simulate_at_bat(self, bases, hitter):
        # [field_out %, strike_out %, walk %, single %, double %, triple %, hr %]
        play = await self.simulate_play(hitter)
        good_odds = random.random() < .66666
        out, strikeout = False, False
        runs = 0
        if play == 0:
            out = True
            if bases[3]:
                if good_odds:
                    runs += 1
                    bases[3] = 0
            if bases[2] and not bases[3]:
                if good_odds:
                    bases[3] = 1
                    bases[2] = 0
            if bases[1] and not bases[2]:
                if good_odds:
                    bases[2] = 1
                    bases[1] = 0
        elif play == 1:
            out = True
            strikeout = True
        elif play == 2:
            if bases[3]:
                runs += 1
                bases[3] = 0
            if bases[2]:
                bases[2] = 0
                bases[3] = 1
            if bases[1]:
                bases[1] = 0
                bases[2] = 1
            bases[1] = 1
        elif play == 3:
            third = False
            if bases[3]:
                runs += 1
                bases[3] = 0
            if bases[2]:
                if good_odds:
                    runs += 1
                else:
                    third = True
                    bases[3] = 1
                bases[2] = 0
            if bases[1]:
                if good_odds and not third:
                    bases[3] = 1
                else:
                    bases[2] = 1
                bases[1] = 0
            bases[1] = 0
        elif play == 4:
            if bases[3]:
                runs += 1
                bases[3] = 0
            if bases[2]:
                runs += 1
                bases[2] = 0
            if bases[1]:
                if not good_odds:
                    bases[3] = 1
                else:
                    runs += 1
                bases[1] = 0
            bases[2] = 1
        elif play >= 5:
            if bases[3]:
                runs += 1
                bases[3] = 0
            if bases[2]:
                runs += 1
                bases[2] = 0
            if bases[1]:
                runs += 1
                bases[1] = 0
            if play == 5:
                bases[3] = 1
            else:
                runs += 1
        return out, runs, bases, strikeout

    async def simulate_play(self, hitter, roll=None):
        if not roll:
            roll = random.random()
        total = 0
        for i in range(len(hitter)):
            total += hitter[i]
            if roll < total:
                return i

    async def setup(self, sim_length):
        html_response = await self.retry_request("https://www.blaseball.com/database/simulationdata")
        if not html_response:
            print('Bet Advice daily message failed to acquire sim data and exited.')
            return
        sim_data = html_response.json()
        season = sim_data['season']
        day = sim_data['day'] + 1

        clf = load(os.path.join("data", "pendant_data", "ab.joblib"))

        games = await self.retry_request(f"https://www.blaseball.com/database/games?day={day}&season={season}")
        games_json = games.json()

        pitcher_stlats, team_stlats = await self.get_player_stlats()

        model = await self.setup_model(games_json, clf, pitcher_stlats, team_stlats)
        outcome_msg, results = await self.simulate(games_json, model, team_stlats, sim_length)
        sorted_shutout_percentage = {k: v for k, v in
                                     sorted(results.items(),
                                            key=lambda item: item[1]["shutout_percentage"],
                                            reverse=True)}
        return sorted_shutout_percentage

    @commands.command(aliases=['tsho'])
    async def _test_shut_out_sim(self, ctx):
        results = await self.setup(1000)
        top_five_shos = list(results.keys())[:5]
        message = ""
        for key in top_five_shos:
            team_name = self.bot.team_names[key]
            message += f"{team_name}: {results[key]['shutout_percentage']}%\n"
        return await ctx.send(message)

def setup(bot):
    bot.add_cog(GameSim(bot))
