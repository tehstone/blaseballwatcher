import asyncio
import itertools
import json
import os

import aiosqlite
import discord
import requests
from discord.ext import commands
from requests import Timeout

from watcher import utils
from watcher.exts.db.watcher_db import PlayerStatSheetsInstance, CycleInstance

PM_ID = "de21c97e-f575-43b7-8be7-ecc5d8c4eaff"
WHEERER_ID = "0bb35615-63f2-4492-80ec-b6b322dc5450"
MOVING_PLAYER_IDS = [
    "97dfc1f6-ac94-4cdc-b0d5-1cb9f8984aa5",
    "1ffb1153-909d-44c7-9df1-6ed3a9a45bbd",
    "d0d7b8fe-bad8-481f-978e-cb659304ed49",
    "f9930cb1-7ed2-4b9a-bf4f-7e35f2586d71",
    "e6502bc7-5b76-4939-9fb8-132057390b30",
    "a691f2ba-9b69-41f8-892c-1acd42c336e4",
    "d8742d68-8fce-4d52-9a49-f4e33bd2a6fc",
    "9ba361a1-16d5-4f30-b590-fc4fc2fb53d2"
]


class Pendants(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_short_map(self):
        with open(os.path.join('data', 'allTeams.json'), 'r', encoding='utf-8') as file:
            all_teams = json.load(file)
        team_short_map = {}
        for team in all_teams:
            team_short_map[team["id"]] = team["shorthand"]
        return team_short_map

    @staticmethod
    async def retry_request(url, tries=10):
        for i in range(tries):
            try:
                response = requests.get(url)
                if response.status_code == 200:
                    return response
            except (Timeout, Exception):
                continue
            finally:
                await asyncio.sleep(.75)
        return None

    async def get_daily_stats(self, day, season):
        # if daily stats sheet file exists, read from that into db
        # if not, then make all the requests to get the player stat sheet ids
        # separate actual scanning of playerstatsheets into a separate method that
        # can be called regardless of previous thing
        filename = f"{season}_{day}player_statsheets.json"
        day_sheet_exists = False
        try:
            with open(os.path.join('data', 'pendant_data', 'statsheets', 'pitching_rotations.json'), 'r') as file:
                pitching_rotations = json.load(file)
        except FileNotFoundError:
            pitching_rotations = {}
        try:
            with open(os.path.join('data', 'pendant_data', 'statsheets', 'team_stats.json'), 'r') as file:
                team_stats = json.load(file)
        except FileNotFoundError:
            team_stats = {}
        try:
            with open(os.path.join('data', 'pendant_data', 'statsheets', 'daily', filename), 'r') as file:
                statsheets = json.load(file)
            with open(os.path.join('data', 'pendant_data', 'statsheets',
                                   'game_team_maps', f's{season}_d{day}_game_team_map.json'), 'r') as file:
                game_team_map = json.load(file)
            day_sheet_exists = True
        except FileNotFoundError:
            statsheets = {}
            games = await self.retry_request(f"https://www.blaseball.com/database/games?day={day}&season={season}")
            if not games:
                return True
            for game in games.json():
                if not game["gameComplete"]:
                    return True
            game_team_map = {}
            for game in games.json():
                game_team_map[game['homeTeam']] = {"game_id": game["id"], "opponent": game['awayTeam']}
                game_team_map[game['awayTeam']] = {"game_id": game["id"], "opponent": game['homeTeam']}
            with open(os.path.join('data', 'pendant_data', 'statsheets', 'game_team_maps',
                                   f's{season}_d{day}_game_team_map.json'), 'w') as file:
                json.dump(game_team_map, file)
            game_statsheet_ids = [game["statsheet"] for game in games.json()]
            game_statsheets = await self.retry_request(
                f"https://www.blaseball.com/database/gameStatsheets?ids={','.join(game_statsheet_ids)}")
            if not game_statsheets:
                return True
            team_statsheet_ids = [game["awayTeamStats"] for game in game_statsheets.json()]
            team_statsheet_ids += [game["homeTeamStats"] for game in game_statsheets.json()]
            team_statsheets = await self.retry_request(
                f"https://www.blaseball.com/database/teamStatsheets?ids={','.join(team_statsheet_ids)}")
            player_statsheet_ids = [team["playerStats"] for team in team_statsheets.json()]
            flat_playerstatsheet_ids = list(itertools.chain.from_iterable(player_statsheet_ids))
            print(f"day {day} player count: {len(flat_playerstatsheet_ids)}")
            chunked_player_ids = [flat_playerstatsheet_ids[i:i + 50] for i in range(0, len(flat_playerstatsheet_ids), 50)]
            for chunk in chunked_player_ids:
                statsheet_chunk = await self.get_player_statsheets(chunk)
                for statsheet in statsheet_chunk:
                    statsheets[statsheet["id"]] = statsheet

        await self.amend_player_statsheets(statsheets, season, day, game_team_map,
                                           pitching_rotations, team_stats)

        if not day_sheet_exists:
            with open(os.path.join('data', 'pendant_data', 'statsheets', 'daily', filename), 'w') as file:
                json.dump(statsheets, file)
        with open(os.path.join('data', 'pendant_data', 'statsheets', 'pitching_rotations.json'), 'w') as file:
            json.dump(pitching_rotations, file)
        with open(os.path.join('data', 'pendant_data', 'statsheets', 'team_stats.json'), 'w') as file:
            json.dump(team_stats, file)
        return False

    async def get_player_statsheets(self, player_ids):
        player_statsheets = await self.retry_request(
            f"https://www.blaseball.com/database/playerStatsheets?ids={','.join(player_ids)}")
        return player_statsheets.json()

    async def amend_player_statsheets(self, players_statsheets, season, day, game_team_map,
                                      pitching_rotations, team_stats):
        statsheets = {}
        pitcher_p_values = {}
        pitcher_hr_counts = {}
        pitcher_team_map = {}
        for pid, p_values in players_statsheets.items():
            save = True
            p_values["rotation_changed"] = False
            opp_id = game_team_map[p_values["teamId"]]["opponent"]
            if p_values['outsRecorded'] > 0:
                pitcher_hr_counts[p_values["teamId"]] = 0
                pitcher_team_map[p_values["teamId"]] = p_values["id"]
            if p_values["outsRecorded"] >= 24 and p_values["earnedRuns"] <= 0:
                if opp_id not in team_stats:
                    team_stats[opp_id] = {"shutout": 0, "at_bats": 0, "plate_appearances": 0,
                                          "struckouts": 0, "name": self.bot.team_names[opp_id],
                                          "lineup_pa": {}}
                team_stats[opp_id]["shutout"] += 1
                if p_values['hitsAllowed'] == 0:
                    if p_values['walksIssued'] == 0:
                        p_values['perfectGame'] = 1
                        # notable["perfect"][p_values["playerId"]] = {
                        #     "name": p_values["name"],
                        #     "strikeouts": p_values["strikeouts"],
                        #     "outsRecorded": p_values["outsRecorded"],
                        #     "game_id": game_team_map[p_values["teamId"]]["game_id"],
                        #     "statsheet_id": p_values["id"]
                        # }
                    else:
                        p_values['noHitter'] = 1
                        # notable["nohitter"][p_values["playerId"]] = {
                        #     "name": p_values["name"],
                        #     "strikeouts": p_values["strikeouts"],
                        #     "outsRecorded": p_values["outsRecorded"],
                        #     "walksIssued": p_values['walksIssued'],
                        #     "game_id": game_team_map[p_values["teamId"]]["game_id"],
                        #     "statsheet_id": p_values["id"]
                        # }
                else:
                    p_values["shutout"] = 1
                    # notable["shutout"][p_values["playerId"]] = {
                    #     "name": p_values["name"],
                    #     "strikeouts": p_values["strikeouts"],
                    #     "outsRecorded": p_values["outsRecorded"],
                    #     "walksIssued": p_values['walksIssued'],
                    #     "hitsAllowed": p_values['hitsAllowed'],
                    #     "game_id": game_team_map[p_values["teamId"]]["game_id"],
                    #     "statsheet_id": p_values["id"]
                    # }
            if p_values["outsRecorded"] > 0:
                p_values["position"] = "rotation"
                rot = (day + 1) % 5
                if rot == 0:
                    rot = 5
                p_values["rotation"] = rot
                if p_values["playerId"] in pitching_rotations:
                    if pitching_rotations[p_values["playerId"]] != rot:
                        p_values["rotation_changed"] = True
                    pitching_rotations[p_values["playerId"]] = rot
                else:
                    pitching_rotations[p_values["playerId"]] = rot
                if "shutout" not in p_values:
                    p_values["shutout"] = 0
                if p_values["playerId"] in pitcher_p_values:
                    if "pitchesThrown" in pitcher_p_values[p_values["playerId"]]:
                        p_values["pitchesThrown"] += pitcher_p_values[p_values["playerId"]]["pitchesThrown"]
                else:
                    pitcher_p_values[p_values["playerId"]] = {"statsheetId": p_values["id"]}
            else:
                if p_values["pitchesThrown"] > 0:
                    save = False
                    if p_values["playerId"] in pitcher_p_values:
                        if "statsheetId" in pitcher_p_values[p_values["playerId"]]:
                            statsheet_id = pitcher_p_values[p_values["playerId"]]["statsheetId"]
                            statsheets[statsheet_id]["pitchesThrown"] += p_values["pitchesThrown"]
                        else:
                            pitcher_p_values[p_values["playerId"]]["pitchesThrown"] += p_values["pitchesThrown"]
                    else:
                        pitcher_p_values[p_values["playerId"]] = {"pitchesThrown": p_values["pitchesThrown"]}
                p_values["position"] = "lineup"
                team_id = p_values["teamId"]
                if team_id not in team_stats:
                    team_stats[team_id] = {"shutout": 0, "at_bats": 0, "plate_appearances": 0,
                                           "struckouts": 0, "name": self.bot.team_names[team_id],
                                           "lineup_pa": {}}
                team_stats[team_id]["at_bats"] += p_values["atBats"]
                if "plate_appearances" not in team_stats[team_id]:
                    team_stats[team_id]["plate_appearances"] = 0
                plate_appearances = p_values["atBats"] + p_values["walks"] + p_values["hitByPitch"]
                team_stats[team_id]["plate_appearances"] += plate_appearances
                if "struckouts" in p_values:
                    team_stats[team_id]["struckouts"] += p_values["struckouts"]
                if "lineup_pa" not in team_stats[team_id]:
                    team_stats[team_id]["lineup_pa"] = {}
                if p_values["playerId"] not in team_stats[team_id]["lineup_pa"]:
                    team_stats[team_id]["lineup_pa"][p_values["playerId"]] = 0
                team_stats[team_id]["lineup_pa"][p_values["playerId"]] += plate_appearances
                if opp_id not in pitcher_hr_counts:
                    pitcher_hr_counts[opp_id] = 0
                pitcher_hr_counts[opp_id] += p_values["homeRuns"]

            if "rotation" not in p_values:
                p_values["rotation"] = -1
            for notable in ["shutout", "noHitter", "perfectGame"]:
                if notable not in p_values:
                    p_values[notable] = 0
            p_values["gameId"] = game_team_map[p_values["teamId"]]["game_id"]
            p_values["homeRunsAllowed"] = 0
            if save:
                statsheets[p_values["id"]] = p_values

        for team_id, hr_count in pitcher_hr_counts.items():
            stats_id = pitcher_team_map[team_id]
            if stats_id in statsheets:
                statsheets[stats_id]["homeRunsAllowed"] = hr_count
        rows = []
        for p_values in statsheets.values():
            rows.append((p_values["id"], season, day, p_values["playerId"], p_values["teamId"],
                         p_values["gameId"], p_values["team"], p_values["name"], p_values["atBats"],
                         p_values["caughtStealing"], p_values["doubles"], p_values["earnedRuns"],
                         p_values["groundIntoDp"], p_values["hits"], p_values["hitsAllowed"],
                         p_values["homeRuns"], p_values["losses"], p_values["outsRecorded"],
                         p_values["rbis"], p_values["runs"], p_values["stolenBases"],
                         p_values["strikeouts"], p_values["struckouts"], p_values["triples"],
                         p_values["walks"], p_values["walksIssued"], p_values["wins"],
                         p_values["hitByPitch"], p_values["hitBatters"], p_values["quadruples"],
                         p_values["pitchesThrown"], p_values["rotation_changed"], p_values["position"],
                         p_values["rotation"], p_values["shutout"], p_values["noHitter"],
                         p_values["perfectGame"], p_values["homeRunsAllowed"]))

        async with aiosqlite.connect(self.bot.db_path) as db:
            await db.executemany("insert into DailyStatSheets values "
                                 "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                                 "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);", rows)
            await db.commit()

    @staticmethod
    def print_top(player_dict, key, string, cutoff=2, limit=7, avg=False):
        message = ""
        count = 0
        for pkey, pvalue in player_dict.items():
            attr_value = pvalue.__getattribute__(key)
            if key == 'strikeouts':
                if count > limit:
                    break
                avg_str = ""
                if avg:
                    k_9_value = round((attr_value / (pvalue.outsRecorded / 27)) * 10) / 10
                    avg_str = f"({k_9_value} {key}/9)"
                message += f"{pvalue.name} {attr_value} {string} {avg_str}\n"
            else:
                if attr_value >= cutoff:
                    message += f"{pvalue.name} {attr_value} {string}\n"
            count += 1
        return message

    async def get_latest_pendant_data(self, current_season: int):
        current_season -= 1
        output_channel = None
        stats_chan_id = self.bot.config['stats_channel']
        if stats_chan_id:
            output_channel = self.bot.get_channel(stats_chan_id)

        day, last_day = 0, 0
        async with aiosqlite.connect(self.bot.db_path) as db:
            async with db.execute("select max(day) from DailyStatSheets where season=?;", [current_season]) as cursor:
                async for row in cursor:
                    if row and row[0]:
                        day = last_day = row[0] + 1

        while True:
            end_loop = await self.get_daily_stats(day, current_season)
            if end_loop:
                break
            day += 1

        while last_day < day:
            players = {}
            async with aiosqlite.connect(self.bot.db_path) as db:
                async with db.execute("select id, season, day, playerId, teamId, gameId, team, name, atBats, "
                                      "caughtStealing, doubles, earnedRuns, groundIntoDp, hits, hitsAllowed, "
                                      "homeRuns, losses, outsRecorded, rbis, runs, stolenBases, "
                                      "strikeouts, struckouts, triples, walks, walksIssued, wins, "
                                      "hitByPitch, hitBatters, quadruples, pitchesThrown, "
                                      "rotation_changed, position, rotation, shutout, noHitter, perfectGame, "
                                      "homeRunsAllowed from DailyStatSheets "
                                      "where season=? and day=?;", (current_season, last_day)) as cursor:
                    async for row in cursor:
                        players[row[0]] = PlayerStatSheetsInstance(*row)
            daily_message = [f"**Daily leaders for Day {last_day}**\n"]
            daily_message_two = ""
            sorted_hits = {k: v for k, v in sorted(players.items(), key=lambda item: item[1].hits, reverse=True)}
            sorted_homeruns = {k: v for k, v in
                               sorted(players.items(), key=lambda item: item[1].homeRuns, reverse=True)}
            sorted_rbis = {k: v for k, v in sorted(players.items(), key=lambda item: item[1].rbis, reverse=True)}
            sorted_stolenbases = {k: v for k, v in
                                  sorted(players.items(), key=lambda item: item[1].stolenBases, reverse=True)}

            hit_message = self.print_top(sorted_hits, 'hits', 'hits', 4)
            if len(hit_message) > 0:
                daily_message.append(f"\n**Hits**\n{hit_message}")

            hr_message = self.print_top(sorted_homeruns, 'homeRuns', 'home runs', 2)
            if len(hr_message) > 0:
                daily_message.append(f"\n**Home Runs**\n{hr_message}")

            rbi_message = self.print_top(sorted_rbis, 'rbis', 'RBIs', 4)
            if len(rbi_message) > 0:
                daily_message.append(f"\n**RBIs**\n{rbi_message}")

            sb_message = self.print_top(sorted_stolenbases, 'stolenBases', 'stolen bases', 2)
            if len(sb_message) > 0:
                daily_message.append(f"\n**Stolen Bases**\n{sb_message}")

            sorted_strikeouts = {k: v for k, v in
                                 sorted(players.items(), key=lambda item: item[1].strikeouts,
                                        reverse=True)}
            daily_message_two += f"{self.bot.empty_str}\n**Strikeouts**\n" \
                                 f"{self.print_top(sorted_strikeouts, 'strikeouts', 'strikeouts', 9, 8, True)}"

            game_watcher_messages = []
            sh_embed = discord.Embed(title="**Shutout!**")
            sh_description = ""
            notable_events = await self._query_notable_events(current_season, last_day)

            for __, event in notable_events["perfect"].items():
                message = f"\n**Perfect Game!**\n{event['name']} with {event['strikeouts']} strikeouts " \
                          f"in {event['outsRecorded']} outs.\n" \
                          f"[reblase](https://reblase.sibr.dev/game/{event['gameId']})"
                if "statsheet_id" in event:
                    message += f" | [statsheet](https://www.blaseball.com/database/playerstatsheets?ids={event['id']})"
                message += "\n"
                if not self.bot.config['live_version']:
                    daily_message_two += message
                game_watcher_messages.append(message)
            for __, event in notable_events["no_hitter"].items():
                message = f"\n**No Hitter!**\n{event['name']} with {event['strikeouts']} strikeouts" \
                          f" in {event['outsRecorded']} outs. {event['walksIssued']} batters walked.\n" \
                          f"[reblase](https://reblase.sibr.dev/game/{event['gameId']})"
                if "statsheet_id" in event:
                    message += f" | [statsheet](https://www.blaseball.com/database/playerstatsheets?ids={event['id']})"
                message += "\n"
                if not self.bot.config['live_version']:
                    daily_message_two += message
                game_watcher_messages.append(message)
            for __, event in notable_events["shutout"].items():
                sh_message = f"{event['name']} with {event['strikeouts']} strikeouts " \
                             f"in {event['outsRecorded']} outs. {event['hitsAllowed']} hits allowed and " \
                             f"{event['walksIssued']} batters walked.\n" \
                             f"[reblase](https://reblase.sibr.dev/game/{event['gameId']})" \
                             f" | [statsheet](https://www.blaseball.com/database/playerstatsheets?ids={event['id']})\n"
                sh_description += sh_message
            for event in notable_events["cycle"]:
                doubles_str = f"{event.doubles} double"
                if event.doubles != 1:
                    doubles_str += "s"
                triples_str = f"{event.triples} triple"
                if event.triples != 1:
                    triples_str += "s"
                hr_str = f"{event.homeRuns} home run"
                if event.homeRuns != 1:
                    hr_str += "s"
                base_message = "for the cycle"
                # quad_str = " "
                # if "quadruples" in event:
                #     quad_str = f"{event['quadruples']} quadruple"
                #     if event['quadruples'] != 1:
                #         quad_str += "s, "
                #     else:
                #         quad_str += ", "
                #     if event['quadruples'] > 0 and event['homeRuns'] > 0 \
                #             and event['triples'] > 0 and event['doubles'] > 0:
                #         base_message = "a super cycle!"
                at_bats_str = f" in {event.atBats} at bats.\n"
                natural_cycle = await self._check_feed_natural_cycle(event.name, event.playerId, last_day)
                message = f"\n**{event.name} hit {base_message}!**{at_bats_str} with {event.hits}" \
                          f" hits, {doubles_str}, {triples_str} " \
                          f"and {hr_str}.\n" \
                          f"[reblase](https://reblase.sibr.dev/game/{event.gameId})" \
                          f" | [statsheet](https://www.blaseball.com/database/playerstatsheets?ids={event.Id})"
                message += f"\n{natural_cycle}\n"
                if not self.bot.config['live_version']:
                    daily_message_two += message
                game_watcher_messages.append(message)
            for __, event in notable_events["dingerparty"].items():
                at_bats_str = ".\n"
                if "atBats" in event:
                    at_bats_str = f" in {event['atBats']} at bats.\n"
                message = f"\n**{event['name']} hit 4+ home runs!**\n{event['homeRuns']} home runs " \
                          f"in {event['hits']} total hits{at_bats_str}" \
                          f"[reblase](https://reblase.sibr.dev/game/{event['gameId']})"
                if "statsheet_id" in event:
                    message += f" | [statsheet](https://www.blaseball.com/database/playerstatsheets?ids={event['Id']})"
                message += "\n"
                if not self.bot.config['live_version']:
                    daily_message_two += message
                game_watcher_messages.append(message)
            for __, event in notable_events["bighits"].items():
                doubles_str = f"{event['doubles']} double"
                if event['doubles'] != 1:
                    doubles_str += "s"
                triples_str = f"{event['triples']} triple"
                if event['triples'] != 1:
                    triples_str += "s"
                hr_str = f"{event['homeRuns']} home run"
                if event['homeRuns'] != 1:
                    hr_str += "s"
                # quad_str = ""
                # if "quadruples" in event:
                #     quad_str = f"{event['quadruples']} quadruple"
                #     if event['quadruples'] != 1:
                #         quad_str += "s, "
                #     else:
                #         quad_str += ", "
                at_bats_str = "\n"
                if "atBats" in event:
                    at_bats_str = f" in {event['atBats']} at bats.\n"
                message = f"\n**{event['name']} got {event['hits']} hits!**{at_bats_str}" \
                          f"with {doubles_str}, {triples_str} and {hr_str}.\n" \
                          f"[reblase](https://reblase.sibr.dev/game/{event['gameId']})"
                if "statsheet_id" in event:
                    message += f" | [statsheet](https://www.blaseball.com/database/playerstatsheets?ids={event['Id']})"
                message += "\n"
                if not self.bot.config['live_version']:
                    daily_message_two += message
                game_watcher_messages.append(message)
            for __, event in notable_events["rbimaster"].items():
                doubles_str = f"{event['doubles']} double"
                if event['doubles'] != 1:
                    doubles_str += "s"
                triples_str = f"{event['triples']} triple"
                if event['triples'] != 1:
                    triples_str += "s"
                hr_str = f"{event['homeRuns']} home run"
                if event['homeRuns'] != 1:
                    hr_str += "s"
                # quad_str = ""
                # if "quadruples" in event:
                #     quad_str = f"{event['quadruples']} quadruple"
                #     if event['quadruples'] != 1:
                #         quad_str += "s, "
                #     else:
                #         quad_str += ", "
                at_bats_str = "\n"
                if "atBats" in event:
                    at_bats_str = f" with {event['hits']} in {event['atBats']} at bats.\n"
                message = f"\n**{event['name']} got {event['rbis']} RBIs!**{at_bats_str}" \
                          f"with {doubles_str}, {triples_str} and {hr_str}.\n" \
                          f"[reblase](https://reblase.sibr.dev/game/{event['gameId']})"
                if "statsheet_id" in event:
                    message += f" | [statsheet](https://www.blaseball.com/database/playerstatsheets?ids={event['Id']})"
                message += "\n"
                if not self.bot.config['live_version']:
                    daily_message_two += message
                game_watcher_messages.append(message)
            if output_channel and len(game_watcher_messages) > 0:
                description = ""
                for message in game_watcher_messages:
                    description += message + "\n"
                msg_embed = discord.Embed(description=description[:2047])
                await output_channel.send(embed=msg_embed)
            if len(daily_message) > 0:
                sh_embed.description = sh_description
                debug_chan_id = self.bot.config.setdefault('debug_channel', None)
                if debug_chan_id:
                    debug_channel = self.bot.get_channel(debug_chan_id)
                    if debug_channel:
                        if len(sh_description) > 0:
                            await utils.send_message_in_chunks(daily_message, debug_channel)
                            await debug_channel.send(daily_message_two, embed=sh_embed)
                        else:
                            await utils.send_message_in_chunks(daily_message, debug_channel)
                            await debug_channel.send(daily_message_two)
                daily_stats_channel_id = self.bot.config.setdefault('daily_stats_channel', None)
                if daily_stats_channel_id:
                    daily_stats_channel = self.bot.get_channel(daily_stats_channel_id)
                    if daily_stats_channel:
                        if len(sh_description) > 0:
                            await utils.send_message_in_chunks(daily_message, daily_stats_channel)
                            await daily_stats_channel.send(daily_message_two, embed=sh_embed)
                        else:
                            await utils.send_message_in_chunks(daily_message, daily_stats_channel)
                            await daily_stats_channel.send(daily_message_two)
            else:
                self.bot.logger.info(f"No daily message sent for {day['day']}")
            last_day += 1
        return day

    async def _query_notable_events(self, season, day):
        notable = {"perfect": {}, "no_hitter": {}, "shutout": {},
                   "cycle": [], "bighits": {}, "rbimaster": {}, "dingerparty": {}}

        async with aiosqlite.connect(self.bot.db_path) as db:
            async with db.execute("select playerId, teamId, gameId, name, outsRecorded, pitchesThrown, "
                                  "strikeouts, Id from DailyStatSheets where "
                                  "season=? and day=? and perfectGame=1;", [season, day]) as cursor:
                async for row in cursor:
                    if row and row[0]:
                        notable["perfect"][row[0]] = {
                            "teamId": row[1],
                            "gameId": row[2],
                            "name": row[3],
                            "outsRecorded": row[4],
                            "pitchesThrown": row[5],
                            "strikeouts": row[6],
                            "id": row[7]
                        }
            async with db.execute("select playerId, teamId, gameId, name, outsRecorded, pitchesThrown, "
                                  "strikeouts, walksIssued, Id from DailyStatSheets where "
                                  "season=? and day=? and noHitter=1;", [season, day]) as cursor:
                async for row in cursor:
                    if row and row[0]:
                        notable["no_hitter"][row[0]] = {
                            "teamId": row[1],
                            "gameId": row[2],
                            "name": row[3],
                            "outsRecorded": row[4],
                            "pitchesThrown": row[5],
                            "strikeouts": row[6],
                            "walksIssued": row[7],
                            "id": row[8]
                        }
            async with db.execute("select playerId, teamId, gameId, name, outsRecorded, pitchesThrown, "
                                  "strikeouts, walksIssued, hitsAllowed, Id from DailyStatSheets where "
                                  "season=? and day=? and shutout=1;", [season, day]) as cursor:
                async for row in cursor:
                    if row and row[0]:
                        notable["shutout"][row[0]] = {
                            "teamId": row[1],
                            "gameId": row[2],
                            "name": row[3],
                            "outsRecorded": row[4],
                            "pitchesThrown": row[5],
                            "strikeouts": row[6],
                            "walksIssued": row[7],
                            "hitsAllowed": row[8],
                            "id": row[9]
                        }
            async with db.execute("select playerId, teamId, gameId, name, hits, doubles, triples, "
                                  "homeRuns, atBats, Id from DailyStatSheets where season=? and day=? "
                                  "and doubles>0 and triples>0 and homeRuns>0 and hits>3 "
                                  "and doubles+triples+homeRuns < hits;", [season, day]) as cursor:
                async for row in cursor:
                    if row:
                        notable["cycle"].append(CycleInstance(*row))

            async with db.execute("select playerId, teamId, gameId, name, hits, doubles, triples, "
                                  "homeRuns, atBats, Id from DailyStatSheets where season=? and day=? "
                                  "and hits>5 ", [season, day]) as cursor:
                async for row in cursor:
                    if row and row[0]:
                        notable["bighits"][row[0]] = {
                            "teamId": row[1],
                            "gameId": row[2],
                            "name": row[3],
                            "hits": row[4],
                            "doubles": row[5],
                            "triples": row[6],
                            "homeRuns": row[7],
                            "atBats": row[8],
                            "id": row[9]
                        }
            async with db.execute("select playerId, teamId, gameId, name, hits, "
                                  "homeRuns, atBats, Id from DailyStatSheets where season=? and day=? "
                                  "and homeRuns>3 ", [season, day]) as cursor:
                async for row in cursor:
                    if row and row[0]:
                        notable["dingerparty"][row[0]] = {
                            "teamId": row[1],
                            "gameId": row[2],
                            "name": row[3],
                            "hits": row[4],
                            "homeRuns": row[5],
                            "atBats": row[6],
                            "id": row[7]
                        }
            async with db.execute("select playerId, teamId, gameId, name, hits, doubles, triples, "
                                  "homeRuns, atBats, rbis, Id from DailyStatSheets where season=? and day=? "
                                  "and rbis>7 ", [season, day]) as cursor:
                async for row in cursor:
                    if row and row[0]:
                        notable["rbimaster"][row[0]] = {
                            "teamId": row[1],
                            "gameId": row[2],
                            "name": row[3],
                            "hits": row[4],
                            "doubles": row[5],
                            "triples": row[6],
                            "homeRuns": row[7],
                            "atBats": row[8],
                            "rbis": row[9],
                            "id": row[10]
                        }

        return notable

    @staticmethod
    async def _check_feed_natural_cycle(player_name, player_id, day):
        player_feed = await utils.retry_request(f"https://www.blaseball.com/database/feed/player?id={player_id}")
        feed_json = player_feed.json()
        day_items = list(filter(lambda d: d['day'] == day, feed_json))
        sorted_items = sorted(day_items, key=lambda item: item['metadata']['play'])

        filtered_items = []
        for item in sorted_items:
            if f"{player_name} hits a" in item['description']:
                filtered_items.append(item)

        for i in range(len(filtered_items)):
            if i + 2 > len(filtered_items):
                break
            if "hits a Single" in filtered_items[i]['description']:
                if "hits a Double" in filtered_items[i + 1]['description']:
                    if "hits a Triple" in filtered_items[i + 2]['description']:
                        if "home run" in filtered_items[i + 3]['description']:
                            return "Natural Cycle!"
        for i in range(len(filtered_items)):
            if i + 2 > len(filtered_items):
                break
            if "home run" in filtered_items[i]['description']:
                if "hits a Triple" in filtered_items[i + 1]['description']:
                    if "hits a Double" in filtered_items[i + 2]['description']:
                        if "hits a Single" in filtered_items[i + 3]['description']:
                            return "Reverse Cycle!"
        return "Not a natural cycle."

    async def compile_stats(self, season):
        hitters, pitchers = {}, {}

        async with aiosqlite.connect(self.bot.db_path) as db:
            async with db.execute("select playerId, name, teamId, sum(hits)-sum(homeRuns), "
                                  "sum(homeRuns), sum(stolenBases) "
                                  "from DailyStatSheets where season=? and position='lineup' "
                                  "group by playerId", [season]) as cursor:
                async for row in cursor:
                    if row and row[0]:
                        hitters[row[0]] = {
                            "name": row[1],
                            "playerId": row[0],
                            "teamId": row[2],
                            "hitsMinusHrs": row[3],
                            "homeRuns": row[4],
                            "stolenBases": row[5]
                        }
        async with aiosqlite.connect(self.bot.db_path) as db:
            async with db.execute("select playerId, name, teamId, sum(outsRecorded), sum(strikeouts), "
                                  "sum(walksIssued), sum(shutout), rotation, rotation_changed, "
                                  "sum(homeRunsAllowed) "
                                  "from DailyStatSheets where season=? and position='rotation' "
                                  "group by playerId", [season]) as cursor:
                async for row in cursor:
                    if row and row[0]:
                        pitchers[row[0]] = {
                            "name": row[1],
                            "playerId": row[0],
                            "teamId": row[2],
                            "outsRecorded": row[3],
                            "strikeouts": row[4],
                            "walksIssued": row[5],
                            "shutout": row[6],
                            "rotation": row[7],
                            "rotation_changed": row[8],
                            "homeRunsAllowed": row[9]
                        }
        return hitters, pitchers

    async def update_leaders_sheet(self, season, day, ps_teams_updated):
        season -= 1
        agc = await self.bot.authorize_agcm()
        if self.bot.config['live_version'] == True:
            sheet = await agc.open_by_key(self.bot.SPREADSHEET_IDS[f"season{season + 1}"])
        else:
            sheet = await agc.open_by_key(self.bot.SPREADSHEET_IDS[f"seasontest"])
        if season >= 12:
            p_worksheet = await sheet.worksheet("Pitching Snacks")
            h_worksheet = await sheet.worksheet("Hitting Snacks")
        else:
            p_worksheet = await sheet.worksheet("Pendants")
            h_worksheet = await sheet.worksheet("Pendants")
        hitters, pitcher_dict = await self.compile_stats(season)

        sorted_combo_payouts, sorted_sickle_payouts, sorted_seed_dog_payouts\
            = self.save_daily_top_hitters(hitters, day, ps_teams_updated)
        rows = []
        team_short_map = await self.get_short_map()
        for i in range(1, 6):
            sorted_strikeouts = {k: v
                                 for k, v in sorted(pitcher_dict.items(),
                                                    key=lambda item: round((item[1]['strikeouts'] / (
                                                            item[1]['outsRecorded'] / 27)) * 10) / 10,
                                                    reverse=True) if v["rotation"] == i and not v["rotation_changed"]}
            top_list = list(sorted_strikeouts.keys())

            if len(top_list) > 3:
                top_keys = top_list[:3]
                for key in top_keys:
                    values = pitcher_dict[key]
                    team = team_short_map[values["teamId"]]
                    name = f"({team}) {values['name']}"
                    k_9_value = round((values['strikeouts'] / (values['outsRecorded'] / 27)) * 10) / 10
                    rows.append([values["rotation"], name, '', '', values["strikeouts"], k_9_value])
        await p_worksheet.batch_update([{
            'range': "A5:F19",
            'values': rows
        }])

        rows = []
        sorted_strikeouts = {k: v
                             for k, v in sorted(pitcher_dict.items(),
                                                key=lambda item: round((item[1]['strikeouts'] / (
                                                        item[1]['outsRecorded'] / 27)) * 10) / 10,
                                                reverse=True) if v["rotation_changed"]}
        top_list = list(sorted_strikeouts.keys())

        top_keys = top_list[:10]
        for key in top_keys:
            values = pitcher_dict[key]
            team = team_short_map[values["teamId"]]
            name = f"({team}) {values['name']}"
            k_9_value = round((values['strikeouts'] / (values['outsRecorded'] / 27)) * 10) / 10
            rows.append([values["rotation"], name, '', '', values["strikeouts"], k_9_value])
        await p_worksheet.batch_update([{
            'range': "A23:F32",
            'values': rows
        }])

        rows = []
        for i in range(1, 6):
            sorted_shutouts = {k: v for k, v in sorted(pitcher_dict.items(), key=lambda item: item[1]['shutout'],
                                                       reverse=True) if
                               v["rotation"] == i and not v["rotation_changed"]}
            top_keys = list(sorted_shutouts.keys())[:3]
            for key in top_keys:
                values = sorted_shutouts[key]
                team = team_short_map[values["teamId"]]
                name = f"({team}) {values['name']}"
                rows.append([name, '', values["shutout"]])
        await p_worksheet.batch_update([{
            'range': "I5:K19",
            'values': rows
        }])

        rows = []
        sorted_shutouts = {k: v for k, v in sorted(pitcher_dict.items(), key=lambda item: item[1]['shutout'],
                                                   reverse=True) if v["rotation_changed"]}
        top_keys = list(sorted_shutouts.keys())[:10]
        for key in top_keys:
            values = sorted_shutouts[key]
            team = team_short_map[values["teamId"]]
            name = f"({team}) {values['name']}"
            rows.append([values["rotation"], name, '', values["shutout"]])
        await p_worksheet.batch_update([{
            'range': "H23:K32",
            'values': rows
        }])

        rows = []
        sorted_dingers_allowed = {k: v for k, v in sorted(pitcher_dict.items(),
                                                          key=lambda item: item[1]['homeRunsAllowed'],
                                                          reverse=True)}
        top_keys = list(sorted_dingers_allowed.keys())[:12]
        for key in top_keys:
            values = sorted_dingers_allowed[key]
            team = team_short_map[values["teamId"]]
            name = f"({team}) {values['name']}"
            rows.append([values["rotation"], name, '', '', values["homeRunsAllowed"]])
        await p_worksheet.batch_update([{
            'range': "A36:F47",
            'values': rows
        }])

        rows = []

        players_seen = []
        top_sickle_keys = list(sorted_sickle_payouts.keys())
        top_seed_dog_keys = list(sorted_seed_dog_payouts.keys())
        top_combo_keys = list(sorted_combo_payouts.keys())

        count = 0
        for key in top_combo_keys:
            if key == "86d4e22b-f107-4bcf-9625-32d387fcb521" or key == "e16c3f28-eecd-4571-be1a-606bbac36b2b":
                continue
            values = sorted_combo_payouts[key]
            hits = hitters[key]["hitsMinusHrs"]
            team = team_short_map[values["teamId"]]
            name = f"({team}) {values['name']}"
            rows.append([name, '', hits, values["homeRuns"], values["stolenBases"]])
            players_seen.append(key)
            count += 1
            if count == 4:
                break

        count = 0
        for key in top_sickle_keys:
            if key == "86d4e22b-f107-4bcf-9625-32d387fcb521" or key == "e16c3f28-eecd-4571-be1a-606bbac36b2b":
                continue
            if key not in players_seen:
                values = sorted_sickle_payouts[key]
                hits = hitters[key]["hitsMinusHrs"]
                team = team_short_map[values["teamId"]]
                name = f"({team}) {values['name']}"
                rows.append([name, '', hits, values["homeRuns"], values["stolenBases"]])
                players_seen.append(key)
                count += 1
                if count == 4:
                    break

        count = 0
        for key in top_seed_dog_keys:
            if key == "86d4e22b-f107-4bcf-9625-32d387fcb521" or key == "e16c3f28-eecd-4571-be1a-606bbac36b2b":
                continue
            if key not in players_seen:
                values = sorted_seed_dog_payouts[key]
                hits = hitters[key]["hitsMinusHrs"]
                team = team_short_map[values["teamId"]]
                name = f"({team}) {values['name']}"
                rows.append([name, '', hits, values["homeRuns"], values["stolenBases"]])
                count += 1
                if count == 4:
                    break

        await h_worksheet.batch_update([{
            'range': f"A9:E{9+len(rows)}",
            'values': rows
        }])

        # York Silk
        ys_id = "86d4e22b-f107-4bcf-9625-32d387fcb521"
        ys_row = ["York Silk", '', 0, 0, 0]
        if ys_id in sorted_combo_payouts:
            ys_row[2] = hitters[ys_id].setdefault("hitsMinusHrs", 0)
        if ys_id in sorted_combo_payouts:
            ys_row[3] = sorted_combo_payouts[ys_id].setdefault("homeRuns", 0)
        if ys_id in sorted_combo_payouts:
            ys_row[4] = sorted_combo_payouts[ys_id].setdefault("stolenBases", 0)
        # Wyatt Glover
        wg_id = "e16c3f28-eecd-4571-be1a-606bbac36b2b"
        wg_row = ["Wyatt Glover", '', 0, 0, 0]
        if wg_id in sorted_combo_payouts:
            wg_row[2] = hitters[wg_id].setdefault("hitsMinusHrs", 0)
        if wg_id in sorted_combo_payouts:
            wg_row[3] = sorted_combo_payouts[wg_id].setdefault("homeRuns", 0)
        if wg_id in sorted_combo_payouts:
            wg_row[4] = sorted_combo_payouts[wg_id].setdefault("stolenBases", 0)
        await h_worksheet.batch_update([{
            'range': "A6:E7",
            'values': [ys_row, wg_row]
        }])

    @staticmethod
    def load_remaining_teams():
        with open(os.path.join('data', 'pendant_data', 'statsheets', 'postseason_teams.json'), 'r') as file:
            team_list = json.load(file)
        return team_list

    @staticmethod
    async def check_remaining_teams(bot):
        sim_data = await utils.retry_request("https://www.blaseball.com/database/simulationData")
        if not sim_data:
            return False
        sd_json = sim_data.json()
        # still midseason, nothing to check
        if sd_json["day"] < 98:
            return True
        if sd_json["day"] == 98:
            # todo check if games complete
            pass
        round_num = sd_json["playOffRound"]
        playoffs = await utils.retry_request(f"https://www.blaseball.com/database/playoffs?number={sd_json['season']}")
        if not playoffs:
            return False
        round_id = playoffs.json()["rounds"][round_num]
        playoff_round = await utils.retry_request(f"https://www.blaseball.com/database/playoffRound?id={round_id}")
        if not playoff_round:
            return False
        pr_json = playoff_round.json()
        matchups = pr_json["matchups"]
        url = f"https://www.blaseball.com/database/playoffMatchups?ids={','.join(matchups)}"
        playoff_matchups = await utils.retry_request(url)
        if not playoff_matchups:
            return False
        pm_json = playoff_matchups.json()
        team_ids = []
        for matchup in pm_json:
            if not matchup["homeTeam"] or not matchup["awayTeam"]:
                continue
            games_needed = int(matchup["gamesNeeded"])
            if matchup["homeWins"] >= games_needed or matchup["awayWins"] >= games_needed:
                continue
            team_ids.append(matchup["homeTeam"])
            team_ids.append(matchup["awayTeam"])
        bot.playoff_teams = team_ids
        with open(os.path.join('data', 'pendant_data', 'statsheets', 'postseason_teams.json'), 'w') as file:
            json.dump(team_ids, file)

    def save_daily_top_hitters(self, hitters, day, ps_teams_updated):
        # need to put in logic for playoffs here
        if ps_teams_updated == True:
            team_list = self.bot.postseason_teams
        else:
            team_list = self.load_remaining_teams()

        sorted_hits = {k: v for k, v in sorted(hitters.items(), key=lambda item: item[1]['hits'],
                                               reverse=True) if v['teamId'] in team_list}
        sorted_homeruns = {k: v for k, v in sorted(hitters.items(), key=lambda item: item[1]['homeRuns'],
                                                   reverse=True) if v['teamId'] in team_list}
        sorted_stolenbases = {k: v for k, v in sorted(hitters.items(), key=lambda item: item[1]['stolenBases'],
                                                      reverse=True) if v['teamId'] in team_list}
        # sorted_hits = {k: v for k, v in sorted(hitters.items(), key=lambda item: item[1]['hitsMinusHrs'],
        #                                        reverse=True)}
        # sorted_homeruns = {k: v for k, v in sorted(hitters.items(), key=lambda item: item[1]['homeRuns'],
        #                                            reverse=True)}
        # sorted_stolenbases = {k: v for k, v in sorted(hitters.items(), key=lambda item: item[1]['stolenBases'],
        #                                               reverse=True)}
        boosted_players = {"86d4e22b-f107-4bcf-9625-32d387fcb521": 2, "e16c3f28-eecd-4571-be1a-606bbac36b2b": 5}
        skip_players = ["167751d5-210c-4a6e-9568-e92d61bab185"]
        total_hit_payouts = {}
        for k, v in sorted_hits.items():
            if k in skip_players or k in self.bot.deceased_players.keys():
                continue
            homeruns = sorted_homeruns[k]["homeRuns"]
            stolenbases = sorted_stolenbases[k]["stolenBases"]
            hits = v["hitsMinusHrs"]

            if k in boosted_players:
                multiplier = boosted_players[k]
            else:
                multiplier = 1
            seed_dog = ((hits * 1500) + (homeruns * 4000)) * multiplier
            sickle = ((hits * 1500) + (stolenbases * 3000)) * multiplier
            combo = ((hits * 1500) + (homeruns * 4000) + (stolenbases * 3000)) * multiplier
            hitters[k]["multiplier"] = multiplier

            total_hit_payouts[k] = {"name": v['name'], "teamId": v["teamId"], "hits": v["hitsMinusHrs"],
                                    "homeRuns": sorted_homeruns[k]["homeRuns"],
                                    "stolenBases": sorted_stolenbases[k]["stolenBases"],
                                    "seed_dog": seed_dog, "combo": combo,
                                    "sickle": sickle, "multiplier": multiplier}
        sorted_seed_dog_payouts = {k: v for k, v in sorted(total_hit_payouts.items(),
                                                           key=lambda item: item[1]['seed_dog'], reverse=True)}
        sorted_sickle_payouts = {k: v for k, v in sorted(total_hit_payouts.items(),
                                                        key=lambda item: item[1]['sickle'], reverse=True)}
        sorted_combo_payouts = {k: v for k, v in sorted(total_hit_payouts.items(),
                                                        key=lambda item: item[1]['combo'], reverse=True)}

        daily_leaders = {"hits": [], "home_runs": [], "stolen_bases": [], "seed_dog": [], "sickle": [], "combo": []}
        for key in list(sorted_hits.keys())[:10]:
            daily_leaders["hits"].append(hitters[key])
        for key in list(sorted_homeruns.keys())[:10]:
            daily_leaders["home_runs"].append(hitters[key])
        for key in list(sorted_stolenbases.keys())[:10]:
            daily_leaders["stolen_bases"].append(hitters[key])
        for key in list(sorted_seed_dog_payouts.keys())[:10]:
            daily_leaders["seed_dog"].append(hitters[key])
        for key in list(sorted_sickle_payouts.keys())[:10]:
            daily_leaders["sickle"].append(hitters[key])
        for key in list(sorted_combo_payouts.keys())[:10]:
            daily_leaders["combo"].append(hitters[key])

        with open(os.path.join('data', 'pendant_data', 'statsheets', f'd{day}_leaders.json'), 'w') as file:
            json.dump(daily_leaders, file)

        return sorted_combo_payouts, sorted_sickle_payouts, sorted_seed_dog_payouts

    @commands.command(aliases=['upp'])
    async def _update_pendants(self, ctx, season: int):
        await ctx.message.add_reaction("⏲️")
        latest_day = await self.get_latest_pendant_data(season)
        await self.update_leaders_sheet(season, latest_day)
        await ctx.message.add_reaction(self.bot.success_react)

    @commands.command(aliases=['sld'])
    async def _set_latest_day(self, ctx, day: int):
        self.bot.config['DAILY_STATS_LAST_DAY'] = day
        return await ctx.message.add_reaction(self.bot.success_react)

    @commands.command(name='set_stats_channel', aliases=['stc'])
    async def _set_stats_channel(self, ctx, item):
        output_channel = await utils.get_channel_by_name_or_id(ctx, item)
        if output_channel is None:
            return await ctx.message.add_reaction(self.bot.failed_react)
        self.bot.config['stats_channel'] = output_channel.id
        return await ctx.message.add_reaction(self.bot.success_react)

    @commands.command(name='set_dailystats_channel', aliases=['sdtc'])
    async def _set_dailystats_channel(self, ctx, item):
        output_channel = await utils.get_channel_by_name_or_id(ctx, item)
        if output_channel is None:
            return await ctx.message.add_reaction(self.bot.failed_react)
        self.bot.config['daily_stats_channel'] = output_channel.id
        return await ctx.message.add_reaction(self.bot.success_react)

    @commands.command(name='set_daily_watch_message', aliases=['sdwm'])
    async def _set_daily_watch_message(self, ctx, *, message_text):
        self.bot.config['daily_watch_message'] = message_text
        self.bot.daily_watch_message = message_text
        return await ctx.message.add_reaction(self.bot.success_react)

    @commands.command(name='test_flood_count', aliases=['ttfc'])
    async def _test_flood_count(self, ctx):
        result = await self.check_remaining_teams(self.bot)
        print(result)
        return
        day_flood_count = 0
        day_runner_count = 0
        game_ids = ["99113b38-77af-48a3-aad8-1cb48f679130", "9274e98a-15c7-4b9a-bd5c-e8275b300cd8", "26cc26b3-dc9f-4339-b9f8-5f40c4aec590", "691a703a-5142-44dd-910c-5ea3fe701e63", "57748419-e0ce-4399-96f4-ae535f942ae9", "3159730a-208d-466f-b6f4-c7756aa3a1cc", "2ec0e69f-5fb4-4eb0-aa09-284e8c9eb7c3", "b1c075fe-ed60-4b7a-bfb1-ded6878d9366", "93c80cb1-59f6-4f89-8c70-674c4efffdb2", "b17f09b5-fc41-481d-b494-0b53d8f06def", "ed6ba6c3-d3c1-4d19-8393-05374042a8a9", "be7e61c3-29b0-44a3-a2c6-9c6bb657f077", "6a00cc1f-9f26-4528-9a84-e6f253a28635", "f3e2c0b0-4fb7-4b96-9dce-f05d90754bec", "88aee411-fcae-4e38-bf84-057012df34cc", "6e2bf11f-577c-4095-95d0-db366b4b1b75", "74210406-9b06-48fe-acde-1f6ee53df07c", "4ac2f8c9-8f2f-49bd-a6e0-d518e32ced75", "b7bb50ac-d06d-442e-83f4-15f4644fc661", "f6b0e995-6292-4f9c-a70d-c20d7c01abf6", "95011bc0-bb43-4373-b0f6-2d90ccaba945", "c0adf4ca-8125-4381-9123-10d3448f0705", "fe643582-c694-4e7e-bc18-6c04bb629ba7", "7523d5dc-4125-49d4-8061-23fe41d70d57", "92bda7ca-d2b1-4b94-a909-e796eb68cfa7", "4894cc29-0aa0-4a68-a326-d227cdaf68ca", "8c4e892f-9c28-4597-9291-2d927206df6a", "22d12ad3-88b1-4f4c-9df4-16ad03a56a33", "c0c93d06-99c8-48a2-90af-6e57898b5059", "3eb58ff0-0161-419b-9c8f-6d379a056d7d", "1d570099-7c0f-4d6c-91e6-2415392e74dc", "e322d071-e0cd-4a9b-8491-699ceee6059d"]
        for game_id in game_ids:
            game_feed = await utils.retry_request(
                f"https://api.blaseball-reference.com/v1/events?gameId={game_id}&baseRunners=true")
            if game_feed:
                feed_json = game_feed.json()
                if len(feed_json['results']) > 0:
                    last_event = None
                    for food in feed_json['results']:
                        for text in food['event_text']:
                            if "Immateria" in text:
                                day_flood_count += 1
                                day_runner_count += len(last_event['base_runners'])
                        last_event = food
        await ctx.send(day_runner_count)


def setup(bot):
    bot.add_cog(Pendants(bot))
