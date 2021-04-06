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

from typing import Dict

snax_fields = {"oil": "snake_oil", "snake oil": "snake_oil", "snake_oil": "snake_oil", "snoil": "snake_oil",
               "snakeoil": "snake_oil",
               "fresh": "fresh_popcorn", "popcorn": "fresh_popcorn",
               "fresh popcorn": "fresh_popcorn", "fresh_popcorn": "fresh_popcorn", "freshpopcorn": "fresh_popcorn",
               "stale": "stale_popcorn", "stale popcorn": "stale_popcorn", "stale_popcorn": "stale_popcorn",
               "stalepopcorn": "stale_popcorn", "stopcorn": "stale_popcorn",
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
               "wet pretzel": "wet_pretzel", "wet_pretzel": "wet_pretzel",
               "wet pretzels": "wet_pretzel", "wet_pretzels": "wet_pretzel",
               "wetpretzel": "wet_pretzel", "wetpretzels": "wet_pretzel",
               'doughnut': 'doughnut', 'donut': 'doughnut', 'doughnuts': 'doughnut', 'donuts': 'doughnut',
               'sundae': 'sundae', 'sundaes': 'sundae', 'sunday': 'sundae', 'sundays': 'sundae',
               'breakfast': 'breakfast', 'breakfasts': 'breakfast',
               'lemonade': 'lemonade', 'lemonades': 'lemonade',
               'taffy': 'taffy', 'taffys': 'taffy', 'taffies': 'taffy',
               'meatball': 'meatball', 'meatballs': 'meatball'
               }


class SnaxCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        season = self.bot.config['current_season']
        self.snaximum_instance = Snaximum(bot, season)

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
            title = "These snax can't be added to your snaxfolio:"
            error_msg = ""
            for part in errored_parts:
                error_msg += f"{part}\n"
            error_msg += "\nCommon errors are forgetting commas, forgetting equals, having invalid snack names, or " \
                         "values too small or too large. (must be between -1 and 99)"
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

        earlseason = self.snaximum_instance.simulation_data['day'] < 5

        if earlseason:
            message = "Currently using last season's performance stats as an estimate for best idol " \
                      "choice this season! Keep in mind that things can and do change significantly " \
                      "between seasons!\n\n"
        else:
            message = ""
        for player in luc_list[:count]:
            name = player[1]["player"]["fullName"]
            player_id = player[1]["player"]["id"]
            shorthand = player[1]["team"]["team_abbreviation"]
            entry = f"[{name}]({'https://www.blaseball.com/player/' + player_id}) "
            stats = player[0]
            message += f"Coins earned this season from {entry} ({shorthand}):\n"
            total = stats['hits'] + stats['home_runs'] + stats['stolen_bases']
            message += f"Total: {total:,} - Hits: {stats['hits']:,} " \
                       f"HRs: {stats['home_runs']:,} SBs: {stats['stolen_bases']:,}\n\n"
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
        post_season = False
        for item in proposal_dict["buy_list"][:limit]:
            post_season = item['post_season']
            if len(message) > 1800:
                message += "Reached maximum recommendation length."
                break
            ratio = (item['sgi'] / item['cost']) if item['cost'] else math.inf
            if math.isinf(item['ratio']):
                ratio = "infinite"
            else:
                ratio = round(ratio*1000)/1000
            name = item['which'].replace('_', ' ')
            message += f"Buy {name} for {item['cost']:,}\n"
            message += f"Expected revenue increase this season: {round(item['sgi'])} ({ratio})\n\n"

        if post_season:
            message += "Revenue increase and ratio above assume a full season upcoming with identical " \
                       "weather and idol performance numbers to the past season. These should be considered " \
                       "rough estimates."
        else:
            message += "(ratio) is the ratio of revenue increase to cost during this season."
        embed = discord.Embed(colour=discord.Colour.green(),
                              title=title, description=message)

        if not snax_set:
            embed.set_footer(text="You'll get better results if you set your snaxfolio!")

        return await ctx.send(embed=embed)

    @commands.command(name='personal_revenue', aliases=['pr'])
    @checks.allow_snax_commands()
    async def _personal_revenue(self, ctx):
        """
        Displays a list of each snack you own along with the total number of coins generated by that
        quantity of snack so far this season.
        """
        snaxfolio = await self._get_user_snax(ctx.author.id)
        revenue_dict, idol_name = self.snaximum_instance.personal_revenue(snaxfolio)
        revenue_msg = ""
        for snack, revenue in revenue_dict.items():
            if revenue > 0:
                name = snack.replace('_', ' ')
                revenue_msg += f"{name.capitalize()}: {revenue:,} coins\n"
        embed = discord.Embed(color=discord.Colour.green(),
                              title=f"Total season revenue based on current snax quantities with idol: {idol_name}",
                              description=revenue_msg)
        embed.set_footer(text="Note: This calculation assumes you had your current snack quantities from Day 1.")
        await ctx.send(embed=embed)

    @commands.command(name='optimize')
    @checks.allow_snax_commands()
    async def _optimize(self, ctx):
        snaxfolio = await self._get_user_snax(ctx.author.id)
        results = self.snaximum_instance.calc_optimal(snaxfolio)
        sorted_results = {k: v for k, v in sorted(results.items(),
                                                  key=lambda item: item[1]["payout"], reverse=True)}
        embed = discord.Embed(title=f"Snaxfolio optimization for {ctx.author.display_name}")
        embed.description = "The list below ranks your optimal snack loadouts, indicating slots filled, total " \
                            "estimated coins, percentage of most optimal, and the snacks to hold per loadout. " \
                            "\nWhile fewer slots may achieve a higher total profit it is more risky as you increase " \
                            "the chances of a single event invalidating your strategy."
        max_payout = 0
        for slots, result in sorted_results.items():
            payout = result["payout"]
            max_payout = max(payout, max_payout)
            ratio = round((payout / max_payout) * 1000)/10
            s_t = "slots"
            if slots == 1:
                s_t = "slot"
            title = f"{slots} {s_t} - {payout:,} coins ({ratio}%)"
            message = ', '.join(result["items"])
            # for item in result["items"]:
            #     message += item + "\n"
            embed.add_field(name=title, value=message)
        return await ctx.send(embed=embed)


    @commands.command(name='season_revenue', aliases=['sr'])
    @checks.allow_snax_commands()
    async def _season_revenue(self, ctx):
        """
        Displays a list of each snack at max level along with the total number of coins generated by that
        quantity of snack so far this season.
        """
        snaxfolio = {
            'wet_pretzel': 99, 'doughnut': 99, 'sundae': 99, 'slushies': 99,
            'snake_oil': 99, 'seeds': 99, 'hot_dog': 99, 'pickles': 99
        }
        revenue_dict, idol_name = self.snaximum_instance.personal_revenue(snaxfolio)
        revenue_msg = ""
        for snack, revenue in revenue_dict.items():
            if revenue > 0:
                name = snack.replace('_', ' ')
                revenue_msg += f"{name.capitalize()}: {revenue:,} coins\n"
        embed = discord.Embed(color=discord.Colour.green(),
                              title=f"Total season revenue based on maxed snax quantities with idol: {idol_name}",
                              description=revenue_msg)
        embed.set_footer(text="Note: This calculation assumes maxed current snack quantities from Day 1.")
        await ctx.send(embed=embed)

    @commands.command(name="snaxfolio", aliases=['snax_folio', 'snax_portfolio', 'my_snax', 'mysnax', 'snackfolio'])
    @checks.allow_snax_commands()
    async def _snaxfolio(self, ctx):
        """
        Displays a list of your current snax.
        """
        snaxfolio = await self._get_user_snax(ctx.author.id)
        ignore_list = await self._get_user_ignore_list(ctx.author.id)

        ignore_str = f"{self.bot.empty_str}"
        if len(ignore_list) > 0:
            ignore_str = "\nCurrent ignore list:\n"
            ignore_str += ', '.join(ignore_list)

        if len(snaxfolio) < 0:
            embed = discord.Embed(colour=discord.Colour.red(),
                                  title="I couldn't find your snaxfolio.",
                                  description="Use the `!set_snax` command to set it up.")
            return await ctx.send(embed=embed)

        if len(snaxfolio.items()) < 2:
            if len(snaxfolio.items()) < 1:
                return await ctx.send(embed=discord.Embed(colour=discord.Colour.green(),
                                      title=f"Your snaxfolio is empty {ctx.author.display_name}!"))
            snack, quantity = list(snaxfolio.items())[0]
            name = snack.replace('_', ' ')
            return await ctx.send(embed=discord.Embed(colour=discord.Colour.green(),
                                                      title=f"{ctx.author.display_name}'s current snaxfolio.",
                                                      description=f"{name.capitalize()}: {quantity}{ignore_str}"))
        snax_msg_parts = []
        for snax, quantity in snaxfolio.items():
            if quantity > 0:
                name = snax.replace('_', ' ')
                snax_msg_parts.append(f"{name.capitalize()}: {quantity}\n")

        embed = discord.Embed(colour=discord.Colour.green(),
                              title=f"{ctx.author.display_name}'s current snaxfolio.")
        if len(ignore_str) > 1:
            embed.description = ignore_str
        split_idx = len(snax_msg_parts) // 2
        left_val = ''.join(snax_msg_parts[:split_idx])
        right_val = ''.join(snax_msg_parts[split_idx:])
        if len(left_val) > 0:
            embed.add_field(name=self.bot.empty_str, value=left_val)
        if len(right_val) > 0:
            embed.add_field(name=self.bot.empty_str, value=right_val)
        return await ctx.send(embed=embed)

    @commands.command(name="cumulative_cost", aliases=['total_cost', 'cc'])
    @checks.allow_snax_commands()
    async def _cumulative_cost(self, ctx, snack, quantity=99):
        if snack in snax_fields:
            normalized_snack = snax_fields[snack]
        else:
            return await ctx.send(f"Unknown snack: {snack}")
        cost = self.snaximum_instance.get_cumulative_cost(normalized_snack, quantity)
        return await ctx.send(f"The cumulative cost for {quantity} {snack} is {cost:,} coins.")

    @commands.command(name="payout")
    @checks.allow_snax_commands()
    async def _get_payout(self, ctx, snack, quantity=99):
        if snack in snax_fields:
            normalized_snack = snax_fields[snack]
        else:
            return await ctx.send(f"Unknown snack: {snack}")
        cost = self.snaximum_instance.get_payout(normalized_snack, quantity)
        return await ctx.send(f"The payout for {quantity} {snack} is {cost:,} coins.")

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
            if insert_value < -1 or insert_value > 99:
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
                                  "hot_dog, seeds, pickles, slushies, wet_pretzel, doughnut, sundae, "
                                  "breakfast, lemonade, taffy, meatball from UserSnaxTable " 
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
                    ignore_list = [i for i in ignore_list_str.split(',') if len(i) > 0]

        return ignore_list

    def refresh_snax_info(self):
        self.snaximum_instance.refresh()


def setup(bot):
    bot.add_cog(SnaxCog(bot))
