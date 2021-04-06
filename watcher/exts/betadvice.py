import json
import os

import aiosqlite
from joblib import load

import discord
import requests
from discord.ext import commands

from watcher import utils
from watcher.exts import gamedata
from watcher.game_sim import daily_sim


class BetAdvice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.team_short_map = None

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

    async def daily_message(self):
        #sim_results = await self._run_daily_sim()
        # sorted_results = sim_results["sorted_results"]
        # season, day = sim_results["season"], sim_results["day"]
        # pitcher_dict = sim_results["pitcher_dict"]
        # pitcher_ids = sim_results["pitcher_ids"]
        # output_text = ""
        # output_text_2 = ""
        # for key, value in sorted_results.items():
        #     rounded_odds = round(key*10)/10
        #     output_text += f"{value}: {key}\n"
        #     output_text_2 += f"{value}: {rounded_odds}\n"
        # output_text += f"\n{output_text_2}"
        # with open(os.path.join('data', 'pendant_data', 'results', f"s{season}_d{day}_so_model_results.txt"), 'a') as fd:
        #     fd.write((output_text))
        #
        # for k in pitcher_dict.keys():
        #     if pitcher_dict[k]['outsRecorded'] > 0:
        #         pitcher_dict[k]['so_nine'] = round((pitcher_dict[k]['strikeouts'] /
        #                                             (pitcher_dict[k]['outsRecorded'] / 27)) * 10) / 10
        #     else:
        #         pitcher_dict[k]['so_nine'] = 0
        #
        # players = await utils.retry_request(f"https://www.blaseball.com/database/players?ids={','.join(pitcher_ids)}")
        # players = players.json()
        # for player in players:
        #     pitcher_dict[player['id']]['ruth'] = player["ruthlessness"]

        results, day = await daily_sim.run_daily_sim(250)
        with open(os.path.join('data', 'season_sim', 'results', f'd{day}_results.json'), 'w') as file:
            json.dump(results, file)

        message = f"Daily Outlook for **day {day+1}**\n" \
                  "Predictions are generated by a Machine Learning model simulating all games courtesy of kjc9#9000"

        embed_fields = []

        team_short_map = await self.get_short_map()
        daily_leaders = None
        f_day = day+1
        while daily_leaders == None:
            try:
                with open(os.path.join('data', 'pendant_data', 'statsheets', f'd{f_day}_leaders.json'), 'r') as file:
                    daily_leaders = json.load(file)
            except FileNotFoundError:
                f_day -= 1

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
        for team in results.keys():
            pitcher_opp_strikeouts[results[team]["opp_pitcher"]["pitcher_id"]] = {
                "strikeout_avg": results[team]["strikeout_avg"],
                "name": results[team]["opp_pitcher"]["pitcher_name"],
                "team": results[team]["opp_pitcher"]["p_team_id"]
            }

        sorted_so_preds = {k: v for k, v in sorted(pitcher_opp_strikeouts.items(),
                                                   key=lambda item: item[1]["strikeout_avg"],
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

        top_five_shos = list(results.keys())[:3]
        sh_message = ""
        for key in top_five_shos:
            team_name = self.bot.team_names[key]
            sh_message += f"{team_name}: {results[key]['shutout_percentage']}%\n"
        embed_fields.append({"name": "Teams most likely to be shutout",
                             "value": sh_message})

        sorted_big_scores = {k: v for k, v in sorted(results.items(),
                                                     key=lambda item: item[1]['over_ten'],
                                                     reverse=True)}
        big_message = ""
        for key in list(sorted_big_scores.keys()):
            if sorted_big_scores[key]['over_ten'] > .03:
                weather = results[key]["weather"]
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

        upset_games = {}
        black_hole_games, flood_games, sun_two_games, eclipse_games = 0, 0, 0, 0
        for team, game in results.items():
            if game["upset"] == True:
                if game["game_info"]["id"] not in upset_games:
                    upset_games[game["game_info"]["id"]] = {
                        "game_info": game["game_info"],
                        "win_percentages": {}
                    }
                upset_games[game["game_info"]["id"]]["win_percentages"][team] = game["win_percentage"]
            if game["weather"] == 14:
                black_hole_games += 1
            if game["weather"] == 18:
                flood_games += 1
            if game["weather"] == 1:
                sun_two_games += 1
            if game["weather"] == 7:
                eclipse_games += 1
        black_hole_games = int(black_hole_games/2)
        flood_games = int(flood_games/2)
        sun_two_games = int(sun_two_games / 2)
        eclipse_games = int(eclipse_games / 2)

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

        upset_msg = ""
        for item in upset_games.values():
            if item["game_info"]["homeOdds"] > item["game_info"]["awayOdds"]:
                win_per = item["win_percentages"][item["game_info"]["awayTeam"]]
                team_name = item["game_info"]["awayTeamName"]
                odds = round(item['game_info']['awayOdds'] * 1000) / 10
                upset_msg += f"{team_name} ({odds}% odds) - {win_per}% sim wins\n"
            else:
                win_per = item["win_percentages"][item["game_info"]["homeTeam"]]
                team_name = item["game_info"]["homeTeamName"]
                odds = round(item['game_info']['homeOdds'] * 1000) / 10
                upset_msg += f"{team_name} ({odds}% odds) - {win_per}% sim wins\n"

        #if len(upset_msg) > 0:
            #embed_fields.append({"name": "Upset Watch",
                           #      "value": upset_msg})

        return message, embed_fields

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
    async def _testdm(self, ctx):
        bet_chan_id = self.bot.config['bet_channel']

        message, embed_fields = await self.daily_message()
        m_embed = discord.Embed(description=message)
        for field in embed_fields:
            m_embed.add_field(name=field["name"], value=field["value"])
        if bet_chan_id:
            output_channel = self.bot.get_channel(bet_chan_id)
            bet_msg = await output_channel.send(embed=m_embed)
            if self.bot.config['live_version']:
                await bet_msg.publish()


def setup(bot):
    bot.add_cog(BetAdvice(bot))
