import aiosqlite
import discord
from discord.ext import commands
import os
import csv
import string

class PlayerStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="player_stats", aliases=['stats'])
    async def _get_player_stats(self, ctx, *, player_name):
        player_id = None
        if player_name in self.bot.player_cache:
            player_id = self.bot.player_cache[player_name]["id"]
        elif player_name.lower() in self.bot.player_names:
            player_id = self.bot.player_names[player_name.lower()]
        if not player_id:
            return await ctx.send(f"Could not find player: {player_name}. Please check your spelling and try again.")

        if player_id in self.bot.player_team_map:
            team_id = self.bot.player_team_map[player_id]
            hex_color = self.bot.team_cache[team_id]["mainColor"].lstrip('#')
            rgb_color = tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
            color = discord.Colour.from_rgb(*rgb_color)
        else:
            color = discord.Colour.from_rgb(255, 255, 255)

        season = self.bot.config['current_season'] - 1
        position = None
        async with aiosqlite.connect(self.bot.db_path) as db:
            async with db.execute("select position "
                                  "from DailyStatSheets where season=? "
                                  "and playerId=? order by day desc limit 1", [season, player_id]) as cursor:
                async for row in cursor:
                    position = row[0]
        if not position:
            return await ctx.send(f"Could not find stats for player: {player_name}.")

        if position == 'lineup':
            return await self._get_hitter_stats(season, player_id, player_name, color, ctx.channel)
        if position == 'rotation':
            return await self._get_pitcher_stats(season, player_id, player_name, color, ctx.channel)

    async def _get_hitter_stats(self, season, player_id, player_name, color, response_channel):
        stats = None
        async with aiosqlite.connect(self.bot.db_path) as db:
            async with db.execute("select playerId, name, teamId, sum(atBats), sum(caughtStealing), sum(doubles), "
                                  "sum(groundIntoDp), sum(hits), sum(homeRuns), sum(rbis), sum(runs), "
                                  "sum(stolenBases), sum(struckouts), sum(triples), sum(walks)"
                                  "from DailyStatSheets where season=? and position='lineup' "
                                  "and playerId=?", [season, player_id]) as cursor:
                async for row in cursor:
                    if row and row[0]:
                        stats = {
                            "playerId": row[0],
                            "name": row[1],
                            "teamId": row[2],
                            "atBats": row[3],
                            "caughtStealing": row[4],
                            "doubles": row[5],
                            "groundIntoDp": row[6],
                            "hits": row[7],
                            "homeRuns": row[8],
                            "rbis": row[9],
                            "runs": row[10],
                            "stolenBases": row[11],
                            "struckouts": row[12],
                            "triples": row[13],
                            "walks": row[14],
                        }
                    break
        if not stats:
            return await response_channel.send(f"Could not find stats for player: {player_name}.")
        title = f"Season {season} stats for {player_name.capitalize()}"
        embed = discord.Embed(colour=color, title=title)

        first_half = f"At Bats: **{stats['atBats']}**\n" \
                     f"Hits: **{stats['hits']}**\n" \
                     f"Doubles: **{stats['doubles']}**\n" \
                     f"Triples: **{stats['triples']}**\n" \
                     f"Home Runs: **{stats['homeRuns']}**\n" \
                     f"RBIs: **{stats['rbis']}**\n"

        second_half = f"Runs: **{stats['runs']}**\n" \
                      f"Stolen Bases: **{stats['stolenBases']}**\n" \
                      f"Caught Stealing: **{stats['caughtStealing']}**\n" \
                      f"Strikeouts: **{stats['struckouts']}**\n" \
                      f"Walks: **{stats['walks']}**\n" \
                      f"Double Plays: **{stats['groundIntoDp']}**\n"

        ba = stats['hits'] / stats['atBats']
        # 2 is a super bad estimate of sac hits that probably doesn't even matter
        # will add hitbypitch if and when it matters again
        obp = (stats['hits'] + stats['walks']) / (stats['atBats'] + stats['walks'] + 2)
        singles = stats['hits'] - stats['doubles'] - stats['triples'] - stats['homeRuns']
        slg = (singles + (2 * stats['doubles']) + (3 * stats['triples']) + (4 * stats['homeRuns'])) / stats['atBats']
        obps = obp + slg

        third_half = f"Batting Avg: **{('%.3f' % (round(ba * 1000)/1000)).lstrip('0')}**\n" + \
                     f"OBP: **{('%.3f' % (round(obp * 1000) / 1000)).lstrip('0')}**\n" + \
                     f"SLG: **{('%.3f' % (round(slg * 1000) / 1000)).lstrip('0')}**\n" + \
                     f"OBPS: **{('%.3f' % (round(obps * 1000) / 1000)).lstrip('0')}**"

        embed.add_field(name=self.bot.empty_str, value=first_half)
        embed.add_field(name=self.bot.empty_str, value=second_half)
        embed.add_field(name=self.bot.empty_str, value=third_half)
        return await response_channel.send(embed=embed)

    async def _get_pitcher_stats(self, season, player_id, player_name, color, response_channel):
        stats = None
        async with aiosqlite.connect(self.bot.db_path) as db:
            async with db.execute("select playerId, name, teamId, sum(earnedRuns), "
                                  "sum(outsRecorded), sum(pitchesThrown), sum(wins), sum(losses), sum(strikeouts), "
                                  "sum(walksIssued), sum(hitsAllowed), sum(homeRunsAllowed), "
                                  "sum(shutout), sum(noHitter), sum(perfectGame) "
                                  "from DailyStatSheets where season=? and position='rotation' "
                                  "and playerId=?", [season, player_id]) as cursor:
                async for row in cursor:
                    if row and row[0]:
                        stats = {
                            "playerId": row[0],
                            "name": row[1],
                            "teamId": row[2],
                            "earnedRuns": row[3],
                            "outsRecorded": row[4],
                            "pitchesThrown": row[5],
                            "wins": row[6],
                            "losses": row[7],
                            "strikeouts": row[8],
                            "walksIssued": row[9],
                            "hitsAllowed": row[10],
                            "homeRunsAllowed": row[11],
                            "shutout": row[12],
                            "noHitter": row[13],
                            "perfectGame": row[14],
                        }

        if not stats:
            return await response_channel.send(f"Could not find stats for player: {player_name}.")
        title = f"Season {season} stats for {player_name.capitalize()}"
        embed = discord.Embed(colour=color, title=title)

        first_half = f"Record: **{stats['wins']}-{stats['losses']}**\n" \
                     f"Pitches Thrown: **{stats['pitchesThrown']}**\n" \
                     f"Strikeouts: **{stats['strikeouts']}**\n" \
                     f"Walks Issued: **{stats['walksIssued']}**\n" \
                     f"Hits Allowed: **{stats['hitsAllowed']}**\n" \
                     f"Home Runs Allowed: **{stats['homeRunsAllowed']}**\n"

        innings_pitched = (stats['outsRecorded'] / 3)
        era = (9 * stats['earnedRuns']) / innings_pitched
        whip = (stats['hitsAllowed'] + stats['walksIssued']) / innings_pitched
        h9 = stats['hitsAllowed'] / (innings_pitched / 9)
        hr9 = stats['homeRunsAllowed'] / (innings_pitched / 9)
        so9 = stats['strikeouts'] / (innings_pitched / 9)
        if stats['walksIssued'] < 1:
            sobb = 0
        else:
            sobb = stats['strikeouts'] / stats['walksIssued']

        second_half = f"ERA: **{round(era * 100) / 100}**\n" + \
                      f"WHIP: **{round(whip * 1000) / 1000}**\n" + \
                      f"H/9: **{round(h9 * 10) / 10}**\n" + \
                      f"HR/9: **{round(hr9 * 10) / 10}**\n" + \
                      f"SO/9: **{round(so9 * 10) / 10}**\n" + \
                      f"SO/BB: **{round(sobb * 1000) / 1000}**\n"

        embed.add_field(name="Basic Stats", value=first_half)
        embed.add_field(name="Calculated Stats", value=second_half)

        if stats['shutout'] + stats['noHitter'] + stats['perfectGame'] > 0:
            notable = ""
            if stats['shutout'] > 0:
                notable += f"Shutouts: **{stats['shutout']}**\n"
            if stats['noHitter'] > 0:
                notable += f"No Hitters: **{stats['noHitter']}**\n"
            if stats['perfectGame'] > 0:
                notable += f"Perfect Games: **{stats['perfectGame']}**\n"
            embed.add_field(name='Notable Games', value=notable)

        return await response_channel.send(embed=embed)

    @commands.command(name="equivalent_exchange", aliases=['ee', 'equiv'])
    async def _equivalent_exchange(self, ctx, *, info):
        player_id = None
        info_split = info.split(",")
        if len(info_split) <= 2:
          return await ctx.send(f"Please include one of: baserunning, defense, pitching, hitting rating types.\n"
                                  f"Command syntax: `!equivalent_exchange rating, player name, options`")

        raw_rating = info_split[0]
        player_name = string.capwords(info_split[1].strip())
        # allows parsing of various keys to the bot
        options_map = {"output": {"inline": 0, "csv": 1}, 
                   "sort": {"increasing": 'asc', "inc": 'asc', "asc": 'asc', "decreasing": 'desc', "dec": 'desc', 'desc': 'desc'}
                  }
        output_format = 0 
        sort_dir = 'desc'
        on_team = ''
        on_team_name = ''
        limit = 'limit 10'
        lim = 10

        if player_name in self.bot.player_cache:
            player_id = self.bot.player_cache[player_name]["id"]
        elif player_name.lower() in self.bot.player_names:
            player_id = self.bot.player_names[player_name.lower()]
        if not player_id:
            return await ctx.send(f"Could not find player: {player_name}. Please check your spelling and try again.")

        if len(info_split) > 2:
          for opt in info_split[2:]:
            #Checks if option is one of the output options
            try:
              output_format = options_map["output"][opt.strip()]
              continue
            except:
              pass

            #Checks if option is one of the sort options
            try:
              sort_dir = options_map["sort"][opt.strip()]
              continue 
            except:
              pass

            #Sets the limit on the search.
            try:
              lim = int(opt)
              continue
            except:
              pass

            # if all that fails check if its a team name
            for team in self.bot.team_names:
              if self.bot.team_names[team].lower() == opt.strip().lower():
                  on_team = f"and team_id = '{team}'"
                  on_team_name = opt.capitalize()

        if output_format == 1:
            limit = ""
            lim = ""
        elif lim > 0:
          limit = f"limit {lim}" 
        async with aiosqlite.connect(self.bot.db_path) as db:
            async with db.execute("select league, combined_stars from PlayerLeagueAndStars where "
                                  "player_id=?", [player_id]) as cursor:
                async for row in cursor:
                    league, combined_stars = row[0], row[1]
        if not league:
            return await ctx.send(f"Could not find league info for player: {player_name}.")
        if league == 'Mild':
            other_league = 'Wild'
        else:
            other_league = 'Mild'
        other_players = []

        rating_map = {"baserunning": "baserunning_rating", "running": "baserunning_rating",
                      "pitching": "pitching_rating",
                      "hitting": "hitting_rating", "batting": "hitting_rating",
                      "defense": "defense_rating"}
        if raw_rating in rating_map:
            rating = rating_map[raw_rating]
        else:
            return await ctx.send(f"Please include one of: baserunning, defense, pitching, hitting rating types.\n"
                                  f"Command syntax: `!equivalent_exchange rating, player name, options`")
        async with aiosqlite.connect(self.bot.db_path) as db:
            async with db.execute(f"select player_id, player_name, combined_stars, team_id, team_name, {rating} "
                                  f"from playerleagueandstars where league = '{other_league}' and "
                                  f"(combined_stars > {combined_stars}-2 and combined_stars < {combined_stars}+2) {on_team}"
                                  f"group by player_id order by {rating} {sort_dir} {limit};") as cursor:
                async for row in cursor:
                    other_players.append([row[0], row[1], row[2], row[3], row[4], row[5]])
        team_caviat = f"on {string.capwords(on_team_name)}" if on_team != '' else ''
        restricted_output = ""
        if len(other_players) < 1:
            return await ctx.send(f"Could not find players within 2 stars of {player_name} {team_caviat}")
        elif len(other_players) > 10 and output_format == 0:
          restricted_output = f"**Displaying 10 of {len(other_players)} results** get full output with option `csv`"
          other_players = other_players[:10]

        p_stars = round((combined_stars * 100)) / 100
        if output_format == 0:
          if limit == '':
            filter_desc = "All players"
          elif sort_dir == 'asc':
            filter_desc = f"Bottom {len(other_players)} players"
          else:
            filter_desc = f"Top {len(other_players)} players"


          response = f"{filter_desc} by {raw_rating} within 2 combined stars of **{player_name.title()}** " \
                     f"({p_stars}) in {other_league} League {team_caviat}\n\n"
          for player in other_players:
              o_player_name, team_name = player[1], player[4]
              stars = round((player[2] * 100)) / 100
              rating_star = player[5] * 5
              rating = round((rating_star * 100)) / 100
              response += f"**{o_player_name}**: {stars} ({team_name}) - {rating}⭐ {raw_rating}\n"
          response += restricted_output
          return await ctx.send(response)
        else:
          filename = f"{player_name}-{raw_rating}-equivilant-exchange.csv"
          fieldnames = ["player", "combined_stars", "team_name", "rating"]
          with open(os.path.join('data', 'equv', 'csv', filename), 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, delimiter=',', fieldnames=fieldnames)
            writer.writeheader()
            for player in other_players:
              o_player_name, team_name = player[1], player[4]
              stars = round((player[2] * 100)) / 100
              rating_star = player[5] * 5
              rating = round((rating_star * 100)) / 100
              writer.writerow({"player": o_player_name, "combined_stars": stars, "team_name": team_name, "rating": rating})

          with open(os.path.join('data', 'equv', 'csv', filename), 'rb') as csvfile:
            await ctx.send(file=discord.File(csvfile, filename=filename))
          pass
          # Returns CSV


def setup(bot):
    bot.add_cog(PlayerStats(bot))
