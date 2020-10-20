import discord
from discord.ext import commands

from watcher import checks


class MyHelpCommand(commands.DefaultHelpCommand):

    def __init__(self):
        super().__init__()

    # Woooo hardcoding help command output!
    async def send_bot_help(self, mapping):
        dest = self.get_destination()
        help_embed = discord.Embed(title="Stat lookup commands")
        text = "**!strikeout_leaderboard** `!k_lb [season]`\nOptionally include a 1-indexed season number, " \
               "defaults to current season\nDisplays each team's shutout count for the season indicated.\n\n"
        text += "**!shutout_leaderboard** `!sho_lb [season]`\nOptionally include a 1-indexed season number, " \
                "defaults to current season\nDisplays each team's strikeout count for the season indicated.\n"
        help_embed.add_field(name="Leaderboard commands", value=text)
        text = "**!team_strikeouts** `!t_ks team nickname [season]`\nRequires the nickname of a team. Optionally " \
               "include a 1-indexed season number, defaults to current season.\nDisplays the team's count of" \
               "times struckout in the season indicated.\n\n"
        text += "**!team_shutouts** `!t_sho team nickname [season]`\nRequires the nickname of a team. Optionally " \
                "include a 1-indexed season number, defaults to current season.\nDisplays the team's count of" \
                "times shutout in the season indicated.\n"
        help_embed.add_field(name="Team stat commands", value=text)
        await dest.send(embed=help_embed)


class HelpCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._original_help_command = bot.help_command
        self.user = bot.user
        self.help_command = bot.help_command = MyHelpCommand()
        bot.help_command.cog = self

    def cog_unload(self):
        self.bot.help_command = self._original_help_command


def setup(bot):
    bot.add_cog(HelpCommand(bot))
