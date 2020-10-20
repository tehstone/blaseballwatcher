import json
import os

import discord
import requests
from discord.ext import commands

from watcher import utils


class TeamLookups(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='strikeout_leaderboard', aliases=['k_lb'])
    async def _strikeout_leaderboard(self, ctx, season: int = None):
        if not season:
            season = self.bot.config['current_season']
        team_stats = self.get_team_stats_from_file(season)
        if not team_stats:
            return await ctx.send(f"No data available for season {season}")
        total = sum([t["struckouts"] for t in team_stats.values()])
        sorted_shutouts = {k: v for k, v in
                           sorted(team_stats.items(), key=lambda item: item[1]["struckouts"], reverse=True)}
        message = f"**Season {season} team times struck out leaderboard**\n"
        message += f"{total} total strikeouts this season\n\n"
        for team_id, stats in sorted_shutouts.items():
            team_name = self.bot.team_names[team_id]
            struckouts = stats["struckouts"]
            message += f"**{team_name}**: struck out {struckouts} times\n"
        return await ctx.send(message)

    @commands.command(name='shutout_leaderboard', aliases=['sho_lb'])
    async def _shutout_leaderboard(self, ctx, season: int = None):
        if not season:
            season = self.bot.config['current_season']
        team_stats = self.get_team_stats_from_file(season)
        if not team_stats:
            return await ctx.send(f"No data available for season {season}")
        total = sum([t["shutout"] for t in team_stats.values()])
        sorted_shutouts = {k: v for k, v in
                           sorted(team_stats.items(), key=lambda item: item[1]["shutout"], reverse=True)}
        message = f"**Season {season} team shutouts leaderboard**\n"
        message += f"{total} total shutouts this season\n\n"
        for team_id, stats in sorted_shutouts.items():
            team_name = self.bot.team_names[team_id]
            shutouts = stats["shutout"]
            message += f"**{team_name}**: {shutouts} shutouts\n"
        return await ctx.send(message)

    @commands.command(name='team_strikeouts', aliases=['t_ks'])
    async def _team_strikeouts(self, ctx, *, info):
        info_parts = info.split()
        season, team_id, team_name = self._process_input(info_parts)

        if not team_id:
            return await ctx.send(f"Could not find team with name {team_name}.")
        team_stats = self.get_team_stats_from_file(season)
        if not team_stats:
            return await ctx.send(f"No data available for season {season}")
        if team_id not in team_stats:
            return await ctx.send(f"Could not find {team_name} in season {season} data.")

        struckouts = team_stats[team_id]["struckouts"]
        suff = ""
        if struckouts != 1:
            suff = "s"
        message = f"{team_name.capitalize()} have been struck out {struckouts} time{suff} in season {season}"
        return await ctx.send(message)

    @commands.command(name='team_shutouts', aliases=['t_sho'])
    async def _team_shutouts(self, ctx, *, info):
        info_parts = info.split()
        season, team_id, team_name = self._process_input(info_parts)

        if not team_id:
            return await ctx.send(f"Could not find team with name {team_name}.")

        team_stats = self.get_team_stats_from_file(season)
        if not team_stats:
            return await ctx.send(f"No data available for season {season}")

        if team_id not in team_stats:
            return await ctx.send(f"Could not find {team_name} in season {season} data.")
        shutouts = team_stats[team_id]["shutout"]
        suff = ""
        if shutouts != 1:
            suff = "s"
        message = f"{team_name.capitalize()} have been shutout {shutouts} time{suff} in season {season}"
        return await ctx.send(message)

    def _process_input(self, info_parts):
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
        return season, team_id, team_name

    def get_team_stats_from_file(self, season):
        try:
            if season == self.bot.config['current_season']:
                with open(os.path.join('data', 'pendant_data', 'statsheets', 'team_stats.json'), 'r') as file:
                    team_stats = json.load(file)
            else:
                with open(os.path.join('data', 'pendant_data', 'statsheets', f'season{season}statsheets',
                                       f's{season-1}_team_stats.json'), 'r') as file:
                    team_stats = json.load(file)
        except FileNotFoundError:
            return None
        return team_stats


def setup(bot):
    bot.add_cog(TeamLookups(bot))
