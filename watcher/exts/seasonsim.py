import time

from discord.ext import commands


class SeasonSim(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def run_season_sim(self, ctx, season, iterations, start, end, run=True, file_id=None):
        if run:
            if not file_id:
                file_id = str(round(time.time()))
            for day in range(start, end+1):
                data = {"iterations": iterations,
                        "season": season,
                        "day": day,
                        "file_id": file_id,
                        "seg_size": 3
                        }
                async with self.bot.session.get(url=f'http://localhost:5555/v1/seasonsim', json=data,
                                                timeout=75000) as response:
                    await response.json()

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
        return await ctx.send(output_msg)

def setup(bot):
    bot.add_cog(SeasonSim(bot))
