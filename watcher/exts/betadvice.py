import asyncio
import csv
import json
import os
from typing import Dict

import aiosqlite
from joblib import load

import discord
import requests
from discord.ext import commands

from watcher import utils
from watcher.exts import gamedata

team_id_name_map: Dict[str, str] = {
        "lovers": "b72f3061-f573-40d7-832a-5ad475bd7909",
        "tacos": "878c1bf6-0d21-4659-bfee-916c8314d69c",
        "steaks": "b024e975-1c4a-4575-8936-a3754a08806a",
        "breath mints": "adc5b394-8f76-416d-9ce9-813706877b84",
        "firefighters": "ca3f1c8c-c025-4d8e-8eef-5be6accbeb16",
        "shoe thieves": "bfd38797-8404-4b38-8b82-341da28b1f83",
        "flowers": "3f8bbb15-61c0-4e3f-8e4a-907a5fb1565e",
        "fridays": "979aee4a-6d80-4863-bf1c-ee1a78e06024",
        "magic": "7966eb04-efcc-499b-8f03-d13916330531",
        "millennials": "36569151-a2fb-43c1-9df7-2df512424c82",
        "crabs": "8d87c468-699a-47a8-b40d-cfb73a5660ad",
        "spies": "9debc64f-74b7-4ae1-a4d6-fce0144b6ea5",
        "pies": "23e4cbc1-e9cd-47fa-a35b-bfa06f726cb7",
        "sunbeams": "f02aeae2-5e6a-4098-9842-02d2273f25c7",
        "wild wings": "57ec08cc-0411-4643-b304-0e80dbc15ac7",
        "tigers": "747b8e4a-7e50-4638-a973-ea7950a3e739",
        "moist talkers": "eb67ae5e-c4bf-46ca-bbbc-425cd34182ff",
        "dale": "b63be8c2-576a-4d6e-8daf-814f8bcea96f",
        "garages": "105bc3ff-1320-4e37-8ef0-8d595cb95dd0",
        "jazz hands": "a37f9158-7f82-46bc-908c-c9e2dda7c33b",
        "lift": "c73b705c-40ad-4633-a6ed-d357ee2e2bcf",
        "georgias": "d9f89a8a-c563-493e-9d64-78e4f9a55d4a",
        "mechanics": "46358869-dce9-4a01-bfba-ac24fc56f57e",
        "worms": "bb4a9de5-c924-4923-a0cb-9d1445f1ee5d",
    }

team_name_map: Dict[str, str] = {
    "b72f3061-f573-40d7-832a-5ad475bd7909": "lovers",
    "878c1bf6-0d21-4659-bfee-916c8314d69c": "tacos",
    "b024e975-1c4a-4575-8936-a3754a08806a": "steaks",
    "adc5b394-8f76-416d-9ce9-813706877b84": "breath mints",
    "ca3f1c8c-c025-4d8e-8eef-5be6accbeb16": "firefighters",
    "bfd38797-8404-4b38-8b82-341da28b1f83": "shoe thieves",
    "3f8bbb15-61c0-4e3f-8e4a-907a5fb1565e": "flowers",
    "979aee4a-6d80-4863-bf1c-ee1a78e06024": "fridays",
    "7966eb04-efcc-499b-8f03-d13916330531": "magic",
    "36569151-a2fb-43c1-9df7-2df512424c82": "millennials",
    "8d87c468-699a-47a8-b40d-cfb73a5660ad": "crabs",
    "9debc64f-74b7-4ae1-a4d6-fce0144b6ea5": "spies",
    "23e4cbc1-e9cd-47fa-a35b-bfa06f726cb7": "pies",
    "f02aeae2-5e6a-4098-9842-02d2273f25c7": "sunbeams",
    "57ec08cc-0411-4643-b304-0e80dbc15ac7": "wild wings",
    "747b8e4a-7e50-4638-a973-ea7950a3e739": "tigers",
    "eb67ae5e-c4bf-46ca-bbbc-425cd34182ff": "moist talkers",
    "b63be8c2-576a-4d6e-8daf-814f8bcea96f": "dale",
    "105bc3ff-1320-4e37-8ef0-8d595cb95dd0": "garages",
    "a37f9158-7f82-46bc-908c-c9e2dda7c33b": "jazz hands",
    "c73b705c-40ad-4633-a6ed-d357ee2e2bcf": "lift",
    "d9f89a8a-c563-493e-9d64-78e4f9a55d4a": "georgias",
    "46358869-dce9-4a01-bfba-ac24fc56f57e": "mechanics",
    "bb4a9de5-c924-4923-a0cb-9d1445f1ee5d": "worms",
}


