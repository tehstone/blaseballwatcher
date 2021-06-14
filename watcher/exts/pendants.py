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
boosted_players = {"86d4e22b-f107-4bcf-9625-32d387fcb521": 2,
                   "e16c3f28-eecd-4571-be1a-606bbac36b2b": 5,
                   "c0732e36-3731-4f1a-abdc-daa9563b6506": 2,
                   "cf8e152e-2d27-4dcc-ba2b-68127de4e6a4": 2,
                   "8ecea7e0-b1fb-4b74-8c8c-3271cb54f659": 2,
                   "9a9bb4f5-d2a5-4ce2-b715-9e2c74a65502": 2,
                   }
skip_players = ["167751d5-210c-4a6e-9568-e92d61bab185"]

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
        # todo remove this after this season and handle better
        if day == 107:
            return False
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
                    else:
                        p_values['noHitter'] = 1
                else:
                    p_values["shutout"] = 1
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
                p_values["plate_appearances"] = p_values["atBats"] + p_values["walks"] + p_values["hitByPitch"]
                team_stats[team_id]["plate_appearances"] += p_values["plate_appearances"]
                if "struckouts" in p_values:
                    team_stats[team_id]["struckouts"] += p_values["struckouts"]
                if "lineup_pa" not in team_stats[team_id]:
                    team_stats[team_id]["lineup_pa"] = {}
                if p_values["playerId"] not in team_stats[team_id]["lineup_pa"]:
                    team_stats[team_id]["lineup_pa"][p_values["playerId"]] = 0
                team_stats[team_id]["lineup_pa"][p_values["playerId"]] += p_values["plate_appearances"]
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
                         p_values["perfectGame"], p_values["homeRunsAllowed"], p_values.get("plate_appearances", 0)))

        async with aiosqlite.connect(self.bot.db_path) as db:
            await db.executemany("insert into DailyStatSheets values "
                                 "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
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
                if pvalue.outsRecorded > 0:
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
                    if row and row[0] is not None:
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
            daily_message = [f"**Daily leaders for Day {last_day+1}**\n"]
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
                natural_cycle = await self._check_feed_natural_cycle(event.name, event.playerId,
                                                                     last_day, current_season)
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
                game_watcher_message = await output_channel.send(f"Notable events on Day {last_day+1}", embed=msg_embed)
                if self.bot.config['live_version']:
                    await game_watcher_message.publish()
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

    async def _check_feed_natural_cycle(self, player_name, player_id, day, season):
        player_feed = await utils.retry_request(f"https://www.blaseball.com/database/feed/player?id={player_id}")
        feed_json = player_feed.json()
        day_items = list(filter(lambda d: d['day'] == day and d['season'] == season
                                and 'metadata' in d and 'play' in d['metadata'], feed_json))
        sorted_items = sorted(day_items, key=lambda item: item['metadata']['play'])

        filtered_items = []
        for item in sorted_items:
            if f"{player_name} hits a" in item['description']:
                filtered_items.append(item)

        try:
            for i in range(len(filtered_items)):
                if i + 1 >= len(filtered_items):
                    break
                if "hits a Single" in filtered_items[i]['description']:
                    if "hits a Double" in filtered_items[i + 1]['description']:
                        if "hits a Triple" in filtered_items[i + 2]['description']:
                            if "home run" in filtered_items[i + 3]['description']:
                                return "Natural Cycle!"
        except IndexError:
            self.bot.logger.warn(f"Failed cycle check on:\n{filtered_items}")
        try:
            for i in range(len(filtered_items)):
                if i + 1 >= len(filtered_items):
                    break
                if "home run" in filtered_items[i]['description']:
                    if "hits a Triple" in filtered_items[i + 1]['description']:
                        if "hits a Double" in filtered_items[i + 2]['description']:
                            if "hits a Single" in filtered_items[i + 3]['description']:
                                return "Reverse Cycle!"
        except IndexError:
            self.bot.logger.warn(f"Failed reverse cycle check on:\n{filtered_items}")
        return "Not a natural cycle."

    async def _update_legendary(self):
        async with aiosqlite.connect(self.bot.db_path) as db:
            async with db.execute("select player_id "
                                  "from PlayerLeagueAndStars where legendary=1;") as cursor:
                async for row in cursor:
                    if row and row[0]:
                        skip_players.append(row[0])

    async def _get_modified_lineup_positions(self, hitters, pitcher_dict):
        team_lineups = {}
        team_lineup_lengths = {}
        team_rotation_lengths = {}
        for team in self.bot.team_names.keys():
            team_lineups[team] = {}
            team_lineup = []
            async with aiosqlite.connect(self.bot.db_path) as db:
                async with db.execute("select player_id, slot, elsewhere, shelled "
                                      "from PlayerLeagueAndStars where team_id=? and position='lineup'"
                                      "order by slot;", [team]) as cursor:
                    async for row in cursor:
                        if row and row[0]:
                            team_lineup.append(
                                {
                                    "playerId": row[0],
                                    "slot": row[1],
                                    "elsewhere": row[2],
                                    "shelled": row[3]
                                }
                            )
            slot = 1
            for player in team_lineup:
                if player["playerId"] in hitters:
                    hitters[player["playerId"]]["teamId"] = team
                if not player["elsewhere"] and not player["shelled"]:
                    team_lineups[player["playerId"]] = slot
                    slot += 1
            team_lineup_lengths[team] = slot - 1

            rotation_len = 0
            async with aiosqlite.connect(self.bot.db_path) as db:
                async with db.execute("select player_id, team_id "
                                      "from PlayerLeagueAndStars where team_id=? and position='rotation'"
                                      "order by slot;", [team]) as cursor:
                    async for row in cursor:
                        if row and row[0]:
                            if row[0] in pitcher_dict:
                                pitcher_dict[row[0]]["teamId"] = row[1]
                                rotation_len += 1
            team_rotation_lengths[team] = rotation_len
        return team_lineups, team_lineup_lengths, team_rotation_lengths

    async def compile_stats(self, season):
        hitters, pitchers = {}, {}

        async with aiosqlite.connect(self.bot.db_path) as db:
            async with db.execute("select playerId, name, sum(hits)-sum(homeRuns), sum(homeRuns), "
                                  "sum(stolenBases), sum(atBats), sum(plateAppearances), "
                                  "count(distinct gameId) as games "
                                  "from DailyStatSheets where season=? and position='lineup' "
                                  "group by playerId;", [season]) as cursor:
                async for row in cursor:
                    if row and row[0]:
                        hitters[row[0]] = {
                            "name": row[1],
                            "playerId": row[0],
                            "hitsMinusHrs": row[2],
                            "homeRuns": row[3],
                            "stolenBases": row[4],
                            "atBats": row[5],
                            "plateAppearances": row[6],
                            "games": row[7]
                        }

        async with aiosqlite.connect(self.bot.db_path) as db:
            async with db.execute("select playerId, sum(atBats)/10.0, sum(plateAppearances)/10.0 "
                                  "from DailyStatSheets where season=18 and position='lineup' "
                                  "and day > (select max(day) from DailyStatSheets where season=?) - 10 "
                                  "group by playerId;", [season]) as cursor:
                async for row in cursor:
                    if row and row[0] and row[0] in hitters:
                        hitters[row[0]]["avg_ab"] = row[1]
                        hitters[row[0]]["avg_pa"] = row[2]

        async with aiosqlite.connect(self.bot.db_path) as db:
            async with db.execute("select playerId, name, sum(outsRecorded), sum(strikeouts), "
                                  "sum(walksIssued), sum(shutout), rotation, rotation_changed, "
                                  "sum(homeRunsAllowed), sum(wins), count(name) as games "
                                  "from DailyStatSheets where season=? and position='rotation' "
                                  "group by playerId", [season]) as cursor:
                async for row in cursor:
                    if row and row[0]:
                        pitchers[row[0]] = {
                            "name": row[1],
                            "playerId": row[0],
                            "outsRecorded": row[2],
                            "strikeouts": row[3],
                            "walksIssued": row[4],
                            "shutout": row[5],
                            "rotation": row[6],
                            "rotation_changed": row[7],
                            "homeRunsAllowed": row[8],
                            "wins": row[9],
                            "games": row[10]
                        }

        async with aiosqlite.connect(self.bot.db_path) as db:
            async with db.execute("select player_id, team_id "
                                  "from PlayerLeagueAndStars;") as cursor:
                async for row in cursor:
                    if row and row[0]:
                        if row[0] in hitters:
                            hitters[row[0]]["teamId"] = row[1]
                        if row[0] in pitchers:
                            pitchers[row[0]]["teamId"] = row[1]

        return hitters, pitchers

    async def update_leaders_sheet(self, season, day):
        season -= 1
        agc = await self.bot.authorize_agcm()
        if self.bot.config['live_version'] == True:
            sheet = await agc.open_by_key(self.bot.SPREADSHEET_IDS[f"season{season + 1}snacks"])
        else:
            sheet = await agc.open_by_key(self.bot.SPREADSHEET_IDS[f"seasontest"])
        ah_sheet = await sheet.worksheet("All Hitters")
        ap_sheet = await sheet.worksheet("All Pitchers")
        await self._update_legendary()
        hitters, pitcher_dict = await self.compile_stats(season)
        team_lineups, team_lineup_lengths, team_rotation_lengths\
            = await self._get_modified_lineup_positions(hitters, pitcher_dict)
        #team_lineup_lengths = await self._get_team_lineup_lengths(season, day - 1)
        team_short_map = await self.get_short_map()

        rows = []
        sorted_hitters = {k: v for k, v in sorted(hitters.items(), key=lambda item: item[1]['atBats'], reverse=True)}
        for hitter in sorted_hitters.values():
            hits = hitter["hitsMinusHrs"]
            lineup_length, team = -1, "null"
            if "teamId" in hitter:
                lineup_length = team_lineup_lengths[hitter["teamId"]]
                team = team_short_map[hitter["teamId"]]

            name = f"{hitter['name']}"
            at_bats = hitter["atBats"]
            plate_appearances = hitter["plateAppearances"]
            games = hitter["games"]
            slot = -1
            if hitter["playerId"] in team_lineups:
                if hitter["playerId"] not in skip_players:
                    slot = team_lineups[hitter["playerId"]]

            avg_ab, avg_pa = 0, 0
            if "avg_ab" in hitter:
                avg_ab = hitter["avg_ab"]
            if "avg_pa" in hitter:
                avg_pa = hitter["avg_pa"]

            rows.append([name, team, hits, hitter["homeRuns"], hitter["stolenBases"],
                         at_bats, plate_appearances, lineup_length, games, slot, avg_ab, avg_pa])
        await ah_sheet.batch_update([{
            'range': f"A5:L{5 + len(rows)}",
            'values': rows
        }])

        rows = []
        sorted_pitchers = {k: v for k, v in sorted(pitcher_dict.items(),
                                                   key=lambda item: item[1]['outsRecorded'], reverse=True)}
        for pitcher in sorted_pitchers.values():
            if pitcher["playerId"] in skip_players:
                continue
            name = f"{pitcher['name']}"
            losses = pitcher['games'] - pitcher['wins']
            team = "null"
            if "teamId" in pitcher:
                team = team_short_map[pitcher["teamId"]]
            rows.append([name, team, pitcher['outsRecorded'], pitcher['wins'], losses, pitcher['games'],
                         pitcher['strikeouts'], pitcher['shutout'], pitcher['homeRunsAllowed'], pitcher['rotation']])
        await ap_sheet.batch_update([{
            'range': f"A5:J{5 + len(rows)}",
            'values': rows
        }])

        hitters, pitcher_dict = await self.compile_stats(season)

        sorted_combo_payouts, sorted_sickle_payouts, sorted_seed_dog_payouts\
            = self.save_daily_top_hitters(hitters, day)
        rows = []
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
                    name = f"{values['name']}"
                    k_9_value = round((values['strikeouts'] / (values['outsRecorded'] / 27)) * 10) / 10
                    rows.append([values["rotation"], name, '', '', values["strikeouts"], k_9_value])
        # await p_worksheet.batch_update([{
        #     'range': "A5:F19",
        #     'values': rows
        # }])

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
            name = f"{values['name']}"
            k_9_value = round((values['strikeouts'] / (values['outsRecorded'] / 27)) * 10) / 10
            rows.append([values["rotation"], name, '', '', values["strikeouts"], k_9_value])
        # await p_worksheet.batch_update([{
        #     'range': "A23:F32",
        #     'values': rows
        # }])

        rows = []
        for i in range(1, 6):
            sorted_shutouts = {k: v for k, v in sorted(pitcher_dict.items(), key=lambda item: item[1]['shutout'],
                                                       reverse=True) if
                               v["rotation"] == i and not v["rotation_changed"]}
            top_keys = list(sorted_shutouts.keys())[:3]
            for key in top_keys:
                values = sorted_shutouts[key]
                name = f"{values['name']}"
                rows.append([name, '', values["shutout"]])
        # await p_worksheet.batch_update([{
        #     'range': "I5:K19",
        #     'values': rows
        # }])

        rows = []
        sorted_shutouts = {k: v for k, v in sorted(pitcher_dict.items(), key=lambda item: item[1]['shutout'],
                                                   reverse=True) if v["rotation_changed"]}
        top_keys = list(sorted_shutouts.keys())[:10]
        for key in top_keys:
            values = sorted_shutouts[key]
            name = f"{values['name']}"
            rows.append([values["rotation"], name, '', values["shutout"]])
        # await p_worksheet.batch_update([{
        #     'range': "H23:K32",
        #     'values': rows
        # }])

        rows = []
        sorted_dingers_allowed = {k: v for k, v in sorted(pitcher_dict.items(),
                                                          key=lambda item: item[1]['homeRunsAllowed'],
                                                          reverse=True)}
        top_keys = list(sorted_dingers_allowed.keys())[:12]
        for key in top_keys:
            values = sorted_dingers_allowed[key]
            name = f"{values['name']}"
            rows.append([values["rotation"], name, '', '', values["homeRunsAllowed"]])
        # await p_worksheet.batch_update([{
        #     'range': "A36:F47",
        #     'values': rows
        # }])

        team_lineup_lengths = await self._get_team_lineup_lengths(season, day - 1)
        rows = []

        players_seen = []
        top_sickle_keys = list(sorted_sickle_payouts.keys())
        top_seed_dog_keys = list(sorted_seed_dog_payouts.keys())
        top_combo_keys = list(sorted_combo_payouts.keys())

        count = 0
        for key in top_combo_keys:
            if key in boosted_players:
                continue
            values = sorted_combo_payouts[key]
            hits = hitters[key]["hitsMinusHrs"]
            lineup_length = team_lineup_lengths[values["teamId"]]
            name = f"{values['name']}"
            atBats = hitters[key]["atBats"]
            games = hitters[key]["games"]
            rows.append([name, '', hits, values["homeRuns"], values["stolenBases"], atBats, lineup_length, games])
            players_seen.append(key)
            count += 1
            if count == 4:
                break

        count = 0
        for key in top_sickle_keys:
            if key in boosted_players:
                continue
            if key not in players_seen:
                values = sorted_sickle_payouts[key]
                hits = hitters[key]["hitsMinusHrs"]
                lineup_length = team_lineup_lengths[values["teamId"]]
                name = f"{values['name']}"
                atBats = hitters[key]["atBats"]
                games = hitters[key]["games"]
                rows.append([name, '', hits, values["homeRuns"], values["stolenBases"], atBats, lineup_length, games])
                players_seen.append(key)
                count += 1
                if count == 4:
                    break

        count = 0
        for key in top_seed_dog_keys:
            if key in boosted_players:
                continue
            if key not in players_seen:
                values = sorted_seed_dog_payouts[key]
                hits = hitters[key]["hitsMinusHrs"]
                lineup_length = team_lineup_lengths[values["teamId"]]
                name = f"{values['name']}"
                atBats = hitters[key]["atBats"]
                games = hitters[key]["games"]
                rows.append([name, '', hits, values["homeRuns"], values["stolenBases"], atBats, lineup_length, games])
                count += 1
                if count == 4:
                    break

        # await h_worksheet.batch_update([{
        #     'range': f"A11:H{10+len(rows)}",
        #     'values': rows
        # }])

        # York Silk
        # ys_id = "86d4e22b-f107-4bcf-9625-32d387fcb521"
        # ys_row = ["York Silk", '', 0, 0, 0, 0, 0, 0]
        # if ys_id in sorted_combo_payouts:
        #     ys_row[2] = hitters[ys_id].setdefault("hitsMinusHrs", 0)
        # if ys_id in sorted_combo_payouts:
        #     ys_row[3] = sorted_combo_payouts[ys_id].setdefault("homeRuns", 0)
        # if ys_id in sorted_combo_payouts:
        #     ys_row[4] = sorted_combo_payouts[ys_id].setdefault("stolenBases", 0)
        # atBats = hitters[ys_id]["atBats"]
        # games = hitters[ys_id]["games"]
        # ys_row[5] = atBats
        # ys_row[6] = team_lineup_lengths[hitters[ys_id]["teamId"]]
        # ys_row[7] = games
        # Wyatt Glover
        # wg_id = "e16c3f28-eecd-4571-be1a-606bbac36b2b"
        # wg_row = ["Wyatt Glover", '', 0, 0, 0]
        # if wg_id in sorted_combo_payouts:
        #     wg_row[2] = hitters[wg_id].setdefault("hitsMinusHrs", 0)
        # if wg_id in sorted_combo_payouts:
        #     wg_row[3] = sorted_combo_payouts[wg_id].setdefault("homeRuns", 0)
        # if wg_id in sorted_combo_payouts:
        #     wg_row[4] = sorted_combo_payouts[wg_id].setdefault("stolenBases", 0)

        # hr_id = "cf8e152e-2d27-4dcc-ba2b-68127de4e6a4"
        # hr_row = ["Hendricks Richardson", '', 0, 0, 0, 0, 0, 0]
        # if hr_id in sorted_combo_payouts:
        #     hr_row[2] = hitters[hr_id].setdefault("hitsMinusHrs", 0)
        # if hr_id in sorted_combo_payouts:
        #     hr_row[3] = sorted_combo_payouts[hr_id].setdefault("homeRuns", 0)
        # if hr_id in sorted_combo_payouts:
        #     hr_row[4] = sorted_combo_payouts[hr_id].setdefault("stolenBases", 0)
        # atBats = hitters[hr_id]["atBats"]
        # games = hitters[hr_id]["games"]
        # hr_row[5] = atBats
        # hr_row[6] = team_lineup_lengths[hitters[hr_id]["teamId"]]
        # hr_row[7] = games
        # fb_id = "8ecea7e0-b1fb-4b74-8c8c-3271cb54f659"
        # fb_row = ["Fitzgerald Blackburn", '', 0, 0, 0, 0, 0, 0]
        # if fb_id in sorted_combo_payouts:
        #     fb_row[2] = hitters[fb_id].setdefault("hitsMinusHrs", 0)
        # if fb_id in sorted_combo_payouts:
        #     fb_row[3] = sorted_combo_payouts[fb_id].setdefault("homeRuns", 0)
        # if fb_id in sorted_combo_payouts:
        #     fb_row[4] = sorted_combo_payouts[fb_id].setdefault("stolenBases", 0)
        # atBats = hitters[fb_id]["atBats"]
        # games = hitters[fb_id]["games"]
        # fb_row[5] = atBats
        # fb_row[6] = team_lineup_lengths[hitters[fb_id]["teamId"]]
        # fb_row[7] = games
        # pt_id = "5bcfb3ff-5786-4c6c-964c-5c325fcc48d7"
        # pt_row = ["Paula Turnip", '', 0, 0, 0, 0, 0, 0]
        # if pt_id in sorted_combo_payouts:
        #     pt_row[2] = hitters[pt_id].setdefault("hitsMinusHrs", 0)
        # if pt_id in sorted_combo_payouts:
        #     pt_row[3] = sorted_combo_payouts[pt_id].setdefault("homeRuns", 0)
        # if pt_id in sorted_combo_payouts:
        #     pt_row[4] = sorted_combo_payouts[pt_id].setdefault("stolenBases", 0)
        # atBats = hitters[pt_id]["atBats"]
        # games = hitters[pt_id]["games"]
        # pt_row[5] = atBats
        # pt_row[6] = team_lineup_lengths[hitters[pt_id]["teamId"]]
        # pt_row[7] = games
        # jh_id = "04e14d7b-5021-4250-a3cd-932ba8e0a889"
        # jh_row = ["Jaylen Hotdogfingers", '', 0, 0, 0, 0, 0, 0]
        # if jh_id in sorted_combo_payouts:
        #     jh_row[2] = hitters[jh_id].setdefault("hitsMinusHrs", 0)
        # if jh_id in sorted_combo_payouts:
        #     jh_row[3] = sorted_combo_payouts[jh_id].setdefault("homeRuns", 0)
        # if jh_id in sorted_combo_payouts:
        #     jh_row[4] = sorted_combo_payouts[jh_id].setdefault("stolenBases", 0)
        # atBats = hitters[jh_id]["atBats"]
        # games = hitters[jh_id]["games"]
        # jh_row[5] = atBats
        # jh_row[6] = team_lineup_lengths[hitters[jh_id]["teamId"]]
        # jh_row[7] = games

        # Nagomi Mcdaniel
        # nm_id = "c0732e36-3731-4f1a-abdc-daa9563b6506"
        # nm_row = ["Nagomi Mcdaniel", '', 0, 0, 0, 0, 0, 0]
        # if nm_id in sorted_combo_payouts:
        #     nm_row[2] = hitters[nm_id].setdefault("hitsMinusHrs", 0)
        # if nm_id in sorted_combo_payouts:
        #     nm_row[3] = sorted_combo_payouts[nm_id].setdefault("homeRuns", 0)
        # if nm_id in sorted_combo_payouts:
        #     nm_row[4] = sorted_combo_payouts[nm_id].setdefault("stolenBases", 0)
        # atBats = hitters[nm_id]["atBats"]
        # games = hitters[nm_id]["games"]
        # nm_row[5] = atBats
        # nm_row[6] = team_lineup_lengths[hitters[nm_id]["teamId"]]
        # nm_row[7] = games

        # await h_worksheet.batch_update([{
        #     'range': "A6:H9",
        #     'values': [hr_row, fb_row, pt_row, jh_row]
        # }])

    async def _get_team_lineup_lengths(self, season, day):
        team_lineup_lengths = {}
        async with aiosqlite.connect(self.bot.db_path) as db:
            async with db.execute("select teamId, count(distinct playerId) from DailyStatSheets "
                                  f"where position='lineup' and season = {season} and day = {day} and atBats > 1 "
                                  "group by teamId, day;") as cursor:
                async for row in cursor:
                    team_lineup_lengths[row[0]] = row[1]
        return team_lineup_lengths

    @staticmethod
    def load_remaining_teams():
        with open(os.path.join('data', 'pendant_data', 'statsheets', 'postseason_teams.json'), 'r') as file:
            team_list = json.load(file)
        return team_list

    @staticmethod
    async def check_remaining_teams_loop(bot):
        async def check_remaining_teams(bot):
            sim_data = await utils.retry_request("https://www.blaseball.com/database/simulationData")
            if not sim_data:
                return False
            sd_json = sim_data.json()
            # still regular season, nothing to check
            if sd_json["day"] < 98:
                return True
            if sd_json["day"] == 98:
                # todo check if games complete
                pass
            bot.logger.info("Checking for teams still in playoff contention")

            async def _get_playoff_info(bot, round_id):
                playoff_round = await utils.retry_request(
                    f"https://www.blaseball.com/database/playoffRound?id={round_id}")
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
                if len(team_ids) < 1:
                    return False
                bot.playoff_teams = team_ids
                with open(os.path.join('data', 'pendant_data', 'statsheets', 'postseason_teams.json'), 'w') as file:
                    json.dump(team_ids, file)
                return True

            round_num = sd_json["tournamentRound"]
            playoffs = await utils.retry_request(
                f"https://www.blaseball.com/database/playoffs?number={sd_json['season']}")
            if not playoffs:
                return False
            round_id = playoffs.json()["rounds"][round_num]
            success = await _get_playoff_info(bot, round_id)
            if not success:
                if round_num + 1 < len(playoffs.json()["rounds"]):
                    round_id = playoffs.json()["rounds"][round_num + 1]
                    success = await _get_playoff_info(bot, round_id)
                    return success
            return success

        res = await check_remaining_teams(bot)
        if res:
            await asyncio.sleep(60 * 15)
        else:
            await asyncio.sleep(60 * 2)

    def save_daily_top_hitters(self, hitters, day):
        # need to put in logic for playoffs here
        # if day >= 98:
        #     team_list = self.bot.playoff_teams
        # else:
        #     team_list = self.load_remaining_teams()

        # sorted_hits = {k: v for k, v in sorted(hitters.items(), key=lambda item: item[1]['hitsMinusHrs'],
        #                                        reverse=True) if v['teamId'] in team_list}
        # sorted_homeruns = {k: v for k, v in sorted(hitters.items(), key=lambda item: item[1]['homeRuns'],
        #                                            reverse=True) if v['teamId'] in team_list}
        # sorted_stolenbases = {k: v for k, v in sorted(hitters.items(), key=lambda item: item[1]['stolenBases'],
        #                                               reverse=True) if v['teamId'] in team_list}
        sorted_hits = {k: v for k, v in sorted(hitters.items(), key=lambda item: item[1]['hitsMinusHrs'],
                                               reverse=True)}
        sorted_homeruns = {k: v for k, v in sorted(hitters.items(), key=lambda item: item[1]['homeRuns'],
                                                   reverse=True)}
        sorted_stolenbases = {k: v for k, v in sorted(hitters.items(), key=lambda item: item[1]['stolenBases'],
                                                      reverse=True)}
        total_hit_payouts = {}
        for k, v in sorted_hits.items():
            if k in skip_players:
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

            if "teamId" in v:
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

        day_flood_count = 0
        day_runner_count = 0
        game_ids = ["99113b38-77af-48a3-aad8-1cb48f679130", "9274e98a-15c7-4b9a-bd5c-e8275b300cd8", "26cc26b3-dc9f-4339-b9f8-5f40c4aec590", "691a703a-5142-44dd-910c-5ea3fe701e63", "57748419-e0ce-4399-96f4-ae535f942ae9", "3159730a-208d-466f-b6f4-c7756aa3a1cc", "2ec0e69f-5fb4-4eb0-aa09-284e8c9eb7c3", "b1c075fe-ed60-4b7a-bfb1-ded6878d9366", "93c80cb1-59f6-4f89-8c70-674c4efffdb2", "b17f09b5-fc41-481d-b494-0b53d8f06def", "ed6ba6c3-d3c1-4d19-8393-05374042a8a9", "be7e61c3-29b0-44a3-a2c6-9c6bb657f077", "3abfba19-c350-440a-9343-8fbea489ba0b", "e561ad08-b913-412c-8144-ff8c8bedaae2", "0afcca89-5ddb-4555-a309-350a1b107a23", "6a00cc1f-9f26-4528-9a84-e6f253a28635", "f3e2c0b0-4fb7-4b96-9dce-f05d90754bec", "88aee411-fcae-4e38-bf84-057012df34cc", "6e2bf11f-577c-4095-95d0-db366b4b1b75", "74210406-9b06-48fe-acde-1f6ee53df07c", "4ac2f8c9-8f2f-49bd-a6e0-d518e32ced75", "b7bb50ac-d06d-442e-83f4-15f4644fc661", "f6b0e995-6292-4f9c-a70d-c20d7c01abf6", "95011bc0-bb43-4373-b0f6-2d90ccaba945", "c0adf4ca-8125-4381-9123-10d3448f0705", "fe643582-c694-4e7e-bc18-6c04bb629ba7", "7523d5dc-4125-49d4-8061-23fe41d70d57", "92bda7ca-d2b1-4b94-a909-e796eb68cfa7", "4894cc29-0aa0-4a68-a326-d227cdaf68ca", "8c4e892f-9c28-4597-9291-2d927206df6a", "22d12ad3-88b1-4f4c-9df4-16ad03a56a33", "c0c93d06-99c8-48a2-90af-6e57898b5059", "3eb58ff0-0161-419b-9c8f-6d379a056d7d", "1d570099-7c0f-4d6c-91e6-2415392e74dc", "e322d071-e0cd-4a9b-8491-699ceee6059d", "9ca91458-728e-4802-b66c-43bf16276941", "1591ff90-2b7f-4fb8-9127-8761c96d268f", "626ca213-c6d8-4bdd-92ed-be074ec1cf39", "0d5fa249-f0d3-4e7b-9cea-28e4753e4012", "18265963-ec45-441f-a924-fa10c1a97166", "e1b8900d-cce3-4245-8798-b51dda16bd6b", "1899f6bf-aace-46ec-919b-29909857f0ab", "22344b08-aa8f-42c7-8f5a-423c154a92af", "b559c055-1bdd-4fff-a96e-aa0fc6377cca", "f8d89073-4a25-4fb2-b213-e46a30b014c6", "2734c432-7e26-4fc4-9504-15576050f223", "3a88872f-a27a-4cfe-8564-09b8e50c5563", "2ecf52c5-eb9d-472a-8903-2245acfce1e8", "8f5b697e-af5b-4f40-b6e9-93457fa25a6f", "a5e36676-830a-4cf6-b64a-b5705966adbe", "3395f4ee-baed-4917-a2e6-317bb5b0c38e", "73f8244a-5fd9-4062-aed4-5243f2aaf638", "9783dc63-6645-4d10-b179-016bad3cbaf7", "327dc6d4-7db5-4d09-95c5-f2386009044c", "37bd24f5-5547-44d8-99ff-4318d47ec521", "0ffc962b-cfbd-48d3-bc8e-dadba75255b0", "c86cec18-4c88-4ad2-a134-25f1eff9e946", "23964a75-b120-4bf8-bedc-64ddc13217dd", "d38669da-05c0-4461-89f4-418f66bd4a8a", "b325f89b-5eda-43bb-ba84-31e10eda39cc", "cba9cbf3-09fd-42dc-b77e-3a6648ec79b3", "46ab588a-75f5-45a9-b923-c10cdae3c973", "3a0e7857-a514-4ec2-a663-9f49bdf291f6", "1efba16f-c05e-4452-ae27-a4e16fe41314", "f11a5a63-e2d7-493b-a5c2-d4c90c6b63dc", "2a761317-10e4-4921-80c9-caff6aaac476", "da7f870a-d795-4e36-8b11-12cfc160361b", "6b8249e6-4cfb-4e6b-bc51-27b29658e16e", "ab6334a0-f2d0-4514-bea1-164823f3295e", "ef1c22a7-e4cc-422a-9e31-3fda74a5c4e3", "3a61548d-ad02-4bcc-92a0-81201ab35197", "647f7fa7-f68b-4752-889d-147a5d6699da", "a500fd55-dd0d-44ed-b122-688626e08c64", "960149ad-98db-4205-9d39-70515f213a2d", "5cb0ccad-9e90-48e9-b5e5-a191a9eec74b", "0fbcd83e-df6c-40c8-ac83-65561bcf7980", "85933f28-c92b-4d12-ba56-cf4bd21fec7a", "a171daba-9dc2-48d4-9443-35df76e43944", "bb06d1ab-25d6-4478-941a-f8e659d69c59", "8bce1b31-6e53-4e18-a998-76306ba92950", "30af572d-b3ae-4ae4-a6b4-93059cd2cccf", "41a6c793-4a14-432d-8e5d-191ca015bde8", "13624872-7a48-4cf7-a457-75a6d883db7c", "d34dd161-9906-40b2-bf18-af8d6ff1de49", "7a79571a-2e92-45b4-ba7e-39e4ce78583f", "7aa503b1-ab83-4d8e-b763-87c4e9413023", "33439f75-5d0d-484a-b4dd-1a84ac41a60b", "6da983e5-3e6e-47d3-8dd8-b0c434a94828", "f4219377-d57b-4d6c-afe6-99725671c271", "434bd51a-883e-4882-8c50-e2ea1e98f72d", "66aeca9b-68e4-4bb1-b055-2444a967bd23", "8e90794a-fbc7-46dc-af31-de60e3e6b4db", "d4f1326d-7981-43c3-b29b-9a419d75eca1", "2daf2993-bbf0-4ae4-ba76-f9612104e97e", "30422284-e451-43c9-9b62-0d3851c4ab72", "9ec53fb5-cd61-41c8-8aca-d1e50de5024a", "1172dd01-5acc-4bc7-b429-c5f339cfe610", "b43668d6-e33c-4908-b575-dfa49bda8ea7", "8278fdfc-a718-49b3-9b13-1fea9355f82c", "4f16c29f-5283-45e2-9c12-b7502a0fd712", "56aad2aa-e21d-44d6-87ee-2f6d9a520670", "e4bb76f3-416c-40c0-853e-3ae28451b461", "608a8b9f-4f15-4e04-bebf-97208de6654d", "0b524179-d54a-4f32-b5a1-7f9eb32f863a", "03207602-7d1d-4fe3-b32d-997c65a0881c", "5142aabd-79e1-417b-95f6-5c3828976d00", "57f46db6-ae37-483a-946c-0a8bf4e45a50", "5205e08e-5ac9-40d4-96b0-80e8b70a4023", "83e42209-fded-49f0-826e-fee2b030d5cb", "6b62ad47-4a1a-4c98-b506-f5281705761d", "03cdc555-16e0-4a02-8aee-945c5dcdcdce", "1d0d553f-713f-478a-9c1f-cf6d33cfd91e", "fd25012a-8cc4-4fd0-8cce-d66ee69de509", "851339d3-3214-42b0-90c0-ad2bcf07dea8", "66a75f23-50b4-4dac-9464-f59bf4dc185f", "40ca31c2-1756-47ec-acdb-d0d333948b75", "e5a2f6aa-2607-49ba-8ee0-31fcccf24954", "7d150475-8d46-44c7-84ac-84defd886f34", "628b899b-e08d-434a-81df-0146cb0c7ba6", "04b94581-1f43-4ed6-84e8-5b41f494f777", "800c2e8d-1b3a-4c92-8e98-b2ae3813775e", "686aa24f-4f10-42a2-95d2-a50d679fd74d", "271b2df9-b297-4723-9ee7-3f2310da078e", "a1d98f60-6fd2-4e0f-9108-2e3450e22748", "8612de95-0dd0-44ff-b3c8-fcc39d534cfb", "28ce1e60-73b1-40c1-9413-9596fded8557", "423a48b0-3876-4bf0-a4d3-d9f639c568cb", "dbdf8664-5b1e-497a-8567-c7be6f4543ba", "581d9914-596a-4bf2-a5d8-8db7043b8d61", "c16169d3-4a92-40b1-aeee-57d20e340bad", "32be927c-d1a5-4672-a1b7-95170e134bbf", "e833cfd6-1552-4c59-90e2-2b9e98517066", "925e1ba8-4fa3-45e4-b740-10513bb76c91", "62ec2c11-8b84-4eab-b6be-1c40909e6270", "a2b1d8f6-ed50-4afb-a698-280a3ee22a38", "84a4aa13-9058-44fb-b56d-ad393f5657a3", "495e7051-6bcc-4cd0-b195-3d814a3b66c8", "5aee3e80-6285-457d-aa81-32fd4c637a56", "dcf35adb-d7da-4a33-88e5-2030b0926919", "9d4e43b4-92c9-455c-80e1-59790685a2f1", "4d898adc-8085-406b-967d-e36321eb2a14", "ecf383e4-d043-4775-a796-48725241a7ab", "ce402aaf-97a5-4a9e-9134-b5dd7ea14d82", "c11e4ec3-0e51-46a2-8eb8-5b7b47960c46", "59b69c33-839a-463b-a9c2-3823466d0359", "2c969659-5a72-4a5d-8161-ef8a73f27f4f", "c119ef6e-67fe-4825-b39f-24bcbfc9b401", "f5c48b5d-bfa5-46fd-b623-a895fa53ec0a", "039a4462-9489-4127-897c-a0fbab6a7381", "ebfccb55-d3bd-4e22-b9ab-b719aaacc0dc", "2e014d84-4421-4180-b8e3-ed8eef6f35ce", "05b4e6b4-12c0-4126-b633-cbb531927506", "9fe12b3b-e9e3-40c5-a39c-d17138405ec0", "556835b2-f1ac-4e80-98a6-87d1e9f7e154", "10fe987d-3624-460f-8e92-b3f19a5a69a9", "38833ce8-b9fe-48a8-b2ad-d933cd3e5b95", "2b5d66ac-ead8-4a9b-a85a-27b76d67a3dd", "dceec485-4e63-4e56-b84c-eaacf97872c0", "ccb730df-af38-4046-8010-ebd5a6d1827a", "c0c4db5a-5227-4fe0-95f0-efe158bca5d5", "b7ac49ba-9879-4223-b8b4-3deae2c8ec16", "79ba9369-1c29-47e2-8d68-01f8ad1565a6", "8291881a-d6d6-41db-b99c-4ac5ed99ea38", "e6d213ba-602f-409d-b1f0-2b7c430dfbbf", "3f3cfc27-624c-4346-b6df-4d1e93a6b7b6", "3572ed73-f953-4599-8a16-3cfd1b8df4b4", "6fbdbc86-1f1b-496d-b97a-3b54698188ee", "d296f94b-6054-455f-9ed5-68cb40b9d362", "7d703b87-9fad-4604-b793-f1e66c7443d6", "7d3949b4-cb6a-49e5-8a65-4117d415052a", "e06e8d60-f8fb-46d6-a5a6-9742d107ba0a", "34e4490a-1332-4d49-b0fa-0994bdc79664", "c8dbb71c-7bc8-40f0-9166-1ba2391f4a51", "1aa65607-a53f-4e6e-9350-76e0324e4d93", "75ea1806-0277-4904-96af-f49f6f3f7961", "4efd6f9e-8e70-47b1-a9b0-1dd967148065", "3b2bd5e1-e74d-4b52-abf6-2e7d0b0fd4f9", "f7dedcd9-3920-41ca-af7a-cb7969515fb0", "e9b600ed-ebd2-44c4-9598-7bda8d2970ec", "9f0bfef4-fa6c-46db-ae14-d843f68d847f", "2a8b42a4-68bf-460d-93da-ff12e60e729d", "e482530d-6af5-4bf5-bd70-7abd3c417223", "6b99dad6-bf77-4f99-8fd8-2c0d4caa7e2f", "9f7ec9eb-480c-47c9-9869-8737926f69f3", "2fedec00-d510-4bf6-9952-28241f931aee", "c1a95c9a-cd9b-45b4-9d5e-751c5346088a", "e9db6b98-ef7b-4c09-9d1c-d4f8498c3d4f", "c87d2155-a791-47dc-830a-0e06ff2097be", "a69faab8-b8a3-4368-bf7d-086d9f3cebd5", "c0de1f40-3f17-4b4a-b669-4d6687e15bea", "ef85d505-4934-4d49-878f-9c3863940f12", "7f9e63d3-62c5-41f4-bfdb-b0eb2903b42f", "95ae569b-51fc-486c-ad02-b14d76fa03cf", "8b7604c6-0e91-4786-94cc-d22fce4daabd", "55267ba0-9e60-4652-b753-80bc453fe7b7", "eb3ea7ff-10d2-44cd-a1ad-b5d2f6438b96", "26377941-a228-4bde-8d05-56079136df1f", "061878a4-843e-4a69-a56f-3d6ae4651388", "d3062272-4220-4631-94d1-d70bd4777b41", "bb21ca31-2850-432d-9923-9bcb57906750", "77f44029-b37d-41f7-8a90-daac9cc1b3e1", "fbf59b4d-9f20-484b-a637-0367febd1851", "8687fb76-3ff7-4b04-b22b-0cd3bad33051", "e35c2abc-1bd1-430d-a3cb-974c86f3bf07", "45678010-3ea2-4d14-b890-f9a36ebff7ab", "0c12b305-6c06-415a-865b-ab0b1272c04b", "b525a327-9b04-493d-a8dc-f6ddd4310852", "a7e7a814-3033-4c74-9a80-36f4d3a12adb", "1aad07e1-7f2b-4493-96c7-7b858a6b819b", "e45784af-d50a-42af-811f-e42617e8e618", "b22ea2f1-d5b9-4b53-aaef-f2fc3fb3d931", "4f56e972-5741-44a3-be3d-2679cd7e6027", "249aa9c9-f8a0-437f-8699-4b7e054d6e5a", "f13cf582-0e95-4c6b-b4fe-067c2cba4650", "7af83a32-8605-4bd2-a2a4-b4e82229324a", "6c5396bd-bbe4-45df-842b-72d9a01fff4b", "ab586820-242e-4c2a-b611-59a8a85e93ad", "f930da04-8bf5-416a-8b99-e58fb550fa0d", "1a4bdbfe-f26b-445e-8641-bee379f06ab6", "62106fa7-7133-4c9b-a634-084ae0fc9b57", "e539a967-aafa-4b06-89aa-737fab01ac34", "41a87540-329f-4e7e-acc6-334163cb5927", "27100629-f8ad-4b81-8a5f-54a596486860", "31d7afa8-7691-4259-8d9d-df3bcda0d2ba", "4a90a582-1492-4b4b-935c-173c375cbb87", "e1a55d80-cd91-4fe2-ac97-7cc5c4d4fd7c", "ec2eb4d3-b81a-430d-90c0-328371126cb2", "4f1cdaab-2f82-45cd-9102-98753307c750", "96c4c583-db0b-4896-b786-98ddbeb941b5", "4a783901-7839-4ddb-ba46-da45454c4dcd", "2a22427c-f20e-4787-b85f-7be79028184a", "7c30a93a-1d6f-42d6-adcf-bd642a28bfba", "8b12fee2-1187-46ee-b7f9-3110575e83f9", "ee306e29-1726-4778-8c53-f18bfaf6839b", "f30baaea-5ed0-464e-bc3e-24fa45b26a0f", "42130e89-b7af-40d7-bdc6-d90bbcd650d6", "5ec7c764-e4b9-4a87-b666-232151615f6d", "25e6d1cc-9431-4045-86b6-cd258d6b3d6f", "1aaef0af-af1b-4ef6-b315-56452a40ec48", "ef375c0d-33ef-48c1-9d5f-37ca4df62d71", "3e9697db-625d-4273-ab6e-087242e76f52", "b6f29a6b-6f6b-4e73-a6dd-4d434d1fa257", "2ba45b0f-bb4e-44cc-a4f9-a8feb5a14e37", "6b9835ed-8454-41c3-ad57-e6db766fadea", "c0dae63e-eb0f-42be-962a-dc49fad39c9d", "9fb8e108-2aa3-43b1-b730-f9e14cc861d4", "c948f4f1-fdc4-48b9-84ea-f2e5a6cca68e", "e6662501-d404-44e7-b0b7-9a1ccd68631f", "4b84b94a-696a-40ca-9e90-7169f52f60f3", "873c0a1f-e375-441e-aee6-39f4326bd231", "468190fe-b78e-4b80-acb1-a2af5799356b", "dba6ee6a-06ee-44ff-a5ac-834a31b08fd4", "5b1e01be-a802-4bdd-8a76-2f0e14ea5359", "fe81ff82-ddf8-4fb4-ba00-2b432663a07c", "dcbc2123-c46a-4d21-8501-302f84ca8207", "b22fcbc0-57f7-46ef-98fb-ef432be4160d", "bf9a3c77-9caa-410d-a97b-9101333ccd29", "ca58a1a4-7d37-4306-8550-2b9aae04b46c", "a1135c4f-9cb5-420c-9452-add5c34e86f6", "0ea7896e-81fc-4113-baa5-65abadf5af9d", "3ad12442-2e6e-4b12-9388-f092e2267c38", "ffd0a40e-24c3-4b5d-8a51-34e975565ae6", "b3f799a9-2dba-47f9-ae05-621334c1c2b5", "c7bcfc0c-78a3-48a0-bf50-dd00eb907992", "ec2359ad-1afb-45e5-9775-1ffbc7f31e67", "c9b750a0-9abc-496d-b761-4c5bbd537e79", "7b3b23ef-053e-40fe-b7a4-c103b58c44dd", "e2f2bc3a-5958-469f-81a4-db115d977392", "d913c9fe-7e33-4843-b1cd-cf94cfa910ba", "768c3770-3557-4acc-ae5c-a9312ee4db79", "d2f74856-edde-4a60-b438-fc980a00b53f", "619f579c-d34a-4025-9f7b-dd65c6ad10f8", "47954361-b60d-485b-a8af-264a9fe29f60", "f72e0080-c9b7-475a-992c-f429b909ca2b", "653b1920-117f-4208-b726-63b6cd35b096", "8bf7a094-075a-4b8d-a0da-35c0f31f0268", "33a9ee54-2850-44e7-8677-510651c32931", "0ae010ff-6763-49fa-842b-133c523149a2", "3eb1a992-de15-45ac-9ae3-78e947df6189", "7a1f1e0d-3979-4e6a-9193-0185d2572227", "c0f71e56-8dc0-4892-9fce-00699983001c", "dffa1a9c-d6ee-481d-9797-54c5ee06a118", "b748921f-19d9-4c8a-8a14-cc60db8acfc5", "a5c111d7-64e3-46d6-9b80-949846cdb416", "56fd609c-5721-404a-bee8-02ee57157fe2", "aa8ac27d-036a-4e0b-83d7-9ae9aa725d62", "3037984e-7ab9-4eab-a3ba-f86653192f81", "69a3bd2f-e881-459b-b3d8-bc63df209e22", "e0099095-8afe-49de-804a-3c59fa9e6eb6", "dafe5e9d-7e08-4d9f-abbb-d56b33cd4d42", "64463694-ba89-4d15-bc9d-b75c423fbd12", "64d19767-0979-4dd1-b415-61f8f5da25c2", "f4292f15-016d-405b-ad00-85b7fbe21888", "9e3f56ad-eac2-4da5-a08c-abbba4982c1f", "fac78f6b-8516-437d-b0ff-a2f9a636e8fa", "a87cc092-19f7-45b1-9ddd-af94dddbad45", "d909dc5d-ecff-4424-ab52-3b8ef28eea9a", "6aeff6cd-8403-4432-b1c5-4a711654740e", "81ccf0f4-bd12-41d5-8eb9-2cab5b051d77", "a68585ee-e364-4c02-9500-ea31f253cfb5", "c6289993-651b-4685-b810-eb24c51c2a84", "a7c9a606-a75b-4aed-ab33-6b52c3a6899e", "c0c84844-9570-46fa-96c0-7381c03911ee", "2ee8b79b-23c8-43c2-9e3d-6a818ee67a90", "d0a612b0-d6fe-4728-8e83-dea41b1ffafd", "ee35dc73-df73-44a1-ad47-f550761c2157", "65c112ec-35cb-4c38-8585-105faf61f062", "651285f1-15cf-42d2-a5f7-e91d112a60df", "0e75d257-7d8c-4fcc-89db-b63b7b06bd46", "7ed3e5e0-e697-4807-adcf-1964acce502c", "451ce85d-3297-4af1-b9ba-0105da061e65", "13233267-36d4-4171-93f9-97c446aa22f1", "780ba721-b6b4-48aa-845c-36721d8b02c0", "11db81cc-a126-4f0f-866d-30ea7b6691e1", "8f9cde6f-9f38-4bfa-984a-0170d179fec0", "632c35ca-708a-409b-9d31-3bc3fc2c3469", "f4c1826d-a946-4933-89d7-f7ab9f0b49f0", "130dc51e-9570-4fc5-a64d-fa63a0d6ae9e", "ebb88869-2a9d-4d4c-9d9a-5ffb68eef017", "ab636c0f-ec96-46f3-b3e0-670ebf67edaf", "af96b8eb-bc05-4ab4-8c63-5d3f782be874", "9dede6c6-5aea-41cf-8462-9717c124719b", "45cdeeb0-48b5-48f6-9add-c8b2a69c1baf", "3ed84b93-f585-4602-b2cb-0bbf41c01b4c", "8a59b6cb-7f1e-493f-a78a-9733c08e7fde", "1027cc23-3e39-44ea-a764-c43549830489", "690f7d74-f42e-4b2d-9b61-db86471fc4eb", "94c7203a-15fb-41a7-85b9-f7db2f6cad8e", "cff19e0c-8a5e-43c0-ab4c-6bde783151cf", "04ceb042-439b-4f52-a99d-dc68c0e4388a", "70d81d16-36e7-4f81-bfce-f66af041ea89", "bbbb3450-6fb8-4c49-8df2-131e5f1ecf04", "b0a2d04c-07af-4600-9e53-94c9b1272bf6", "59d7b6b4-5d48-4bbd-944c-079b710e38a5", "5ea2ac67-272e-4519-95e9-5413a8c74d14", "b6752ba0-5c41-4120-a512-c67ca032989e", "443dfb86-af65-4390-bb7a-71c9f1814c01", "a332c8be-2b89-49c0-afca-4c0a4a3be75d", "fb30c27e-8353-4e04-b046-67953fce59b9", "9822eebf-34cc-4a38-93b9-f72a513410d2", "62033258-e28e-4a2b-9b0c-25d0ac01ea77", "2074fb52-7be8-40b3-97e2-d3d3e25938ef", "ddc774e3-90b0-48bb-863e-1f56c8c03318", "e09e932c-871b-48a4-a152-cdeee7cb6251", "f92e8bf3-2ef1-495b-80c4-041766535ebd", "26b8ed90-329d-4ee8-8532-88597a408b6c", "377a725e-e4a6-428f-b966-0f012ab4ced7", "05226f55-ead1-4d5a-b556-a676ebf161be", "bd7528be-caf8-4adc-87a3-87ec1f9db5b1", "07dbc407-33da-4c5a-a710-c2cab5addcdb", "0c1cb3e3-d69e-43c9-b5a9-6439cee03fa7", "e2cd070c-5862-4aad-b7ab-7d8fc280bdff", "46c0a8f1-7527-4c13-83e0-0d3b696ed181", "a70eb0c3-7854-44b3-978a-f3a7bc6543bb", "451f5050-f4fa-4919-8d0b-db6f87bb14ee", "ff2252c8-3786-4115-88c6-af8ae89dc9dc", "39e0835c-6cdb-4aec-b083-c1d29f90aefa", "7b5926f5-0e05-4eca-a0c3-843681b78bed", "0eee3dfa-bc33-4348-b78e-bbf33a770810", "e2479263-8b18-4ac8-b637-60ed1cd915cb", "a05e7135-2eb4-4445-8e84-1f465b54a58a", "45d6d61b-2c2f-4249-9602-30efc7661951", "06823e7d-3d30-4938-a414-e2533d49f416", "7047fcc4-42e0-47fe-a27e-64dd5c5b8918", "749a273e-9c33-4457-8ff8-59df65733901", "0e3f1027-2422-4e4b-8557-eb1b56a9b7ca", "b7242db0-7a4a-4b99-ace7-2d6ed012f79c", "20923569-4403-4d8f-9da6-c60c719852ed", "5811a45e-ca8c-40fe-bbf9-40910f0096cf", "1d0da858-90a6-4600-a8b1-b4315d3929e3", "2f4a6f5e-8e83-44f1-9ef7-688484d92fab", "653898e0-a4c4-472f-a3d4-bbfa777c2732", "7cca61bc-c0bc-4a0d-bc07-f97df72c3441", "bc1b1ee6-cc1e-4f34-bdd6-b54929982585", "3a5865e8-0cca-4fa1-8bfe-e9d4c339ddd5", "cff77449-444c-45ba-bd1c-faf73afc0ca7", "6374295c-d49a-4db7-a91a-bf27f013c4cb", "48b1816d-7dfc-4d34-a253-1d5dd0ece593", "1100e294-03e8-4fa6-bda1-efede89e1dda", "10112e43-67cf-4146-9e44-1681bab75d72", "f5371772-7fec-45a5-ac8a-e36045e1bbac", "889a5656-59e9-4d59-b076-93328a4a196f", "4a2dd0bf-4e1b-44c4-bfd4-1c186c670596", "87dabfb7-092f-4254-aa42-57c82cd19d51", "447eeec3-a34f-4dc3-8456-57b31aab2631", "8337d378-79e8-471d-a977-eb32e2b985dd", "f7189407-71ba-4409-8ba1-30caf8cdcd2c", "2696a7fb-fda0-4697-a883-fe2a7e75fabe", "bb121f9b-7b05-46c3-9373-8116441a9dbe", "e2f64cca-dfb8-46a5-ac1c-863d30789815", "1959774a-c53e-4fb8-9d9e-93665b5a638b", "48951160-1a4a-42e8-83ac-2272c03277d1", "4b89879a-d432-455c-b143-7ca276cda8d5", "8e6f2ad8-ef36-49ae-b2e5-7722621399b0", "76ca2e7a-7fb2-4bd0-be42-35afc75356e5", "f964b4e1-357a-49e6-a150-ea167af95cf8", "14244761-af4d-493b-8fa5-31d8c95e0b4a", "c9ce0d9f-4e18-4675-bb3c-0fcf19c7e2cb", "e1ef5cbe-4d34-44f7-93ff-4ba6f3b74d29", "fa9e281b-4256-4c79-95fe-6242a8bf8f79", "9b1021d7-407b-4694-9a39-0bda86d47d88", "4644e239-1091-4657-a62d-f7c1a7f1d869", "d41babda-81bd-4992-a0e6-b389db1b080d", "1d0945ee-834e-47a2-a800-658eb6e51741", "fca08829-0fb9-4060-b1b3-d3bd9b854a30", "f39475a7-862a-452f-b202-678cd3d48130", "b9ee812f-a695-48d5-86a4-6908038f0320", "9245066f-d3d7-44b3-914e-12ef1a65cd64", "9642899c-876a-4efa-8a6a-5493a25e14ae", "b6ede4cc-13df-408d-959e-04b25afa8d47", "71b4d637-6043-4f47-90af-4b3c7845cfd0", "4a793637-858e-422e-a982-213f8e4a13b0", "8831d3ab-6230-4b34-8e72-791c8e6c4834", "3c25761b-1708-4c5d-865d-279c55c441b6", "a12d2435-7a16-4519-abd3-464e8b283578", "b1fd7aaa-922d-4844-a735-c7cd8f1afe72", "1f0514df-71dd-4233-bbd1-1e2a5b2b1cde", "4694ffb4-bc99-442c-b5aa-5e556ab4ecf2", "70b9a295-3a4f-4d57-a660-dd5aa0eaafcc", "2196610a-cf0d-4367-966a-4d09c9f83be0", "c3e5ab37-5d3d-4ca8-a945-5ab8f0d2d148", "cf6c0833-5a3a-4cf3-a1dd-7814dcad5cda", "75a43400-97a9-4b8a-8516-60c831d7b931", "d95d08ca-84b1-4ac4-bed9-eedc04cde56f", "2c787f33-5f4d-4c0a-a44f-49709ba2969a", "856d3c21-e681-4f51-9419-6746d7813024", "e071692d-ff09-4558-81ec-9e99bbd21bbe", "bc21ab2e-dda0-4956-8b2d-8b663d54a3ee", "0df42cd3-64de-44d5-ac57-6dfecc7b0da8", "0925f4f8-2aa7-4fce-80f7-15357291fc9a", "27f72b7a-23e3-4f5d-849c-caec4efad21e", "08e2c78a-0042-4122-842a-28133a7c2268", "df302967-01f2-47ad-b2b5-fe1a12927d60", "d8e2cb49-bb9d-482e-a61e-860de84ef3b5", "bacb6496-d2ea-4ece-aacd-6ef2d91faa63", "ccc05523-2bf3-431f-adf7-356e574ae113", "c62aa7a4-1e23-489a-a8a8-d71fd342dba5", "c3e2515d-fb87-4314-977b-d7ff0a8316ae", "7e819bfd-c831-486f-9693-613ee52da621", "a12ca464-d81d-417d-99b8-9248c4634d82", "8467ea4d-a963-4755-af9b-05db0dd34c38", "4c74f2b0-d4c4-4bed-892e-1e77b043e373", "87195e42-b751-4516-910c-88ca3a203100", "7919ac74-d005-491c-8adc-05664c398745", "795b81bf-7241-4fe3-af98-c80918edcfd4", "742c5f3a-9a83-401c-a8de-bcadd064c76e", "fd7e0006-0f5a-4cf5-b179-4399e8fcc7b6", "0e8feebc-d9f4-45d2-ac66-54744382d480", "c36efec4-f27a-4a85-a2a1-95a7a94e0ca5", "f829fa59-2eec-4c73-9877-567eefe380d2", "b97c6b25-fe86-47de-99c0-5d862f38dea1", "32eeedfc-11a6-43b4-9428-dd50a35b4a83", "6cbcb743-bbfd-4ac0-9d22-85d2bd3bb35c", "8576ddc4-4464-40e7-a588-79226e183c2b", "f0d2de86-6e19-4a09-8cc1-ab3224b8753b", "b936d236-edcb-4ab2-9abf-e6bc433c568e", "86a26e9d-4bad-42d9-a059-7b8327105440", "933c4ed7-1a48-4024-8261-f527b694e243", "aed1edf7-1f26-4615-adbd-f5431b77de1d", "e54a9e15-88ac-484e-8900-4adde442ba99", "c9c94bc2-7c34-4803-9df2-0c3c3bfe183c", "f2ed1b54-4a7b-4aee-8303-ad683821cbed", "0e8d9532-1156-4217-84db-e6e11e1bbb20", "15b2cc53-0ab3-4dd8-910a-7846dfbff29c", "11c0f353-d747-4086-a9ff-6370ca40bed6", "8799ea10-69fc-4df3-ad1e-983803433412", "84ff3468-37ed-4d79-83f1-770aeed0511e", "e2147470-6c67-4df7-89b7-9816873b25aa", "063ed5db-3117-4a41-8996-3f8d31e8ce7f", "c27931cc-45aa-46bf-bce5-6fd8548e4212", "f8adc703-1cb9-4c25-8772-0e26156c8138", "a8150cd2-50c3-4007-a3a4-bd388ff880a5", "3dcd7283-a745-4b38-b17a-8d0c14b2fc5f", "6e6505ff-37f9-496e-8253-b15dcaf3ebbf", "48e7f29b-d488-4892-b332-ba864a66d07c", "2c5215cb-eaaf-4314-9dfa-a4f88f3697de", "8e42a845-33ce-4819-ab16-3709a5bf35ce", "1370a08a-42b6-4caf-bf87-55ceb035e619", "3b1f95ee-4a2f-4d51-8329-0dca612cb2a7", "ec999334-ca62-4270-b7bd-d8ab64fbc39b", "4d490394-c4a7-4107-a3ad-c91148c2e91c", "5e03788c-f6eb-43e8-9907-8d9525550304", "c20cc2a4-c77f-4106-ae60-58381a70b071", "7008901b-2ae6-4395-8555-86b6edefabe5", "a5aba34c-8a94-49b7-907b-ed34549b5398", "5cdc53cd-d0d2-45ac-a9f9-978817452560", "1e2b70ea-c700-42cf-acc2-3f4b41827c26", "05ceb04f-56d9-4fd5-84f4-7b1a77c9ec76", "92df7cad-55ac-4539-99c4-da72c6c2bda5", "dcc5c18f-535e-4a4f-8024-9aa025897ee2", "016c13f4-c081-46c6-825b-6a4a0f454e19", "3d220f9c-d18f-4ccf-adee-adfd0a5fe00b", "b261cd05-52a0-4d1e-8bf3-3dae0124c55c", "80540093-8d80-490c-8018-f36b492bc9e4", "044d1400-2fbc-4799-8f45-51085873965d", "83c27132-3eb3-4f44-80ba-73cabf2b3030", "d52eb1eb-9a98-4149-b207-4d97a9c82322", "7b0c7729-8d36-4f50-a077-4ac327a54961", "d0ec904c-6a31-42c8-baaa-62250a2f00f7", "1c06da52-7aaa-4235-8722-716d7eba9713", "de87f56e-14de-4d29-955e-b88864076d2b", "68a04644-ac15-4ef8-b008-cfdea3721f91", "29a1dd19-e479-42a2-9067-cdc63ceb32cb", "772bc9e9-d2ef-4cd4-97ac-50165337a022", "b35f095d-9bc9-4a1c-822a-3749a7b83bcb", "01a99c7a-e569-4baa-94f2-13c6b746f609", "90b009ac-b946-4f46-8d76-424f87d38d25", "adb01a92-f4c1-4100-bf4c-c3cd967f8769", "dfedcc06-ff70-493c-b210-37b585423960", "b7d86625-1ca9-4cba-810c-93fd2ee27f32", "90f195e0-d80d-43ec-8207-d2a65970dae4", "0e49d58f-4128-4276-aa69-32b94458cc6b", "bdb36bcf-c798-4a52-8ba5-875420c07d8e", "59e75b23-75cf-485e-8633-5ab4f4a857e4", "91efe926-73e7-470d-8372-9a8ceb3b644d", "805d938c-4270-45a5-859e-b9592e04e013", "b8f09848-8f22-4790-be4c-e44689e18af8", "534f5328-4a19-4091-86fd-182dc438d9e5", "6f5a6a45-186d-4c6e-b3e1-471b7f67cdf2", "f203cfd6-844c-4a34-98dc-88ce54779509", "56a4842f-44ab-4b71-b88c-29874b04e6d3", "b8e60742-c50a-4fd8-a4d5-c838f913b712", "d4d5a7ac-e8c1-4303-b654-a863c2e2c412", "b48ac0a6-7eb9-4550-b20d-e04fd53912ce", "d6d7f1f1-c197-44a2-83bc-2742bac19f95", "d3d306f9-46db-4dd7-8fec-7a7a39c663e0", "1cd57d39-18e9-4e3f-9bd8-095d5e84ec98", "6692ad15-99de-4989-bd7e-0104bf86eeb5", "28e3ca7f-ab40-452a-9a04-126a74b3ec13", "c491de55-7290-4752-b959-8288cd673887", "bfe640d0-2f0f-48ea-8623-3289a1ddc86b", "ab892943-ceeb-4871-be36-9f4628aaeffd", "f5c14361-6955-4d19-a734-a99ae285331a", "5f4d5a16-8c7f-47c9-8eaf-3683405f0f0f", "277ac88a-4c7a-4812-8cf5-94e21704fbb4", "1ebddef0-594c-462d-b3ee-058509563f63", "7a939677-38c8-471b-83d6-1f4bef8c71cc", "73e68ca3-a0c7-4813-b92e-e6261261b4fd", "5bed2ddb-3f79-476b-8219-74e250013953", "929664d5-a860-40ef-88ff-caafbd2779c3", "403daf9a-f492-4627-9709-cb55a39c88f8", "5433f061-edb5-4b1e-95f1-f90a9a5a1060", "3d4464cd-cd12-4193-8689-1d43dcb5b7c8", "4413a06d-9d9d-494f-b8e6-038beb6803b6", "db918ece-458c-4c7e-ac33-fb7987069004", "bc9d9b1f-772a-47b3-aac5-47642da38251", "75d4713b-3d95-4667-a6b4-8c122e0aa48a", "78aaf54f-cb60-4c77-87d3-20cbafbaa627", "490e6795-44e8-4ab0-b90f-9eea637d28ba", "4cc49ca7-d79d-4ab0-8bfe-a5b971211103", "d45c8ef8-3cda-4b95-bfb8-67ebf3404f8d", "63caa9b2-4e99-4f43-9bba-a5620d5da29b", "eb60734d-eb82-46a7-acb3-969e3f203f35", "c5ab934f-1922-4ab2-8252-a97e4aa240d2", "38f91437-54a3-40d1-b35a-594cab115baa", "e6c3c5e9-372e-48dd-a27f-7e1f55955b63", "68abc1ab-4bb6-48a4-8e05-91d7311ce4e3", "2c701ea0-fe1e-456a-bba2-395d8ad9f125", "8ac77e5c-fa21-4403-9b67-855d6a469e92", "15756d82-a959-490d-bf55-26239e3b427a", "dde90034-279e-498d-a41c-20a31bb02e93", "9789292b-97c5-4de0-a16f-d559b721a607", "cbdac865-c251-49f3-aac9-a504b1f97df6", "ec5107bd-18f1-482b-ad98-2dee7aaef1a8", "7612dac7-21d1-4234-a9fa-5a8ec1030859", "bfa15d0e-ac59-4801-a619-e321f6fd2b24", "848468ab-3f7a-4490-a22f-2b06466b54ab", "01f43699-b9e0-45e9-8b76-4033a572f23d", "acf338f4-b820-45d6-a7c3-7ee4242293db", "e92b6bdc-f7fc-4d7e-b7dd-a53b3967cfe9", "c84fe866-23a3-41d5-93e1-76967e0addb2", "4a5cd958-7c14-48b5-8923-cda928d67190", "44194389-96e5-4760-b861-925ea8f3a2b4", "4cb7ecd8-0918-419b-a17c-165df36fe615", "2d482428-2eb5-4c53-b3cf-8c7350bc9452", "961c135c-06b6-4460-8166-6f69b1963424", "260e9c25-ecdf-426c-a18b-266520acb8e8", "4d8f002b-282a-458e-a76d-4bc6c37fea8a", "6e1b9f5f-7ddc-4136-8751-00ae9c893bf9", "5827b3fe-67b8-4345-8e9d-96cccd6518fe", "3841a5cf-d982-4b21-ae81-80d8347565dc", "5f20d8d1-bcb6-42b6-8434-852acaefc005", "b0efc638-e2a7-474d-8535-271da0fd4535", "08638fae-c6f2-4698-a65a-1dfb6d5b1458", "6d5cadef-7192-42f1-a1df-3e61df152e1a", "ea7e391a-8c5b-4547-b520-a7ee44a9946c", "857fd0d6-974e-4fe4-a3e0-74cb38f2e62c", "7e1907d9-2457-4e88-b7ed-5c8174011903", "749674c7-8590-4eaa-8d2f-93fcf3165591", "e2e10167-3b18-4934-bd1a-c3629fa3edfc", "0114739e-8e98-4e4f-b387-52ad0a60c9fa", "efabed30-ddc7-4396-a742-90ac60a8fa30", "adfc1a1b-e59b-46ed-a509-48a5df899988", "b024e7a4-5375-463f-baad-b73dacc9d24d", "a0d0fb26-3aa2-4af2-99fe-08b4a34f439c", "bdc58e76-1b80-4528-b3eb-5ce3cfa2ee51", "6cca6460-266a-4e2c-8a6b-0c0cc1097f5f", "8b4a0984-06fa-4d65-8687-68d63579c2c5", "ae619683-535c-46b0-b503-2d3e2ff21bfc", "983d137a-670e-49a4-aef6-e6bc6c74139c", "670214b2-13c8-43a5-aa72-9a62432643f4", "96e912e8-1f89-4235-b246-b6d517997a1a", "f5333b28-7d7f-4966-b861-16cdb9918e53", "81956ebc-081f-4dac-8ee8-53893496a48a", "e8dc41e5-6ac5-4102-b723-b31e2b19138b", "0923b3fa-be73-4e3d-a7db-d423dc7e18ac", "bbcb3c19-82cb-4350-9666-cdcf3df8dd89", "0d20861f-816c-441c-8ad4-a57a7898fb01", "524cedb4-7165-462c-9a16-f9c187f95f37", "9ae136e4-04f6-419b-9edd-ca6a88dcaf77", "3e6fc617-9fbd-4cbf-beb2-1a90fb2f8782", "191e39e1-bfea-4ac1-9ef9-2960d40ee07f", "630d926a-a868-42fd-837e-eacac827054f", "24404ec5-b738-4d2c-90ed-d0a1bede0b08", "17375d2e-5261-42e8-95a2-96c9421ab354", "c03c6495-d850-4ce4-9438-338d50a9edc4", "78db17e6-719f-422e-830c-d70233df30b7", "1aa7e5e1-facf-4ee3-ab78-de92eb88be4f", "7fd29202-d725-4167-8303-fb40b0b14cb1", "e5a8e9f1-a065-4552-9333-4772dcb9de69", "fe142929-a872-4863-9e3c-f974805d07d3", "0cab391d-f1e4-4d69-95a4-19b130b4aff5", "c4d39701-16f4-43af-a4b0-a6bd6cfb2d7f", "12dbfe5f-2812-4755-b6ee-0f36faf011c3", "bcadc72a-b1bd-455e-89de-b0a7bd978477", "4f28d538-9bb7-4141-a37d-1d67425236e8", "5f76c816-d6a9-4984-94a7-2da44201e85b", "db3512ec-5ddd-4d7e-88a0-62de9740c5d2", "826548b2-6dbb-4436-87ea-7ebdd6a304ed", "d102cccd-89cc-40ae-8ec0-b4734b1d1a30", "d85e8451-7562-44be-bf0f-5a849f86a9d2", "1ca49899-cfd5-4619-9e98-056acdaef2d0", "485dcb27-eab9-486a-80f1-dca11fffb167", "e9d13610-9821-42f7-933b-927e4f70dd5d", "57f7f2c3-b25d-49c0-8594-5e7e7f86cd5e", "0e385bd0-b088-40f2-8607-0da368ee60b7", "7cece4d1-f451-49f2-935c-a854d75ff072", "821ec840-4ae3-4124-be60-6cb366398be3", "e7b247e6-626a-4c4f-8a32-408621769e53", "aeac9740-6fd6-43cb-86a2-a1f5ed56b195", "232f0083-bc94-454e-96a2-da367c5b7a06", "d05d8db2-08f0-4d01-83ac-2de1962b6399", "a65a9171-0052-4c62-831f-aa5ad2f4a7b3", "768e266c-9c34-4cdc-8e64-33f4ef3b382d", "9b8f70a6-9e66-4bcf-a7f4-19f9ba855d7d", "981588ac-aa0e-4fcd-98f9-fb6bb7b3396e", "e881128d-3cfc-4311-a7a9-0e6b6dee1f25", "cc8ee11b-0382-45f7-bf60-1e07630190de", "b0b272eb-0242-4b27-a5b0-1146cd4237f7", "6f8fa107-23c1-4081-8fb1-678cd3a01bf1", "d2430b8b-4eca-4b80-b92f-caae9e29eecf", "a34259de-3bfc-45b6-bd68-eae438ede009", "982194f0-c8ff-4b4d-99b6-b8cf83a73090", "296e303d-9338-46d5-be4c-142214df0e89", "20cf862b-201d-41ad-b9fa-0971a5d9d856", "5ffd315d-53ba-4f1a-aa1a-e74c308fa6a3", "3795d8aa-12b6-4ee4-93cd-77997a06646a", "1cd4165e-4c13-4614-8abf-76a55cbb5a42", "34d94e42-f9d9-4c37-87d5-b662d5bd4259", "3f21fbcf-bc5c-4bb3-9831-82be44f50b23", "27d4e641-135f-42b8-95bf-902e84691688", "9e729390-1294-4e4a-b9b2-3b7a2d8f67ac", "8e1e09e2-0c57-40fa-906e-5aa60d70a6f2", "e9d70fbe-d4ea-415d-9e03-91b96302804e", "3de02fa4-f3d9-4ca7-9fc9-dbae8f7ada67", "c71120c0-9104-4914-be57-161ed15a3cdb", "2de4638a-d95a-4a8c-9c2b-01519a46c74b", "085af7d9-2ea9-4485-9fee-caec5956032b", "df718e8c-552d-490f-b3e0-951b2cb30f66", "98b3ca86-7cb9-4054-aff0-648a97af1b1b", "e5b4308b-9df9-4c59-8873-37bbb55b7f2b", "e9980459-3d0a-4ccf-af0e-3a1106e31ee2", "d3e9bd79-c5b1-417b-bdf0-fbb8920ebf2e", "f148f6b0-a360-498f-a189-a213269b9534", "daa0f99a-3b05-46d3-a7cf-d03e4ba7d42e", "2225417e-3c90-4423-80da-708102dd938e", "17529818-64db-4046-8191-0a5f3b4af089", "ad34e28d-64c8-4b53-805e-fbd2b75da2c9", "2cc9903e-c42f-40ed-b448-dd86f7211da4", "9c2a382d-f1e1-4d2f-88e1-620978037172", "259af0f6-1c07-40ac-b14a-fbfa1990aa24", "bf090bfc-0b4b-4654-bd85-f2ec3123341d", "d2bcb35a-689c-4bf3-a869-07a8e101e597", "bdbf2441-2f4b-458b-858e-ea0417369603", "397ca807-81e9-4d78-84a8-4f423cfe832c", "42100978-b382-4cc4-9549-acf74cd225b1", "73ccded9-b2ab-4012-a6ba-f0e1dc5d8e7d", "a1ad2005-7bb6-4f7f-95bf-8260d43b923e"]
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
                                for runner in last_event['base_runners']:
                                    if runner['base_after_play'] != 4:
                                        day_runner_count += 1
                        last_event = food
        await ctx.send(day_runner_count)


def setup(bot):
    bot.add_cog(Pendants(bot))
