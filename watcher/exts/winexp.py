import glob
import json
import os
import statistics

import discord
import matplotlib.pyplot as plt
from discord.ext import commands
from watcher import utils

team_colors = {
    'Lovers': {'primary': '#780018', 'secondary': '#212121'},
    'Crabs': {'primary': '#593037', 'secondary': '#c48b41'},
    'Millennials': {'primary': '#ffd4d8', 'secondary': '#543d04'},
    'Firefighters': {'primary': '#8c2a3e', 'secondary': '#d6cbb0'},
    'Jazz Hands': {'primary': '#6388ad', 'secondary': '#9182C4'},
    'Spies': {'primary': '#67556b', 'secondary': '#d1bece'},
    'Flowers': {'primary': '#f7d1ff', 'secondary': '#ffbaba'},
    'Dale': {'primary': '#9141ba', 'secondary': '#bfe9ff'},
    'Dalé': {'primary': '#9141ba', 'secondary': '#bfe9ff'},
    'Sunbeams': {'primary': '#fffbab', 'secondary': '#fffaab'},
    'Tacos': {'primary': '#64376e', 'secondary': '#dbd26e'},
    'Tigers': {'primary': '#5c1c1c', 'secondary': '#919191'},
    'Moist Talkers': {'primary': '#f5feff', 'secondary': '#757575'},
    'Garages': {'primary': '#2b4075', 'secondary': '#543d04'},
    'Steaks': {'primary': '#8c8d8f', 'secondary': '#ededed'},
    'Breath Mints': {'primary': '#178f55', 'secondary': '#e6ffec'},
    'Mild Wings': {'primary': '#d15700', 'secondary': '#e8e8e8'},
    'Wild Wings': {'primary': '#d15700', 'secondary': '#e8e8e8'},
    'Fridays': {'primary': '#3ee652', 'secondary': '#e67575'},
    'Pies': {'primary': '#399d8f', 'secondary': '#ffffff'},
    'Shoe Thieves': {'primary': '#ffce0a', 'secondary': '#E2DBAC'},
    'Magic': {'primary': '#bf0043', 'secondary': '#16756f'}
}

