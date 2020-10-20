import json
import os

import discord
import requests
from discord.ext import commands

from watcher import utils


class TeamLookups(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='shutout')
    async def _shutout(self, ctx, *, info):
        info_parts = info.split()
        season = None
        try:
            season = int(info_parts[-1])
            del info_parts[-1]
        except ValueError:
            pass
        if not season:
            season = self.bot.config['current_season']

        team_name = ' '.join(info_parts)
        team_id = None
        for team in self.bot.team_names:
            if self.bot.team_names[team].lower() == team_name.lower():
                team_id = team
        if not team_id:
            return await ctx.message.add_reaction(self.bot.failed_react)

        if season == self.bot.config['current_season']:
            with open(os.path.join('data', 'pendant_data', 'statsheets', 'team_stats.json'), 'r') as file:
                team_stats = json.load(file)
        else:
            with open(os.path.join('data', 'pendant_data', 'statsheets', f'season{season}statsheets',
                                   f's{season-1}_team_stats.json'), 'r') as file:
                team_stats = json.load(file)
        if team_id not in team_stats:
            return await ctx.message.add_reaction(self.bot.failed_react)
        shutouts = team_stats[team_id]["shutout"]
        suff = ""
        if shutouts != 1:
            suff = "s"
        message = f"{team_name.capitalize()} have been shutout {shutouts} time{suff} in season {season}"
        return await ctx.send(message)


def setup(bot):
    bot.add_cog(TeamLookups(bot))
