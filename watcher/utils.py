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
