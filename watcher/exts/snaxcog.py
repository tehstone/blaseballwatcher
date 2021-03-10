import asyncio
import re

import discord
from discord.ext import commands

from watcher import utils
from watcher.exts.db.watcher_db import UserSnaxTable, WatcherDB, SnaxInstance
from watcher.snaximum import Snaximum


class SnaxCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.snaximum_instance = Snaximum()

    def update_counts(self, blackholes, floods):
        self.snaximum_instance.set_blackhole_count(blackholes)
        self.snaximum_instance.set_flood_count(floods)
        self.snaximum_instance.refresh_all()

    @commands.command(hidden=True, name='set_snax_channel', aliases=['ssc'])
    @commands.has_permissions(manage_roles=True)
    async def _set_snax_channel(self, ctx, channel_id):
        output_channel = await utils.get_channel_by_name_or_id(ctx, channel_id)
        if output_channel is None:
            return await ctx.message.add_reaction(self.bot.failed_react)
        self.bot.config['snax_channel'] = output_channel.id
        return await ctx.message.add_reaction(self.bot.success_react)

    @commands.command(name='set_snax')
    async def _set_snax(self, ctx, *, snax_info):
        snax_channel_id = self.bot.config.get('snax_channel', 0)
        if ctx.channel.id != snax_channel_id:
            return await ctx.message.delete()
        """
        Usage: !set_snax snackname=quantity [,snackname=quantity...]
        Can accept any number of snack name/quantity pairs. Each pair should be separated by a comma
        and have an '=' between name and quantity. Snack name is somewhat forgiving so you won't need
        to remember the exact name the bot expects but if you receive an error you will need to check
        your spelling and try again.
        Examples:
        !set_snax seeds=50, hot dogs = 100
        !set_snax wetzels = 10, snoil=50
        """
        info_parts = re.split(r',\s+', snax_info)
        errored_parts = []
        success_parts = []
        user_snacks = {}
        for part in info_parts:
            part_bits = part.split('=')
            if len(part_bits) < 2:
                errored_parts.append(part)
                continue

            snack, quantity = part_bits[0].strip(), part_bits[1].strip()
            user_snacks[snack] = quantity

        fields = {"oil": "snake_oil", "snake oil": "snake_oil", "snake_oil": "snake_oil", "snoil": "snake_oil",
                  "fresh": "fresh_popcorn", "popcorn": "fresh_popcorn",
                  "fresh popcorn": "fresh_popcorn", "fresh_popcorn": "fresh_popcorn",
                  "stale": "stale_popcorn", "stale popcorn": "stale_popcorn", "stale_popcorn": "stale_popcorn",
                  "chips": "chips", "burger": "burger", "burgers": "burger",
                  "seed": "seeds", "sunflower": "seeds", "sunflower seeds": "seeds", "seeds": "seeds",
                  "pickle": "pickles", "pickles": "pickles",
                  "hot dog": "hot_dog", "hot dogs": "hot_dog", "hot_dog": "hot_dog", "hot_dogs": "hot_dog",
                  "dog": "hot_dog", "dogs": "hot_dog",
                  "slushie": "slushie", "slushies": "slushie", "slush": "slushie",
                  "wetzle": "wet_pretzel", "wetzel": "wet_pretzel",
                  "wetzles": "wet_pretzel", "wetzels": "wet_pretzel",
                  "pretzel": "wet_pretzel", "pretzels": "wet_pretzel",
                  "wet pretzel": "wet_pretzel", "wet_pretzel": "wet_pretzel"
                  }

        insert_values = []
        for key, value in user_snacks.items():
            if key not in fields:
                errored_parts.append(f"{key}={value}")
                continue
            try:
                insert_value = int(value)
            except:
                errored_parts.append(f"{key}={value}")
                continue

            insert_values.append(f"{fields[key]}={str(insert_value)}")
            success_parts.append(f"{fields[key]} - {str(insert_value)}")

        insert_value_str = ",".join(insert_values)
        if len(insert_value_str) > 0:
            __, __ = UserSnaxTable.get_or_create(user_id=ctx.author.id)
            query_str = f"update UserSnaxTable set {insert_value_str} where user_id == {ctx.author.id}"
            WatcherDB._db.execute_sql(query_str)

        if len(errored_parts) > 0:
            error_msg = "Failed to update the following: \n"
            for part in errored_parts:
                error_msg += f"{part}\n"
            await ctx.send(error_msg)

        if len(success_parts) > 0:
            succcess_msg = "Successfully set:\n"
            for part in success_parts:
                succcess_msg += f"{part}\n"
            await ctx.send(succcess_msg)

    @commands.command(name='lucrative_batters', aliases=['lucrative_batter', 'lucrativeb', 'lucb'])
    async def _lucrative_batters(self, ctx, count: int = 3):
        snax_channel_id = self.bot.config.get('snax_channel', 0)
        if ctx.channel.id != snax_channel_id:
            return await ctx.message.delete()
        """
        Usage: !lucrative_batters [count] - count is optional.
        Will return the best hitting idol choices for you based on the real performance of each player
        so far this season. Count is optional, has a default of 3 and has a hard limit of 10. This
        command is much more useful if you have set up your snaxfolio using the !set_snax command.
        """
        user_result = (UserSnaxTable.select(
                        UserSnaxTable.user_id,
                        UserSnaxTable.snake_oil,
                        UserSnaxTable.fresh_popcorn,
                        UserSnaxTable.stale_popcorn,
                        UserSnaxTable.chips,
                        UserSnaxTable.burger,
                        UserSnaxTable.hot_dog,
                        UserSnaxTable.seeds,
                        UserSnaxTable.pickles,
                        UserSnaxTable.slushie,
                        UserSnaxTable.wet_pretzel
                    ).where(UserSnaxTable.user_id == ctx.author.id))
        user_snax = user_result.objects(SnaxInstance)
        if len(user_snax) > 0:
            snax_set = True
            title = "The most lucrative batters this season based on your snaxfolio:\n"
            luc_list = self.snaximum_instance.get_lucrative_batters(user_snax[0].get_as_dict())
        else:
            snax_set = False
            title = "The most lucrative batters this season"
            luc_list = self.snaximum_instance.get_lucrative_batters()

        count = min(count, 10)
        count = max(count, 1)

        message = ""
        for player in luc_list[:count]:
            name = player[1]["player"]["fullName"]
            stats = player[0]
            message += f"Coins earned this season from {name}:\n"
            total = stats['hits'] + stats['home_runs'] + stats['stolen_bases']
            message += f"Total: {total} - Hits: {stats['hits']}, HRs: {stats['home_runs']}, SBs: {stats['stolen_bases']}\n\n"
        embed = discord.Embed(colour=discord.Colour.green(),
                              title=title, description=message)
        if not snax_set:
            embed.set_footer(text="You'll get better results if you set your snaxfolio!")
        await ctx.send(embed=embed)

    @commands.command(name='propose_upgrades', aliases=['propose_upgrade', 'what_next', "what_to_buy", 'pu'])
    async def _propose_upgrades(self, ctx, coins=50000):
        snax_channel_id = self.bot.config.get('snax_channel', 0)
        if ctx.channel.id != snax_channel_id:
            return await ctx.message.delete()
        """
        Usage: !propose_upgrades [coins] - coins is optional.
        Will return the most optimal next purchases for you. Coins is optional but is useful to filter
        the results to what you can actually afford right now. This command is not very useful unless
        you have set up your snaxfolio using the !set_snax command.
        """
        user_result = (UserSnaxTable.select(
            UserSnaxTable.user_id,
            UserSnaxTable.snake_oil,
            UserSnaxTable.fresh_popcorn,
            UserSnaxTable.stale_popcorn,
            UserSnaxTable.chips,
            UserSnaxTable.burger,
            UserSnaxTable.hot_dog,
            UserSnaxTable.seeds,
            UserSnaxTable.pickles,
            UserSnaxTable.slushie,
            UserSnaxTable.wet_pretzel
        ).where(UserSnaxTable.user_id == ctx.author.id))
        user_snax = user_result.objects(SnaxInstance)

        coins = min(coins, 500000)
        coins = max(coins, 100)

        if len(user_snax) > 0:
            snaxfolio = user_snax[0].get_as_dict()
            proposal_dict = self.snaximum_instance.propose_upgrades(coins, snaxfolio)
            title = "What you should buy next based on your snaxfolio:\n"
            snax_set = True
        else:
            proposal_dict = self.snaximum_instance.propose_upgrades(coins)
            title = "What you should buy next\n"
            snax_set = False

        if proposal_dict["none_available"] == True:
            embed = discord.Embed(colour=discord.Colour.red(),
                                  title="There are no more upgrades available!")
            return await ctx.send(embed=embed)

        message = ""
        if len(proposal_dict["buy_list"]) < 3:
            message += "Your buy list is pretty small, consider providing a higher coin count" \
                       "with this command. The default is 50,000."
        for item in proposal_dict["buy_list"]:
            if len(message) > 1800:
                message += "Reached maximum recommendation length."
                break
            message += f"Buy {item['which']} for {item['cost']}\n"
            message += f"Expected marginal profit this season: {item['dx']}\n\n"

        embed = discord.Embed(colour=discord.Colour.green(),
                              title=title, description=message)

        if not snax_set:
            embed.set_footer(text="You'll get better results if you set your snaxfolio!")

        return await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(SnaxCog(bot))
