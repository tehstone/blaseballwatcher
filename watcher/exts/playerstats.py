import aiosqlite
import discord
from discord.ext import commands


class PlayerStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="player_stats", aliases=['stats'])
    async def _get_player_stats(self, ctx, *, player_name):
        player_id = None
        if player_name in self.bot.player_cache:
            player_id = self.bot.player_cache[player_name]
        elif player_name.lower() in self.bot.player_names:
            player_id = self.bot.player_names[player_name.lower()]
        if not player_id:
            return await ctx.send(f"Could not find player: {player_name}. Please check your spelling and try again.")

        # todo make this dynamic
        season = 13
        stats = None
        async with aiosqlite.connect(self.bot.db_path) as db:
            async with db.execute("select playerId, name, teamId, sum(atBats), sum(caughtStealing), sum(doubles), "
                                  "sum(groundIntoDp), sum(hits), sum(homeRuns), sum(rbis), sum(runs), "
                                  "sum(stolenBases), sum(struckouts), sum(triples), sum(walks)"
                                  "from DailyStatSheets where season=? and position='lineup' "
                                  "and playerId=?", [season, player_id]) as cursor:
                async for row in cursor:
                    if row and row[0]:
                        stats = {
                            "playerId": row[0],
                            "name": row[1],
                            "teamId": row[2],
                            "atBats": row[3],
                            "caughtStealing": row[4],
                            "doubles": row[5],
                            "groundIntoDp": row[6],
                            "hits": row[7],
                            "homeRuns": row[8],
                            "rbis": row[9],
                            "runs": row[10],
                            "stolenBases": row[11],
                            "struckouts": row[12],
                            "triples": row[13],
                            "walks": row[14],
                        }
                    break
        if not stats:
            return await ctx.send(f"Could not find stats for player: {player_name}.")
        title = f"Season 13 stats for {player_name}"
        embed = discord.Embed(colour=discord.Colour.green(),
                              title=title)

        first_half = f"At Bats: {stats['atBats']}\n" \
                     f"Hits: {stats['hits']}\n" \
                     f"Doubles: {stats['doubles']}\n" \
                     f"Triples: {stats['triples']}\n" \
                     f"Home Runs: {stats['homeRuns']}\n" \
                     f"RBIs: {stats['rbis']}\n"

        second_half = f"Runs: {stats['runs']}\n" \
                      f"Stolen Bases: {stats['stolenBases']}\n" \
                      f"Caught Stealing: {stats['caughtStealing']}\n" \
                      f"Strikeouts: {stats['struckouts']}\n" \
                      f"Walks: {stats['walks']}\n" \
                      f"Double Plays: {stats['groundIntoDp']}\n"

        embed.add_field(name=self.bot.empty_str, value=first_half)
        embed.add_field(name=self.bot.empty_str, value=second_half)
        return await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(PlayerStats(bot))