class BetAdvice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.team_short_map = None

    @commands.command(name="build_power_ranking_matchups", aliases=['bprm'])
    async def build_power_ranking_matchups(self, ctx):
        matchups = []
        for team_name, team_id in team_id_name_map.items():
            m = {"team_name": team_name, "team_id": team_id, "matches": []}
            for __, o_team_id in team_id_name_map.items():
                if o_team_id != team_id:
                    m["matches"].append(o_team_id)
            matchups.append(m)
        with open(os.path.join('data', 'bprm', 'matches.json'), 'w') as file:
            json.dump(matchups, file)

    async def get_short_map(self):
        if self.team_short_map:
            return self.team_short_map
        with open(os.path.join('data', 'allTeams.json'), 'r', encoding='utf-8') as file:
            all_teams = json.load(file)
        team_short_map = {}
        for team in all_teams:
            team_short_map[team["id"]] = team["shorthand"]
        self.team_short_map = team_short_map
        return team_short_map

    async def get_player_stlats(self):
        batters = {}
        pitcher_ids = []
        pitcher_stlats = {}
        team_stlats = {}
        teams_response = await utils.retry_request("https://www.blaseball.com/database/allteams")
        teams_json = teams_response.json()
        for team in teams_json:
            team_stlats[team["id"]] = {"lineup": {}}
            pitcher_ids += team["rotation"]
            for batter in team["lineup"]:
                batters[batter] = team["id"]
        chunked_pitcher_ids = [pitcher_ids[i:i + 50] for i in range(0, len(pitcher_ids), 50)]
        for chunk in chunked_pitcher_ids:
            b_url = f"https://www.blaseball.com/database/players?ids={','.join(chunk)}"
            pitcher_response = await utils.retry_request(b_url)
            pitcher_json = pitcher_response.json()
            for pitcher in pitcher_json:
                pitcher_stlats[pitcher["id"]] = pitcher
        batter_ids = list(batters.keys())
        chunked_batter_ids = [batter_ids[i:i + 50] for i in range(0, len(batter_ids), 50)]
        for chunk in chunked_batter_ids:
            b_url = f"https://www.blaseball.com/database/players?ids={','.join(chunk)}"
            batter_response = await utils.retry_request(b_url)
            batter_json = batter_response.json()
            for batter in batter_json:
                team_id = batters[batter["id"]]
                team_stlats[team_id]["lineup"][batter["id"]] = batter
        return pitcher_stlats, team_stlats

    async def strikeout_odds(self, hp_stlats, opp_stlats, clf, team_stats, day, at_bat_counts):
        stlats_arr = []
        unthwack = float(hp_stlats["unthwackability"])
        ruth = float(hp_stlats["ruthlessness"])
        overp = float(hp_stlats["overpowerment"])
        cold = float(hp_stlats["coldness"])
        lineup_size = len(opp_stlats["lineup"].items())
        lineup = []
        for pid, opponent in opp_stlats["lineup"].items():
            lineup.append(pid)
            s_arr = []
            for stlat in ["tragicness", "patheticism", "thwackability", "divinity",
                          "moxie", "musclitude", "laserlikeness", "continuation",
                          "baseThirst", "indulgence", "groundFriction"]:
                s_arr.append(float(opponent[stlat]))
            s_arr += [unthwack, ruth, overp, cold]
            stlats_arr.append(s_arr)
        odds_list = clf.predict_proba(stlats_arr)
        odds_sum = 0

        for i in range(len(odds_list)):
            odds = odds_list[i][1]
            pid = lineup[i]
            if pid in at_bat_counts:
                plate_appearances = at_bat_counts[pid]
            else:
                plate_appearances = team_stats["plate_appearances"] / lineup_size
            odds *= plate_appearances / day
            odds_sum += odds
        return odds_sum

    @commands.command(name='single_game_sim', aliases=['sgs'])
    async def _single_game_sim(self, ctx, *, info):
        """Usage: !single_game_sim <day>, <iterations>, <away team>, <home team> [, rerun]
        Team names must be accurate for that day or the sim will run the actual game
        for whichever team is found first. Optionally include 'true' at the end to rerun
        a previously run sim."""
        if ctx.message.author.id not in [329316904714108931, 371387628093833216]:
            return await ctx.message.delete()
        season = self.bot.config['current_season'] - 1
        info_split = info.split(',')
        day = int(info_split[0].strip())
        if day < 0:# or day > 98:
            return await ctx.send(f"{day} is out of the range of a season (0-98)")
        iterations = int(info_split[1].strip())
        if iterations > 1000:
            await ctx.send(f"{iterations} is too many, running 1000 iterations.")
            iterations = 1000

        away_team_name = info_split[2].strip()
        home_team_name = info_split[3].strip()
        away_team = team_id_name_map.get(away_team_name, None)
        home_team = team_id_name_map.get(home_team_name, None)
        if not away_team:
            return await ctx.send(f"Could not find team: {away_team_name}")
        if not home_team:
            return await ctx.send(f"Could not find team: {home_team_name}")
        filename = os.path.join('data', 'season_sim', 'results', 'singles',
                                f"s{season}_d{day}_{iterations}_{away_team_name}_{home_team_name}_sim_results.json")
        rerun = False
        if len(info_split) > 4:
            rerun_str = info_split[4]
            if rerun_str.strip().lower() == "true":
                rerun = True
        if not rerun:
            if os.path.exists(filename):
                with open(filename, 'r') as file:
                    result = json.load(file)

                debug_message = await self._create_debug_message(result['data'], day)
                return await ctx.send(debug_message)

        data = {"iterations": iterations,
                "day": day,
                "away_team": away_team,
                "home_team": home_team,
                "save_stlats": "false"}
        async with self.bot.session.get(url=f'http://localhost:5555/v1/dailysim', json=data,
                                        timeout=1200) as response:
            result = await response.json()
        day, time_elapsed = result['day'], result["time_elapsed"]
        debug_message = await self._create_debug_message(result['data'], day)
        await ctx.send(debug_message)

        with open(filename, 'w') as file:
            json.dump(result, file)
            print(f"ran {iterations} iter sim for day {day} {away_team_name} "
                  f"at {home_team_name} in {time_elapsed} seconds")

    @commands.command(name="run_power_rank_sim", aliases=['rprs', 'power'])
    async def _run_power_rank_sim(self, ctx, season, iterations):
        data = {"iterations": iterations,
                "season": season}
        async with self.bot.session.get(url=f'http://localhost:5555/v1/powerrankings', json=data,
                                        timeout=75000) as response:
            result = await response.json()
            await ctx.send(result["output"])

    @commands.command()
    async def rds(self, ctx, day: int):
        data = {"iterations": 501, "day": day}
        async with self.bot.session.get(url=f'http://localhost:5555/v1/dailysim', json=data, timeout=1200) as response:
            result = await response.json()
        day, time_elapsed = result['day'], result["time_elapsed"]
        with open(os.path.join('data', 'season_sim', 'results', f"s15_d{day}_sim_results_rerun.json"), 'w') as file:
            json.dump(result, file)
        output_msg = await self._create_debug_message(result['data'], day)
        outputchan_id = self.bot.config['game_sim_output_chan_id']
        output_channel = self.bot.get_channel(outputchan_id)
        if output_channel:
            await output_channel.send(output_msg)
        print(f"ran 501 iter sim for day {day} in {time_elapsed} seconds")

    async def run_daily_sim(self, season, iterations):
        data = {"iterations": iterations}
        async with self.bot.session.get(url=f'http://localhost:5555/v1/dailysim', json=data, timeout=1200) as response:
            result = await response.json()
        day, time_elapsed = result['day'], result["time_elapsed"]
        with open(os.path.join('data', 'season_sim', 'results', f"s{season}_d{day}_sim_results.json"), 'w') as file:
            json.dump(result, file)
        debug_message = await self._create_debug_message(result['data'], day)
        outputchan_id = self.bot.config['game_sim_output_chan_id']
        output_channel = self.bot.get_channel(outputchan_id)
        if output_channel and len(debug_message) > 15:
            await output_channel.send(debug_message)
        return time_elapsed

    async def update_day_winners(self, season, day):
        upset_wins, upset_losses = 0, 0
        try:
            filepath = os.path.join('data', 'season_sim', 'results', f"s{season}_d{day}_sim_results.json")
            if os.path.exists(filepath):
                with open(filepath, 'r') as file:
                    day_results = json.load(file)
                url = f"https://blaseball.com/database/games?day={day}&season={season}"
                html_response = await utils.retry_request(url)
                rows = []
                if html_response:
                    day_data = html_response.json()
                    for game in day_data:
                        upset = day_results["data"][game["id"]]["upset"]
                        if game["homeScore"] > game["awayScore"]:
                            day_results["data"][game["id"]]["home_team"]["win"] = True
                            if upset:
                                if day_results["data"][game["id"]]["home_team"]["win_percentage"] > \
                                        day_results["data"][game["id"]]["away_team"]["win_percentage"]:
                                    upset_wins += 1
                                else:
                                    upset_losses += 1
                        else:
                            day_results["data"][game["id"]]["away_team"]["win"] = True
                            if upset:
                                if day_results["data"][game["id"]]["away_team"]["win_percentage"] > \
                                        day_results["data"][game["id"]]["home_team"]["win_percentage"]:
                                    upset_wins += 1
                                else:
                                    upset_losses += 1

                        row = [
                            season,
                            day,
                            game["id"],
                            day_results["data"][game["id"]]["home_team"]["team_id"],
                            day_results["data"][game["id"]]["home_team"]["odds"],
                            day_results["data"][game["id"]]["home_team"]["shutout_percentage"],
                            day_results["data"][game["id"]]["home_team"]["win"],
                            day_results["data"][game["id"]]["home_team"]["win_percentage"],
                            day_results["data"][game["id"]]["away_team"]["team_id"],
                            day_results["data"][game["id"]]["away_team"]["odds"],
                            day_results["data"][game["id"]]["away_team"]["shutout_percentage"],
                            day_results["data"][game["id"]]["away_team"]["win"],
                            day_results["data"][game["id"]]["away_team"]["win_percentage"],
                            upset,
                            day_results["data"][game["id"]]["weather"],
                        ]
                        rows.append(row)
                with open(os.path.join('data', 'season_sim', 'results', f"s{season}_d{day}_sim_results.json"), 'w') as file:
                    json.dump(day_results, file)
                async with aiosqlite.connect(self.bot.db_path) as db:
                    await db.executemany("insert into DailyGameResultsTable (season, day, gameid, hometeamid, "
                                         "hometeamodds, hometeamshutoutpercentage, hometeamwin, hometeamwinpercentage, "
                                         "awayteamid, awayteamodds, awayteamshutoutpercentage, awayteamwin, "
                                         "awayteamwinpercentage, upset, weather) values "
                                         "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);", rows)
                    await db.commit()
        except Exception as e:
            print(e)
        return upset_wins, upset_losses

    async def daily_message(self, season, day):
        if int(day) < 99:
            with open(os.path.join('data', 'season_sim', 'results', f"s{season}_d{day}_sim_results.json"), 'r') as file:
                result = json.load(file)
            results, day, output = result['data'], result['day'], result['output']
        else:
            data = {"iterations": 501}
            async with self.bot.session.get(url=f'http://localhost:5555/v1/dailysim', json=data,
                                            timeout=1200) as response:
                result = await response.json()
            results, day, time_elapsed = result['data'], result['day'], result['output']
            with open(os.path.join('data', 'season_sim', 'results', f"s{season}_d{day}_sim_results.json"), 'w') as file:
                json.dump(result, file)

        message = f"Daily Outlook for **day {day+1}**\n" \
                  "Predictions are generated by a Machine Learning model simulating all games courtesy of kjc9#9000\n" \
                  "Games under the 'Caveat Emptor' heading have simulated results closer than the odds on the site, " \
                  "bet with caution!"

        try:
            async with aiosqlite.connect(self.bot.db_path) as db:
                async with db.execute("select count(*) as correct_upsets from dailygameresultstable where "
                                      "( "
                                      "    (.495 < hometeamodds and hometeamodds < .505) and "
                                      "        ( "
                                      "            (hometeamwinpercentage > awayteamwinpercentage) or "
                                      "            (awayteamwinpercentage > hometeamwinpercentage ) "
                                      "        ) "
                                      "    ) "
                                      "or "
                                      "( "
                                      "    (hometeamwinpercentage > awayteamwinpercentage and "
                                      "        ( "
                                      "            (hometeamodds < .495 or hometeamodds > .505) and "
                                      "            (hometeamodds < awayteamodds) "
                                      "        ) "
                                      "    ) "
                                      "or "
                                      "    (awayteamwinpercentage > hometeamwinpercentage and "
                                      "        ( "
                                      "            (hometeamodds < .495 or hometeamodds > .505) and "
                                      "            (awayteamodds < hometeamodds) "
                                      "        ) "
                                      "    ) "
                                      ") "
                                      " and season = ?;", [season]) as cursor:
                    async for row in cursor:
                        if row and row[0] is not None:
                            predict_count = row[0]

                async with db.execute("select count(*) as correct_upsets from dailygameresultstable where  "
                                      "( "
                                          "(.495 < hometeamodds and hometeamodds < .505) and  "
                                              "((hometeamwinpercentage > awayteamwinpercentage and hometeamwin) or "
                                               "(awayteamwinpercentage > hometeamwinpercentage  and awayteamwin)) "
                                      ") "
                                      "or  "
                                      "( "
                                          "(hometeamwin and hometeamwinpercentage > awayteamwinpercentage and  "
                                              "( "
                                                  "(hometeamodds < .495 or hometeamodds > .505) and "
                                                  "(hometeamodds < awayteamodds) "
                                              ") "
                                          ")  "
                                      "or  "
                                      "( "
                                          "awayteamwin and awayteamwinpercentage > hometeamwinpercentage and  "
                                              "( "
                                                  "(hometeamodds < .495 or hometeamodds > .505) and  "
                                                  "(awayteamodds < hometeamodds) "
                                              ") "
                                          ")                                    "
                                      ") "
                                      "and season = ?; ", [season]) as cursor:
                    async for row in cursor:
                        if row and row[0] is not None:
                            correct_count = row[0]

                async with db.execute("select count(*) from dailygameresultstable where "
                                      "((hometeamwin and hometeamwinpercentage > awayteamwinpercentage) or "
                                      "(awayteamwin and awayteamwinpercentage > hometeamwinpercentage)) "
                                      "and season = ?;", [season]) as cursor:
                    async for row in cursor:
                        if row and row[0] is not None:
                            predict_win_count = row[0]

                async with db.execute("select count(*) from dailygameresultstable where "
                                      "((hometeamwin and hometeamodds > awayteamodds) or "
                                      "(awayteamwin and awayteamodds > hometeamodds)) "
                                      "and season = ?;", [season]) as cursor:
                    async for row in cursor:
                        if row and row[0] is not None:
                            site_win_count = row[0]

                async with db.execute("select count(*) from dailygameresultstable where season=?;", [season]) as cursor:
                    async for row in cursor:
                        if row and row[0] is not None:
                            game_count = row[0]

            ratio = round((correct_count/predict_count) * 1000)/10
            message += f"\n\nSo far this season **{correct_count}** of **{predict_count}** predicted upsets have been " \
                       f"correct (**{ratio}%**)."
            # message += f"\nOf **{game_count}** games this season, odds displayed on the site have predicted " \
            #            f"**{site_win_count}** wins while the bot has predicted **{predict_win_count}** for an " \
            #            f"improvement of **{predict_win_count-site_win_count}** bet wins."
        except:
            pass

        embed_fields = []

        team_short_map = await self.get_short_map()
        # daily_leaders = None
        # f_day = day+1
        # while daily_leaders == None:
        #     try:
        #         with open(os.path.join('data', 'pendant_data', 'statsheets', f'd{f_day}_leaders.json'), 'r') as file:
        #             daily_leaders = json.load(file)
        #     except FileNotFoundError:
        #         f_day -= 1
        #     if f_day < 0:
        #         break

        # hitter_list = []
        # for player in daily_leaders["seed_dog"][:3]:
        #     name = player["name"]
        #     shorthand = team_short_map[player["teamId"]]
        #     hits = player["hitsMinusHrs"]
        #     home_runs = player["homeRuns"]
        #     mult_text = ""
        #     if "multiplier" in player:
        #         if int(player["multiplier"]) > 1:
        #             mult_text = f' ({str(player["multiplier"])}x)'
        #     entry = f"[{name}]({'https://www.blaseball.com/player/' + player['playerId']}) "
        #     entry += f"([{shorthand}]({'https://www.blaseball.com/team/' + player['teamId']}))"
        #     entry += f"\n[{hits} hits, {home_runs} HRs]({'https://blaseball-reference.com/players/' + player['playerId']}){mult_text}"
        #     hitter_list.append(entry)
        #
        # embed_fields.append({"name": "Best Idols - Hold the Pickles",
        #                      "value": '\n'.join(hitter_list)})
        #
        # hitter_list = []
        # for player in daily_leaders["combo"][:3]:
        #     name = player["name"]
        #     shorthand = team_short_map[player["teamId"]]
        #     hits = player["hitsMinusHrs"]
        #     home_runs = player["homeRuns"]
        #     steals = player["stolenBases"]
        #     entry = f"[{name}]({'https://www.blaseball.com/player/' + player['playerId']}) "
        #     entry += f"([{shorthand}]({'https://www.blaseball.com/team/' + player['teamId']}))"
        #     entry += f"\n[{hits} hits, {home_runs} HRs, {steals} SBs]({'https://blaseball-reference.com/players/' + player['playerId']})"
        #     hitter_list.append(entry)
        #
        # embed_fields.append({"name": "Best Idols - With Pickles",
        #                      "value": '\n'.join(hitter_list)})

        pitcher_opp_strikeouts = {}
        for game in results.values():
            pitcher_opp_strikeouts[game["home_team"]["opp_pitcher"]["pitcher_id"]] = {
                "strikeout_avg": game["home_team"]["strikeout_avg"],
                "name": game["home_team"]["opp_pitcher"]["pitcher_name"],
                "team": game["home_team"]["opp_pitcher"]["p_team_id"]
            }
            pitcher_opp_strikeouts[game["away_team"]["opp_pitcher"]["pitcher_id"]] = {
                "strikeout_avg": game["away_team"]["strikeout_avg"],
                "name": game["away_team"]["opp_pitcher"]["pitcher_name"],
                "team": game["away_team"]["opp_pitcher"]["p_team_id"]
            }

        sorted_so_preds = {k: v for k, v in sorted(pitcher_opp_strikeouts.items(),
                                                   key=lambda item: item[1]['strikeout_avg'],
                                                   reverse=True)}
        top_list = list(sorted_so_preds.keys())[:4]
        pitcher_list = []
        for key in top_list:
            pitcher = pitcher_opp_strikeouts[key]
            name = pitcher["name"]
            shorthand = team_short_map[pitcher["team"]]

            opp_k_per = pitcher["strikeout_avg"]
            pred = round(opp_k_per * 10) / 10
            entry = f"[{name}]({'https://www.blaseball.com/player/'+key}) "
            entry += f"([{shorthand}]({'https://www.blaseball.com/team/' + pitcher['team']}))"
            entry += f" - [{pred}]({'https://blaseball-reference.com/players/'+key}) "
            pitcher_list.append(entry)

        embed_fields.append({"name": "Strikeout Predictions",
                             "value": '\n'.join(pitcher_list)})

        shutouts = {}
        for game in results.values():
            shutouts[game["home_team"]["team_id"]] = game["home_team"]["shutout_percentage"]
            shutouts[game["away_team"]["team_id"]] = game["away_team"]["shutout_percentage"]

        sorted_shutout_preds = {k: v for k, v in sorted(shutouts.items(), key=lambda item: item[1], reverse=True)}
        top_list = list(sorted_shutout_preds.keys())[:3]
        sh_message = ""
        for key in top_list:
            team_name = self.bot.team_names[key]
            sh_message += f"{team_name}: {shutouts[key]}%\n"
        embed_fields.append({"name": "Teams most likely to be shutout",
                             "value": sh_message})

        over_ten_check = {}
        for game in results.values():
            game["home_team"]['weather'] = game['weather']
            over_ten_check[game["home_team"]["team_id"]] = game["home_team"]
            game["away_team"]['weather'] = game['weather']
            over_ten_check[game["away_team"]["team_id"]] = game["away_team"]
        sorted_big_scores = {k: v for k, v in sorted(over_ten_check.items(),
                                                     key=lambda item: item[1]['over_ten'],
                                                     reverse=True)}
        big_message = ""
        for key in list(sorted_big_scores.keys()):
            if sorted_big_scores[key]['over_ten'] > .03:
                weather = sorted_big_scores[key]["weather"]
                if weather == 1 or weather == 14:
                    weather_name = gamedata.weather_types[weather]
                    team_name = self.bot.team_names[key]
                    over_ten = round(sorted_big_scores[key]['over_ten'] * 1000) / 10
                    big_message += f"{team_name}: {over_ten}% chance\n({weather_name})\n"
            else:
                break

        if len(big_message) > 0:
            embed_fields.append({"name": "Teams most likely to score 10+",
                                 "value": big_message})

        black_hole_games, flood_games, sun_two_games, eclipse_games = 0, 0, 0, 0
        for game in results.values():
            if game["weather"] == 14:
                black_hole_games += 1
            if game["weather"] == 18:
                flood_games += 1
            if game["weather"] == 1:
                sun_two_games += 1
            if game["weather"] == 7:
                eclipse_games += 1
        black_hole_games = int(black_hole_games)
        flood_games = int(flood_games)
        sun_two_games = int(sun_two_games)
        eclipse_games = int(eclipse_games)

        weather_msg = ""
        if black_hole_games > 0:
            weather_msg += f"{black_hole_games} games in Black Hole Weather\n"
        if sun_two_games > 0:
            weather_msg += f"{sun_two_games} games in Sun 2 Weather\n"
        if flood_games > 0:
            weather_msg += f"{flood_games} games in Flooding Weather\n"
        if eclipse_games > 0:
            weather_msg += f"{eclipse_games} games in Eclipse Weather\n"
        if len(weather_msg) > 0:
            embed_fields.append({"name": "Weather Forecast",
                                 "value": weather_msg})

        if day < 99:
            upset_msg = ""
            sorted_results = {k: v for k, v in
                              sorted(results.items(), key=lambda item: item[1]["win_percentage"], reverse=True)
                              if v["upset"] == True}
            for item in sorted_results.values():
                win_per = item["win_percentage"]
                home_team, away_team = item["home_team"], item["away_team"]
                if home_team["win_percentage"] > away_team["win_percentage"]:
                    team_name = self.bot.team_names[home_team["team_id"]]
                    odds = round(home_team["odds"] * 1000) / 10

                    upset_msg += f"{team_name} {odds}% site odds - **{win_per}% sim odds**\n"
                else:
                    team_name = self.bot.team_names[away_team["team_id"]]
                    odds = round(away_team["odds"] * 1000) / 10
                    upset_msg += f"{team_name} {odds}% site odds - **{win_per}% sim odds**\n"

            if len(upset_msg) > 0:
                embed_fields.append({"name": "SimSim's Spicy Picks",
                                     "value": upset_msg})

            close_msg = ""
            sorted_close = {k: v for k, v in
                            sorted(results.items(), key=lambda item: item[1]["win_percentage"], reverse=True)
                            if v["win_percentage"] / 100 < v["odds"] and v["upset"] is False}
            for item in sorted_close.values():
                win_per = item["win_percentage"]
                home_team, away_team = item["home_team"], item["away_team"]
                if home_team["win_percentage"] > away_team["win_percentage"]:
                    team_name = self.bot.team_names[home_team["team_id"]]
                    odds = round(home_team["odds"] * 1000) / 10

                    close_msg += f"{team_name} {odds}% site odds - **{win_per}% sim odds**\n"
                else:
                    team_name = self.bot.team_names[away_team["team_id"]]
                    odds = round(away_team["odds"] * 1000) / 10

                    close_msg += f"{team_name} {odds}% site odds - **{win_per}% sim odds**\n"

            if len(close_msg) > 0:
                embed_fields.append({"name": "Caveat Emptor",
                                     "value": close_msg})
        else:
            sorted_results = {k: v for k, v in
                              sorted(results.items(), key=lambda item: item[1]["win_percentage"], reverse=True)}
            predict_msg = ""
            for item in sorted_results.values():
                win_per = item["win_percentage"]
                home_team, away_team = item["home_team"], item["away_team"]
                if home_team["win_percentage"] > away_team["win_percentage"]:
                    team_name = self.bot.team_names[home_team["team_id"]]
                    odds = round(home_team["odds"] * 1000) / 10

                    predict_msg += f"{team_name} {odds}% site odds - **{win_per}% sim odds**\n"
                else:
                    team_name = self.bot.team_names[away_team["team_id"]]
                    odds = round(away_team["odds"] * 1000) / 10
                    predict_msg += f"{team_name} {odds}% site odds - **{win_per}% sim odds**\n"

            if len(predict_msg) > 0:
                embed_fields.append({"name": "SimSim's Pickled Postseason Picks",
                                     "value": predict_msg})

        output_msg = await self._create_debug_message(results, day)
        return message, embed_fields, output_msg

    async def _create_debug_message(self, results, day):
        output_msg = f"Day {day + 1}\n"
        sorted_results = {k: v for k, v in
                          sorted(results.items(), key=lambda item: item[1]["odds"], reverse=True)}
        for item in sorted_results.values():
            msg = ""
            home_team, away_team = item["home_team"], item["away_team"]
            if item["upset"]:
                msg += "‼️ "
            elif item["win_percentage"] / 100 > item["odds"]:
                msg += "✅ "
            else:
                msg += "⚠️ "
            home_odds = round(home_team["odds"] * 1000) / 10
            away_odds = round(away_team["odds"] * 1000) / 10

            ev_raw = self._calculate_ev(home_team["odds"], home_team['win_percentage'],
                                        away_team["odds"], away_team['win_percentage'])
            ev_str = f"{round(ev_raw * 1000) / 10}%"

            if home_team["win_percentage"] > away_team["win_percentage"]:
                diff = round((home_team['win_percentage'] - home_odds) * 100) / 100
                diff_str = f"{diff}"
                if diff >= 0:
                    diff_str = f"+{diff_str}"
                pred_str = f"**{home_team['team_name']}** sim: {home_team['win_percentage']}% " \
                           f"odds: {home_odds} **{diff_str}** EV: {ev_str}"
            else:
                diff = round((away_team['win_percentage'] - away_odds) * 100) / 100
                diff_str = f"{diff}"
                if diff >= 0:
                    diff_str = f"+{diff_str}"
                pred_str = f"**{away_team['team_name']}** sim: {away_team['win_percentage']}% " \
                           f"odds: {away_odds} **{diff_str}** EV: {ev_str}"
            msg += f"{pred_str}\n"
            output_msg += msg
        return output_msg

    @staticmethod
    def _calculate_ev(home_odds, home_win_percentage, away_odds, away_win_percentage):
        home_win_percentage /= 100
        away_win_percentage /= 100
        site_odds = home_odds if home_win_percentage > away_win_percentage else away_odds
        winning_team_percentage = max(home_win_percentage, away_win_percentage)

        if site_odds == 0.5:
            payout_ratio = 2
        elif site_odds < 0.5:
            payout_ratio = 2 + 0.0015 * (100 * (0.5 - site_odds)) ** 2.2
        else:
            payout_ratio = 3.206 / (1 + (0.443 * (site_odds - 0.5)) ** 0.95) - 1.206

        return (payout_ratio * winning_team_percentage) - 1

    async def _run_daily_sim(self):
        html_response = await utils.retry_request("https://www.blaseball.com/database/simulationdata")
        if not html_response:
            self.bot.logger.warning('Bet Advice daily message failed to acquire sim data and exited.')
            return
        sim_data = html_response.json()
        season = sim_data['season']
        day = sim_data['day'] + 1
        clf = load(os.path.join("data", "pendant_data", "so.joblib"))

        with open(os.path.join('data', 'pendant_data', 'statsheets', 'team_stats.json'), 'r') as file:
            team_stats = json.load(file)
        pitcher_stlats, team_stlats = await self.get_player_stlats()
        filename = os.path.join('data', 'pendant_data', 'stlats', f's{season}_d{day}_pitcher_stlats.json')
        with open(filename, 'w') as file:
            json.dump(pitcher_stlats, file)
        filename = os.path.join('data', 'pendant_data', 'stlats', f's{season}_d{day}_team_stlats.json')
        with open(filename, 'w') as file:
            json.dump(team_stlats, file)

        at_bat_counts = {}
        async with aiosqlite.connect(self.bot.db_path) as db:
            async with db.execute("select playerId, sum(atBats) from DailyStatSheets "
                                  f"where season={int(season)};") as cursor:
                async for row in cursor:
                    at_bat_counts[row[0]] = row[1]

        games = await utils.retry_request(f"https://www.blaseball.com/database/games?day={day}&season={season}")
        games_json = games.json()
        pitcher_ids = []
        pitcher_ids += [game["homePitcher"] for game in games_json]
        pitcher_ids += [game["awayPitcher"] for game in games_json]
        pitcher_dict = {}
        for k in pitcher_ids:
            pitcher_dict[k] = {"shutout": 0, "strikeouts": 0, "outsRecorded": 0,
                               "name": "", "team": "", "opponent": "", "odds": 0}
        results = {}
        for game in games_json:
            if game["homePitcher"] not in pitcher_dict:
                pitcher_dict[game["homePitcher"]] = {"shutout": 0, "strikeouts": 0, "outsRecorded": 0,
                                                     "name": game["homePitcherName"], "team": game["homeTeamNickname"],
                                                     "opponent": game["awayTeamNickname"], "odds": game["homeOdds"]}
            pitcher_dict[game["homePitcher"]]["team"] = game["homeTeam"]
            pitcher_dict[game["homePitcher"]]["name"] = game["homePitcherName"]
            pitcher_dict[game["homePitcher"]]["opponent"] = game["awayTeam"]
            pitcher_dict[game["homePitcher"]]["odds"] = game["homeOdds"]
            struckouts = team_stats[game["awayTeam"]]["struckouts"]
            at_bats = team_stats[game["awayTeam"]]["at_bats"]
            pitcher_dict[game["homePitcher"]]["opponentSOAvg"] = round((struckouts / at_bats) * 1000) / 1000
            pitcher_dict[game["homePitcher"]]["opp_shutouts"] = team_stats[game["awayTeam"]]["shutout"]
            pitcher_dict[game["homePitcher"]]["shutout_weight"] = pitcher_dict[game["homePitcher"]]["shutout"] \
                                                                  * team_stats[game["awayTeam"]]["shutout"]
            hp_stlats = pitcher_stlats[game["homePitcher"]]
            opp_stlats = team_stlats[game["awayTeam"]]
            strikeout_odds = await self.strikeout_odds(hp_stlats, opp_stlats, clf,
                                                       team_stats[game["awayTeam"]], day, at_bat_counts)
            results[strikeout_odds] = game["homePitcherName"]
            pitcher_dict[game["homePitcher"]]["k_prediction"] = strikeout_odds

            if game["awayPitcher"] not in pitcher_dict:
                pitcher_dict[game["awayPitcher"]] = {"shutout": 0, "strikeouts": 0, "outsRecorded": 0,
                                                     "name": game["awayPitcherName"], "team": game["awayTeamNickname"],
                                                     "opponent": game["homeTeamNickname"], "odds": game["awayOdds"]}
            pitcher_dict[game["awayPitcher"]]["team"] = game["awayTeam"]
            pitcher_dict[game["awayPitcher"]]["name"] = game["awayPitcherName"]
            pitcher_dict[game["awayPitcher"]]["opponent"] = game["homeTeam"]
            pitcher_dict[game["awayPitcher"]]["odds"] = game["awayOdds"]
            struckouts = team_stats[game["homeTeam"]]["struckouts"]
            at_bats = team_stats[game["homeTeam"]]["at_bats"]
            pitcher_dict[game["awayPitcher"]]["opponentSOAvg"] = round((struckouts / at_bats) * 1000) / 1000
            pitcher_dict[game["awayPitcher"]]["opp_shutouts"] = team_stats[game["homeTeam"]]["shutout"]
            pitcher_dict[game["awayPitcher"]]["shutout_weight"] = pitcher_dict[game["awayPitcher"]]["shutout"] \
                                                                  * team_stats[game["homeTeam"]]["shutout"]
            hp_stlats = pitcher_stlats[game["awayPitcher"]]
            opp_stlats = team_stlats[game["homeTeam"]]
            strikeout_odds = await self.strikeout_odds(hp_stlats, opp_stlats, clf,
                                                       team_stats[game["homeTeam"]], day, at_bat_counts)
            results[strikeout_odds] = game["awayPitcherName"]
            pitcher_dict[game["awayPitcher"]]["k_prediction"] = strikeout_odds

        sorted_results = {k: v for k, v in
                          sorted(results.items(), key=lambda item: item[0], reverse=True)}
        return {
            "sorted_results": sorted_results,
            "pitcher_dict": pitcher_dict,
            "season": season,
            "day": day,
            "pitcher_ids": pitcher_ids
        }

    @staticmethod
    async def send_to_webhook(message, embed_fields, url):
        data = {"content": message, "avatar_url": "https://i.imgur.com/q9OOb63.png",
                "embeds": [{"fields": embed_fields}]
                }
        result = requests.post(url, data=json.dumps(data), headers={"Content-Type": "application/json"})

        try:
            result.raise_for_status()
        except requests.exceptions.HTTPError as err:
            print(err)
        else:
            print("Payload delivered successfully, code {}.".format(result.status_code))

    async def calculate_SO_Avg(self, all_players, pitcher):
        struckouts = 0
        at_bats = 0
        for player in all_players:
            if all_players[player]["teamId"] == pitcher["opponent"]:
                if all_players[player]["rotation"] == -1:
                    struckouts += all_players[player]["struckouts"]
                    at_bats += all_players[player]["atBats"]
        pitcher["opponentSOAvg"] = round((struckouts / at_bats) * 1000) / 1000

    @commands.command(name='set_bet_channel', aliases=['sbc'])
    async def _set_bet_channel(self, ctx, item):
        output_channel = await utils.get_channel_by_name_or_id(ctx, item)
        if output_channel is None:
            return await ctx.message.add_reaction(self.bot.failed_react)
        self.bot.config['bet_channel'] = output_channel.id
        return await ctx.message.add_reaction(self.bot.success_react)

    @commands.command(aliases=['tdm'])
    async def _testdm(self, ctx, season, day):
        bet_chan_id = self.bot.config['bet_channel']
        message, embed_fields, output = await self.daily_message(season, day)
        m_embed = discord.Embed(description=message)

        for field in embed_fields:
            m_embed.add_field(name=field["name"], value=field["value"])
        if bet_chan_id:
            output_channel = self.bot.get_channel(bet_chan_id)
            bet_msg = await output_channel.send(embed=m_embed)
            d_output_chan = self.bot.get_channel(self.bot.config['gamesim_debug_channel'])
            await d_output_chan.send(output)
            if self.bot.config['live_version']:
                await bet_msg.publish()

    @commands.command()
    async def fill_daily_table(self, ctx, season: int, start: int, end: int):
        for day in range(start, end+1):
            await self.update_day_winners(season, day)

    @commands.command(name="game_results_to_csv", aliases=['csv'])
    async def _game_results_to_csv(self, ctx, season: int):
        gameresult_rows = []
        async with aiosqlite.connect(self.bot.db_path) as db:
            async with db.execute("select day, gameid, hometeamid, hometeamodds, hometeamwin, hometeamwinpercentage, "
                                  "awayteamid, awayteamodds, awayteamwin, awayteamwinpercentage, upset, weather "
                                  "from dailygameresultstable where season=? order by day;", [season]) as cursor:
                async for row in cursor:
                    gameresult_rows.append(row)
        fieldnames = ["day", "game_id", "home_team_id", "home_team_odds", "home_team_win",
                      "home_team_sim_win_percentage", "away_team_id", "away_team_odds", "away_team_win",
                      "away_team_sim_win_percentage", "sim_upset", "weather"]
        filename = f"s{season}_simsim_gameresults.csv"
        with open(os.path.join('data', 'season_sim', 'csv', filename), 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, delimiter=',', fieldnames=fieldnames)
            writer.writeheader()
            for row in gameresult_rows:
                rowdict = dict(zip(fieldnames, row))
                writer.writerow(rowdict)
        with open(os.path.join('data', 'season_sim', 'csv', filename), 'rb') as csvfile:
            await ctx.send(file=discord.File(csvfile, filename=filename))

    async def check_game_sim_loop(self):
        while not self.bot.is_closed():
            self.bot.logger.info("Checking for game sim run")
            html_response = await utils.retry_request("https://www.blaseball.com/database/simulationdata")
            sim_data = html_response.json()
            season = sim_data['season']
            day = sim_data['day'] + 1
            filename = f"s{season}_d{day}_sim_results.json"
            filepath = os.path.join('data', 'season_sim', 'results', filename)
            done = False
            if os.path.exists(filepath):
                with open(filepath, 'r') as file:
                    maybe_data = json.load(file)
                if len(maybe_data) > 0:
                    if 'data' in maybe_data:
                        if len(maybe_data['data']) > 0:
                            done = True
            if not done:
                self.bot.logger.info("No game sim run found, starting now")
                time_elapsed = await asyncio.wait_for(self.run_daily_sim(season, 501), 1200)
                self.bot.logger.info(f"s{season}_d{day} sim results saved to file in {time_elapsed} seconds")
                await asyncio.sleep(60 * 40)
            else:
                await asyncio.sleep(60 * 4)

    @commands.command(name="pitcher_names", aliases=['pn', 'pnames', 'pitchernames'])
    async def _pitcher_names(self, ctx, day):
        with open(os.path.join('data', 'season_sim', 'results', f"s{14}_d{day}_sim_results.json"), 'r') as file:
            result = json.load(file)
        msg = ""
        for game in result["data"].values():
            home_team, away_team = game["home_team"], game["away_team"]
            home_pitcher = away_team["opp_pitcher"]["pitcher_name"]
            away_pitcher = home_team["opp_pitcher"]["pitcher_name"]
            home_name = home_team["team_name"]
            away_name = away_team["team_name"]
            msg += f"{home_name}: {home_pitcher} - {away_name}: {away_pitcher}\n"
        await ctx.send(msg)


def setup(bot):
    bot.add_cog(BetAdvice(bot))
