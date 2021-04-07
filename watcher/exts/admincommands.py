import asyncio
import errno
import io
import json
import os
import pickle
import sys
import textwrap
import tempfile
import traceback

from contextlib import redirect_stdout

from discord.ext import commands

from watcher import checks, utils


class AdminCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.failed_react = '❌'
        self.success_react = '✅'

    async def cog_command_error(self, ctx, error):
        if isinstance(error, (commands.BadArgument, commands.MissingRequiredArgument)):
            ctx.resolved = True
            return await ctx.send_help(ctx.command)

    @commands.command(hidden=True, name="eval")
    @checks.is_dev_or_owner()
    async def _eval(self, ctx, *, body: str):
        """Evaluates a code"""
        env = {
            'bot': ctx.bot,
            'ctx': ctx,
            'channel': ctx.channel,
            'author': ctx.author,
            'guild': ctx.guild,
            'message': ctx.message,
            'guild_dict': ctx.bot.guild_dict
        }

        def cleanup_code(content):
            """Automatically removes code blocks from the code."""
            # remove ```py\n```
            if content.startswith('```') and content.endswith('```'):
                return '\n'.join(content.split('\n')[1:-1])
            # remove `foo`
            return content.strip('` \n')

        env.update(globals())
        body = cleanup_code(body)
        stdout = io.StringIO()
        to_compile = f'async def func():\n{textwrap.indent(body, "  ")}'
        try:
            exec(to_compile, env)
        except Exception as e:
            return await ctx.send(f'```py\n{e.__class__.__name__}: {e}\n```')
        func = env['func']
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception as e:
            value = stdout.getvalue()
            await ctx.send(f'```py\n{value}{traceback.format_exc()}\n```')
        else:
            value = stdout.getvalue()
            try:
                await ctx.message.add_reaction('\u2705')
            except:
                pass
            if ret is None:
                if value:
                    paginator = commands.Paginator(prefix='```py')
                    for line in textwrap.wrap(value, 80):
                        paginator.add_line(line.rstrip().replace('`', '\u200b`'))
                    for p in paginator.pages:
                        await ctx.send(p)
            else:
                ctx.bot._last_result = ret
                await ctx.send(f'```py\n{value}{ret}\n```')

    @commands.command(name='vote')
    async def vote_command(self, ctx, *, message):
        vote_message = await ctx.send(message)
        await vote_message.add_reaction("👍")
        await vote_message.add_reaction("👎")
        #await vote_message.add_reaction("<:ballclark:786049152969867341>")
        await vote_message.add_reaction("<:ballclark:766457844811431997>")

    @commands.command(name='check_for_games_complete', aliases=['cfgc'])
    async def _check_for_games_complete(self, ctx, check: bool):
        if check == self.bot.config['check_for_games_complete']:
            return await ctx.message.add_reaction(self.bot.success_react)
        self.bot.config['check_for_games_complete'] = check
        tasks = self.bot.tasks
        if check:
            event_loop = asyncio.get_event_loop()
            self.bot.tasks.append(event_loop.create_task(utils.game_check_loop(self.bot)))
        else:
            for t in range(len(tasks)):
                task = tasks[t]
                if task._coro.cr_code.co_name == "game_check_loop":
                    tasks.pop(t)
                    task.cancel()
                    break
        return await ctx.message.add_reaction(self.bot.success_react)

    @commands.command(name='save')
    @checks.is_owner()
    async def save_command(self, ctx):
        """Usage: `!save`
        Save persistent state to file, path is relative to current directory."""
        try:
            await self.save()
            self.bot.logger.info('CONFIG SAVED')
            await ctx.message.add_reaction('✅')
        except Exception as err:
            await self._print(self.bot.owner, 'Error occurred while trying to save!')
            await self._print(self.bot.owner, err)

    async def save(self):
        try:
            with open('config.json', 'w') as fd:
                json.dump(self.bot.config, fd, indent=4)
        except Exception as e:
            self.bot.logger.error(f"Failed to save config. Error: {str(e)}")
        try:
            with tempfile.NamedTemporaryFile('wb', dir=os.path.dirname(os.path.join('data', 'serverdict')),
                                             delete=False) as tf:
                pickle.dump(self.bot.guild_dict, tf, 4)
                tempname = tf.name
            try:
                os.remove(os.path.join('data', 'serverdict_backup'))
            except OSError:
                pass
            try:
                os.rename(os.path.join('data', 'serverdict'), os.path.join('data', 'serverdict_backup'))
            except OSError as e:
                if e.errno != errno.ENOENT:
                    raise
            os.rename(tempname, os.path.join('data', 'serverdict'))
        except Exception as e:
            self.bot.logger.error(f"Failed to save serverdict. Error: {str(e)}")
        rc_cog = self.bot.cogs.get('WordReactor')
        rc_cog.save_word_reacts()

    async def _print(self, owner, message):
        if 'launcher' in sys.argv[1:]:
            if 'debug' not in sys.argv[1:]:
                try:
                    await owner.send(message)
                except:
                    pass
        print(message)
        self.bot.logger.info(message)

    @commands.command()
    @checks.is_owner()
    async def restart(self, ctx):
        """Usage: `!restart`
        Calls the save function and restarts Watcher."""
        try:
            await self.save()
        except Exception as err:
            await self._print(self.bot.owner, 'Error occurred while trying to save!')
            await self._print(self.bot.owner, err)
        await ctx.channel.send('Restarting...')
        self.bot._shutdown_mode = 26
        await self.bot.close()

    @commands.command()
    @checks.is_owner()
    async def exit(self, ctx):
        """Usage: `!exit`
        Calls the save function and shuts down the bot.
        **Note**: If running bot through docker, Watcher will likely restart."""
        try:
            await self.save()
        except Exception as err:
            await self._print(self.bot.owner, 'Error occurred while trying to save!')
            await self._print(self.bot.owner, err)
        await ctx.channel.send('Shutting down...')
        self.bot._shutdown_mode = 0
        await self.bot.close()

    @commands.command(name='load')
    @checks.is_owner()
    async def _load(self, ctx, *extensions):
        for ext in extensions:
            try:
                self.bot.load_extension(f"watcher.exts.{ext}")
            except Exception as e:
                error_title = '**Error when loading extension'
                await ctx.send(f'{error_title} {ext}:**\n'
                               f'{type(e).__name__}: {e}')
            else:
                await ctx.send('**Extension {ext} Loaded.**\n'.format(ext=ext))

    @commands.command(name='reload', aliases=['rl'])
    @checks.is_owner()
    async def _reload(self, ctx, *extensions):
        for ext in extensions:
            try:
                self.bot.reload_extension(f"watcher.exts.{ext}")
            except Exception as e:
                error_title = '**Error when reloading extension'
                await ctx.send(f'{error_title} {ext}:**\n'
                               f'{type(e).__name__}: {e}')
            else:
                await ctx.send('**Extension {ext} Reloaded.**\n'.format(ext=ext))

    @commands.command(name='unload')
    @checks.is_owner()
    async def _unload(self, ctx, *extensions):
        exts = [ex for ex in extensions if f"watcher.exts.{ex}" in self.bot.extensions]
        for ex in exts:
            self.bot.unload_extension(f"watcher.exts.{ex}")
        s = 's' if len(exts) > 1 else ''
        await ctx.send("**Extension{plural} {est} unloaded.**\n".format(plural=s, est=', '.join(exts)))


    def can_manage(self, user):
        if checks.is_user_dev_or_owner(self.bot.config, user.id):
            return True
        for role in user.roles:
            if role.permissions.manage_messages:
                return True
        return False

    @commands.command(name='set_current_season', aliases=['scs'])
    @checks.is_owner()
    async def _set_current_season(self, ctx, current_season: int):
        self.bot.config['current_season'] = current_season
        await ctx.message.add_reaction(self.bot.success_react)

    @commands.command(name='toggle_rec_message_publish', aliases=['trmp'])
    @checks.is_owner()
    async def _toggle_rec_message_publish(self, ctx):
        if 'publish_rec_message' not in self.bot.config.keys():
            self.bot.config['publish_rec_message'] = False
        publish = self.bot.config['publish_rec_message']
        self.bot.config['publish_rec_message'] = not publish
        await ctx.message.add_reaction(self.bot.success_react)

    @commands.command(name='set_output_channel', aliases=['soc'])
    @checks.is_owner()
    async def _set_output_channel(self, ctx, channel_in):
        channel = await utils.get_channel_by_name_or_id(ctx, channel_in)
        if not channel:
            return await ctx.message.add_reaction(self.bot.failed_react)

        self.bot.guild_dict[ctx.guild.id]['configure_dict']['output_channel'] = channel.id
        await ctx.message.add_reaction(self.bot.success_react)


def setup(bot):
    bot.add_cog(AdminCommands(bot))