class WinExp(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.odds_chart = {}
        with open(os.path.join('data', 'odds_chart.csv')) as file:
            lines = file.readlines()
            for line in lines:
                line_values = line.split('\t')
                self.odds_chart[int(line_values[0])] = [float(s) for s in line_values[1:]]

    async def get_game_logs(self, season, day, team):
        url = f"https://blaseball.com/database/games?day={day-1}&season={season-1}"
        html_response = await utils.retry_request(self.bot.session, url)
        if not html_response:
            return
        day_data = await html_response.json()
        for game in day_data:
            found = False
            if team.lower() == "dalé" or team.lower() == "dale":
                if game["homeTeamNickname"].lower() in ["dale", "dalé"] \
                        or game["awayTeamNickname"].lower() in ["dale", "dalé"]:
                    found = True
            elif team.lower() in ["mild wings", "wild wings", "wings"]:
                if game["homeTeamNickname"].lower() in ["mild wings", "wild wings"] \
                        or game["awayTeamNickname"].lower() in ["mild wings", "wild wings"]:
                    found = True
            elif team.lower() == game["homeTeamNickname"].lower() or team.lower() == game["awayTeamNickname"].lower():
                found = True
            if found:
                away_team = game["awayTeamNickname"]
                home_team = game["homeTeamNickname"]
                game_id = game["id"]
                break
        try:
            filename = f"s{season}d{day}_{away_team}vs{home_team}.png"
            if os.path.exists(os.path.join('data', 'winexpectancy', 'images', filename)):
                return "image", filename, home_team, away_team
        except FileNotFoundError:
            pass
        filename = f"s{season}d{day}_{away_team}vs{home_team}.log"
        try:
            if os.path.exists(os.path.join('data', 'winexpectancy', 'logs', filename)):
                return "log", filename, home_team, away_team
        except:
            pass
        url = f"https://api.blaseball-reference.com/v1/events?gameId={game_id}&baseRunners=true"
        html_response = await utils.retry_request(self.bot.session, url)
        if not html_response:
            return
        game_data = await html_response.json()
        with open(os.path.join('data', 'winexpectancy', 'logs', filename), 'w') as file:
            json.dump(game_data["results"], file)
        return "log", filename, home_team, away_team

    def calculate_odds(self, game, last_odds, last_inning):
        inning = min((game["inning"] + 1), 9) * 10 + 1
        new_inning = game["inning"] != last_inning
        if not game["top_of_inning"]:
            inning += 1
        bases = 1
        bases_occupied = []
        for b in game["base_runners"]:
            new_bases = b["base_after_play"]
            if new_bases < 4:
                bases += new_bases
                bases_occupied.append(new_bases)
        bases *= 10
        if game["outs_before_play"] + game["outs_on_play"] == 3:
            # last, message, inc_odds, last_inning, new_inning
            return last_odds, None, None, game["inning"], new_inning
        bases += game["outs_before_play"] + game["outs_on_play"]
        inn_base_out = inning * 100 + bases
        run_diff = game["home_score"] - game["away_score"]
        if run_diff < -15:
            home_odds = 0.000003978333494
        elif run_diff > 15:
            home_odds = 0.999996021666506
        else:
            score_odds = self.odds_chart[inn_base_out]
            try:
                home_odds = score_odds[run_diff - (-15)]
            except IndexError:
                home_odds = last_odds
        new_message, inc_odds = None, None
        if home_odds != last_odds:
            inc_odds = home_odds
        return home_odds, new_message, inc_odds, game["inning"], new_inning

    @commands.command(name="game_win_expectancy", aliases=["chart", "gwe"])
    async def _game_win_expectancy(self, ctx, season: int, day: int, *, team: str):
        filetype, filename, home_team, away_team = await self.get_game_logs(season, day, team)
        if filetype == "image":
            with open(os.path.join('data', 'winexpectancy', 'images', filename), 'rb') as file:
                return await ctx.send(file=discord.File(file, filename=filename))
        elif filetype == "log":
            with open(os.path.join('data', 'winexpectancy', 'logs', filename), 'r') as file:
                last_inning = 0
                game_events = json.load(file)
                game_info = {"last": .5, "messages": [], "inc_odds": [],
                             "season": season, "day": day, "inning_breaks": []}
                for event in game_events:
                    last, message, inc_odds, last_inning, new_inning = self.calculate_odds(event, game_info["last"],
                                                                                           last_inning)
                    game_info["last"] = last
                    if message:
                        game_info["messages"].append(message)
                    if inc_odds:
                        game_info["inc_odds"].append(inc_odds)
                    if new_inning:
                        game_info["inning_breaks"].append(len(game_info["inc_odds"]) - 1)

                team_odds = game_info["inc_odds"]
                opp_odds = [1 - i for i in team_odds]
                m_team_odds = [(i - .5) * 2 for i in team_odds]
                m_opp_odds = [(i - .5) * 2 for i in opp_odds]

                plt.figure()
                plt.suptitle(f"Win Expectancy - Season {season} Day {day} - {away_team} @ {home_team}")
                home_color = team_colors[home_team]['primary']
                away_color = team_colors[away_team]['primary']
                if home_team == "Moist Talkers":
                    home_color = team_colors[home_team]['secondary']
                if away_team == "Moist Talkers":
                    away_color = team_colors[away_team]['secondary']

                plt.step(m_team_odds, home_color, label=f"{home_team}")
                plt.step(m_opp_odds, away_color, label=f"{away_team}")

                for inning in game_info["inning_breaks"]:
                    plt.axvline(x=inning, linewidth=1.0, dashes=[2, 2])
                plt.legend(loc='best',
                           ncol=1, borderaxespad=0.)

                filename = f"s{season}d{day}_{away_team}vs{home_team}.png"
                plt.savefig(os.path.join('data', 'winexpectancy', 'images', filename),
                            transparent=False, dpi=80, bbox_inches="tight")
                with open(os.path.join('data', 'winexpectancy', 'images', filename), 'rb') as file:
                    return await ctx.send(file=discord.File(file, filename=filename))

    @commands.command(name="winexp", aliases=['win'])
    async def _winexp(self, ctx):
        with open(os.path.join('data', 'winexpectancy', 'allgames.json'), 'r') as file:
            all_game_data = json.load(file)
        odds = {}
        players = {}

        for season in range(2, 8):
            print(season)
            odds[season] = {}
            for day in range(114):
                odds[season][day] = []
                for filename in glob.glob(os.path.join('data', 'winexpectancy', 'logs', f'{season}_{day}_*')):
                    with open(filename, 'r') as file:
                        game_events = json.load(file)
                    last_inning = 0
                    batter_id = game_events[0]["batter_id"]
                    for game in all_game_data[str(season)][str(day)]:
                        if game["id"] == game_events[0]["game_id"]:
                            game_json = game
                    game_info = {"last": .5, "messages": [], "inc_odds": [], "odds_delta": [],
                                 "season": season, "day": day, "inning_breaks": [],
                                 "home_team": game_json["homeTeam"],
                                 "away_team": game_json["awayTeam"]}
                    home_team = game_json["homeTeamNickname"]
                    away_team = game_json["awayTeamNickname"]
                    for event in game_events:
                        last, message, inc_odds, last_inning, new_inning = self.calculate_odds(event, game_info["last"],
                                                                                               last_inning)
                        game_info["last"] = last
                        if message:
                            game_info["messages"].append(message)
                        if inc_odds:
                            game_info["inc_odds"].append(inc_odds)
                            if len(game_info["inc_odds"]) > 1:
                                delta = inc_odds - game_info["inc_odds"][len(game_info["inc_odds"]) - 2]
                                game_info["odds_delta"].append({"delta": delta, "batter": batter_id})
                                if batter_id not in players:
                                    players[batter_id] = {}
                                if season not in players[batter_id]:
                                    players[batter_id][season] = {}
                                if event["game_id"] not in players[batter_id][season]:
                                    players[batter_id][season][event["game_id"]] = []

                                players[batter_id][season][event["game_id"]].append(delta)
                        if new_inning:
                            game_info["inning_breaks"].append(len(game_info["inc_odds"]) - 1)
                        batter_id = event['batter_id']

                    output = {"incremental_odds": game_info["inc_odds"],
                              "odds_deltas": game_info["odds_delta"]}
                    odds[season][day].append(output)
                    filename = f"odds_{season}_{day}_{game_json['id']}.json"
        with open(os.path.join('data', 'winexpectancy', 'odds_output', 'all_odds.json'), 'w') as file:
            json.dump(odds, file)
        with open(os.path.join('data', 'winexpectancy', 'odds_output', 'player_deltas.json'), 'w') as file:
            json.dump(players, file)
        print("finished updating win expectancy")

                        # team_odds = game_info["inc_odds"]
                        # opp_odds = [1 - i for i in team_odds]
                        # m_team_odds = [(i - .5) * 2 for i in team_odds]
                        # m_opp_odds = [(i - .5) * 2 for i in opp_odds]
                        #
                        # plt.figure()
                        # plt.suptitle(f"Win Expectancy - Season {season+1} Day {day+1} - {away_team} @ {home_team}")
                        # home_color = team_colors[home_team]['primary']
                        # away_color = team_colors[away_team]['primary']
                        # if home_team == "Moist Talkers":
                        #     home_color = team_colors[home_team]['secondary']
                        # if away_team == "Moist Talkers":
                        #     away_color = team_colors[away_team]['secondary']
                        #
                        # plt.step(m_team_odds, home_color, label=f"{home_team}")
                        # plt.step(m_opp_odds, away_color, label=f"{away_team}")
                        #
                        # for inning in game_info["inning_breaks"]:
                        #     plt.axvline(x=inning, linewidth=1.0, dashes=[2, 2])
                        # plt.legend(loc='best',
                        #            ncol=1, borderaxespad=0.)
                        #
                        # filename = f"s{season}d{day}_{away_team}vs{home_team}.png"
                        # plt.savefig(os.path.join('data', 'winexpectancy', 'images', filename),
                        #             transparent=False, dpi=80, bbox_inches="tight")
                        # with open(os.path.join('data', 'winexpectancy', 'images', filename), 'rb') as file:
                        #     return await ctx.send(file=discord.File(file, filename=filename))

    @commands.command(name="deltas", aliases=['dd'])
    async def _deltas(self, ctx):
        with open(os.path.join('data', 'winexpectancy', 'odds_output', 'player_deltas.json'), 'r') as file:
            players = json.load(file)
        with open(os.path.join('data', 'winexpectancy', 'odds_output', 'player_names.json'), 'r') as file:
            player_names = json.load(file)
        player_odds = {}
        for player in players:
            all_odds = []
            for season in players[player]:
                for game in players[player][season]:
                    for delta in players[player][season][game]:
                        # if delta < -.8:
                        # if delta > .8:
                        #     print(f"{player_names[player]}\t{game}\t{delta}")
                        all_odds.append(delta)
            all_odds.sort()
            lows = all_odds[:5]
            highs = all_odds[-5:]
            highs.sort()
            mean = statistics.mean(all_odds)
            median = statistics.median(all_odds)
            over_five = []
            over_ten = []
            for odds in all_odds:
                if odds > .05:
                    over_five.append(odds)
                    if odds > .1:
                        over_ten.append(odds)

            player_odds[player] = {"name": player_names[player],
                                   "low": lows[0], "high": highs[0],
                                   "mean": mean, "median": median,
                                   "total": len(all_odds),
                                   "over5": len(over_five), "over10": len(over_ten),
                                   "o5percent": len(over_five) / len(all_odds),
                                   "o10percent": len(over_ten) / len(all_odds)}
            if len(over_five) == 0:
                print(0)

        sorted_mean = {k: v for k, v in
                         sorted(player_odds.items(), key=lambda item: item[1]['mean'], reverse=True)}
        sorted_median = {k: v for k, v in
                         sorted(player_odds.items(), key=lambda item: item[1]['median'], reverse=True)}
        sorted_fives = {k: v for k, v in
                         sorted(player_odds.items(), key=lambda item: item[1]['over5'], reverse=True)}
        sorted_tens = {k: v for k, v in
                         sorted(player_odds.items(), key=lambda item: item[1]['over10'], reverse=True)}
        sorted_five_pers = {k: v for k, v in
                         sorted(player_odds.items(), key=lambda item: item[1]['o5percent'], reverse=True)}
        sorted_ten_pers = {k: v for k, v in
                         sorted(player_odds.items(), key=lambda item: item[1]['o10percent'], reverse=True)}
        top_means = list(sorted_mean.keys())[:5]
        top_medians = list(sorted_median.keys())[:5]
        top_fives = list(sorted_fives.keys())[:5]
        top_tens = list(sorted_tens.keys())[:5]
        top_fiveps = list(sorted_five_pers.keys())[:5]
        top_tenps = list(sorted_ten_pers.keys())[:5]

        # for m in top_means:
        #     print(f"mean: {player_names[m]} {sorted_mean[m]['mean']}")
        # for m in top_medians:
        #     print(f"median: {player_names[m]} {sorted_median[m]['median']}")
        for m in top_fives:
            print(f">5% changes: {player_names[m]} {sorted_fives[m]['over5']}")
        for m in top_tens:
            print(f">10% changes: {player_names[m]} {sorted_tens[m]['over10']}")
        for m in top_fiveps:
            print(f"% of changes > 5%: {player_names[m]} {sorted_five_pers[m]['o5percent']} ({sorted_five_pers[m]['total']} total)")
        for m in top_tenps:
            print(f"% of changes > 10%: {player_names[m]} {sorted_ten_pers[m]['o10percent']} ({sorted_five_pers[m]['total']} total)")
        with open(os.path.join('data', 'winexpectancy', 'odds_output', 'player_delta_stats.json'), 'w') as file:
            json.dump(player_odds, file)



def setup(bot):
    bot.add_cog(WinExp(bot))
