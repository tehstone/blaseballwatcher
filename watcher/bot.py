import gspread_asyncio
import json
import os
import pickle
import re
import sys
import time

import requests
from google.oauth2.service_account import Credentials

from watcher.logs import init_loggers
from watcher.errors import custom_error_handling

import discord
from discord.ext import commands

default_exts = ['admincommands', 'betadvice', 'gamedata', 'helpcommand',
                'jsonwatcher', 'pendants', 'playerdata', 'playerstats', 'ruleswatcher', 'seasonsim',
                'snaxcog', 'teamlookups', 'winexp', 'wordreactor']


def _prefix_callable(bot, msg):
    user_id = bot.user.id
    base = [f'<@!{user_id}> ', f'<@{user_id}> ']
    if msg.guild is None:
        base.append('!')
    else:
        try:
            prefix = bot.guild_dict[msg.guild.id]['configure_dict']['settings']['prefix']
        except (KeyError, AttributeError):
            prefix = None
        if not prefix:
            prefix = bot.config['default_prefix']
        base.extend(prefix)
    return base


class WatcherBot(commands.AutoShardedBot):

    def __init__(self):
        super().__init__(command_prefix=_prefix_callable,
                         case_insensitive=True,
                         activity=discord.Game(name="Blaseball"))

        self.logger = init_loggers()
        custom_error_handling(self, self.logger)
        self.guild_dict = {'configure_dict': {}}
        self._load_data()
        self._load_config()
        self.db_path = 'data/watcher.db'
        self.success_react = '✅'
        self.failed_react = '❌'
        self.thumbsup_react = '👍'
        self.empty_str = '\u200b'
        self.initial_start = True
        self.watch_servers = [738107179294523402, 671866672562307091]
        self.off_topic_channels = [756667935728074754, 815745893315772426]
        self.SPREADSHEET_IDS = {}
        self.favor_rankings = self.config.setdefault('favor_rankings', {})
        self.daily_watch_message = self.config.setdefault('daily_watch_message', 'Go Bet!')
        self.check_for_games_complete = self.config.setdefault('check_for_games_complete', False)
        self.check_for_new_schedules = self.config.setdefault('check_for_new_schedules', False)
        self.current_day = 0
        self.tasks = []
        self.agcm = gspread_asyncio.AsyncioGspreadClientManager(self.get_creds)
        self.team_cache = {}
        self.player_cache = {}
        self.player_names = {}
        self.player_id_to_name = {}
        self.team_names = {}
        self.player_team_map = {}
        self.deceased_players = {}
        self.team_cache_updated = False
        self.divisions = None
        self.load_defaults()
        self.playoff_teams = []
        self.session = None

        for ext in default_exts:
            try:
                self.load_extension(f"watcher.exts.{ext}")
            except Exception as e:
                print(f'**Error when loading extension {ext}:**\n{type(e).__name__}: {e}')
            else:
                if 'debug' in sys.argv[1:]:
                    print(f'Loaded {ext} extension.')

    def load_defaults(self):
        # todo add a scheduled check to update this
        try:
            with open(os.path.join("data", "spreadsheet_ids.json")) as json_file:
                self.SPREADSHEET_IDS = json.load(json_file)
        except FileNotFoundError:
            pass
        try:
            with open(os.path.join("data", "divisions.json")) as json_file:
                self.divisions = json.load(json_file)
        except FileNotFoundError:
            pass
        try:
            with open(os.path.join("data", "api_cache", "team_cache.json"), encoding='utf-8') as json_file:
                self.team_cache = json.load(json_file)
        except FileNotFoundError:
            pass
        try:
            with open(os.path.join("data", "api_cache", "team_names.json"), encoding='utf-8') as json_file:
                self.team_names = json.load(json_file)
        except FileNotFoundError:
            pass
        try:
            with open(os.path.join("data", "api_cache", "player_cache.json"), encoding='utf-8') as json_file:
                self.player_cache = json.load(json_file)
        except FileNotFoundError:
            pass
        try:
            with open(os.path.join("data", "api_cache", "player_names.json"), encoding='utf-8') as json_file:
                self.player_names = json.load(json_file)
        except FileNotFoundError:
            pass
        try:
            with open(os.path.join("data", "api_cache", "player_id_to_name.json"), encoding='utf-8') as json_file:
                self.player_id_to_name = json.load(json_file)
        except FileNotFoundError:
            pass
        try:
            with open(os.path.join("data", "api_cache", "player_team_map.json"), encoding='utf-8') as json_file:
                self.player_team_map = json.load(json_file)
        except FileNotFoundError:
            pass
        try:
            with open(os.path.join("data", "api_cache", "deceased_players.json"), encoding='utf-8') as json_file:
                self.deceased_players = json.load(json_file)
        except FileNotFoundError:
            pass

    @staticmethod
    def get_creds():
        creds = Credentials.from_service_account_file(os.path.join("gspread", "service_account.json"))
        scoped = creds.with_scopes([
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ])
        return scoped

    async def authorize_agcm(self):
        return await self.agcm.authorize()

    class RenameUnpickler(pickle.Unpickler):
        def find_class(self, module, name):
            return super().find_class(module, name)

    def _load_data(self):
        try:
            with open(os.path.join('data', 'serverdict'), 'rb') as fd:
                self.guild_dict = self.RenameUnpickler(fd).load()
            self.logger.info('Serverdict Loaded Successfully')
        except OSError:
            self.logger.info('Serverdict Not Found - Looking for Backup')
            try:
                with open(os.path.join('data', 'serverdict_backup'), 'rb') as fd:
                    self.guild_dict = self.RenameUnpickler(fd).load()
                self.logger.info('Serverdict Backup Loaded Successfully')
            except OSError:
                self.logger.info('Serverdict Backup Not Found - Creating New Serverdict')
                self.guild_dict = {}
                with open(os.path.join('data', 'serverdict'), 'wb') as fd:
                    pickle.dump(self.guild_dict, fd, -1)
                self.logger.info('Serverdict Created')

    def _load_config(self):
        with open('config.json', 'r') as fd:
            self.config = json.load(fd)
        if 'current_season' not in self.config:
            self.config['current_season'] = 9
        if 'live_version' not in self.config:
            self.config['live_version'] = True
        if "cloudflare_id" not in self.config:
            self.config["cloudflare_id"] = "d35iw2jmbg6ut8"

    @staticmethod
    def _has_string(string, text):
        match = re.search(string, text)
        if match:
            return True
        else:
            return False

    async def on_message(self, message):
        if message.type == discord.MessageType.pins_add and message.author == self.user:
            return await message.delete()
        if message.guild:
            if message.guild.id in self.watch_servers:
                if self._has_string(r"\ba cop\b", message.clean_content.lower()):
                    await message.add_reaction("🚨")
                if message.channel.id in self.off_topic_channels \
                        and self._has_string(r"\bblaseball\b", message.clean_content.lower()):
                    await message.add_reaction("<:ballclark:766457844811431997>")
                if message.clean_content == "sip":
                    await message.channel.send("https://imgur.com/zAUU6FD")
                if message.clean_content == "spinny":
                    await message.channel.send("https://tenor.com/view/ikea-blahaj-doll-spinning-shark-gif-18118200")
                if message.clean_content == "facepalm":
                    await message.channel.send("https://cdn.discordapp.com/attachments/738835237655806033/826994031380529162/joelfacepalm.gif")
        debug_chan_id = self.config.setdefault('debug_channel', None)
        debug_channel = None
        if debug_chan_id:
            debug_channel = self.get_channel(debug_chan_id)
        if debug_channel and message.channel == debug_channel \
                and self.daily_watch_message in message.clean_content:
            bet_chan_id = self.config['bet_channel']
            current_season = self.config['current_season']
            pendant_cog = self.cogs.get('Pendants')
            latest_day = await pendant_cog.get_latest_pendant_data(current_season)
            await debug_channel.send(f"Pendant data updated.")
            self.logger.info(f"Pendant data updated.  {time.time()}")
            try:
                await pendant_cog.update_leaders_sheet(current_season, latest_day)
                self.logger.info(f"Leaders Sheet updated. {time.time()}")
            except Exception as e:
                self.logger.warning(f"Failed to update pendant leaders: {e}")

            gamedata_cog = self.cogs.get('GameData')
            await gamedata_cog.save_json_range(current_season-1)
            await gamedata_cog.update_spreadsheets([current_season-1])
            await debug_channel.send(f"Spreadsheets updated.")
            self.logger.info(f"Spreadsheets updated. {time.time()}")

            betadvice_cog = self.cogs.get('BetAdvice')
            try:
                upset_wins, upset_losses = await betadvice_cog.update_day_winners(current_season - 1, latest_day - 1)
                message, embed_fields, output = await betadvice_cog.daily_message(current_season - 1, latest_day)
                m_embed = discord.Embed(description=message)
                for field in embed_fields:
                    m_embed.add_field(name=field["name"], value=field["value"])
                await debug_channel.send(message, embed=m_embed)
                await debug_channel.send(output)
                if upset_wins + upset_losses > 0:
                    await debug_channel.send(f"Day {latest_day} upset record: {upset_wins}-{upset_losses}")
            except Exception as e:
                self.logger.warning(f"Failed to send pendant picks: {e}")

        elif not message.author.bot:
            await self.process_commands(message)

    @staticmethod
    async def send_to_webhook(message, url, embed_fields=None):
        data = {"content": message, "avatar_url": "https://i.imgur.com/q9OOb63.png"}
        if embed_fields:
            data["embeds"] = [{"fields": embed_fields}]
        result = requests.post(url, data=json.dumps(data), headers={"Content-Type": "application/json"})

        try:
            result.raise_for_status()
        except requests.exceptions.HTTPError as err:
            print(err)
        else:
            print("Payload delivered successfully, code {}.".format(result.status_code))

    async def process_commands(self, message):
        """Processes commands that are registered with the bot and it's groups.

        Without this being run in the main `on_message` event, commands will
        not be processed.
        """
        if message.author.bot:
            return
        if message.content.startswith('!'):
            if message.content[1] == " ":
                message.content = message.content[0] + message.content[2:]
            content_array = message.content.split(' ')
            content_array[0] = content_array[0].lower()

        ctx = await self.get_context(message)
        if not ctx.command:
            return
        await self.invoke(ctx)

    def get_guild_prefixes(self, guild, *, local_inject=_prefix_callable):
        proxy_msg = discord.Object(id=None)
        proxy_msg.guild = guild
        return local_inject(self, proxy_msg)

    async def on_member_join(self, member):
        pass

    async def on_member_remove(self, member):
        pass

    async def on_guild_join(self, guild):
        owner = guild.owner
        self.guild_dict[guild.id] = {
            'configure_dict': {},
        }
        await owner.send("Welcome.")

    async def on_guild_remove(self, guild):
        try:
            if guild.id in self.guild_dict:
                try:
                    del self.guild_dict[guild.id]
                except KeyError:
                    pass
        except KeyError:
            pass

    async def on_member_update(self, before, after):
        pass

    async def on_message_delete(self, message):
        pass

