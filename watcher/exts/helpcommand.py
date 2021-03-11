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
        text = "`!set_snax snackname=quantity [,snackname=quantity...]` Sets your snack quantities.\n\n"
        text += "`!set_ignore snack [,snack2...]` Sets the list of snacks to be ignored for recommendations. " \
                "Overwrites previously set list.\n\n"
        text += "`!add_ignore snack [,snack2...]` Adds snack(s) to your list of ignored snacks\n\n"
        text += "`!remove_ignore snack [,snack2...]` Removes snack(s) from your list of ignored snacks\n\n"
        text += "`!snaxfolio` Displays your current snack quantities."
        help_embed.add_field(name="Snaxfolio Management", value=text)
        text = "`!lucrative_batters [count]` count is optional. Returns personalized best hitting idol choices based " \
               "on current performance of all players and your snaxfolio.\n\n"
        text += "`!propose_upgrades [coins], ['profit']` coins is optional. Returns optimal next snack upgrade path." \
                "Include 'profit' to sort the list by total profit rather than profit:cost ratio."
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
