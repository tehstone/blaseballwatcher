import discord
from discord.ext import commands
from discord.ext.commands.errors import CommandError
from inspect import signature, getfullargspec
import asyncio


class SnaxChannelCheckFail(CommandError):
    """Exception raised checks.subscriptionchannel fails"""
    pass


async def delete_error(message, error, delay):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except (discord.errors.Forbidden, discord.errors.HTTPException):
        pass
    try:
        await error.delete()
    except (discord.errors.Forbidden, discord.errors.HTTPException):
        pass


def missing_arg_msg(ctx):
    prefix = ctx.prefix.replace(ctx.bot.user.mention, '@' + ctx.bot.user.name)
    command = ctx.invoked_with
    callback = ctx.command.callback
    sig = list(signature(callback).parameters.keys())
    (args, varargs, varkw, defaults, kwonlyargs, kwonlydefaults, annotations) = getfullargspec(callback)
    if defaults:
        rqargs = args[:(- len(defaults))]
    else:
        rqargs = args
    if varargs:
        if varargs != 'args':
            rqargs.append(varargs)
    arg_num = len(ctx.args) - 1
    sig.remove('ctx')
    args_missing = sig[arg_num:]
    msg = "I'm missing some details! Usage: {prefix}{command}".format(prefix=prefix, command=command)
    for a in sig:
        if kwonlydefaults:
            if a in kwonlydefaults.keys():
                msg += ' [{0}]'.format(a)
                continue
        if a in args_missing:
            msg += ' **<{0}>**'.format(a)
        else:
            msg += ' <{0}>'.format(a)
    return msg


def custom_error_handling(bot, logger):

    @bot.event
    async def on_command_error(ctx, error):
        channel = ctx.channel
        prefix = ctx.prefix.replace(ctx.bot.user.mention, '@' + ctx.bot.user.name)
        if isinstance(error, commands.MissingRequiredArgument):
            error = await channel.send(embed=discord.Embed(colour=discord.Colour.red(), description=missing_arg_msg(ctx)))
            await delete_error(ctx.message, error, 10)
        elif isinstance(error, commands.BadArgument):
            error = await channel.send(f"Incorrect arguments provided for **{prefix}{ctx.command} command**"
                                       f"\nError: {error}")
            await delete_error(ctx.message, error, 20)
        elif isinstance(error, commands.CommandNotFound):
            pass
        elif isinstance(error, commands.CheckFailure):
            pass
        elif isinstance(error, SnaxChannelCheckFail):
            msg = f"Please use **{prefix}{ctx.invoked_with}** in the following channel"
            snax_channels = bot.config.get('snax_channels', [])
            if len(snax_channels) > 1:
                msg += 's:\n'
            else:
                msg += ': '
            counter = 0
            for c in snax_channels:
                channel = bot.get_channel(c)
                if counter > 0:
                    msg += '\n'
                if channel:
                    msg += channel.mention
                else:
                    msg += '\n#deleted-channel'
                counter += 1
            error = await ctx.channel.send(embed=discord.Embed(colour=discord.Colour.red(), description=msg))
            await delete_error(ctx.message, error, 10)
        else:
            logger.exception(type(error).__name__, exc_info=error)
