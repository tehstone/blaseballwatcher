import asyncio
import re

import discord


# Convert an arbitrary string into something which
# is acceptable as a Discord channel name.
import requests
from requests import Timeout


def sanitize_name(name):
    # Remove all characters other than alphanumerics,
    # dashes, underscores, and spaces
    ret = re.sub('[^a-zA-Z0-9 _\\-]', '', name)
    # Replace spaces with dashes
    ret = ret.replace(' ', '-')
    return ret


async def get_channel_by_name_or_id(ctx, name):
    channel = None
    # If a channel mention is passed, it won't be recognized as an int but this get will succeed
    name = sanitize_name(name)
    try:
        channel = discord.utils.get(ctx.guild.text_channels, id=int(name))
    except ValueError:
        pass
    if not channel:
        channel = discord.utils.get(ctx.guild.text_channels, name=name)
    if channel:
        guild_channel_list = []
        for textchannel in ctx.guild.text_channels:
            guild_channel_list.append(textchannel.id)
        diff = {channel.id} - set(guild_channel_list)
    else:
        diff = True
    if diff:
        return None
    return channel


async def retry_request(url, tries=10):
    headers = {
        'User-Agent': 'sibrDataWatcher/0.5test (tehstone#8448@sibr)'
    }

    for i in range(tries):
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                return response
        except (Timeout, Exception):
            continue
        finally:
            await asyncio.sleep(.5)
    return None


async def game_check_loop(bot):
    while not bot.is_closed():
        bot.logger.info("Checking for games complete")
        failed = False
        url = 'https://www.blaseball.com/database/simulationdata'
        html_response = await retry_request(url)
        if not html_response:
            failed = True
            continue
        resp_json = html_response.json()
        season = resp_json["season"]
        day = resp_json["day"]
        games = await retry_request(f"https://www.blaseball.com/database/games?day={day}&season={season}")
        complete = True
        for game in games.json():
            if not game["gameComplete"]:
                complete = False
                break
        if complete and failed == False:
            interval = 45
            debug_channel = bot.get_channel(bot.config['debug_channel'])
            await debug_channel.send("Internal Bet Reminder")
        else:
            interval = 1
        await asyncio.sleep(interval * 60)
