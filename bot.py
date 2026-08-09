import os
import time
import discord
from discord.ext import commands
from collections import defaultdict, deque
from dotenv import load_dotenv
from keep_alive import keep_alive

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# ---------- CONFIGURATION ----------
PREFIX = "!"
MOD_LOG_CHANNEL_NAME = "mod-log"   # nom du salon où les logs de modération sont envoyés
VOUCH_CHANNEL_NAME = "⭐│feedback"  # nom du salon où les avis !vouch sont publiés

# Anti-spam : nombre de messages max autorisés dans la fenêtre de temps
SPAM_MESSAGE_LIMIT = 5
SPAM_TIME_WINDOW = 5          # secondes
SPAM_TIMEOUT_DURATION = 60    # secondes de mute en cas de spam détecté
# ------------------------------------

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=commands.DefaultHelpCommand())

# Suivi des messages par utilisateur pour l'anti-spam : {user_id: deque[timestamps]}
message_log = defaultdict(lambda: deque(maxlen=SPAM_MESSAGE_LIMIT))
# Suivi des avertissements : {user_id: [raisons]}
warnings = defaultdict(list)


async def log_action(guild: discord.Guild, message: str):
    """Envoie un message dans le salon de logs de modération, si il existe."""
    channel = discord.utils.get(guild.text_channels, name=MOD_LOG_CHANNEL_NAME)
    if channel:
        await channel.send(message)


@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"🔄 {len(synced)} commande(s) slash synchronisée(s).")
    except Exception as e:
        print(f"⚠️ Erreur de synchronisation des commandes slash : {e}")
    print("------")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    # --- Anti-spam ---
    now = time.time()
    log = message_log[message.author.id]
    log.append(now)

    if len(log) == SPAM_MESSAGE_LIMIT and (now - log[0]) < SPAM_TIME_WINDOW:
        try:
            await message.author.timeout(
                discord.utils.utcnow() + discord.timedelta(seconds=SPAM_TIMEOUT_DURATION),
                reason="Anti-spam automatique"
            )
            await message.channel.send(
                f"🔇 {message.author.mention} a été mis en sourdine {SPAM_TIMEOUT_DURATION}s pour spam."
            )
            await log_action(message.guild, f"🚨 **Anti-spam** : {message.author} mute {SPAM_TIMEOUT_DURATION}s.")
        except discord.Forbidden:
            pass
        log.clear()

    await bot.process_commands(message)


def is_mod():
    """Vérifie que l'utilisateur a la permission de gérer les messages/membres."""
    async def predicate(ctx):
        return ctx.author.guild_permissions.moderate_members or ctx.author.guild_permissions.administrator
    return commands.check(predicate)


# ---------- COMMANDES ----------

@bot.command(help="Bannit un membre. Usage: !ban @membre [raison]")
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason: str = "Aucune raison fournie"):
    await member.ban(reason=reason)
    await ctx.send(f"🔨 {member.mention} a été banni. Raison : {reason}")
    await log_action(ctx.guild, f"🔨 **Ban** : {member} banni par {ctx.author}. Raison : {reason}")


@bot.command(help="Débannit un membre via son ID. Usage: !unban <id>")
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int):
    user = await bot.fetch_user(user_id)
    await ctx.guild.unban(user)
    await ctx.send(f"✅ {user.mention} a été débanni.")
    await log_action(ctx.guild, f"✅ **Unban** : {user} débanni par {ctx.author}.")


@bot.command(help="Expulse un membre. Usage: !kick @membre [raison]")
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason: str = "Aucune raison fournie"):
    await member.kick(reason=reason)
    await ctx.send(f"👢 {member.mention} a été expulsé. Raison : {reason}")
    await log_action(ctx.guild, f"👢 **Kick** : {member} expulsé par {ctx.author}. Raison : {reason}")


@bot.command(help="Mute un membre (timeout). Usage: !mute @membre <minutes> [raison]")
@commands.has_permissions(moderate_members=True)
async def mute(ctx, member: discord.Member, minutes: int, *, reason: str = "Aucune raison fournie"):
    duration = discord.timedelta(minutes=minutes)
    await member.timeout(discord.utils.utcnow() + duration, reason=reason)
    await ctx.send(f"🔇 {member.mention} a été mute pour {minutes} min. Raison : {reason}")
    await log_action(ctx.guild, f"🔇 **Mute** : {member} mute {minutes}min par {ctx.author}. Raison : {reason}")


@bot.command(help="Retire le mute d'un membre. Usage: !unmute @membre")
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, member: discord.Member):
    await member.timeout(None)
    await ctx.send(f"🔊 {member.mention} n'est plus mute.")
    await log_action(ctx.guild, f"🔊 **Unmute** : {member} démuté par {ctx.author}.")


