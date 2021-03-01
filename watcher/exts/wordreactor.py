import asyncio
import json
import os
import re

import discord
from discord.ext import commands


class WordReactor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.word_reacts = {}
        self.load_word_reacts()

    def load_word_reacts(self):
        try:
            with open(os.path.join('data', 'word_reacts.json'), 'r') as fd:
                self.word_reacts = json.load(fd)
        except FileNotFoundError:
            self.word_reacts = {}

    def save_word_reacts(self):
        with open(os.path.join('data', 'word_reacts.json'), 'w') as fd:
            json.dump(self.word_reacts, fd, indent=4)

    @commands.command(name="add_word_react", aliases=['awr'])
    async def _add_word_react(self, ctx, *, info):
        """
        Do '!add_react_list <name>, <emoji>, <channel_id>, <word1>[,<word2>, <word3>]'
        For example: `!add_react_list snivy, :snivy:, 103110311031103110, snivy`
        Use 'none' instead of a channel id to apply this react list to all channels.
        (don't include the <> or [] when running the command)
        Also works with '!arl'
        """
        info = re.split(r',\s+', info)
        if len(info) < 2:
            await ctx.message.add_reaction(self.bot.failed_react)
            return await ctx.send(
                "Must provide at least a word and 1 reaction emoji.",
                delete_after=10)
        name = info[0]
        rl_name = f"{ctx.guild.id}_{name}"
        if rl_name in self.word_reacts.keys():
            await ctx.message.add_reaction(self.bot.failed_react)
            return await ctx.send(
                f"A reaction already exists for {name}. To add an emoji to its reaction list, use the "
                f"`!add_emoji_to_react_list/!aerl` command",
                delete_after=20)
        converter = commands.PartialEmojiConverter()
        emoji_list = []
        for i in info[1:]:
            emoji_to_add = None
            emoji = i.strip()
            try:
                emoji_to_add = await converter.convert(ctx, emoji)
                await ctx.message.add_reaction(emoji_to_add)
                emoji_list.append(emoji_to_add)
            except:
                pass
            try:
                await ctx.message.add_reaction(emoji)
                emoji_to_add = emoji
                emoji_list.append(emoji_to_add)
            except:
                pass
            if not emoji_to_add:
                await ctx.message.add_reaction(self.bot.failed_react)
                return await ctx.send(f"Could not find emoji {i}.", delete_after=10)

        self.word_reacts[rl_name] = {
            "name": name,
            "emoji_list": emoji_list,
            "guild_id": ctx.guild.id
        }
        self.save_word_reacts()
        await ctx.message.add_reaction(self.bot.success_react)

    @commands.command(name="add_emoji_to_react_list", aliases=['aerl'])
    @commands.has_permissions(manage_roles=True)
    async def _add_emoji_to_react_list(self, ctx, name, emoji):
        """
                Do '!add_emoji_to_react_list <name> <emoji>'
                For example: `!add_emoji_to_react_list blaseball, :ballclark:`
                (don't include the <> or [] when running the command)
                (don't use a comma in this command!)
                Also works with '!aerl'
                """
        rl_name = f"{ctx.guild.id}_{name.strip()}"
        if rl_name not in self.word_reacts.keys():
            await ctx.send(f"No react list named {name} found.", delete_after=10)
            return await ctx.message.add_reaction(self.bot.failed_react)
        converter = commands.PartialEmojiConverter()
        done = False
        try:
            emoji_to_add = await converter.convert(ctx, emoji)
            await ctx.message.add_reaction(emoji_to_add)
            self.word_reacts[rl_name]["emoji_list"].append(emoji_to_add)
            done = True
        except:
            try:
                await ctx.message.add_reaction(emoji)
                emoji_to_add = emoji
                self.word_reacts[rl_name]["emoji_list"].append(emoji_to_add)
                done = True
            except:
                pass
        self.save_word_reacts()
        if not done:
            await ctx.message.add_reaction(self.bot.failed_react)
            return await ctx.send(f"Could not find emoji {emoji}.", delete_after=10)


    # @commands.command(name="list_react_lists", aliases=['lrl'])
    # @commands.has_permissions(manage_roles=True)
    # async def list_react_lists(self, ctx):
    #     output = ""
    #     for key in self.react_lists.keys():
    #         if self.react_lists[key]["guild_id"] == ctx.guild.id:
    #             output += f"Name: {self.react_lists[key]['name']} - Emoji: {self.react_lists[key]['emoji']}\n"
    #             output += f"{', '.join(self.react_lists[key]['words'])}\n\n"
    #             if self.react_lists[key]["channel_id"] != "none":
    #                 output += f"Active in {self.react_lists[key]['channel_id']}"
    #     await ctx.send(output)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.guild:
            if message.guild.id in self.bot.watch_servers:
                check_str = message.clean_content.lower()
                if message.author != self.bot.user:
                    for name in self.word_reacts:
                        this_react = self.word_reacts[name]
                        if this_react["guild_id"] == message.guild.id:
                            if self._has_string(fr'\b{this_react["name"]}\b', check_str):
                                try:
                                    for emoji in this_react["emoji_list"]:
                                        await message.add_reaction(emoji)
                                        await asyncio.sleep(.25)
                                except Exception as e:
                                    pass


    @staticmethod
    def _check_words(word_list, message):
        for word in word_list:
            if word in message:
                return True
        return False

    @staticmethod
    def _has_string(string, text):
        match = re.search(string, text)
        if match:
            return True
        else:
            return False


def setup(bot):
    bot.add_cog(WordReactor(bot))
