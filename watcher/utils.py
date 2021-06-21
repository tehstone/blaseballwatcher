import asyncio
import json
import os
import random
import re

import discord

import requests
from requests import Timeout


# Convert an arbitrary string into something which
# is acceptable as a Discord channel name.
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


async def send_message_in_chunks(message_parts, channel):
    current_msg = ""
    for part in message_parts:
        if len(current_msg) + len(part) > 1999:
            await channel.send(current_msg)
            current_msg = ""
        current_msg += part
    if len(current_msg) > 0:
        await channel.send(current_msg)

async def retry_request(session, url, tries=10, timeout=10):
    headers = {
        'User-Agent': 'sibrDataWatcher/0.5test (tehstone#8448@sibr)'
    }

    for i in range(tries):
        try:
            async with session.get(url=url, timeout=timeout, headers=headers) as response:
                await response.json()
            if response.status == 200:
                return response
        except (Timeout, Exception):
            await asyncio.sleep(.5)
    return None


async def game_check_loop(bot):
    while not bot.is_closed():
        bot.logger.info("Checking for games complete")
        failed = False
        url = 'https://www.blaseball.com/database/simulationdata'
        html_response = await retry_request(bot.session, url)
        if not html_response:
            failed = True
            continue
        resp_json = html_response.json()
        season = resp_json["season"]
        day = resp_json["day"]
        bot.current_day = day
        games = await retry_request(bot.session, f"https://www.blaseball.com/database/games?day={day}&season={season}")
        complete = True
        for game in games.json():
            if not game["gameComplete"]:
                complete = False
                break
        if complete and failed == False:
            interval = 35
            debug_channel = bot.get_channel(bot.config['debug_channel'])
            await debug_channel.send(bot.daily_watch_message)
        else:
            interval = 2
        await asyncio.sleep(interval * 60)


def get_a_clark():
    clarks = ["<:ballclark:786049152969867341>",
              "<:coolark:822271813026840597>",
              "<:blushclark:822271813102731285>",
              "<:happyclark:822271813643927563>",
              "<:incinclark:822271814083280918>",
              "<:mehclark:822271814100582452>",
              "<:ohokclark:822271814289457153>",
              "<:happyincinclark:822271814381993994>",
              "<:skepticlark:822271814511493130>",
              "<:laptopclark:822271814653706260>",
              "<a:rubclark:822271814482001941>",
              "<a:patpatcatcatclark:822271814033866772>"]
    return random.choice(clarks)


async def update_cumulative_statsheets(season):
    data = {"pitchers": {}, "hitters": {}}
    last_day = 0
    for day in range(98):
        try:
            filename = os.path.join('data', 'pendant_data', 'statsheets', f'{season-1}_{day}player_statsheets.json')
            with open(filename, 'r') as file:
                player_stats = json.load(file)
            last_day = day
        except FileNotFoundError:
            break
        for player in player_stats:
            for k, p_values in player.items():
                if p_values["position"] == "rotation":
                    if p_values["playerId"] not in data["pitchers"]:
                        data["pitchers"][p_values["playerId"]] = {
                            "earnedRuns": 0,
                            "hitsAllowed": 0,
                            "losses": 0,
                            "outsRecorded": 0,
                            "strikeouts": 0,
                            "walksIssued": 0,
                            "wins": 0,
                            "hitBatters": 0,
                            "pitchesThrown": 0,
                            "shutout": 0
                        }
                    for key in ["earnedRuns", "hitsAllowed", "losses", "outsRecorded", "strikeouts",
                                "walksIssued", "wins", "hitBatters", "pitchesThrown", "shutout"]:
                        data["pitchers"][p_values["playerId"]][key] += p_values[key]
                    data["pitchers"][p_values["playerId"]]["name"] = p_values["name"]
                    data["pitchers"][p_values["playerId"]]["team"] = p_values["team"]
                    data["pitchers"][p_values["playerId"]]["teamId"] = p_values["teamId"]
                else:
                    if p_values["playerId"] not in data["hitters"]:
                        data["hitters"][p_values["playerId"]] = {
                            "atBats": 0,
                            "plateAppearances": 0,
                            "caughtStealing": 0,
                            "doubles": 0,
                            "groundIntoDp": 0,
                            "hits": 0,
                            "homeRuns": 0,
                            "rbis": 0,
                            "runs": 0,
                            "stolenBases": 0,
                            "struckouts": 0,
                            "triples": 0,
                            "walks": 0,
                            "hitByPitch": 0,
                            "quadruples": 0
                        }
                    plate_appearances = p_values["atBats"] + p_values["walks"] + p_values["hitByPitch"]
                    for key in ["atBats", "caughtStealing", "doubles", "groundIntoDp", "hits",
                                "homeRuns", "rbis", "runs", "stolenBases", "struckouts",
                                "triples", "walks", "hitByPitch", "quadruples"]:
                        data["hitters"][p_values["playerId"]][key] += p_values[key]
                    data["hitters"][p_values["playerId"]]["name"] = p_values["name"]
                    data["hitters"][p_values["playerId"]]["team"] = p_values["team"]
                    data["hitters"][p_values["playerId"]]["teamId"] = p_values["teamId"]
                    data["hitters"][p_values["playerId"]]["plateAppearances"] += plate_appearances

    with open(os.path.join('data', 'pendant_data', 'statsheets', f's{season-1}_player_stats_upto_d{last_day}.json'), 'w') as file:
        json.dump(data, file)
    with open(os.path.join('data', 'pendant_data', 'statsheets', f's{season-1}_current_player_stats.json'), 'w') as file:
        json.dump(data, file)
