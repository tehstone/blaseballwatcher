import asyncio
import json
import math
import os
import re

import aiosqlite
import discord
from discord.ext import commands

from watcher import utils, checks
from watcher.exts.db.watcher_db import SnaxInstance
from watcher.snaximum import Snaximum

from typing import Any, Dict, Iterable, List, Optional, Tuple, cast

snax_fields = {"oil": "snake_oil", "snake oil": "snake_oil", "snake_oil": "snake_oil", "snoil": "snake_oil",
               "fresh": "fresh_popcorn", "popcorn": "fresh_popcorn",
               "fresh popcorn": "fresh_popcorn", "fresh_popcorn": "fresh_popcorn", "freshpopcorn": "fresh_popcorn",
               "stale": "stale_popcorn", "stale popcorn": "stale_popcorn", "stale_popcorn": "stale_popcorn",
               "stalepopcorn": "stale_popcorn",
               "chips": "chips", "burger": "burger", "burgers": "burger",
               "seed": "seeds", "sunflower": "seeds", "sunflower seeds": "seeds", "seeds": "seeds",
               "sunflower_seeds": "seeds",
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
        season = self.bot.config['current_season']
        self.snaximum_instance = Snaximum(bot, season)
        self.team_short_map = None

    def update_counts(self, black_holes, floods, day):
        self.snaximum_instance.set_blackhole_count(black_holes)
        self.snaximum_instance.set_flood_count(floods)
        self.snaximum_instance.set_current_day(day)
        self.snaximum_instance.bets.set_current_day(day)
        self.snaximum_instance.refresh()

    async def get_short_map(self):
        if self.team_short_map:
            return self.team_short_map
        with open(os.path.join('data', 'allTeams.json'), 'r', encoding='utf-8') as file:
            all_teams = json.load(file)
        team_short_map = {}
        for team in all_teams:
            team_short_map[team["id"]] = team["shorthand"]
        self.team_short_map = team_short_map
        return team_short_map

    @commands.command(hidden=True, name='add_snax_channel', aliases=['asc'])
    @commands.has_permissions(manage_roles=True)
    async def _add_snax_channel(self, ctx, channel_id):
        output_channel = await utils.get_channel_by_name_or_id(ctx, channel_id)
        if output_channel is None:
            return await ctx.message.add_reaction(self.bot.failed_react)
        snax_channels = self.bot.config.setdefault('snax_channels', [])
        if output_channel.id not in snax_channels:
            snax_channels.append(output_channel.id)
        return await ctx.message.add_reaction(self.bot.success_react)

    @commands.command(hidden=True, name='rem_snax_channel', aliases=['rsc'])
    @commands.has_permissions(manage_roles=True)
    async def _rem_snax_channel(self, ctx, channel_id):
        output_channel = await utils.get_channel_by_name_or_id(ctx, channel_id)
        if output_channel is None:
            return await ctx.message.add_reaction(self.bot.failed_react)
        snax_channels = self.bot.config.setdefault('snax_channels', [])
        if output_channel.id in snax_channels:
            snax_channels.remove(output_channel.id)
        return await ctx.message.add_reaction(self.bot.success_react)

    @commands.command(name='set_snax', aliases=['setsnax', 'set_snack', 'set_snacks'])
    @checks.allow_snax_commands()
    async def _set_snax(self, ctx, *, snax_info):
        """
        Usage: !set_snax snackname=quantity [,snackname=quantity...]
        Aliases: !setsnax !set_snack !set_snacks
        Can accept any number of snack name/quantity pairs. Each pair should be separated by a comma
        and have an '=' between name and quantity. Snack name is somewhat forgiving so you won't need
        to remember the exact name the bot expects but if you receive an error you will need to check
        your spelling and try again.
        Examples:
        !set_snax seeds=50, hot dogs = 100
        !set_snax wetzels = 10, snoil=50
        """
        success_parts, errored_parts, user_snacks = self._process_snack_parts(snax_info)

        insert_value_str = ",".join(success_parts)
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
            success_msg = ""
            for part in success_parts:
                success_msg += f"{part.replace('=', ' - ')}\n"
            embed = discord.Embed(colour=discord.Colour.green(),
                                  title=title, description=success_msg)
            await ctx.send(embed=embed)

    @commands.command(name='increment_snax', aliases=['incrementsnax', 'incsnax', 'snax++'])
    @checks.allow_snax_commands()
    async def _increment_snax(self, ctx, *, snax_info):
        """
        Usage: !increment_snax snackname=quantity [,snackname=quantity...]
        Aliases !incrementsnax !incsnax !snax++
        Adds the number provided to the already stored number of snacks for that item.
        Can accept any number of snack name/quantity pairs. Each pair should be separated by a comma
        and have an '=' between name and quantity. Snack name is somewhat forgiving so you won't need
        to remember the exact name the bot expects but if you receive an error you will need to check
        your spelling and try again.
        Examples:
        !increment_snax seeds=50, hot dogs = 100
        !increment_snax wetzels = 10, snoil=50
        """
        success_parts, errored_parts, user_snacks = self._process_snack_parts(snax_info)

        async with aiosqlite.connect(self.bot.db_path) as db:
            await db.execute(f"insert or ignore into UserSnaxTable (user_id) values ({ctx.author.id})")
            await db.commit()
        snaxfolio = await self._get_user_snax(ctx.author.id)
        for part in success_parts:
            snack, quantity = part.split('=')
            snaxfolio[snack] += int(quantity)

        insert_values = []
        for snack, quantity in snaxfolio.items():
            insert_values.append(f"{snack}={quantity}")
        insert_value_str = ','.join(insert_values)
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
            title = "These look tasty, I've added a few more to your snaxfolio:"
            success_msg = ""
            for part in success_parts:
                success_msg += f"{part.replace('=', ' - ')}\n"
            embed = discord.Embed(colour=discord.Colour.green(),
                                  title=title, description=success_msg)
            await ctx.send(embed=embed)

    @commands.command(name='set_ignore', aliases=['setignore'])
    @checks.allow_snax_commands()
    async def _set_ignore(self, ctx, *, ignore_info=None):
        """
        Usage: !set_ignore snack[,snack2...]
        Will accept any number of snacks separated by commas. Each time you use this command your previously
        saved ignore list will be overwritten.
        """
        if not ignore_info:
            async with aiosqlite.connect(self.bot.db_path) as db:
                await db.execute(f"insert or ignore into UserSnaxIgnoreTable (user_id) values ({ctx.author.id})")
                await db.execute(f"UPDATE UserSnaxIgnoreTable SET ignore_list = '' where user_id == {ctx.author.id}")
                await db.commit()
            return await ctx.send("Ignore list cleared!")

        success_parts, errored_parts = self._process_ignore_parts(ignore_info)

        if len(success_parts) > 0:
            input_str = ','.join(success_parts)
            async with aiosqlite.connect(self.bot.db_path) as db:
                await db.execute(f"insert or ignore into UserSnaxIgnoreTable (user_id) values ({ctx.author.id})")
                await db.execute(f"update UserSnaxIgnoreTable set ignore_list='{input_str}' where user_id={ctx.author.id}")
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

    @commands.command(name='add_ignore', aliases=['addignore'])
    @checks.allow_snax_commands()
    async def _add_ignore(self, ctx, *, ignore_info):
        """
        Usage: !add_ignore snack[,snack2...]
        Adds the provided snacks to the list that will be ignored when proposing upgrades.
        Will accept any number of snacks separated by commas.
        """
        current_ignore_list = await self._get_user_ignore_list(ctx.author.id)
        success_parts, errored_parts = self._process_ignore_parts(ignore_info)

        for part in success_parts:
            if part not in current_ignore_list:
                current_ignore_list.append(part)

        input_str = ','.join(current_ignore_list)
        async with aiosqlite.connect(self.bot.db_path) as db:
            await db.execute(f"insert or ignore into UserSnaxIgnoreTable (user_id) values ({ctx.author.id})")
            await db.execute(f"update UserSnaxIgnoreTable set ignore_list='{input_str}' where user_id={ctx.author.id}")
            await db.commit()

        if len(errored_parts) > 0:
            error_msg = "Failed to update the following: \n"
            for part in errored_parts:
                error_msg += f"{part}\n"
            await ctx.send(error_msg)

        await ctx.send(f"Your current ignore list is: {', '.join(current_ignore_list)}")

    @commands.command(name='remove_ignore', aliases=['removeignore', 'rem_ignore', 'remignore'])
    @checks.allow_snax_commands()
    async def _remove_ignore(self, ctx, *, ignore_info):
        """
        Usage: !remove_ignore snack[,snack2...]
        Removes the provided snacks from the list that will be ignored when proposing upgrades.
        Will accept any number of snacks separated by commas.
        """
        current_ignore_list = await self._get_user_ignore_list(ctx.author.id)
        success_parts, errored_parts = self._process_ignore_parts(ignore_info)

        for part in success_parts:
            if part in current_ignore_list:
                current_ignore_list.remove(part)

        input_str = ','.join(current_ignore_list)
        async with aiosqlite.connect(self.bot.db_path) as db:
            await db.execute(f"insert or ignore into UserSnaxIgnoreTable (user_id) values ({ctx.author.id})")
            await db.execute(f"update UserSnaxIgnoreTable set ignore_list='{input_str}' where user_id={ctx.author.id}")
            await db.commit()

        if len(errored_parts) > 0:
            error_msg = "Failed to update the following: \n"
            for part in errored_parts:
                error_msg += f"{part}\n"
            await ctx.send(error_msg)

        await ctx.send(f"Your current ignore list is: {', '.join(current_ignore_list)}")

    @commands.command(name='lucrative_batters', aliases=['lucrative_batter', 'lb'])
    @checks.allow_snax_commands()
    async def _lucrative_batters(self, ctx, count: int = 3):
        """
        Usage: !lucrative_batters [count] - count is optional.
        Will return the best hitting idol choices for you based on the real performance of each player
        so far this season. Count is optional, has a default of 3 and has a hard limit of 10. This
        command is much more useful if you have set up your snaxfolio using the !set_snax command.
        """
        snaxfolio = await self._get_user_snax(ctx.author.id)

        if len(snaxfolio) > 0:
            snax_set = True
            title = f"Tastiest snacks in {ctx.author.display_name}'s snaxfolio:\n"
            luc_list = self.snaximum_instance.get_lucrative_batters(snaxfolio)
        else:
            snax_set = False
            title = "Tastiest snacks in the League this season"
            luc_list = self.snaximum_instance.get_lucrative_batters()

        count = min(count, 10)
        count = max(count, 1)

        team_short_map = await self.get_short_map()
        message = ""
        for player in luc_list[:count]:
            name = player[1]["player"]["fullName"]
            player_id = player[1]["player"]["id"]
            team_id = player[1]["team"]["team_id"]
            shorthand = team_short_map[team_id]
            entry = f"[{name}]({'https://www.blaseball.com/player/' + player_id}) "
            stats = player[0]
            message += f"Coins earned this season from {entry} ({shorthand}):\n"
            total = stats['hits'] + stats['home_runs'] + stats['stolen_bases']
            message += f"Total: {total} - Hits: {stats['hits']}, HRs: {stats['home_runs']}, SBs: {stats['stolen_bases']}\n\n"
        embed = discord.Embed(colour=discord.Colour.green(),
                              title=title, description=message)
        if not snax_set:
            embed.set_footer(text="You'll get better results if you set your snaxfolio!")
        await ctx.send(embed=embed)

    @commands.command(name='propose_upgrades', aliases=['propose_upgrade', 'what_next', "what_to_buy", 'pu'])
    @checks.allow_snax_commands()
    async def _propose_upgrades(self, ctx, *, info=None):
        """
        Usage: !propose_upgrades [coins] - coins is optional.
        Will return the most optimal next purchases for you. Coins is optional but is useful to filter
        the results to what you can actually afford right now. This command is not very useful unless
        you have set up your snaxfolio using the !set_snax command.
        """
        snaxfolio = await self._get_user_snax(ctx.author.id)
        ignore_list = await self._get_user_ignore_list(ctx.author.id)

        coins = 50000

        if info:
            info_parts = info.split(',')
            for part in info_parts:
                try:
                    new_coins = int(part)
                    coins = min(new_coins, 500000)
                    coins = max(coins, 100)
                except ValueError:
                    continue

        if len(snaxfolio) > 0:
            proposal_dict = self.snaximum_instance.do_propose_upgrades(coins, snaxfolio, ignore_list)
            title = f"Happy Hour Menu for {ctx.author.display_name}'s snaxfolio:\n"
            snax_set = True
        else:
            proposal_dict = self.snaximum_instance.do_propose_upgrades(coins, None, ignore_list)
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
            ratio = (item['sgi'] / item['cost']) if item['cost'] else math.inf
            if math.isinf(item['ratio']):
                ratio = "infinite"
            else:
                ratio = round(ratio*1000)/1000
            name = item['which'].replace('_', ' ')
            message += f"Buy {name} for {item['cost']}\n"
            message += f"Expected revenue increase this season: {round(item['sgi'])} ({ratio})\n\n"

        message += "(ratio) is the ratio of revenue increase to cost during this season."
        embed = discord.Embed(colour=discord.Colour.green(),
                              title=title, description=message)

        if not snax_set:
            embed.set_footer(text="You'll get better results if you set your snaxfolio!")

        return await ctx.send(embed=embed)

    @commands.command(name="snaxfolio", aliases=['snax_folio', 'snax_portfolio', 'my_snax', 'mysnax'])
    @checks.allow_snax_commands()
    async def _snaxfolio(self, ctx):
        """
        Displays a list of your current snax.
        """
        snaxfolio = await self._get_user_snax(ctx.author.id)

        if len(snaxfolio) < 0:
            embed = discord.Embed(colour=discord.Colour.red(),
                                  title="I couldn't find your snaxfolio.",
                                  description="Use the `!set_snax` command to set it up.")
            return await ctx.send(embed=embed)

        snax_msg = ""
        for snack, quantity in snaxfolio.items():
            if quantity > 0:
                name = snack.replace('_', ' ')
                snax_msg += f"{name.capitalize()}: {quantity}\n"

        embed = discord.Embed(colour=discord.Colour.green(),
                              title=f"{ctx.author.display_name}'s current snaxfolio.",
                              description=snax_msg)
        return await ctx.send(embed=embed)

    @staticmethod
    def _process_snack_parts(snack_str):
        info_parts = re.split(r',', snack_str)
        success_parts = []
        errored_parts = []
        user_snacks = {}
        for part in info_parts:
            part_bits = part.split('=')
            if len(part_bits) < 2:
                errored_parts.append(part)
                continue

            snack, quantity = part_bits[0].strip().lower(), part_bits[1].strip()
            if snack not in snax_fields:
                errored_parts.append(part)
                continue
            try:
                insert_value = int(quantity)
            except:
                errored_parts.append(part)
                continue
            success_parts.append(f"{snax_fields[snack]}={str(insert_value)}")
            user_snacks[snack] = quantity
        return success_parts, errored_parts, user_snacks

    @staticmethod
    def _process_ignore_parts(ignore_str):
        info_parts = re.split(r',', ignore_str)
        errored_parts = []
        success_parts = []
        for part in info_parts:
            part = part.strip().lower()
            if part in snax_fields:
                normalized_part = snax_fields[part]
                success_parts.append(normalized_part)
            else:
                errored_parts.append(part)
        return success_parts, errored_parts

    async def _get_user_snax(self, user_id: int) -> Dict:
        snaxfolio = {}
        async with aiosqlite.connect(self.bot.db_path) as db:
            async with db.execute("select user_id, snake_oil, fresh_popcorn, stale_popcorn, chips, burger, " 
                                  "hot_dog, seeds, pickles, slushies, wet_pretzel from UserSnaxTable " 
                                  f"where user_id={user_id};") as cursor:
                async for row in cursor:
                    user_snax = SnaxInstance(*row)
                    snaxfolio = user_snax.get_as_dict()

        return snaxfolio

    async def _get_user_ignore_list(self, user_id: int) -> list:
        ignore_list = []
        async with aiosqlite.connect(self.bot.db_path) as db:
            async with db.execute("select user_id, ignore_list from UserSnaxIgnoreTable " 
                                  f"where user_id={user_id};") as cursor:
                async for row in cursor:
                    ignore_list_str = row[1]
                    ignore_list = ignore_list_str.split(',')

        return ignore_list


def setup(bot):
    bot.add_cog(SnaxCog(bot))
