import asyncio
import json
import os
import time

import discord

from discord.ext import commands

from watcher import utils


class JsonWatcher(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.latest_tie = None

    @commands.command(name='set_json_update_interval', aliases=['sjui'])
    async def _set_update_interval(self, ctx, minutes: int):
        self.bot.config['json_watch_interval'] = minutes
        return await ctx.message.add_reaction(self.bot.success_react)

    @commands.command(name='get_json_update_interval', aliases=['gjui'])
    async def _get_update_interval(self, ctx):
        interval = self.bot.config.setdefault('json_watch_interval', 10)
        return await ctx.channel.send(f"Delay interval between checks for Json changes is {interval} minutes.")

    @commands.command(name='testjson', aliases=['tj'])
    async def _test2(self, ctx):
        #await self.check_for_field_updates()
        await self.check_for_comprehensive_updates()

    async def check_for_field_updates(self):
        output_channel = self.bot.get_channel(self.bot.config['notify_channel'])
        html_response = await utils.retry_request("https://www.blaseball.com/database/simulationdata")
        if not html_response:
            self.bot.logger.warn('Failed to acquire sim data')
            return
        sim_data = html_response.json()
        season = sim_data['season']
        day = sim_data['day']
        league_id = sim_data['league']
        if day == 0:
            day = 107
            season -= 1

        with open(os.path.join("json_data", "game.json"), encoding='utf-8') as json_file:
            game_json = json.load(json_file)
        with open(os.path.join("json_data", "gamestatsheet.json"), encoding='utf-8') as json_file:
            gamestatsheet = json.load(json_file)
        with open(os.path.join("json_data", "teamstatsheet.json"), encoding='utf-8') as json_file:
            teamstatsheet = json.load(json_file)
        with open(os.path.join("json_data", "playerstatsheet.json"), encoding='utf-8') as json_file:
            playerstatsheet = json.load(json_file)
        with open(os.path.join("json_data", "player.json"), encoding='utf-8') as json_file:
            player_json = json.load(json_file)
        with open(os.path.join("json_data", "league.json"), encoding='utf-8') as json_file:
            league_json = json.load(json_file)
        with open(os.path.join("json_data", "subleague.json"), encoding='utf-8') as json_file:
            subleague_json = json.load(json_file)

        try:
            html_response = await utils.retry_request(f"https://www.blaseball.com/database/games?season={season}&day={day}")
            if not html_response:
                self.bot.logger.warn('Failed to acquire game data')
                return
            cur_json = json.loads(html_response.content.decode('utf-8'))
            changed = await self.check_single_json(cur_json[0], game_json[0], output_channel, "games")
            self.save_files(cur_json, "game.json", changed)

            sid = cur_json[0]['statsheet']
            html_response = await utils.retry_request(f"https://www.blaseball.com/database/gamestatsheets?ids={sid}")
            if not html_response:
                self.bot.logger.warn('Failed to acquire gamestatsheet data')
                return
            cur_json = json.loads(html_response.content.decode('utf-8'))
            changed = await self.check_single_json(cur_json[0], gamestatsheet[0], output_channel, "gamestatsheet")
            self.save_files(cur_json, "gamestatsheet.json", changed)

            sid = cur_json[0]['awayTeamStats']
            html_response = await utils.retry_request(f"https://www.blaseball.com/database/teamstatsheets?ids={sid}")
            if not html_response:
                self.bot.logger.warn('Failed to acquire teamstatsheet data')
                return
            cur_json = json.loads(html_response.content.decode('utf-8'))
            changed = await self.check_single_json(cur_json[0], teamstatsheet[0], output_channel, "teamstatsheet")
            self.save_files(cur_json, "teamstatsheet.json", changed)

            sid = cur_json[0]['playerStats'][0]
            html_response = await utils.retry_request(f"https://www.blaseball.com/database/playerstatsheets?ids={sid}")
            if not html_response:
                self.bot.logger.warn('Failed to acquire playerstatsheet data')
                return
            cur_json = json.loads(html_response.content.decode('utf-8'))
            changed = await self.check_single_json(cur_json[0], playerstatsheet[0], output_channel, "playerstatsheet")
            self.save_files(cur_json, "playerstatsheet.json", changed)

            sid = cur_json[0]['playerId']
            html_response = await utils.retry_request(f"https://www.blaseball.com/database/players?ids={sid}")
            if not html_response:
                self.bot.logger.warn('Failed to acquire playerstatsheet data')
                return
            cur_json = json.loads(html_response.content.decode('utf-8'))
            changed = await self.check_single_json(cur_json[0], player_json[0], output_channel, "player")
            self.save_files(cur_json, "player.json", changed)
        except Exception as e:
            self.bot.logger.warn('Failed to acquire game data, cascading failures to gamestatsheet, '
                                 f'teamstatsheet, playerstatsheet, player\n{e}')

        try:
            html_response = await utils.retry_request(f"https://www.blaseball.com/database/league?id={league_id}")
            if not html_response:
                self.bot.logger.warn('Failed to acquire league data')
                return
            cur_json = json.loads(html_response.content.decode('utf-8'))
            changed = await self.check_single_json(cur_json, league_json, output_channel, "league")
            self.save_files(cur_json, "league.json", changed)
            self.latest_tie = cur_json['tiebreakers']

            sid = cur_json['subleagues'][0]
            html_response = await utils.retry_request(f"https://www.blaseball.com/database/subleague?id={sid}")
            if not html_response:
                self.bot.logger.warn('Failed to acquire subleague data')
                return
            cur_json = json.loads(html_response.content.decode('utf-8'))
            changed = await self.check_single_json(cur_json, subleague_json, output_channel, "subleague")
            self.save_files(cur_json, "subleague.json", changed)
        except:
            self.bot.logger.warn('Failed to acquire league data. Cascading failure to subleague')

    async def check_for_comprehensive_updates(self):
        output_channel = self.bot.get_channel(self.bot.config['notify_channel'])
        with open(os.path.join("json_data", "allteams.json"), encoding='utf-8') as json_file:
            current_allteams = json.load(json_file)
        try:
            html_response = await utils.retry_request("https://www.blaseball.com/database/allteams")
            if not html_response:
                self.bot.logger.warn('Failed to acquire allteams data')
                return
            latest_allteams = json.loads(html_response.content.decode('utf-8'))
            changed = await self.check_single_json(latest_allteams[0], current_allteams[0], output_channel, "allteams")
            messages = await self.check_all_teams(latest_allteams, current_allteams)
            changed = changed or len(messages) > 0
            self.save_files(latest_allteams, "allteams.json", changed)
            if len(messages) > 0:
                with open(os.path.join("json_data", "allteams.json"), 'rb') as logfile:
                    await output_channel.send(content='\n'.join(messages),
                                              file=discord.File(logfile,
                                                                filename=f'allteams{int(time.time())}.json'))
        except Exception as e:
            self.bot.logger.warn(f'Failed to acquire allteams data: {e}')

    async def check_for_content_updates(self):
        output_channel = self.bot.get_channel(self.bot.config['notify_channel'])

        with open(os.path.join("json_data", "simulationdata.json"), encoding='utf-8') as json_file:
            simulationdata_json = json.load(json_file)
        html_response = await utils.retry_request("https://www.blaseball.com/database/simulationdata")
        if not html_response:
            self.bot.logger.warn('Failed to acquire sim data')
            return
        new_sim_data = html_response.json()
        changed = await self.check_single_json(new_sim_data, simulationdata_json, output_channel, "simulationdata")
        self.save_files(new_sim_data, "simulationdata.json", changed)

        with open(os.path.join("json_data", "offseasonsetup.json"), encoding='utf-8') as json_file:
            offseasonsetup_json = json.load(json_file)
        html_response = await utils.retry_request("https://www.blaseball.com/database/offseasonsetup")
        if not html_response:
            self.bot.logger.warn('Failed to acquire offseasonsetup data')
            return
        new_oss_data = html_response.json()
        changed = await self.check_single_json(new_oss_data, offseasonsetup_json, output_channel, "offseasonsetup")
        self.save_files(new_oss_data, "offseasonsetup.json", changed)

        with open(os.path.join("json_data", "alldivisions.json"), encoding='utf-8') as json_file:
            alldivisions_json = json.load(json_file)
        html_response = await utils.retry_request("https://www.blaseball.com/database/alldivisions")
        if not html_response:
            self.bot.logger.warn('Failed to acquire divisions data')
            return
        new_div_data = html_response.json()
        messages, changed = await self.check_for_division_changes(alldivisions_json, new_div_data)
        self.save_files(new_div_data, "alldivisions.json", changed)
        if changed:
            with open(os.path.join("json_data", "alldivisions.json"), 'rb') as logfile:
                await output_channel.send(content='\n'.join(messages),
                                          file=discord.File(logfile, filename=f'alldivisions{int(time.time())}.json'))

        if self.latest_tie:
            tie_id = self.latest_tie
            with open(os.path.join("json_data", "tiebreakers.json"), encoding='utf-8') as json_file:
                tiebreakers_json = json.load(json_file)
            html_response = await utils.retry_request(f"https://www.blaseball.com/database/tiebreakers?id={tie_id}")
            if not html_response:
                self.bot.logger.warn('Failed to acquire tiebreakers data')
                return
            new_ties_json = html_response.json()
            self.save_files(new_ties_json, "tiebreakers.json", tiebreakers_json != new_ties_json)
            if tiebreakers_json != new_ties_json:
                with open(os.path.join("json_data", "tiebreakers.json"), 'rb') as logfile:
                    await output_channel.send(content='Tiebreakers have changed!',
                                              file=discord.File(logfile,
                                                                filename=f'tiebreakers{int(time.time())}.json'))
                await self.update_bot_tiebreakers(new_ties_json)

    async def update_bot_tiebreakers(self, new_ties_json):
        favor_rankings = {}
        position = 0
        for team in new_ties_json["order"]:
            team_name = self.bot.team_names[team]
            favor_rankings[team_name] = position
            position += 1
        self.bot.config['favor_rankings'] = favor_rankings
        await self.save()

    @staticmethod
    async def check_for_division_changes(old_divisions, new_divisions):
        messages = []
        changed = False
        old_div_ids = [div["id"] for div in old_divisions]
        new_div_ids = [div["id"] for div in new_divisions]
        div_diff = set(old_div_ids) - set(new_div_ids)
        if len(div_diff) > 0:
            messages.append(f"Divisions removed: {div_diff}")
            changed = True
        div_diff = set(new_div_ids) - set(old_div_ids)
        if len(div_diff) > 0:
            messages.append(f"Divisions Added: {div_diff}")
            changed = True
        for div in new_divisions:
            if div["id"] in old_div_ids:
                for o_div in old_divisions:
                    if o_div["id"] == div["id"]:
                        team_diff = set(div["teams"]) - set(o_div["teams"])
                        if len(team_diff) > 0:
                            messages.append(f"{div['name']} Division added teams: {team_diff}")
                            changed = True
                        team_diff = set(o_div["teams"]) - set(div["teams"])
                        if len(team_diff) > 0:
                            messages.append(f"{div['name']} Division lost teams: {team_diff}")
                            changed = True
        return messages, changed

    @staticmethod
    async def check_all_teams(new_team_list, old_team_list):
        old_teams = {}
        new_teams = {}
        for team in old_team_list:
            old_teams[team["id"]] = team
        for team in new_team_list:
            new_teams[team["id"]] = team
        messages = []
        for team in old_teams:
            if team in new_teams:
                for group in ["lineup", "rotation", "bullpen", "bench"]:
                    r_diff = set(old_teams[team][group]) - set(new_teams[team][group])
                    if len(r_diff) > 0:
                        messages.append(f"{','.join(r_diff)} no longer in {old_teams[team]['nickname']} {group}")
                    r_diff = set(new_teams[team][group]) - set(old_teams[team][group])
                    if len(r_diff) > 0:
                        messages.append(f"{','.join(r_diff)} added to {new_teams[team]['nickname']} {group}")
                for attrset in ["seasAttr", "permAttr", "weekAttr", "gameAttr"]:
                    a_diff = set(old_teams[team][attrset]) - set(new_teams[team][attrset])
                    if len(a_diff) > 0:
                        messages.append(f"{','.join(a_diff)} no longer in {old_teams[team]['nickname']} {attrset}")
                    a_diff = set(new_teams[team][attrset]) - set(old_teams[team][attrset])
                    if len(a_diff) > 0:
                        messages.append(f"{','.join(a_diff)} added to {new_teams[team]['nickname']} {attrset}")
                for attr in ["fullName", "location", "mainColor", "nickname",
                             "secondaryColor", "shorthand", "emoji", "slogan"]:
                    if old_teams[team][attr] != new_teams[team][attr]:
                        messages.append(f"{new_teams[team]['nickname']} {attr} changed from {old_teams[team][attr]}"
                                        f" to {new_teams[team][attr]}")
        return messages


    @staticmethod
    def save_files(data, filename, changed):
        with open(os.path.join("json_data", filename), 'w') as json_file:
            json.dump(data, json_file)
        if changed:
            with open(os.path.join("json_data", "historic", f"{time.time()}{filename}"), 'w') as json_file:
                json.dump(data, json_file)

    async def check_single_json(self, new_json, old_json, output_channel, name):
        new_keys = []
        for key in new_json.keys():
            if key not in old_json:
                new_keys.append(key)
        if len(new_keys) > 0:
            await output_channel.send(f"New fields added to {name} json: {', '.join(new_keys)}")
            return True
        return False

    async def check_loop(self):
        while not self.bot.is_closed():
            await self.check_for_field_updates()
            await self.check_for_content_updates()
            await self.check_for_comprehensive_updates()
            await self.save()
            await asyncio.sleep(self.bot.config.setdefault('json_watch_interval', 10) * 60)

    async def save(self):
        admin_cog = self.bot.cogs.get('AdminCommands')
        await admin_cog.save()


def setup(bot):
    bot.add_cog(JsonWatcher(bot))
