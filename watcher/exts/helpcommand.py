import discord
from discord.ext import commands

from watcher import checks


class MyHelpCommand(commands.DefaultHelpCommand):

    def __init__(self):
        super().__init__()

    # Woooo hardcoding help command output!
    async def send_bot_help(self, mapping):
        dest = self.get_destination()
        help_embed = discord.Embed(title="Snaxfolio Commands")
        text = "!set_snax\n"
        text += "!increment_snax\n"
        text += "!snaxfolio"
        help_embed.add_field(name="Snaxfolio Management", value=text)

        text = "!set_ignore\n"
        text += "!add_ignore\n"
        text += "!remove_ignore"
        help_embed.add_field(name="Ignoring Snax", value=text)

        text = "!lucrative_batters \n"
        text += "!propose_upgrades "
        help_embed.add_field(name="Snaxfolio Usage", value=text)
        text = "Do `!help <command_name>` for any command to see more detailed help."
        help_embed.add_field(name="Additional Help", value=text)
        help_embed.set_footer(text="[ ] square brackets indicate optional parameters and should not be included in your messages")
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
