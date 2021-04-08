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

default_exts = ['admincommands', 'betadvice', 'gamedata', 'gamesim', 'helpcommand',
                'jsonwatcher', 'pendants', 'playerdata', 'playerstats', 'ruleswatcher', 'snaxcog',
                'teamlookups', 'winexp', 'wordreactor']


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
        self.SPREADSHEET_IDS = {'season1': '1yvGP3DwIHC7NOsPIlSCMYKbrZp6Luvir2vRMvVfe4rg',
                                'season2': '1LT2lE31Azx7iyT-KgHXrknUIXUVjr_WJ5iH7eYIWDmU',
                                'season3': '1tGDP50yFYbYYrptcUB-735D75ZOTDxHHV-XC32wUFdc',
                                'season4': '12Ue_hLxbnIefyw_JPrBsYq2cusMMq0ay9MqOJ8WCwvE',
                                'season5': '1TUEM2RFYcZoNTukX205zwAxOyASmzaAenaBZGCBBKk8',
                                'season6': '1-A9ioMPiG6SvuGG2BfZoB1W_mR44YoQVc_hUUIjorQA',
                                'season7': '12OtIj2TOF7XuOCLl7fjy5Ho5A_yy0G95XpLE1euwgcc',
                                'season8': '1Kl82vIqlNJByLnxlD241cSwokBUPCsCSAGsHZvDglV4',
                                'season9': '112PR3GNXqGqOdhE-vnkeX0H-_LOycneHCw9RVgmoj3o',
                                'season10': '1PM-0Ph2qk0bF8oo2Ir5mb6YsLH_6f451BtoejcYQbio',
                                'season11': '1XwpooTCzeiLYuV7UlreLEXBvBIBISrLtOUbw1221Xw0',
                                'season12': '1eqjTTUnKokuQyvxQtUkYATXPO8updy8iMNE8yRXIT84',
                                'season13': '15H7A6oug4vTKOtKRaDXQpxS9NzNyCbkYcOWiCt9gi5o',
                                'season14': '1ACuJjarKCpoZtxZM9ogsrrYsD7T0GKoWzOI2xcdKGlk',
                                'season15': '1QZ6EhLSCa6C7HqUsIp71V-D97ithsOHqV1bcjSEOTsU',
                                'seasontest': '1ojfPPpGp5aVDxF7egl-QM__NKIWLMXMKAgaR3kOpC_8'
                                #'seasontest': '1eS-8UdJEautAS1sbna-ViPn1efCTYpaXwaber5ckqHA'
                                }
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
        self.team_names = {}
        self.player_team_map = {}
        self.deceased_players = {}
        self.team_cache_updated = False
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
            result = await pendant_cog.check_remaining_teams(self)
            if result == False:
                self.logger.info("Failed to update current post season teams.")
            self.logger.info(f"Pendant data updated.  {time.time()}")
            try:
                await pendant_cog.update_leaders_sheet(current_season, latest_day, result)
                self.logger.info(f"Leaders Sheet updated. {time.time()}")
            except Exception as e:
                self.logger.warning(f"Failed to update pendant leaders: {e}")

            betadvice_cog = self.cogs.get('BetAdvice')
            try:
                await betadvice_cog.update_day_winners(current_season - 1, latest_day - 1)
                self.logger.info(f"Starting daily sim. {time.time()}")
                message, embed_fields, output = await betadvice_cog.daily_message(current_season-1, latest_day)
                m_embed = discord.Embed(description=message)
                for field in embed_fields:
                    m_embed.add_field(name=field["name"], value=field["value"])
                if bet_chan_id:
                    output_channel = self.get_channel(bet_chan_id)
                    bet_msg = await output_channel.send(message, embed=m_embed)
                    publish = self.config.setdefault('publish_rec_message', False)
                    if publish:
                        await bet_msg.publish()
                try:
                    game_sim_output_chan_id = self.config['game_sim_output_chan_id']
                    output_channel = self.get_channel(game_sim_output_chan_id)
                    await output_channel.send(output)
                except:
                    pass
                self.logger.info(f"Daily sim complete. {time.time()}")
            except Exception as e:
                self.logger.warning(f"Failed to send pendant picks: {e}")

            gamedata_cog = self.cogs.get('GameData')
            await gamedata_cog.save_json_range(current_season-1)
            await gamedata_cog.update_spreadsheets([current_season-1])
            await debug_channel.send(f"Spreadsheets updated.")
            self.logger.info(f"Spreadsheets updated. {time.time()}")

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