@bot.command(help="Avertit un membre. Usage: !warn @membre [raison]")
@commands.has_permissions(moderate_members=True)
async def warn(ctx, member: discord.Member, *, reason: str = "Aucune raison fournie"):
    warnings[member.id].append(reason)
    count = len(warnings[member.id])
    await ctx.send(f"⚠️ {member.mention} a reçu un avertissement ({count} au total). Raison : {reason}")
    await log_action(ctx.guild, f"⚠️ **Warn** : {member} averti par {ctx.author} ({count} total). Raison : {reason}")


@bot.command(name="warnings", help="Affiche les avertissements d'un membre. Usage: !warnings @membre")
async def warnings_cmd(ctx, member: discord.Member):
    user_warnings = warnings.get(member.id, [])
    if not user_warnings:
        await ctx.send(f"{member.mention} n'a aucun avertissement.")
        return
    text = "\n".join(f"{i+1}. {r}" for i, r in enumerate(user_warnings))
    await ctx.send(f"⚠️ Avertissements de {member.mention} :\n{text}")


@bot.command(help="Ajoute un rôle à un membre. Usage: !addrole @membre @role")
@commands.has_permissions(manage_roles=True)
async def addrole(ctx, member: discord.Member, role: discord.Role):
    if role >= ctx.guild.me.top_role:
        await ctx.send("❌ Je ne peux pas attribuer un rôle égal ou supérieur à mon propre rôle le plus haut.")
        return
    await member.add_roles(role)
    await ctx.send(f"✅ Le rôle {role.mention} a été ajouté à {member.mention}.")
    await log_action(ctx.guild, f"➕ **Rôle ajouté** : {role} ajouté à {member} par {ctx.author}.")


@bot.command(help="Retire un rôle à un membre. Usage: !removerole @membre @role")
@commands.has_permissions(manage_roles=True)
async def removerole(ctx, member: discord.Member, role: discord.Role):
    if role >= ctx.guild.me.top_role:
        await ctx.send("❌ Je ne peux pas retirer un rôle égal ou supérieur à mon propre rôle le plus haut.")
        return
    await member.remove_roles(role)
    await ctx.send(f"✅ Le rôle {role.mention} a été retiré à {member.mention}.")
    await log_action(ctx.guild, f"➖ **Rôle retiré** : {role} retiré à {member} par {ctx.author}.")


@bot.command(help="Supprime des messages. Usage: !clear <nombre>")
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    deleted = await ctx.channel.purge(limit=amount + 1)  # +1 pour supprimer la commande elle-même
    msg = await ctx.send(f"🧹 {len(deleted) - 1} messages supprimés.")
    await msg.delete(delay=3)


# ---------- COMMANDE !vouch (avis produit) ----------

@bot.command(
    name="vouch",
    help="Poste un avis sur un produit. Usage: !vouch <produit> <note 1-5> [commentaire]"
)
async def vouch(ctx, produit: str, note: int, *, commentaire: str = None):
    if note < 1 or note > 5:
        await ctx.send("❌ La note doit être comprise entre 1 et 5.")
        return

    channel = discord.utils.get(ctx.guild.text_channels, name=VOUCH_CHANNEL_NAME)
    if channel is None:
        await ctx.send(f"❌ Le salon #{VOUCH_CHANNEL_NAME} n'existe pas sur ce serveur.")
        return

    stars = "⭐" * note + "☆" * (5 - note)

    embed = discord.Embed(
        title="Nouvel avis",
        color=discord.Color.purple(),
        timestamp=discord.utils.utcnow()
    )
    embed.add_field(name="Produit", value=produit, inline=False)
    embed.add_field(name="Note", value=f"{stars} ({note}/5)", inline=False)
    embed.add_field(name="Commentaire", value=commentaire or "Aucun commentaire", inline=False)
    embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)

    if ctx.message.attachments:
        embed.set_image(url=ctx.message.attachments[0].url)

    await channel.send(embed=embed)
    if channel.id != ctx.channel.id:
        await ctx.send(f"✅ Ton avis a été publié dans #{VOUCH_CHANNEL_NAME} !")


# ---------- GESTION DES ERREURS ----------

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Tu n'as pas la permission d'utiliser cette commande.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ Membre introuvable.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Argument manquant. Usage : `{PREFIX}{ctx.command} {ctx.command.signature}`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Argument invalide.")
    else:
        raise error


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("❌ DISCORD_TOKEN manquant. Ajoute-le dans un fichier .env (voir README.md).")
    keep_alive()
    bot.run(TOKEN)
