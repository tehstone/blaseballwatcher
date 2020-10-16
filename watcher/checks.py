from discord.ext import commands
import discord.utils


def is_user_owner_check(config, userid):
    owner = config['master']
    return userid == owner


def is_user_dev_check(userid):
    dev_list = [371387628093833216]
    return userid in dev_list


def is_user_dev_or_owner(config, userid):
    if is_user_dev_check(userid) or is_user_owner_check(config, userid):
        return True
    else:
        return False


def is_owner_check(ctx):
    author = ctx.author.id
    owner = ctx.bot.config['master']
    return author == owner


def is_owner():
    return commands.check(is_owner_check)


def is_dev_check(ctx):
    author = ctx.author.id
    dev_list = [371387628093833216]
    return author in dev_list


def is_dev_or_owner():
    def predicate(ctx):
        if is_dev_check(ctx) or is_owner_check(ctx):
            return True
        else:
            return False

    return commands.check(predicate)


def check_permissions(ctx, perms):
    if not perms:
        return False
    ch = ctx.channel
    author = ctx.author
    resolved = ch.permissions_for(author)
    return all((getattr(resolved, name, None) == value for (name, value) in perms.items()))


def role_or_permissions(ctx, check, **perms):
    if check_permissions(ctx, perms):
        return True
    ch = ctx.channel
    author = ctx.author
    if ch.is_private:
        return False
    role = discord.utils.find(check, author.roles)
    return role is not None


def has_role(ctx, role):
    role = discord.utils.get(ctx.guild.roles, name=role)
    if role is None:
        return False
    author = ctx.author
    return role in author.roles


def serverowner_or_permissions(**perms):
    def predicate(ctx):
        owner = ctx.guild.owner
        if ctx.author.id == owner.id:
            return True
        allowed = check_permissions(ctx, perms)
        return allowed

    return commands.check(predicate)


def serverowner():
    return serverowner_or_permissions()


def is_dev_or_owner_or_perms(**perms):
    def predicate(ctx):
        if is_dev_check(ctx) or is_owner_check(ctx):
            return True
        else:
            return check_permissions(ctx, perms)

    return commands.check(predicate)
