import json
import os
import pickle
import re
import sys

import requests

from watcher import utils
from watcher.logs import init_loggers
from watcher.errors import custom_error_handling

import discord
from discord.ext import commands

default_exts = ['admincommands', 'betadvice', 'gamedata', 'gamesim', 'helpcommand',
                'jsonwatcher', 'pendants', 'playerdata', 'ruleswatcher', 'snaxcog',
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
        self.off_topic_channels = [756667935728074754]
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
                                'seasontest': '1ojfPPpGp5aVDxF7egl-QM__NKIWLMXMKAgaR3kOpC_8'
                                #'seasontest': '1eS-8UdJEautAS1sbna-ViPn1efCTYpaXwaber5ckqHA'
                                }
        self.favor_rankings = self.config.setdefault('favor_rankings', {})
        self.team_names = {
                        "b72f3061-f573-40d7-832a-5ad475bd7909": "Lovers",
                        "878c1bf6-0d21-4659-bfee-916c8314d69c": "Tacos",
                        "b024e975-1c4a-4575-8936-a3754a08806a": "Steaks",
                        "adc5b394-8f76-416d-9ce9-813706877b84": "Breath Mints",
                        "ca3f1c8c-c025-4d8e-8eef-5be6accbeb16": "Firefighters",
                        "bfd38797-8404-4b38-8b82-341da28b1f83": "Shoe Thieves",
                        "3f8bbb15-61c0-4e3f-8e4a-907a5fb1565e": "Flowers",
                        "979aee4a-6d80-4863-bf1c-ee1a78e06024": "Fridays",
                        "7966eb04-efcc-499b-8f03-d13916330531": "Magic",
                        "36569151-a2fb-43c1-9df7-2df512424c82": "Millennials",
                        "8d87c468-699a-47a8-b40d-cfb73a5660ad": "Crabs",
                        "9debc64f-74b7-4ae1-a4d6-fce0144b6ea5": "Spies",
                        "23e4cbc1-e9cd-47fa-a35b-bfa06f726cb7": "Pies",
                        "f02aeae2-5e6a-4098-9842-02d2273f25c7": "Sunbeams",
                        "57ec08cc-0411-4643-b304-0e80dbc15ac7": "Wild Wings",
                        "747b8e4a-7e50-4638-a973-ea7950a3e739": "Tigers",
                        "eb67ae5e-c4bf-46ca-bbbc-425cd34182ff": "Moist Talkers",
                        "b63be8c2-576a-4d6e-8daf-814f8bcea96f": "Dale",
                        "105bc3ff-1320-4e37-8ef0-8d595cb95dd0": "Garages",
                        "a37f9158-7f82-46bc-908c-c9e2dda7c33b": "Jazz Hands",
                        "c73b705c-40ad-4633-a6ed-d357ee2e2bcf": "Lift",
                        "d9f89a8a-c563-493e-9d64-78e4f9a55d4a": "Georgias",
                        "bb4a9de5-c924-4923-a0cb-9d1445f1ee5d": "Worms",
                        "46358869-dce9-4a01-bfba-ac24fc56f57e": "Mechanics"
                        }
        self.daily_watch_message = self.config.setdefault('daily_watch_message', 'Go Bet!')
        self.check_for_games_complete = self.config.setdefault('check_for_games_complete', False)
        self.current_day = 0
        self.tasks = []

        for ext in default_exts:
            try:
                self.load_extension(f"watcher.exts.{ext}")
            except Exception as e:
                print(f'**Error when loading extension {ext}:**\n{type(e).__name__}: {e}')
            else:
                if 'debug' in sys.argv[1:]:
                    print(f'Loaded {ext} extension.')

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
                    await message.add_reaction("❌")
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
            if debug_channel:
                await debug_channel.send("Pendant data updated.")
            try:
                await pendant_cog.update_leaders_sheet(current_season, latest_day)
            except Exception as e:
                self.logger.warning(f"Failed to update pendant leaders: {e}")

            await utils.update_cumulative_statsheets(self.config['current_season'])

            betadvice_cog = self.cogs.get('BetAdvice')
            try:
                message, embed_fields = await betadvice_cog.daily_message()
                m_embed = discord.Embed(description=message)
                for field in embed_fields:
                    m_embed.add_field(name=field["name"], value=field["value"])
                if bet_chan_id:
                    output_channel = self.get_channel(bet_chan_id)
                    bet_msg = await output_channel.send(message, embed=m_embed)
                    publish = self.config.setdefault('publish_rec_message', False)
                    if publish:
                        await bet_msg.publish()
            except Exception as e:
                self.logger.warning(f"Failed to send pendant picks: {e}")

            gamedata_cog = self.cogs.get('GameData')
            await gamedata_cog.save_json_range(current_season-1)
            await gamedata_cog.update_spreadsheets([current_season-1])
            if debug_channel:
                await debug_channel.send("Spreadsheets updated.")

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

