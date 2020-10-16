import json
import os
from datetime import datetime

import discord
from discord.ext import commands

from watcher import utils


class PlayerData(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def parse_teams(self, ctx, include_fk=False):
        players = {}
        url = "https://www.blaseball.com/database/allTeams"
        html_response = await utils.retry_request(url)
        if not html_response:
            return
        teams_data = html_response.json()
        for team in teams_data:
            batters = team["lineup"]
            pitchers = team["rotation"]
            bullpen = team["bullpen"]
            bench = team["bench"]
            for batter in batters:
                players[batter] = {"team": team["nickname"], "position": "batter"}
            for pitcher in pitchers:
                players[pitcher] = {"team": team["nickname"], "position": "pitcher"}
            if include_fk:
                for pitcher in bullpen:
                    players[pitcher] = {"team": team["nickname"], "position": "bullpen"}
                for batter in bench:
                    players[batter] = {"team": team["nickname"], "position": "bench"}

        async def get_batch(id_string):
            b_url = f"https://www.blaseball.com/database/players?ids={id_string}"
            html_response = await utils.retry_request(b_url)
            return html_response.json()

        batter_ids = list(players.keys())
        all_json = []
        min_players = {}
        chunked_player_ids = [batter_ids[i:i + 50] for i in range(0, len(batter_ids), 50)]
        for chunk in chunked_player_ids:
            batch_json = await get_batch(','.join(chunk))
            for player in batch_json:
                min_players[player["id"]] = {"team": players[player["id"]]["team"],
                                             "name": player["name"],
                                             "position": players[player["id"]]["position"]
                                             }
                player["position"] = players[player["id"]]["position"]
                player["team"] = players[player["id"]]["team"]
                all_json.append(player)
                    # writer.writerow({
                    #     "id": player["id"],
                    #     "team": team,
                    #     "position": position,
                    #     "anticapitalism": player["anticapitalism"],
                    #     "baseThirst": player["baseThirst"],
                    #     "buoyancy": player["buoyancy"],
                    #     "chasiness": player["chasiness"],
                    #     "coldness": player["coldness"],
                    #     "continuation": player["continuation"],
                    #     "divinity": player["divinity"],
                    #     "groundFriction": player["groundFriction"],
                    #     "indulgence": player["indulgence"],
                    #     "laserlikeness": player["laserlikeness"],
                    #     "martyrdom": player["martyrdom"],
                    #     "moxie": player["moxie"],
                    #     "musclitude": player["musclitude"],
                    #     "name": player["name"],
                    #     "bat": player["bat"],
                    #     "omniscience": player["omniscience"],
                    #     "overpowerment": player["overpowerment"],
                    #     "patheticism": player["patheticism"],
                    #     "ruthlessness": player["ruthlessness"],
                    #     "shakespearianism": player["shakespearianism"],
                    #     "suppression": player["suppression"],
                    #     "tenaciousness": player["tenaciousness"],
                    #     "thwackability": player["thwackability"],
                    #     "tragicness": player["tragicness"],
                    #     "unthwackability": player["unthwackability"],
                    #     "watchfulness": player["watchfulness"],
                    #     "pressurization": player["pressurization"],
                    #     "totalFingers": player["totalFingers"],
                    #     "soul": player["soul"],
                    #     "deceased": player["deceased"],
                    #     "peanutAllergy": player["peanutAllergy"],
                    #     "cinnamon": player["cinnamon"],
                    #     "fate": player["fate"],
                    #     "armor": player["armor"],
                    #     "ritual": player["ritual"],
                    #     "coffee": player["coffee"],
                    #     "blood": player["blood"]
                    # })
        timestamp = round(datetime.utcnow().timestamp())
        with open(os.path.join('data', 'stlats', f'player_ids_{timestamp}.json'), 'w') as file:
            json.dump(min_players, file)
        with open(os.path.join('data', 'stlats', f'player_ids_{timestamp}.json'), 'rb') as logfile:
            await ctx.send(file=discord.File(logfile, filename=f'player_ids_{timestamp}.json'))
        with open(os.path.join('data', 'stlats', f'player_stlats_{timestamp}.json'), 'w') as file:
            json.dump(all_json, file)
        with open(os.path.join('data', 'stlats', f'player_stlats_{timestamp}.json'), 'rb') as logfile:
            await ctx.send(file=discord.File(logfile, filename=f'player_stlats_{timestamp}.json'))

    @commands.command(name="save_player_data", aliases=['spd'])
    async def _save_player_data(self, ctx):
        await self.parse_teams(ctx)


def setup(bot):
    bot.add_cog(PlayerData(bot))
