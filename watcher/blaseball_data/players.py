import asyncio
import json
import os

import aiosqlite

from watcher import utils


async def get_players(player_ids):
    url = f"https://www.blaseball.com/database/players?ids={','.join(player_ids)}"
    players_response = await utils.retry_request(url)
    if players_response:
        players_json = players_response.json()
        if len(players_json) > 0:
            return players_json
    return None

def get_team_league_division_map(bot):
    team_map = {}
    for div in bot.divisions:
        for team in div["teams"]:
            team_map[team] = {"league": div["league"], "division": div["name"]}
    return team_map


async def get_deceased():
    players_response = await utils.retry_request("https://api.blaseball-reference.com/v1/deceased")
    if players_response:
        players_json = players_response.json()
        if len(players_json) > 0:
            return players_json
    return None


async def update_player_cache(bot):
    try:
        player_rows = []
        player_ids = []
        player_positions = {}
        player_slots = {}
        team_map = get_team_league_division_map(bot)
        for tid in team_map.keys():
            team = bot.team_cache[tid]
            new_player_ids = team["lineup"] + team["rotation"] + team["shadows"]
            for position in ["lineup", "rotation", "shadows"]:
                slot = 1
                for player in team[position]:
                    player_positions[player] = position
                    player_slots[player] = slot
                    slot += 1
            player_ids += new_player_ids
            for pid in new_player_ids:
                bot.player_team_map[pid] = tid
        chunked_player_ids = [player_ids[i:i + 50] for i in range(0, len(player_ids), 50)]
        for chunk in chunked_player_ids:
            players = await get_players(chunk)
            for player in players:
                stars = 0
                for rating in ["baserunningRating", "pitchingRating", "hittingRating", "defenseRating"]:
                    stars += player[rating]
                combined_stars = stars * 5
                player['slot'] = player_slots[player["id"]]
                player['elsewhere'], player['shelled'], player['legendary'] = False, False, False
                if "permAttr" in player:
                    if "ELSEWHERE" in player["permAttr"]:
                        player['elsewhere'] = True
                    if "SHELLED" in player["permAttr"]:
                        player['shelled'] = True
                    if "LEGENDARY" in player["permAttr"]:
                        player['legendary'] = True
                bot.player_cache[player["name"]] = player
                bot.player_names[player["name"].lower()] = player["id"]
                bot.player_id_to_name[player["id"]] = player["name"]
                if player_positions[player["id"]] in ["lineup", "rotation"]:
                    if player["leagueTeamId"] in team_map:
                        league = team_map[player["leagueTeamId"]]["league"]
                        division = team_map[player["leagueTeamId"]]["division"]
                        team_id = player["leagueTeamId"]
                        team_name = bot.team_cache[team_id]["nickname"]
                        position = player_positions[player["id"]]

                        player_rows.append([player["id"], player["name"], combined_stars, player["baserunningRating"],
                                            player["pitchingRating"], player["hittingRating"], player["defenseRating"],
                                            team_id, team_name, league, division, position, player['slot'],
                                            player['elsewhere'], player['shelled'], player['legendary']])
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
        with open(os.path.join("data", "api_cache", "player_id_to_name.json"), 'w', encoding='utf-8') as json_file:
            json.dump(bot.player_id_to_name, json_file)

        async with aiosqlite.connect(bot.db_path) as db:
            await db.execute("DELETE FROM PlayerLeagueAndStars;")
            await db.executemany("insert into PlayerLeagueAndStars (player_id, player_name, combined_stars, "
                                 "baserunning_rating, pitching_rating, hitting_rating, defense_rating, "
                                 "team_id, team_name, league, division, position, slot, elsewhere, shelled, legendary) "
                                 "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);", player_rows)
            await db.commit()
        return True
    except Exception as e:
        bot.logger.warn(f"Failed to update player cache with error: \n{e}")


async def check_players_loop(bot):
    while True:
        await update_player_cache(bot)
        # todo make this configurable, 30 minutes should be ok for now
        sleep = 60 * 30
        bot.logger.info("Successfully updated player cache")
        await asyncio.sleep(sleep)
