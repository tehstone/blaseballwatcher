import asyncio
import json
import os

from watcher import utils


async def get_players(player_ids):
    url = f"https://www.blaseball.com/database/players?ids={','.join(player_ids)}"
    players_response = await utils.retry_request(url)
    if players_response:
        players_json = players_response.json()
        if len(players_json) > 0:
            return players_json
    return None


async def get_deceased():
    players_response = await utils.retry_request("https://api.blaseball-reference.com/v1/deceased")
    if players_response:
        players_json = players_response.json()
        if len(players_json) > 0:
            return players_json
    return None


async def update_player_cache(bot):
    team_ids = bot.team_cache.keys()
    if len(team_ids) < 1:
        return None
    player_ids = []
    for tid in team_ids:
        team = bot.team_cache[tid]
        new_player_ids = team["lineup"] + team["rotation"] + team["bullpen"] + team["bench"]
        player_ids += new_player_ids
        for pid in new_player_ids:
            bot.player_team_map[pid] = tid
    chunked_player_ids = [player_ids[i:i + 50] for i in range(0, len(player_ids), 50)]
    for chunk in chunked_player_ids:
        players = await get_players(chunk)
        for player in players:
            bot.player_cache[player["name"]] = player
            bot.player_names[player["name"].lower()] = player["id"]
    deceased = await get_deceased()
    if not deceased:
        bot.logger.info("Failed to update deceased players cache.")
    else:
        for player in deceased:
            bot.deceased_players[player["player_id"]] = player
    with open(os.path.join("data", "api_cache", "player_cache.json"), 'w', encoding='utf-8') as json_file:
        json.dump(bot.player_cache, json_file)
    with open(os.path.join("data", "api_cache", "player_names.json"), 'w', encoding='utf-8') as json_file:
        json.dump(bot.player_names, json_file)
    with open(os.path.join("data", "api_cache", "player_team_map.json"), 'w', encoding='utf-8') as json_file:
        json.dump(bot.player_team_map, json_file)
    with open(os.path.join("data", "api_cache", "deceased_players.json"), 'w', encoding='utf-8') as json_file:
        json.dump(bot.deceased_players, json_file)
    return True


async def check_players_loop(bot):
    while True:
        if bot.team_cache_updated:
            success = await update_player_cache(bot)
            if success:
                # todo make this configurable, 30 minutes should be ok for now
                sleep = 60 * 30
                bot.logger.info("Successfully updated player cache")
            else:
                sleep = 60
                bot.logger.info("Failed to update player cache, trying again in 1 minute")
        else:
            sleep = 60
            bot.logger.info("Failed to update player cache, trying again in 1 minute")
        await asyncio.sleep(sleep)
