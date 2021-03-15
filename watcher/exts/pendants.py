import asyncio
import itertools
import json
import os

import discord
import gspread
import requests
from discord.ext import commands
from requests import Timeout

from watcher import utils

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

    async def get_daily_stats(self, all_statsheets, day, season):
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
        games = await self.retry_request(f"https://www.blaseball.com/database/games?day={day}&season={season}")
        for game in games.json():
            if not game["gameComplete"]:
                return None
        game_team_map = {}
        for game in games.json():
            game_team_map[game['homeTeam']] = {"game_id": game["id"], "opponent": game['awayTeam']}
            game_team_map[game['awayTeam']] = {"game_id": game["id"], "opponent": game['homeTeam']}
        game_statsheet_ids = [game["statsheet"] for game in games.json()]
        game_statsheets = await self.retry_request(
            f"https://www.blaseball.com/database/gameStatsheets?ids={','.join(game_statsheet_ids)}")
        if not game_statsheets:
            return None
        team_statsheet_ids = [game["awayTeamStats"] for game in game_statsheets.json()]
        team_statsheet_ids += [game["homeTeamStats"] for game in game_statsheets.json()]
        team_statsheets = await self.retry_request(
            f"https://www.blaseball.com/database/teamStatsheets?ids={','.join(team_statsheet_ids)}")
        player_statsheet_ids = [team["playerStats"] for team in team_statsheets.json()]
        flat_playerstatsheet_ids = list(itertools.chain.from_iterable(player_statsheet_ids))
        print(f"day {day} player count: {len(flat_playerstatsheet_ids)}")
        chunked_player_ids = [flat_playerstatsheet_ids[i:i + 50] for i in range(0, len(flat_playerstatsheet_ids), 50)]

        statsheets = {}
        pitcher_p_values = {}
        notable = {"perfect": {}, "nohitter": {}, "shutout": {}, "cycle": {},
                   "4homerun": {}, "bighits": {}, "rbimaster": {}}
        for chunk in chunked_player_ids:
            c_notable = await self.get_player_statsheets(chunk, day, statsheets, game_team_map,
                                                         pitching_rotations, team_stats, pitcher_p_values)
            for key, value in c_notable.items():
                for ikey, ivalue in c_notable[key].items():
                    notable[key][ikey] = ivalue
        day_stats = {'day': day, 'season': season, 'statsheets': statsheets, "notable": notable}
        all_statsheets.append(day_stats)
        filename = f"{season}_{day}player_statsheets.json"
        with open(os.path.join('data', 'pendant_data', 'statsheets', filename), 'w') as file:
            json.dump([statsheets], file)

        with open(os.path.join('data', 'pendant_data', 'statsheets', 'all_statsheets.json'), 'w') as file:
            json.dump(all_statsheets, file)
        with open(os.path.join('data', 'pendant_data', 'statsheets', 'pitching_rotations.json'), 'w') as file:
            json.dump(pitching_rotations, file)
        with open(os.path.join('data', 'pendant_data', 'statsheets', 'team_stats.json'), 'w') as file:
            json.dump(team_stats, file)
        return notable

    async def get_player_statsheets(self, player_ids, day, statsheets, game_team_map,
                                    pitching_rotations, team_stats, pitcher_p_values):
        notable = {"perfect": {}, "nohitter": {}, "shutout": {},
                   "cycle": {}, "4homerun": {}, "bighits": {}, "rbimaster": {}}
        player_statsheets = await self.retry_request(
            f"https://www.blaseball.com/database/playerStatsheets?ids={','.join(player_ids)}")
        players_list = player_statsheets.json()

        for p_values in players_list:
            save = True
            p_values["rotation_changed"] = False
            if p_values["outsRecorded"] >= 24 and p_values["earnedRuns"] <= 0:
                opp_id = game_team_map[p_values["teamId"]]["opponent"]
                if opp_id not in team_stats:
                    team_stats[opp_id] = {"shutout": 0, "at_bats": 0, "plate_appearances": 0,
                                          "struckouts": 0, "name": self.bot.team_names[opp_id],
                                          "lineup_pa": {}}
                team_stats[opp_id]["shutout"] += 1
                if p_values['hitsAllowed'] == 0:
                    if p_values['walksIssued'] == 0:
                        p_values['perfectGame'] = 1
                        notable["perfect"][p_values["playerId"]] = {
                            "name": p_values["name"],
                            "strikeouts": p_values["strikeouts"],
                            "outsRecorded": p_values["outsRecorded"],
                            "game_id": game_team_map[p_values["teamId"]]["game_id"],
                            "statsheet_id": p_values["id"]
                        }
                    else:
                        p_values['nohitter'] = 1
                        notable["nohitter"][p_values["playerId"]] = {
                            "name": p_values["name"],
                            "strikeouts": p_values["strikeouts"],
                            "outsRecorded": p_values["outsRecorded"],
                            "walksIssued": p_values['walksIssued'],
                            "game_id": game_team_map[p_values["teamId"]]["game_id"],
                            "statsheet_id": p_values["id"]
                        }
                else:
                    p_values["shutout"] = 1
                    notable["shutout"][p_values["playerId"]] = {
                        "name": p_values["name"],
                        "strikeouts": p_values["strikeouts"],
                        "outsRecorded": p_values["outsRecorded"],
                        "walksIssued": p_values['walksIssued'],
                        "hitsAllowed": p_values['hitsAllowed'],
                        "game_id": game_team_map[p_values["teamId"]]["game_id"],
                        "statsheet_id": p_values["id"]
                    }
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
                        statsheet_id = pitcher_p_values[p_values["playerId"]]["statsheetId"]
                        statsheets[statsheet_id]["pitchesThrown"] += p_values["pitchesThrown"]
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

                if p_values["hits"] >= 4:
                    if p_values["homeRuns"] > 0 and p_values["doubles"] > 0 and p_values["triples"] > 0 and \
                            p_values["hits"] - p_values["homeRuns"] - p_values["doubles"] - p_values["triples"] > 0:
                        notable["cycle"][p_values["playerId"]] = {
                            "name": p_values["name"],
                            "atBats": p_values["atBats"],
                            "hits": p_values["hits"],
                            "homeRuns": p_values["homeRuns"],
                            "doubles": p_values["doubles"],
                            "triples": p_values["triples"],
                            "game_id": game_team_map[p_values["teamId"]]["game_id"],
                            "statsheet_id": p_values["id"]
                        }
                        print("Cycle")
                    if p_values["hits"] >= 6:
                        print("bighits")
                        notable["bighits"][p_values["playerId"]] = {
                            "name": p_values["name"],
                            "atBats": p_values["atBats"],
                            "hits": p_values["hits"],
                            "homeRuns": p_values["homeRuns"],
                            "doubles": p_values["doubles"],
                            "triples": p_values["triples"],
                            "game_id": game_team_map[p_values["teamId"]]["game_id"],
                            "statsheet_id": p_values["id"]
                        }
                    if p_values["homeRuns"] >= 4:
                        print("4homerun")
                        notable["4homerun"][p_values["playerId"]] = {
                            "name": p_values["name"],
                            "atBats": p_values["atBats"],
                            "hits": p_values["hits"],
                            "homeRuns": p_values["homeRuns"],
                            "doubles": p_values["doubles"],
                            "triples": p_values["triples"],
                            "game_id": game_team_map[p_values["teamId"]]["game_id"],
                            "statsheet_id": p_values["id"]
                        }
                    if p_values["rbis"] >= 8:
                        print("rbimaster")
                        notable["rbimaster"][p_values["playerId"]] = {
                            "name": p_values["name"],
                            "atBats": p_values["atBats"],
                            "rbis": p_values["rbis"],
                            "hits": p_values["hits"],
                            "homeRuns": p_values["homeRuns"],
                            "doubles": p_values["doubles"],
                            "triples": p_values["triples"],
                            "game_id": game_team_map[p_values["teamId"]]["game_id"],
                            "statsheet_id": p_values["id"]
                        }
            if "rotation" not in p_values:
                p_values["rotation"] = -1
            if "shutout" not in p_values:
                p_values["shutout"] = -1
            if save:
                statsheets[p_values["id"]] = p_values
        return notable

    def print_top(self, player_dict, key, string, cutoff=2, avg=False):
        message = ""
        for pkey, pvalue in player_dict.items():
            if pvalue[key] >= cutoff:
                if key == 'strikeouts':
                    avg_str = ""
                    if avg:
                        k_9_value = round((pvalue[key] / (pvalue['outsRecorded'] / 27)) * 10) / 10
                        avg_str = f"({k_9_value} {key}/9)"
                    message += f"{pvalue['name']} {pvalue[key]} {string} {avg_str}\n"
                else:
                    message += f"{pvalue['name']} {pvalue[key]} {string}\n"
        return message

    async def get_latest_pendant_data(self, current_season):
        current_season -= 1
        output_channel = None
        stats_chan_id = self.bot.config['stats_channel']
        if stats_chan_id:
            output_channel = self.bot.get_channel(stats_chan_id)
        all_statsheets = []
        try:
            with open(os.path.join('data', 'pendant_data', 'statsheets', 'all_statsheets.json'), 'r') as file:
                all_statsheets = json.load(file)
        except FileNotFoundError:
            pass
        last_day = -1
        for day in all_statsheets:
            if day['season'] != current_season:
                continue
            last_day = max(last_day, day['day'])
        latest_day = last_day + 1
        notable = 1
        while notable:
            notable = await self.get_daily_stats(all_statsheets, latest_day, current_season)
            latest_day += 1
            if latest_day == 99:
                break

        for day in all_statsheets:
            if day['season'] != current_season:
                continue
            if day['day'] > last_day:
                players = day['statsheets']
                daily_message = [f"**Daily leaders for day {day['day'] + 1}**\n"]
                daily_message_two = ""
                sorted_hits = {k: v for k, v in sorted(players.items(), key=lambda item: item[1]['hits'], reverse=True)}
                sorted_homeruns = {k: v for k, v in
                                   sorted(players.items(), key=lambda item: item[1]['homeRuns'], reverse=True)}
                sorted_rbis = {k: v for k, v in sorted(players.items(), key=lambda item: item[1]['rbis'], reverse=True)}
                sorted_stolenbases = {k: v for k, v in
                                      sorted(players.items(), key=lambda item: item[1]['stolenBases'], reverse=True)}

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
                                     sorted(players.items(), key=lambda item: item[1]['strikeouts'],
                                            reverse=True)}
                daily_message_two += f"{self.bot.empty_str}\n**Strikeouts**\n" \
                                     f"{self.print_top(sorted_strikeouts, 'strikeouts', 'strikeouts', 9, True)}"

                game_watcher_messages = []
                sh_embed = discord.Embed(title="**Shutout!**")
                sh_description = ""
                if 'notable' in day:
                    notable = day['notable']
                    for __, event in notable["perfect"].items():
                        message = f"\n**Perfect Game!**\n{event['name']} with {event['strikeouts']} strikeouts " \
                                  f"in {event['outsRecorded']} outs.\n" \
                                  f"[reblase](https://reblase.sibr.dev/game/{event['game_id']})"
                        if "statsheet_id" in event:
                            message += f" | [statsheet](https://www.blaseball.com/database/playerstatsheets?ids={event['statsheet_id']})"
                        message += "\n"
                        if not self.bot.config['live_version']:
                            daily_message_two += message
                        game_watcher_messages.append(message)
                    for __, event in notable["nohitter"].items():

                        message = f"\n**No Hitter!**\n{event['name']} with {event['strikeouts']} strikeouts" \
                                  f" in {event['outsRecorded']} outs. {event['walksIssued']} batters walked.\n" \
                                  f"[reblase](https://reblase.sibr.dev/game/{event['game_id']})"
                        if "statsheet_id" in event:
                            message += f" | [statsheet](https://www.blaseball.com/database/playerstatsheets?ids={event['statsheet_id']})"
                        message += "\n"
                        if not self.bot.config['live_version']:
                            daily_message_two += message
                        game_watcher_messages.append(message)
                    for __, event in notable["shutout"].items():
                        sh_message = f"{event['name']} with {event['strikeouts']} strikeouts " \
                                     f"in {event['outsRecorded']} outs. {event['hitsAllowed']} hits allowed and " \
                                     f"{event['walksIssued']} batters walked.\n" \
                                     f"[reblase](https://reblase.sibr.dev/game/{event['game_id']})" \
                                     f" | [statsheet](https://www.blaseball.com/database/playerstatsheets?ids={event['statsheet_id']})\n"
                        sh_description += sh_message

                    if 'cycle' in notable:
                        for player_id, event in notable["cycle"].items():
                            doubles_str = f"{event['doubles']} double"
                            if event['doubles'] != 1:
                                doubles_str += "s"
                            triples_str = f"{event['triples']} triple"
                            if event['triples'] != 1:
                                triples_str += "s"
                            hr_str = f"{event['homeRuns']} home run"
                            if event['homeRuns'] != 1:
                                hr_str += "s"
                            quad_str = " "
                            base_message = "for the cycle"
                            if "quadruples" in event:
                                quad_str = f"{event['quadruples']} quadruple"
                                if event['quadruples'] != 1:
                                    quad_str += "s, "
                                else:
                                    quad_str += ", "
                                if event['quadruples'] > 0 and event['homeRuns'] > 0 \
                                        and event['triples'] > 0 and event['doubles'] > 0:
                                    base_message = "a super cycle!"
                            at_bats_str = ".\n"
                            if "atBats" in event:
                                at_bats_str = f" in {event['atBats']} at bats.\n"
                            natural_cycle = await self._check_feed_natural_cycle(event['name'], player_id, day['day'])
                            message = f"\n**{event['name']} hit {base_message}!**{at_bats_str} with {event['hits']}" \
                                      f" hits, {doubles_str}, {triples_str}, {quad_str}" \
                                      f"and {hr_str}.\n" \
                                      f"[reblase](https://reblase.sibr.dev/game/{event['game_id']})"

                            if "statsheet_id" in event:
                                message += f" | [statsheet](https://www.blaseball.com/database/playerstatsheets?ids={event['statsheet_id']})"
                            message += f"\n{natural_cycle}\n"
                            if not self.bot.config['live_version']:
                                daily_message_two += message
                            game_watcher_messages.append(message)
                    if '4homerun' in notable:
                        for __, event in notable["4homerun"].items():
                            at_bats_str = ".\n"
                            if "atBats" in event:
                                at_bats_str = f" in {event['atBats']} at bats.\n"
                            message = f"\n**{event['name']} hit 4+ home runs!**\n{event['homeRuns']} home runs " \
                                      f"in {event['hits']} total hits{at_bats_str}" \
                                      f"[reblase](https://reblase.sibr.dev/game/{event['game_id']})"
                            if "statsheet_id" in event:
                                message += f" | [statsheet](https://www.blaseball.com/database/playerstatsheets?ids={event['statsheet_id']})"
                            message += "\n"
                            if not self.bot.config['live_version']:
                                daily_message_two += message
                            game_watcher_messages.append(message)
                    if 'bighits' in notable:
                        for __, event in notable["bighits"].items():
                            doubles_str = f"{event['doubles']} double"
                            if event['doubles'] != 1:
                                doubles_str += "s"
                            triples_str = f"{event['triples']} triple"
                            if event['triples'] != 1:
                                triples_str += "s"
                            hr_str = f"{event['homeRuns']} home run"
                            if event['homeRuns'] != 1:
                                hr_str += "s"
                            quad_str = ""
                            if "quadruples" in event:
                                quad_str = f"{event['quadruples']} quadruple"
                                if event['quadruples'] != 1:
                                    quad_str += "s, "
                                else:
                                    quad_str += ", "
                            at_bats_str = "\n"
                            if "atBats" in event:
                                at_bats_str = f" in {event['atBats']} at bats.\n"
                            message = f"\n**{event['name']} got {event['hits']} hits!**{at_bats_str}" \
                                      f"with {doubles_str}, {triples_str}, {quad_str}and {hr_str}.\n" \
                                      f"[reblase](https://reblase.sibr.dev/game/{event['game_id']})"
                            if "statsheet_id" in event:
                                message += f" | [statsheet](https://www.blaseball.com/database/playerstatsheets?ids={event['statsheet_id']})"
                            message += "\n"
                            if not self.bot.config['live_version']:
                                daily_message_two += message
                            game_watcher_messages.append(message)
                    if "rbimaster" in notable:
                        for __, event in notable["rbimaster"].items():
                            doubles_str = f"{event['doubles']} double"
                            if event['doubles'] != 1:
                                doubles_str += "s"
                            triples_str = f"{event['triples']} triple"
                            if event['triples'] != 1:
                                triples_str += "s"
                            hr_str = f"{event['homeRuns']} home run"
                            if event['homeRuns'] != 1:
                                hr_str += "s"
                            quad_str = ""
                            if "quadruples" in event:
                                quad_str = f"{event['quadruples']} quadruple"
                                if event['quadruples'] != 1:
                                    quad_str += "s, "
                                else:
                                    quad_str += ", "
                            at_bats_str = "\n"
                            if "atBats" in event:
                                at_bats_str = f" with {event['hits']} in {event['atBats']} at bats.\n"
                            message = f"\n**{event['name']} got {event['rbis']} RBIs!**{at_bats_str}" \
                                      f"with {doubles_str}, {triples_str}, {quad_str}and {hr_str}.\n" \
                                      f"[reblase](https://reblase.sibr.dev/game/{event['game_id']})"
                            if "statsheet_id" in event:
                                message += f" | [statsheet](https://www.blaseball.com/database/playerstatsheets?ids={event['statsheet_id']})"
                            message += "\n"
                            if not self.bot.config['live_version']:
                                daily_message_two += message
                            game_watcher_messages.append(message)
                if output_channel and len(game_watcher_messages) > 0:
                    desription = ""
                    for message in game_watcher_messages:
                        desription += message + "\n"
                    msg_embed = discord.Embed(description=desription[:2047])
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
        return latest_day

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
            if i + 3 > len(filtered_items):
                break
            if "hits a Single" in filtered_items[i]['description']:
                if "hits a Double" in filtered_items[i + 1]['description']:
                    if "hits a Triple" in filtered_items[i + 2]['description']:
                        if "home run" in filtered_items[i + 3]['description']:
                            return "Natural Cycle!"
        for i in range(len(filtered_items)):
            if i + 3 > len(filtered_items):
                break
            if "home run" in filtered_items[i]['description']:
                if "hits a Triple" in filtered_items[i + 1]['description']:
                    if "hits a Double" in filtered_items[i + 2]['description']:
                        if "hits a Single" in filtered_items[i + 3]['description']:
                            return "Reverse Cycle!"
        return "Not a natural cycle."

    async def compile_stats(self):
        try:
            with open(os.path.join('data', 'pendant_data', 'statsheets', 'all_statsheets.json'), 'r') as file:
                all_statsheets = json.load(file)
        except FileNotFoundError:
            all_statsheets = []
        players = {}
        for day in all_statsheets:
            for pid in day['statsheets']:
                player = day['statsheets'][pid]
                if player["playerId"] not in players:
                    players[player["playerId"]] = player
                else:
                    for key in ["atBats", "caughtStealing", "doubles", "earnedRuns", "groundIntoDp", "hits",
                                "hitsAllowed", "homeRuns", "losses", "outsRecorded", "rbis", "runs", "stolenBases",
                                "strikeouts", "struckouts", "triples", "walks", "walksIssued", "wins",
                                "hitByPitch", "hitBatters", "shutout"]:
                        if key in player:
                            if key in players[player["playerId"]]:
                                players[player["playerId"]][key] += player[key]
                            else:
                                players[player["playerId"]][key] = player[key]
                    players[player["playerId"]]["teamId"] = player["teamId"]
                    players[player["playerId"]]["rotation"] = player["rotation"]
                    players[player["playerId"]]["rotation_changed"] = player["rotation_changed"]
                    players[player["playerId"]]["name"] = player["name"]
                    if "position" in player:
                        players[player["playerId"]]["position"] = player["position"]
        return players

    async def update_leaders_sheet(self, season, day):
        season -= 1
        agc = await self.bot.authorize_agcm()
        if self.bot.config['live_version'] == True:
            sheet = await agc.open_by_key(self.bot.SPREADSHEET_IDS[f"season{season + 1}"])
        else:
            sheet = await agc.open_by_key(self.bot.SPREADSHEET_IDS[f"seasontest"])
        if season >= 12:
            p_worksheet = await sheet.worksheet("Snack Income")
        else:
            p_worksheet = await sheet.worksheet("Pendants")
        all_players = await self.compile_stats()

        sorted_hits, sorted_homeruns, \
            sorted_total_hit_payouts, sorted_stolenbases = self.save_daily_top_players(all_players, day)
        rows = []

        pitcher_dict = {k: v for k, v in all_players.items() if v['outsRecorded'] > 0}
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
                    values = all_players[key]
                    team = team_short_map[values["teamId"]]
                    name = f"({team}) {values['name']}"
                    k_9_value = round((values['strikeouts'] / (values['outsRecorded'] / 27)) * 10) / 10
                    rows.append([values["rotation"], name, '', '', values["strikeouts"], k_9_value])
        await p_worksheet.batch_update([{
            'range': "A23:F37",
            'values': rows
        }])

        rows = []
        sorted_strikeouts = {k: v
                             for k, v in sorted(pitcher_dict.items(),
                                                key=lambda item: round((item[1]['strikeouts'] / (
                                                        item[1]['outsRecorded'] / 27)) * 10) / 10,
                                                reverse=True) if v["rotation_changed"]}
        top_list = list(sorted_strikeouts.keys())

        top_keys = top_list[:7]
        for key in top_keys:
            values = all_players[key]
            team = team_short_map[values["teamId"]]
            name = f"({team}) {values['name']}"
            k_9_value = round((values['strikeouts'] / (values['outsRecorded'] / 27)) * 10) / 10
            rows.append([values["rotation"], name, '', values["strikeouts"], k_9_value])
        await p_worksheet.batch_update([{
            'range': "L23:P29",
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
            'range': "H23:J37",
            'values': rows
        }])

        rows = []
        sorted_shutouts = {k: v for k, v in sorted(pitcher_dict.items(), key=lambda item: item[1]['shutout'],
                                                   reverse=True) if v["rotation_changed"]}
        top_keys = list(sorted_shutouts.keys())[:5]
        for key in top_keys:
            values = sorted_shutouts[key]
            team = team_short_map[values["teamId"]]
            name = f"({team}) {values['name']}"
            rows.append([values["rotation"], name, '', values["shutout"]])
        await p_worksheet.batch_update([{
            'range': "L33:O37",
            'values': rows
        }])

        rows = []

        sb_max = 3
        hit_max = 10
        top_sb_keys = list(sorted_stolenbases.keys())[:sb_max]
        top_keys = list(sorted_total_hit_payouts.keys())[:hit_max]
        for i in range(sb_max):
            if top_sb_keys[i] not in top_keys:
                hit_max -= 1

        count = 0
        for key in top_keys:
            if key == "86d4e22b-f107-4bcf-9625-32d387fcb521" or key == "e16c3f28-eecd-4571-be1a-606bbac36b2b":
                continue
            values = sorted_total_hit_payouts[key]
            if "hitsMinusHrs" in all_players[key]:
                hits = all_players[key]["hitsMinusHrs"]
            else:
                hits = all_players[key]["hits"]
            team = team_short_map[values["teamId"]]
            name = f"({team}) {values['name']}"
            rows.append([name, '', hits, values["homeRuns"], values["stolenBases"]])
            count += 1
            if count == hit_max:
                break

        for key in top_sb_keys:
            if key not in top_keys:
                values = sorted_stolenbases[key]
                if "hitsMinusHrs" in all_players[key]:
                    hits = all_players[key]["hitsMinusHrs"]
                else:
                    hits = all_players[key]["hits"]
                team = team_short_map[values["teamId"]]
                name = f"({team}) {values['name']}"
                rows.append([name, '', hits, values["homeRuns"], values["stolenBases"]])

        await p_worksheet.batch_update([{
            'range': "A9:E18",
            'values': rows
        }])

        # York Silk
        ys_id = "86d4e22b-f107-4bcf-9625-32d387fcb521"
        ys_row = ["York Silk", '', 0, 0, 0]
        if ys_id in sorted_hits:
            ys_row[2] = all_players[ys_id].setdefault("hitsMinusHrs", 0)
        if ys_id in sorted_homeruns:
            ys_row[3] = sorted_homeruns[ys_id].setdefault("homeRuns", 0)
        if ys_id in sorted_stolenbases:
            ys_row[4] = sorted_stolenbases[ys_id].setdefault("stolenBases", 0)
        # Wyatt Glover
        wg_id = "e16c3f28-eecd-4571-be1a-606bbac36b2b"
        wg_row = ["Wyatt Glover", '', 0, 0, 0]
        if wg_id in sorted_hits:
            wg_row[2] = all_players[wg_id].setdefault("hitsMinusHrs", 0)
        if wg_id in sorted_homeruns:
            wg_row[3] = sorted_homeruns[wg_id].setdefault("homeRuns", 0)
        if wg_id in sorted_stolenbases:
            wg_row[4] = sorted_stolenbases[wg_id].setdefault("stolenBases", 0)
        await p_worksheet.batch_update([{
            'range': "A6:E7",
            'values': [ys_row, wg_row]
        }])

        with open(os.path.join('data', 'pendant_data', 'all_players.json'), 'w') as file:
            json.dump(all_players, file)

        with open(os.path.join('data', 'pendant_data', 'statsheets', f's{season}_day_weather.json'), 'r') as file:
            day_weather = json.load(file)
        black_holes, sunset, incineration = 0, 0, 0
        for __, weather_map in day_weather.items():
            if "Black Hole" in weather_map:
                black_holes += weather_map["Black Hole"]
            if "Sunset" in weather_map:
                sunset += weather_map["Sunset"]
            if "Incinerations" in weather_map:
                sunset += weather_map["Incinerations"]
        await p_worksheet.batch_update([{
            'range': "B2:B2",
            'values': [[black_holes]]
        }])

        flood_count, runner_count, new_runner_count = await self._lookup_floods(season)
        await p_worksheet.batch_update([{
            'range': "L2:M2",
            'values': [[flood_count, runner_count]]
        }])

        with open(os.path.join('season_data', 'weather_occurrences.json'), 'r') as file:
            weather_occurrences = json.load(file)
        season_str = str(season)
        if season_str not in weather_occurrences:
            weather_occurrences[season_str] = {"black_holes": 0, "flooded_runners": 0, "sunsets": 0, "incinerations": 0}
        weather_occurrences[season_str]["black_holes"] += black_holes
        weather_occurrences[season_str]["flooded_runners"] += new_runner_count
        weather_occurrences[season_str]["sunsets"] += sunset
        weather_occurrences[season_str]["incinerations"] += incineration
        with open(os.path.join('season_data', 'weather_occurrences.json'), 'w') as file:
            json.dump(weather_occurrences, file)

    @staticmethod
    def load_remaining_teams():
        with open(os.path.join('data', 'pendant_data', 'statsheets', 'postseason_teams.json'), 'r') as file:
            team_list = json.load(file)
        return team_list

    def save_daily_top_players(self, all_players, day):
        # need to put in logic for playoffs here
        #team_list = self.load_remaining_teams()

        # sorted_hits = {k: v for k, v in sorted(all_players.items(), key=lambda item: item[1]['hits'],
        #                                        reverse=True) if v['teamId'] in team_list}
        # sorted_homeruns = {k: v for k, v in sorted(all_players.items(), key=lambda item: item[1]['homeRuns'],
        #                                            reverse=True) if v['teamId'] in team_list}
        # sorted_stolenbases = {k: v for k, v in sorted(all_players.items(), key=lambda item: item[1]['stolenBases'],
        #                                               reverse=True) if v['teamId'] in team_list}
        sorted_hits = {k: v for k, v in sorted(all_players.items(), key=lambda item: item[1]['hits'],
                                               reverse=True)}
        sorted_homeruns = {k: v for k, v in sorted(all_players.items(), key=lambda item: item[1]['homeRuns'],
                                                   reverse=True)}
        sorted_stolenbases = {k: v for k, v in sorted(all_players.items(), key=lambda item: item[1]['stolenBases'],
                                                      reverse=True)}
        boosted_players = {"86d4e22b-f107-4bcf-9625-32d387fcb521": 2, "e16c3f28-eecd-4571-be1a-606bbac36b2b": 5}
        total_hit_payouts = {}
        for k, v in sorted_hits.items():
            homeruns = sorted_homeruns[k]["homeRuns"]
            stolenbases = sorted_stolenbases[k]["stolenBases"]
            hits = v["hits"] - homeruns

            if k in boosted_players:
                multiplier = boosted_players[k]
            else:
                multiplier = 1
            seed_dog = ((hits * 1500) + (homeruns * 4000)) * multiplier
            combo = ((hits * 1500) + (homeruns * 4000) + (stolenbases * 3000)) * multiplier
            all_players[k]["multiplier"] = multiplier
            all_players[k]["hitsMinusHrs"] = hits

            total_hit_payouts[k] = {"name": v['name'], "teamId": v["teamId"], "hits": v["hits"],
                                    "homeRuns": sorted_homeruns[k]["homeRuns"],
                                    "stolenBases": sorted_stolenbases[k]["stolenBases"],
                                    "seed_dog": seed_dog, "combo": combo, "multiplier": multiplier}
        sorted_seed_dog_payouts = {k: v for k, v in sorted(total_hit_payouts.items(),
                                                           key=lambda item: item[1]['seed_dog'], reverse=True)}
        sorted_combo_payouts = {k: v for k, v in sorted(total_hit_payouts.items(),
                                                        key=lambda item: item[1]['combo'], reverse=True)}

        daily_leaders = {"hits": [], "home_runs": [], "stolen_bases": [], "seed_dog": [], "combo": []}
        for key in list(sorted_hits.keys())[:10]:
            daily_leaders["hits"].append(all_players[key])
        for key in list(sorted_homeruns.keys())[:10]:
            daily_leaders["home_runs"].append(all_players[key])
        for key in list(sorted_stolenbases.keys())[:10]:
            daily_leaders["stolen_bases"].append(all_players[key])
        for key in list(sorted_seed_dog_payouts.keys())[:10]:
            daily_leaders["seed_dog"].append(all_players[key])
        for key in list(sorted_combo_payouts.keys())[:10]:
            daily_leaders["combo"].append(all_players[key])

        with open(os.path.join('data', 'pendant_data', 'statsheets', f'd{day}_leaders.json'), 'w') as file:
            json.dump(daily_leaders, file)

        return sorted_hits, sorted_homeruns, sorted_seed_dog_payouts, sorted_stolenbases

    async def _lookup_floods(self, season):
        season_flood_count, season_runner_count, new_runner_count = 0, 0, 0
        try:
            with open(os.path.join('data', 'pendant_data', 'statsheets', f's{season}_flood_lookups.json'),
                      'r') as file:
                flood_lookups = json.load(file)
        except FileNotFoundError:
            flood_lookups = {}
            self.bot.logger.warning("No flood lookup data found.")
        for day, day_info in flood_lookups.items():
            if day_info['lookedup'] == False:
                day_flood_count = 0
                day_runner_count = 0
                failed_count = 0
                for game_id in day_info["floods"]:
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
                        else:
                            failed_count += 1
                    else:
                        failed_count += 1

                if failed_count == 0:
                    day_info['lookedup'] = True
                    day_info['flood_count'] = day_flood_count
                    day_info['runner_count'] = day_runner_count

                    season_flood_count += day_flood_count
                    season_runner_count += day_runner_count
                    new_runner_count += day_runner_count
            else:
                if "flood_count" in day_info:
                    season_flood_count += day_info['flood_count']
                if "runner_count" in day_info:
                    season_runner_count += day_info['runner_count']
            flood_lookups[day] = day_info
        with open(os.path.join('data', 'pendant_data', 'statsheets', f's{season}_flood_lookups.json'),
                  'w') as file:
            json.dump(flood_lookups, file)
        return season_flood_count, season_runner_count, new_runner_count

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


def setup(bot):
    bot.add_cog(Pendants(bot))
