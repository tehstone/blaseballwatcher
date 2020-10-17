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

    async def strikeout_odds(self, hp_stlats, opp_stlats, clf, team_stats, day):
        stlats_arr = []
        unthwack = float(hp_stlats["unthwackability"])
        ruth = float(hp_stlats["ruthlessness"])
        overp = float(hp_stlats["overpowerment"])
        cold = float(hp_stlats["coldness"])
        for __, opponent in opp_stlats["lineup"].items():
            s_arr = []
            for stlat in ["tragicness", "patheticism", "thwackability", "divinity",
                          "moxie", "musclitude", "laserlikeness", "continuation",
                          "baseThirst", "indulgence", "groundFriction"]:
                s_arr.append(float(opponent[stlat]))
            s_arr += [unthwack, ruth, overp, cold]
            stlats_arr.append(s_arr)
        odds_list = clf.predict_proba(stlats_arr)
        odds_sum = 0
        for odds in odds_list:
            odds_sum += odds[1]
        return odds_sum * ((team_stats["at_bats"] * 1.05) / day)

    async def daily_message(self):
        html_response = await utils.retry_request("https://www.blaseball.com/database/simulationdata")
        if not html_response:
            self.bot.logger.warn('Bet Advice daily message failed to acquire sim data and exited.')
            return
        sim_data = html_response.json()
        season = sim_data['season']
        day = sim_data['day'] + 1
        clf = load(os.path.join("data", "pendant_data", "so.joblib"))

        with open(os.path.join('data', 'pendant_data', 'all_players.json'), 'r') as file:
            all_players = json.load(file)
        with open(os.path.join('data', 'pendant_data', 'statsheets', 'team_stats.json'), 'r') as file:
            team_stats = json.load(file)
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
        for k in pitcher_dict.keys():
            pitcher_dict[k]['so_nine'] = round((pitcher_dict[k]['strikeouts'] /
                                                (pitcher_dict[k]['outsRecorded'] / 27)) * 10) / 10

        for game in games_json:
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
            strikeout_odds = await self.strikeout_odds(hp_stlats, opp_stlats, clf, team_stats[game["awayTeam"]], day)
            pitcher_dict[game["homePitcher"]]["k_prediction"] = strikeout_odds

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
            strikeout_odds = await self.strikeout_odds(hp_stlats, opp_stlats, clf, team_stats[game["homeTeam"]], day)
            pitcher_dict[game["awayPitcher"]]["k_prediction"] = strikeout_odds

        players = await utils.retry_request(f"https://www.blaseball.com/database/players?ids={','.join(pitcher_ids)}")
        players = players.json()
        for player in players:
            pitcher_dict[player['id']]['ruth'] = player["ruthlessness"]

        sorted_strikeouts = {k: v
                             for k, v in sorted(pitcher_dict.items(),
                                                key=lambda item: item[1]['so_nine'],
                                                reverse=True) if k in pitcher_ids}
        sorted_ruth = {k: v for k, v in sorted(pitcher_dict.items(),
                                               key=lambda item: item[1]['ruth'],
                                               reverse=True) if k in pitcher_ids}
        sorted_sho = {k: v for k, v in sorted(pitcher_dict.items(),
                                              key=lambda item: item[1]['shutout_weight'],
                                              reverse=True) if k in pitcher_ids}
        sorted_ml_model = {k: v for k, v in sorted(pitcher_dict.items(),
                                                   key=lambda item: item[1]['k_prediction'],
                                                   reverse=True) if k in pitcher_ids}

        message = f"Pitching Idol recommendations for **day {day+1}**\n"
        embed_fields = []
        top_list = list(sorted_strikeouts.keys())[:2]
        for key in top_list:
            values = pitcher_dict[key]
            name = values["name"]
            team = self.bot.team_names[values["team"]]
            opponent = self.bot.team_names[values["opponent"]]
            k_9_value = round((values['strikeouts'] / (values['outsRecorded'] / 27)) * 10) / 10
            odds = round((values["odds"] * 1000)) / 10
            br_link = f"[blaseball-ref]({'https://blaseball-reference.com/players/'+key})"
            br_link += f" | [idol]({'https://www.blaseball.com/player/'+key})"
            shutout = "\n"
            if values["shutout"] > 0:
                if values["shutout"] > 1:
                    shutout = f" ({values['shutout']} shutouts)\n"
                else:
                    shutout = f" ({values['shutout']} shutout)\n"
            k_message = f'{br_link}\nSO: **{values["strikeouts"]}** SO/9: **{k_9_value}**{shutout}' \
                        f'{team} vs **{opponent}** SO/AB: **{values["opponentSOAvg"]}** ' \
                        f'Game odds: **{odds}%**'
            if values["opp_shutouts"] >= 1:
                k_message += f'\n{opponent} shutout {values["opp_shutouts"]} times'
            embed_fields.append({"name": f"**{name}**",
                                 "value": k_message})
        top_list = list(sorted_ml_model.keys())[:2]
        ep_msg = ""
        for i in range(2):
            values = pitcher_dict[top_list[i]]
            opponent = self.bot.team_names[values['opponent']]
            ep_msg += f"{values['name']} vs. {opponent}\n"
        embed_fields.append({"name": "Experimental picks",
                             "value": ep_msg})
        top_list = list(sorted_sho.keys())[:1]
        values = pitcher_dict[top_list[0]]
        opponent = self.bot.team_names[values['opponent']]
        sho_message = f"{values['name']} vs. {opponent}"
        if opponent != "Fridays" and day < 99:
            sho_message += "\n(or whoever's pitching against the Fridays)"
        embed_fields.append({"name": "Most likely shutout",
                             "value": sho_message})
        top_list = list(sorted_ruth.keys())[:3]
        r_message = "||"
        for key in top_list:
            values = pitcher_dict[key]
            r_message += f"{values['name']}: {values['ruth']}\n"
        r_message += "||"
        embed_fields.append({"name": "||Top by Ruthlessness||",
                             "value": r_message})

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



def setup(bot):
    bot.add_cog(BetAdvice(bot))
