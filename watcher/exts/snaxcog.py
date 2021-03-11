import asyncio
import math
import re

import aiosqlite
import discord
from discord.ext import commands

from watcher import utils
from watcher.exts.db.watcher_db import SnaxInstance
from watcher.snaximum import Snaximum

snax_fields = {"oil": "snake_oil", "snake oil": "snake_oil", "snake_oil": "snake_oil", "snoil": "snake_oil",
               "fresh": "fresh_popcorn", "popcorn": "fresh_popcorn",
               "fresh popcorn": "fresh_popcorn", "fresh_popcorn": "fresh_popcorn",
               "stale": "stale_popcorn", "stale popcorn": "stale_popcorn", "stale_popcorn": "stale_popcorn",
               "chips": "chips", "burger": "burger", "burgers": "burger",
               "seed": "seeds", "sunflower": "seeds", "sunflower seeds": "seeds", "seeds": "seeds",
               "pickle": "pickles", "pickles": "pickles",
               "hot dog": "hot_dog", "hot dogs": "hot_dog", "hot_dog": "hot_dog", "hot_dogs": "hot_dog",
               "dog": "hot_dog", "dogs": "hot_dog", "hotdog": "hot_dog", "hotdogs": "hot_dog",
               "slushie": "slushies", "slushies": "slushies", "slush": "slushies",
               "wetzle": "wet_pretzel", "wetzel": "wet_pretzel",
               "wetzles": "wet_pretzel", "wetzels": "wet_pretzel",
               "pretzel": "wet_pretzel", "pretzels": "wet_pretzel",
               "wet pretzel": "wet_pretzel", "wet_pretzel": "wet_pretzel"
               }


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
        if ctx.guild:
            snax_channel_id = self.bot.config.get('snax_channel', 0)
            if ctx.channel.id != snax_channel_id:
                return await ctx.message.delete()
        info_parts = re.split(r',', snax_info)
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

        insert_values = []
        for key, value in user_snacks.items():
            key = key.lower()
            if key not in snax_fields:
                errored_parts.append(f"{key}={value}")
                continue
            try:
                insert_value = int(value)
            except:
                errored_parts.append(f"{key}={value}")
                continue

            insert_values.append(f"{snax_fields[key]}={str(insert_value)}")
            success_parts.append(f"{snax_fields[key]} - {str(insert_value)}")

        insert_value_str = ",".join(insert_values)
        if len(insert_value_str) > 0:
            async with aiosqlite.connect(self.bot.db_path) as db:
                await db.execute(f"insert or ignore into UserSnaxTable (user_id) values ({ctx.author.id})")
                await db.execute(f"update UserSnaxTable set {insert_value_str} where user_id == {ctx.author.id}")
                await db.commit()

        if len(errored_parts) > 0:
            title = "These snacks have spoiled, I've not added them to your snaxfolio:"
            error_msg = ""
            for part in errored_parts:
                error_msg += f"{part}\n"
            embed = discord.Embed(colour=discord.Colour.red(),
                                  title=title, description=error_msg)
            await ctx.send(embed=embed)

        if len(success_parts) > 0:
            title = "mmm these are tasty, I've added them to your snaxfolio:"
            succcess_msg = ""
            for part in success_parts:
                succcess_msg += f"{part}\n"
            embed = discord.Embed(colour=discord.Colour.green(),
                                  title=title, description=succcess_msg)
            await ctx.send(embed=embed)

    @commands.command(name='set_ignore')
    async def _set_ignore(self, ctx, *, ignore_info=None):
        """
        Usage: !set_ignore snack[,snack2...]
        Will accept any number of snacks separated by commas. Each time you use this command your previously
        saved ignore list will be overwritten.
        """
        if ctx.guild:
            snax_channel_id = self.bot.config.get('snax_channel', 0)
            if ctx.channel.id != snax_channel_id:
                return await ctx.message.delete()
        if not ignore_info:
            async with aiosqlite.connect(self.bot.db_path) as db:
                await db.execute(f"insert or ignore into UserSnaxIgnoreTable (user_id) values ({ctx.author.id})")
                await db.execute(f"UPDATE UserSnaxIgnoreTable SET ignore_list = '' where user_id == {ctx.author.id}")
                await db.commit()
            return await ctx.send("Ignore list cleared!")

        info_parts = re.split(r',', ignore_info)
        errored_parts = []
        success_parts = []
        for part in info_parts:
            part = part.strip().lower()
            if part in snax_fields:
                normalized_part = snax_fields[part]
                success_parts.append(normalized_part)
            else:
                errored_parts.append(part)
        if len(success_parts) > 0:
            input_str = ','.join(success_parts)
            async with aiosqlite.connect(self.bot.db_path) as db:
                await db.execute(f"insert or ignore into UserSnaxIgnoreTable (user_id) values ({ctx.author.id})")
                await db.execute(f"update UserSnaxIgnoreTable ignore_list = '{input_str}' where user_id == {ctx.author.id}")
                await db.commit()
            succcess_msg = "Successfully ignored:\n"
            for part in success_parts:
                succcess_msg += f"{part}\n"
            await ctx.send(succcess_msg)

        if len(errored_parts) > 0:
            error_msg = "Failed to update the following: \n"
            for part in errored_parts:
                error_msg += f"{part}\n"
            await ctx.send(error_msg)

    @commands.command(name='lucrative_batters', aliases=['lucrative_batter', 'lucrativeb', 'lucb'])
    async def _lucrative_batters(self, ctx, count: int = 3):
        """
        Usage: !lucrative_batters [count] - count is optional.
        Will return the best hitting idol choices for you based on the real performance of each player
        so far this season. Count is optional, has a default of 3 and has a hard limit of 10. This
        command is much more useful if you have set up your snaxfolio using the !set_snax command.
        """
        if ctx.guild:
            snax_channel_id = self.bot.config.get('snax_channel', 0)
            if ctx.channel.id != snax_channel_id:
                return await ctx.message.delete()

        user_snax = await self._get_user_snax(ctx.author.id)
        user_snax_dict = user_snax.get_as_dict()
        if len(user_snax_dict) > 0:
            snax_set = True
            title = f"Tastiest snacks in {ctx.author.display_name}'s snaxfolio:\n"
            luc_list = self.snaximum_instance.get_lucrative_batters(user_snax_dict)
        else:
            snax_set = False
            title = "Tastiest snacks in the League this season"
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
        """
        Usage: !propose_upgrades [coins] - coins is optional.
        Will return the most optimal next purchases for you. Coins is optional but is useful to filter
        the results to what you can actually afford right now. This command is not very useful unless
        you have set up your snaxfolio using the !set_snax command.
        """
        if ctx.guild:
            snax_channel_id = self.bot.config.get('snax_channel', 0)
            if ctx.channel.id != snax_channel_id:
                return await ctx.message.delete()

        user_snax = await self._get_user_snax(ctx.author.id)
        user_snax_dict = user_snax.get_as_dict()
        ignore_list = []
        # ignore_result = (UserSnaxIgnoreTable.select(
        #     UserSnaxIgnoreTable.user_id,
        #     UserSnaxIgnoreTable.ignore_list
        # ).where(UserSnaxIgnoreTable.user_id == ctx.author.id))
        # if len(ignore_result) > 0:
        #     ignore_list_str = ignore_result[0].ignore_list
        #     ignore_list = ignore_list_str.split(',')

        coins = min(coins, 500000)
        coins = max(coins, 100)

        if len(user_snax_dict) > 0:
            proposal_dict = self.snaximum_instance.propose_upgrades(coins, user_snax_dict, ignore_list)
            title = f"Happy Hour Menu for {ctx.author.display_name}'s snaxfolio:\n"
            snax_set = True
        else:
            proposal_dict = self.snaximum_instance.propose_upgrades(coins, None, ignore_list)
            title = "Generic Happy Hour Menu\n"
            snax_set = False

        if proposal_dict["none_available"] == True:
            embed = discord.Embed(colour=discord.Colour.red(),
                                  title="There are no more upgrades available!")
            return await ctx.send(embed=embed)

        message = ""
        limit = 6
        if len(proposal_dict["buy_list"]) < 3:
            message += "Your buy list is pretty small, consider providing a higher coin count" \
                       "with this command. The default is 50,000.\n"
        for item in proposal_dict["buy_list"][:limit]:
            if len(message) > 1800:
                message += "Reached maximum recommendation length."
                break
            if math.isinf(item['ratio']):
                ratio = "infinite"
            else:
                ratio = round(item['ratio']*1000)/1000
            name = item['which'].replace('_', ' ')
            message += f"Buy {name} for {item['cost']}\n"
            message += f"Expected marginal profit this season: {item['dx']} ({ratio})\n\n"

        message += "Value in parentheses indicates expected profitability this season.\nAny value > 1 " \
                   "will result in profit during the current season."
        embed = discord.Embed(colour=discord.Colour.green(),
                              title=title, description=message)

        if not snax_set:
            embed.set_footer(text="You'll get better results if you set your snaxfolio!")

        return await ctx.send(embed=embed)

    @commands.command(name="snaxfolio", aliases=['snax_folio', 'snax_portfolio', 'my_snax', 'mysnax'])
    async def _snaxfolio(self, ctx):
        if ctx.guild:
            snax_channel_id = self.bot.config.get('snax_channel', 0)
            if ctx.channel.id != snax_channel_id:
                return await ctx.message.delete()
        user_snax = await self._get_user_snax(ctx.author.id)
        snaxfolio = user_snax.get_as_dict()
        if len(snaxfolio) < 0:
            embed = discord.Embed(colour=discord.Colour.red(),
                                  title="I couldn't find your snaxfolio.",
                                  description="Use the `!set_snax` command to set it up.")
            return await ctx.send(embed=embed)

        snax_msg = ""
        for snack, quantity in snaxfolio.items():
            name = snack.replace('_', ' ')
            if quantity > 0:
                snax_msg += f"{name.capitalize()}: {quantity}\n"
        embed = discord.Embed(colour=discord.Colour.green(),
                              title=f"{ctx.author.display_name}'s current snaxfolio.",
                              description=snax_msg)
        return await ctx.send(embed=embed)

    async def _get_user_snax(self, user_id):
        async with aiosqlite.connect(self.bot.db_path) as db:
            async with db.execute(
                """select user_id, snake_oil, fresh_popcorn, stale_popcorn, chips, burger,
                       hot_dog, seeds, pickles, slushies, wet_pretzel
                   where user_id == ?;""", user_id) as cursor:
                async for row in cursor:
                    user_snax = SnaxInstance(*row)

        return user_snax


def setup(bot):
    bot.add_cog(SnaxCog(bot))
