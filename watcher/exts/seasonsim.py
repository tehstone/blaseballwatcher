import time

from discord.ext import commands


class SeasonSim(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def sum_season(self, ctx, file_id=None):
        # season: int, iterations: int, start: int, end: int, run=True,
        # if run:
        #     if not file_id:
        #         file_id = str(round(time.time()))
        #     for day in range(start, end+1):
        #         data = {"iterations": iterations,
        #                 "season": season,
        #                 "day": day,
        #                 "file_id": file_id,
        #                 "seg_size": 3
        #                 }
        #         async with self.bot.session.get(url=f'http://localhost:5555/v1/seasonsim', json=data,
        #                                         timeout=75000) as response:
        #             await response.json()

        data = {
                "file_id": file_id
               }
        async with self.bot.session.get(url=f'http://localhost:5555/v1/sumseason', json=data,
                                        timeout=75000) as response:
            result = await response.json()
        if len(result["failed"]) > 0:
            await ctx.send(f"Days {', '.join(result['failed'])} failed to sim.")
        output = result["output"]
        output_msg = ""
        sorted_output = {k: v for k, v in sorted(output.items(), key=lambda item: item[1]['wins'], reverse=True)}
        for team in sorted_output:
            if team in self.bot.team_cache:
                output_msg += f'{self.bot.team_cache[team]["nickname"]}'
                output_msg += f'\t{sorted_output[team]["wins"]} - {sorted_output[team]["losses"]}\n'
        await ctx.send(output_msg)

        player_stats = result["stats"]
        sorted_hits = {k: v for k, v in sorted(player_stats.items(),
                                               key=lambda item: item[1].get("Batter hits", 0),
                                               reverse=True)}
        hitter_msg = ""
        top_hit_keys = list(sorted_hits.keys())[:10]
        for pid in top_hit_keys:
            if pid not in self.bot.player_id_to_name:
                continue
            name = self.bot.player_id_to_name[pid]
            hitter_msg += f"{name}: {round(sorted_hits[pid]['Batter hits'])}\n"
        await ctx.send(hitter_msg)

        sorted_hrs = {k: v for k, v in sorted(player_stats.items(),
                                               key=lambda item: item[1].get("Batter hrs", 0),
                                               reverse=True)}
        hr_msg = ""
        top_hit_keys = list(sorted_hrs.keys())[:10]
        for pid in top_hit_keys:
            if pid not in self.bot.player_id_to_name:
                continue
            name = self.bot.player_id_to_name[pid]
            hr_msg += f"{name}: {round(sorted_hrs[pid]['Batter hrs'])}\n"
        await ctx.send(hr_msg)


def setup(bot):
    bot.add_cog(SeasonSim(bot))
