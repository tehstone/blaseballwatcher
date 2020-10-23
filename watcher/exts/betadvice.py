import json
import os
from joblib import load

import discord
import requests
from discord.ext import commands

from watcher import utils


class BetAdvice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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

    async def strikeout_odds(self, hp_stlats, opp_stlats, clf, team_stats, day, cumulative_stats):
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
            if pid in cumulative_stats["hitters"]:
                plate_appearances = cumulative_stats["hitters"][pid]["plateAppearances"]
            else:
                plate_appearances = team_stats["plate_appearances"] / lineup_size
            #print(plate_appearances / day)
            odds *= plate_appearances / day
            odds_sum += odds
        return odds_sum


    async def daily_message(self):
        html_response = await utils.retry_request("https://www.blaseball.com/database/simulationdata")
        if not html_response:
            self.bot.logger.warn('Bet Advice daily message failed to acquire sim data and exited.')
            return
        sim_data = html_response.json()
        season = sim_data['season']
        day = sim_data['day'] + 1
        #day = 97
        clf = load(os.path.join("data", "pendant_data", "so.joblib"))

        with open(os.path.join('data', 'pendant_data', 'all_players.json'), 'r') as file:
            all_players = json.load(file)
        with open(os.path.join('data', 'pendant_data', 'statsheets', 'team_stats.json'), 'r') as file:
            team_stats = json.load(file)
        with open(os.path.join('data', 'pendant_data', 'statsheets', f's{season}_current_player_stats.json'), 'r') as file:
            cumulative_stats = json.load(file)
        pitcher_stlats, team_stlats = await self.get_player_stlats()
        filename = os.path.join('data', 'pendant_data', 'stlats', f's{season}_d{day}_pitcher_stlats.json')
        with open(filename, 'w') as file:
            json.dump(pitcher_stlats, file)
        filename = os.path.join('data', 'pendant_data', 'stlats', f's{season}_d{day}_team_stlats.json')
        with open(filename, 'w') as file:
            json.dump(team_stlats, file)

        games = await utils.retry_request(f"https://www.blaseball.com/database/games?day={day}&season={season}")
        games_json = games.json()
        pitcher_ids = []
        pitcher_ids += [game["homePitcher"] for game in games_json]
        pitcher_ids += [game["awayPitcher"] for game in games_json]
        pitcher_dict = {k: v for k, v in all_players.items() if k in pitcher_ids}
        results = {}

        for game in games_json:
            if game["homePitcher"] not in pitcher_dict:
                pitcher_dict[game["homePitcher"]] = {"shutout": 0, "strikeouts": 0, "outsRecorded": 0,
                                                     "name": game["homePitcherName"], "team": game["homeTeamNickname"],
                                                     "opponent": game["awayTeamNickname"], "odds": game["homeOdds"]}
            pitcher_dict[game["homePitcher"]]["team"] = game["homeTeam"]
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
                                                       team_stats[game["awayTeam"]], day, cumulative_stats)
            results[strikeout_odds] = game["homePitcherName"]
            pitcher_dict[game["homePitcher"]]["k_prediction"] = strikeout_odds

            if game["awayPitcher"] not in pitcher_dict:
                pitcher_dict[game["awayPitcher"]] = {"shutout": 0, "strikeouts": 0, "outsRecorded": 0,
                                                     "name": game["awayPitcherName"], "team": game["awayTeamNickname"],
                                                     "opponent": game["homeTeamNickname"], "odds": game["awayOdds"]}
            pitcher_dict[game["awayPitcher"]]["team"] = game["awayTeam"]
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
                                                       team_stats[game["homeTeam"]], day, cumulative_stats)
            results[strikeout_odds] = game["awayPitcherName"]
            pitcher_dict[game["awayPitcher"]]["k_prediction"] = strikeout_odds

        sorted_results = {k: v for k, v in
                       sorted(results.items(), key=lambda item: item[0], reverse=True)}
        output_text = ""
        output_text_2 = ""
        for key, value in sorted_results.items():
            rounded_odds = round(key*10)/10
            output_text += f"{value}: {key}\n"
            output_text_2 += f"{value}: {rounded_odds}\n"
        output_text += f"\n{output_text_2}"
        with open(os.path.join('data', 'pendant_data', 'results', f"s{season}_d{day}_so_model_results.txt"), 'a') as fd:
            fd.write((output_text))

        for k in pitcher_dict.keys():
            if pitcher_dict[k]['outsRecorded'] > 0:
                pitcher_dict[k]['so_nine'] = round((pitcher_dict[k]['strikeouts'] /
                                                    (pitcher_dict[k]['outsRecorded'] / 27)) * 10) / 10
            else:
                pitcher_dict[k]['so_nine'] = 0

        players = await utils.retry_request(f"https://www.blaseball.com/database/players?ids={','.join(pitcher_ids)}")
        players = players.json()
        for player in players:
            pitcher_dict[player['id']]['ruth'] = player["ruthlessness"]

        sorted_ml_model = {k: v for k, v in sorted(pitcher_dict.items(),
                                                   key=lambda item: item[1]['k_prediction'],
                                                   reverse=True) if k in pitcher_ids}

        game_sim_cog = self.bot.cogs.get('GameSim')
        results = await game_sim_cog.setup(1000)

        message = f"Pitching Idol recommendations for **day {day+1}**\n" \
                  f"Ranked by Machine Learning model simulating pitchers vs " \
                  f"the full opposing lineup courtesy of kjc9#9000\n"
        embed_fields = []
        top_list = list(sorted_ml_model.keys())[:5]
        count = 1
        # add projected strikeouts * 200 + expected shutout * 10000
        for key in top_list:
            values = pitcher_dict[key]
            name = values["name"]
            team = self.bot.team_names[values["team"]]
            pred = values["k_prediction"]
            pred = round(pred * 10) / 10
            opponent = self.bot.team_names[values["opponent"]]
            opp_sho_per = results[values["opponent"]]["shutout_percentage"]
            opp_k_per = results[values["opponent"]]["strikeout_percentage"]
            predicted_payout_ko = round(opp_k_per * 200)
            predicted_payout = round((opp_k_per * 200) + ((opp_sho_per/100) * 10000))
            k_9_value = values['so_nine']
            br_link = f"[blaseball-ref]({'https://blaseball-reference.com/players/'+key})"
            br_link += f" | [idol]({'https://www.blaseball.com/player/'+key})"
            shutout = "\n"
            if values["shutout"] > 0:
                if values["shutout"] > 1:
                    shutout = f" ({values['shutout']} shutouts)\n"
                else:
                    shutout = f" ({values['shutout']} shutout)\n"
            k_message = f'{br_link}\nKs: **{values["strikeouts"]}** K/9: **{k_9_value}**{shutout}' \
                        f'{team} vs **{opponent}** K/AB: **{values["opponentSOAvg"]}** '
            k_message += f"\nPredicted payout: {predicted_payout}. \nKs only: {predicted_payout_ko}"

            embed_fields.append({"name": f"**{count}. {name}** - {pred}",
                                 "value": k_message})
            count += 1

        top_five_shos = list(results.keys())[:5]
        sh_message = ""
        for key in top_five_shos:
            team_name = self.bot.team_names[key]
            sh_message += f"{team_name}: {results[key]['shutout_percentage']}%\n"
        embed_fields.append({"name": "Teams most likely to be shutout",
                             "value": sh_message})

        debug_chan_id = self.bot.config.setdefault('debug_channel', None)
        if debug_chan_id:
            debug_channel = self.bot.get_channel(debug_chan_id)
            if debug_channel:
                sorted_big_scores = {k: v for k, v in sorted(results.items(),
                                                             key=lambda item: item[1]['over_ten'],
                                                             reverse=True)}
                big_message = ""
                for key in list(sorted_big_scores.keys()):
                    if sorted_big_scores[key]['over_ten'] > .04:
                        team_name = self.bot.team_names[key]
                        over_ten = round(sorted_big_scores[key]['over_ten'] * 1000) / 10
                        big_message += f"{team_name}: {over_ten}% chance\n"
                    else:
                        break
                if len(big_message) > 0:
                    big_message = f"Day {day}:\nTeams Likely to score 10+\n{big_message}"

                sorted_xbig_scores = {k: v for k, v in sorted(results.items(),
                                                              key=lambda item: item[1]['over_twenty'],
                                                              reverse=True)}
                x_big_message = ""
                for key in list(sorted_xbig_scores.keys()):
                    if sorted_big_scores[key]['over_twenty'] > .01:
                        team_name = self.bot.team_names[key]
                        over_twenty = round(sorted_big_scores[key]['over_twenty'] * 1000) / 10
                        x_big_message += f"{team_name}: {over_twenty}% chance\n"
                    else:
                        break
                if len(x_big_message) > 0:
                    x_big_message = f"\nTeams Likely to score 20+\n{x_big_message}"
                    big_message += x_big_message

                if len(big_message) > 0:
                    daily_stats_channel_id = self.bot.config.setdefault('daily_stats_channel', None)
                    if daily_stats_channel_id:
                        daily_stats_channel = self.bot.get_channel(daily_stats_channel_id)
                        if daily_stats_channel:
                            await daily_stats_channel.send(big_message)

        return message, embed_fields

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
            bet_msg = await output_channel.send(message, embed=m_embed)
            if self.bot.config['live_version']:
                await bet_msg.publish()


def setup(bot):
    bot.add_cog(BetAdvice(bot))
