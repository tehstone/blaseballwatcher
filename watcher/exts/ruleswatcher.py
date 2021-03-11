import asyncio
import datetime
import difflib
import json
import os
import time

import aiohttp
import aiosqlite
import discord
import requests
from bs4 import BeautifulSoup as bs
from urllib.parse import urljoin

from discord.ext import commands

from watcher import utils, parse_blaseball_book


class RulesWatcher(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.default_interval_minutes = 10
        self.no_reply_messages = ["No change to Rule Book text.",
                                  "Failed to find a js URL.",
                                  "Failed to obtain most recent page text."]
        self.main_guild_id = 738107179294523402

    @commands.command(name='set_notify_channel', aliases=['snc'])
    async def _set_notify_channel(self, ctx, item):
        output_channel = await utils.get_channel_by_name_or_id(ctx, item)
        if output_channel is None:
            return await ctx.message.add_reaction(self.bot.failed_react)
        self.bot.config['notify_channel'] = output_channel.id
        return await ctx.message.add_reaction(self.bot.success_react)

    @commands.command(name='_set_debug_channel', aliases=['sdb'])
    async def _set_debug_channel(self, ctx, item):
        output_channel = await utils.get_channel_by_name_or_id(ctx, item)
        if output_channel is None:
            return await ctx.message.add_reaction(self.bot.failed_react)
        self.bot.config['debug_channel'] = output_channel.id
        return await ctx.message.add_reaction(self.bot.success_react)

    @commands.command(name='set_update_interval', aliases=['sui'])
    async def _set_update_interval(self, ctx, minutes: int):
        self.bot.config['interval_minutes'] = minutes
        return await ctx.message.add_reaction(self.bot.success_react)

    @commands.command(name='set_rules_ping_role', aliases=['srpr'])
    async def _set_rules_ping_role(self, ctx, role_id):
        role_id = utils.sanitize_name(role_id)
        try:
            role_id = int(role_id)
            role = discord.utils.get(ctx.guild.roles, id=role_id)
        except:
            role = discord.utils.get(ctx.guild.roles, name=role_id)
        if role is None:
            await ctx.message.add_reaction(self.bot.failed_react)
            return await ctx.send(embed=discord.Embed(colour=discord.Colour.red(),
                                                      description=f"Unable to find role with name or id: **{role_id}**."),
                                  delete_after=10)
        self.bot.config['rules_ping_role'] = role.id
        return await ctx.message.add_reaction(self.bot.success_react)

    @commands.command(name='get_update_interval', aliases=['gui'])
    async def _get_update_interval(self, ctx):
        interval = self.bot.config.setdefault('interval_minutes', self.default_interval_minutes)
        return await ctx.channel.send(f"Delay interval between checks for Rule Book updates is {interval} minutes.")

    @commands.command(name='set_player_interval', aliases=['spi'])
    async def _set_update_interval(self, ctx, seconds: int):
        self.bot.config['player_change_interval'] = seconds
        return await ctx.message.add_reaction(self.bot.success_react)

    @staticmethod
    def retryrequest(url, tries=5):
        for i in range(tries):
            response = requests.get(url)
            if response.status_code == 200:
                return response
        return None

    @staticmethod
    async def request_text(url):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                return await resp.text()

    async def watch_players(self):
        rituals = self.bot.config.setdefault('rituals', {})
        watch_list = self.bot.config.setdefault('player_watch_list', ["3a96d76a-c508-45a0-94a0-8f64cd6beeb4",
                                                                      "1f159bab-923a-4811-b6fa-02bfde50925a"])
        url = f"https://www.blaseball.com/database/players?ids={','.join(watch_list)}"
        output_channel = self.bot.get_channel(self.bot.config['notify_channel'])
        html_response = await utils.retry_request(url)
        if html_response:
            for player in html_response.json():
                if player["id"] in rituals:
                    if player["ritual"] != rituals[player["id"]]['ritual']:
                        message = f"{player['name']}'s pregame ritual has changed from " \
                                  f"\"{rituals[player['id']]['ritual']}\" to \"{player['ritual']}\".\n" \
                                  f"https://www.blaseball.com/database/players?ids={player['id']}"
                        await output_channel.send(message)
                    if rituals[player["id"]] != player:
                        print(f"Player {player['name']} has changed.")
                        with open(os.path.join("json_data", "players", f"{player['name']}{time.time()}.json"), 'w') as file:
                            json.dump(player, file)
                rituals[player['id']] = player
        else:
            self.bot.logger.warning("Could not get updated player pages.")
        await self.save()

    async def _check_for_rules_update(self):
        messages = []
        retries = 3
        new_page_text, js_url = None, None
        for i in range(retries):
            try:
                new_page_text, js_url = await parse_blaseball_book.parse_book_from_javascript(self.bot)
                break
            except:
                pass
        if not js_url:
            messages.append("Failed to find a js URL.")
            return messages, None
        old_url = self.bot.config.setdefault('last_js_url', None)

        self.bot.logger.info(f"Current url: {js_url} Old url: {old_url}")
        if not old_url:
            self.bot.config['last_js_url'] = js_url
        else:
            if old_url != js_url:
                self.bot.config['last_js_url'] = js_url
                appended = False
                ping_role_id = self.bot.config.setdefault('rules_ping_role', None)
                if ping_role_id:
                    guild = await self.bot.fetch_guild(self.main_guild_id)
                    ping_role = guild.get_role(ping_role_id)
                    if ping_role:
                        messages.append(f'Script URL has changed {ping_role.mention}!\nOld: <{old_url}>\nNew: <{js_url}>')
                        appended = True
                if not appended:
                    messages.append(f'Script URL has changed!\nOld: <{old_url}>\nNew: <{js_url}>')

        if not new_page_text:
            #self.bot.logger.warning("Failed to obtain updated page text.")
            return messages, None
        last_page_text = await self._get_last_text()
        if not last_page_text:
            messages.append("Failed to obtain most recent page text.")
            return messages, None
        if new_page_text == last_page_text:
            messages.append(self.no_reply_messages[0])
            return messages, None
        else:
            new_lines = new_page_text.splitlines()
            old_lines = last_page_text.splitlines()
            diff = difflib.ndiff(old_lines, new_lines)
            filename = f'diff_{datetime.datetime.utcnow().timestamp()}.txt'
            with open(os.path.join('diffs', filename), 'w') as file:
                for line in diff:
                    file.write(f"{line}\n")
            await self._update_last_text(new_page_text)
            messages.append("Rule book text changed!")
            return messages, filename

    @commands.command(name='test', aliases=['tt'])
    async def _testt(self, ctx):
        messages, filename = await self._check_for_rules_update()
        for m in messages:
            await ctx.send(m)
            self.bot.logger.info(m)
        if filename:
            output_channel_id = self.bot.guild_dict[ctx.guild.id]['configure_dict'].setdefault('notify_channel', None)
            if output_channel_id:
                output_channel = self.bot.get_channel(output_channel_id)
                if output_channel:
                    with open(os.path.join('diffs', filename), 'rb') as logfile:
                        await ctx.send(file=discord.File(logfile, filename=filename))

    async def _get_last_text(self):
        try:
            async with aiosqlite.connect(self.bot.db_path) as db:
                async with db.execute("select page_text from RulesBlogTable order by pull_date desc limit 1") as cursor:
                    async for row in cursor:
                        return row[0]
        except:
            return None

    async def _update_last_text(self, text):
        text = text.replace("'", "''")
        async with aiosqlite.connect(self.bot.db_path) as db:
            await db.execute("insert into RulesBlogTable (pull_date, page_text) values "
                             f"('{datetime.datetime.utcnow()}', '{text}')")
            await db.commit()

    def _get_page_text(self):
        session = requests.Session()
        session.headers[
            "User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.2403.157 Safari/537.36"
        b_url = "https://blaseball.com/static/js/main.js"
        html = session.get(b_url).content
        soup = bs(html, "html.parser")
        url, new_text = None, None
        for script in soup.find_all("script"):
            if script.attrs.get("src"):
                script_url = urljoin("https://blaseball.com", script.attrs.get("src"))
                if "js/main." in script_url:
                    url = script_url
                    break
        if not url:
            return None
        # url = "https://blaseball.com/static/js/main.e71dc0e8.chunk.js"
        response = self.retryrequest(url)
        if not response:
            self.bot.logger.warning("Failed to get a response loading js file.")
        else:
            script_text = response.text
            # while "handleComplete" in script_text:
            #     response = self.retryrequest(url)
            #     if response:
            #         script_text = response.text

            start_index = script_text.find("TheBook-All")
            end_index = script_text.find("TheBook-RedactGroup")
            interesting_bits = script_text[start_index - 12:end_index]
            next_quote = 0
            text = ""
            while True:
                next_quote = interesting_bits.find('"', next_quote)
                following_quote = interesting_bits.find('"', next_quote + 1)
                if interesting_bits[next_quote:next_quote + 5] == '"div"':
                    text += "\n"
                elif interesting_bits[next_quote:next_quote + 6] == '"span"':
                    pass
                elif interesting_bits[next_quote - 10:next_quote] == 'className:':
                    pass
                else:
                    piece = interesting_bits[next_quote + 1:following_quote]
                    text += f"{piece}"
                next_quote += 1
                following = interesting_bits.find('"', next_quote) + 1
                if following < next_quote:
                    break
                next_quote = following

            new_text = text
        return new_text

    async def check_players_loop(self):
        while not self.bot.is_closed():
            await self.watch_players()

            interval = self.bot.config.setdefault('player_change_interval', 30)
            await self.save()
            await asyncio.sleep(interval)
            continue

    async def check_book_loop(self):
        while not self.bot.is_closed():
            print("checking for book changes")
            messages, filename = await self._check_for_rules_update()
            output_channel_id = self.bot.config['notify_channel']
            if output_channel_id:
                output_channel = self.bot.get_channel(output_channel_id)
                if output_channel:
                    for m in messages:
                        if m not in self.no_reply_messages:
                            await output_channel.send(m)
                        self.bot.logger.info(m)
                    if filename:
                        with open(os.path.join('diffs', filename), 'rb') as logfile:
                            await output_channel.send(file=discord.File(logfile, filename=filename))

            interval = self.bot.config['interval_minutes']
            await self.save()
            await asyncio.sleep(interval * 60)
            continue

    async def save(self):
        admin_cog = self.bot.cogs.get('AdminCommands')
        await admin_cog.save()


def setup(bot):
    bot.add_cog(RulesWatcher(bot))
