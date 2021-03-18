import asyncio
import json
import os

from watcher import utils


async def get_all_teams():
    teams_response = await utils.retry_request("https://www.blaseball.com/database/allTeams")
    if teams_response:
        teams_json = teams_response.json()
        if len(teams_json) > 0:
            return teams_json
    return None


async def update_team_cache(bot):
    teams = await get_all_teams()
    if not teams:
        return None
    for team in teams:
        bot.team_cache[team["id"]] = team
        bot.team_names[team["id"]] = team["nickname"]
    with open(os.path.join("data", "api_cache", "team_cache.json"), 'w', encoding='utf-8') as json_file:
        json.dump(bot.team_cache, json_file)
    with open(os.path.join("data", "api_cache", "team_names.json"), 'w', encoding='utf-8') as json_file:
        json.dump(bot.team_names, json_file)

    return True


async def check_teams_loop(bot):
    while True:
        success = await update_team_cache(bot)
        if success:
            # todo make this configurable, 30 minutes should be ok for now
            sleep = 60 * 30
            bot.logger.info("Successfully updated team cache")
            bot.team_cache_updated = True
        else:
            sleep = 60
            bot.logger.info("Failed to update team cache, trying again in 1 minute")
        await asyncio.sleep(sleep)
