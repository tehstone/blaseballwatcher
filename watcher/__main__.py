import asyncio
import datetime
import sys

import aiohttp
import discord

from watcher import utils
from watcher.bot import WatcherBot
from watcher.blaseball_data import teams
from watcher.blaseball_data import players
from watcher.exts.db import watcher_db

watcher_db.initialize('data/watcher.db')

Watcher = WatcherBot()
logger = Watcher.logger

guild_dict = Watcher.guild_dict
config = Watcher.config

event_loop = asyncio.get_event_loop()
Watcher.event_loop = event_loop


async def _print(owner, message):
    if 'launcher' in sys.argv[1:]:
        if 'debug' not in sys.argv[1:]:
            try:
                await owner.send(message)
            except:
                pass
    print(message)
    logger.info(message)


async def start_task_loops(bot):
    try:
        rules_watcher = bot.get_cog("RulesWatcher")
        bot.tasks.append(event_loop.create_task(rules_watcher.check_book_loop()))
        bot.tasks.append(event_loop.create_task(rules_watcher.check_players_loop()))

        json_watcher = bot.get_cog("JsonWatcher")
        bot.tasks.append(event_loop.create_task(json_watcher.check_loop()))

        if bot.check_for_games_complete:
            bot.tasks.append(event_loop.create_task(utils.game_check_loop(bot)))
        if bot.check_for_new_schedules:
            gamedata_cog = bot.get_cog('GameData')
            bot.tasks.append(event_loop.create_task(gamedata_cog.check_new_schedule_loop()))

        bot.tasks.append(event_loop.create_task(teams.check_teams_loop(bot)))
        bot.tasks.append(event_loop.create_task(players.check_players_loop(bot)))
        pendants_cog = bot.get_cog('Pendants')
        event_loop.create_task(pendants_cog.check_remaining_teams(bot))
        logger.info('Loops initiated')
    except KeyboardInterrupt:
        [task.cancel() for task in bot.tasks]


@Watcher.event
async def on_ready():
    if not Watcher.session:
        Watcher.session = aiohttp.ClientSession()
    Watcher.owner = Watcher.get_user(config['master'])
    if Watcher.initial_start:
        await _print(Watcher.owner, 'Starting up...')
    Watcher.uptime = datetime.datetime.now()
    owners = []
    guilds = len(Watcher.guilds)
    users = 0
    for guild in Watcher.guilds:
        users += guild.member_count
        try:
            if guild.id not in guild_dict:
                guild_dict[guild.id] = {'configure_dict': {}}
            else:
                guild_dict[guild.id].setdefault('configure_dict', {})
        except KeyError:
            guild_dict[guild.id] = {'configure_dict': {}}
        owners.append(guild.owner)
    if Watcher.initial_start:
        await _print(Watcher.owner, "{server_count} servers connected.\n{member_count} members found."
                     .format(server_count=guilds, member_count=users))
        Watcher.initial_start = False
        await start_task_loops(Watcher)
    else:
        logger.warning("bot failed to resume")


try:
    event_loop.run_until_complete(Watcher.start(config['bot_token']))
except discord.LoginFailure:
    logger.critical('Invalid token')
    event_loop.run_until_complete(Watcher.logout())
    Watcher._shutdown_mode = 0
except KeyboardInterrupt:
    logger.info('Keyboard interrupt detected. Quitting...')
    event_loop.run_until_complete(Watcher.logout())
    Watcher._shutdown_mode = 0
except Exception as e:
    logger.critical('Fatal exception', exc_info=e)
    event_loop.run_until_complete(Watcher.logout())
finally:
    pass
try:
    sys.exit(Watcher._shutdown_mode)
except AttributeError:
    sys.exit(0)

