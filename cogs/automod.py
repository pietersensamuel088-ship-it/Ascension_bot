import asyncio
import logging
import re
from datetime import datetime, timezone

import discord
from discord.ext import commands

from utils.config import Config

logger = logging.getLogger("AscensionBot.AutoMod")

# Regex to strictly match Discord server invite links
DISCORD_INVITE_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?(?:discord\.(?:gg|io|me|li)|discord(?:app)?\.com/invite)/([a-zA-Z0-9\-]+)",
    re.IGNORECASE,
)


def is_immune(member: discord.Member) -> bool:
    """Check if member is exempt from AutoMod (Staff, Admin, Owners)."""
    if member.id in (Config.OWNER_ID, Config.CO_OWNER_ID):
        return True
    if member.guild_permissions.administrator:
        return True
    return any(r.id in (Config.STAFF_ROLE_ID, Config.ADMIN_ROLE_ID) for r in member.roles)


class AutoMod(commands.Cog):
    """Auto-moderation cog protecting against unauthorized Discord server invite links."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def check_message(self, message: discord.Message) -> bool:
        """Check if message contains a Discord server invite and take action."""
        if not message.guild or message.author.bot:
            return False

        if not isinstance(message.author, discord.Member):
            return False

        if is_immune(message.author):
            return False

        matches = DISCORD_INVITE_REGEX.findall(message.content)
        if not matches:
            return False

        full_matches = [m.group(0) for m in DISCORD_INVITE_REGEX.finditer(message.content)]
        invite_str = ", ".join(f"`{inv}`" for inv in full_matches)

        # 1. Delete violating message
        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound) as e:
            logger.warning(f"Could not delete invite message from {message.author}: {e}")

        # 2. Send temporary channel warning
        try:
            warn_msg = await message.channel.send(
                f"⚠️ {message.author.mention}, posting Discord server invite links is not permitted here!"
            )
            # Auto-delete warning after 6 seconds
            await asyncio.sleep(6)
            await warn_msg.delete()
        except Exception:
            pass

        # 3. Send log to automod log channel
        log_channel_id = Config.AUTOMOD_LOG_CHANNEL_ID
        if log_channel_id:
            log_channel = message.guild.get_channel(log_channel_id)
            if not log_channel:
                try:
                    log_channel = await self.bot.fetch_channel(log_channel_id)
                except Exception:
                    log_channel = None

            if log_channel and hasattr(log_channel, "send"):
                now_unix = int(datetime.now(timezone.utc).timestamp())
                log_embed = discord.Embed(
                    title="🛡️ Auto-Mod — Discord Invite Link Blocked",
                    description=f"A Discord server invite was detected and removed in {message.channel.mention}.",
                    color=0xE74C3C,
                    timestamp=datetime.now(timezone.utc),
                )
                log_embed.set_thumbnail(url=message.author.display_avatar.url)
                log_embed.add_field(
                    name="User",
                    value=f"{message.author.mention} (`{message.author.name}` / `{message.author.id}`)",
                    inline=True,
                )
                log_embed.add_field(
                    name="Channel",
                    value=f"{message.channel.mention} (`#{message.channel.name}`)",
                    inline=True,
                )
                log_embed.add_field(name="Invite Link(s) Found", value=invite_str, inline=False)
                clean_content = message.content[:1000] or "*No additional text*"
                log_embed.add_field(
                    name="Original Message Content",
                    value=f"```{clean_content}```",
                    inline=False,
                )
                log_embed.add_field(name="Timestamp", value=f"<t:{now_unix}:F> (<t:{now_unix}:R>)", inline=False)
                log_embed.set_footer(text="Ascension SMP Auto-Mod")

                try:
                    await log_channel.send(embed=log_embed)
                except Exception as e:
                    logger.error(f"Failed to send AutoMod log: {e}")

        logger.info(f"AutoMod removed invite link from {message.author} in #{message.channel.name}")
        return True

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        await self.check_message(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if before.content != after.content:
            await self.check_message(after)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoMod(bot))
