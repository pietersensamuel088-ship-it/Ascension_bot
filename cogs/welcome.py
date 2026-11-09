import logging
import discord
from discord.ext import commands
from datetime import datetime, timezone
from utils.config import Config
from data.storage import JsonStorage

logger = logging.getLogger("AscensionBot.Welcome")


class Welcome(commands.Cog):
    """Cog handling welcome messages for Ascension SMP."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.storage = JsonStorage("welcome_data", {
            "total_welcomes": 0,
            "last_welcomed_user": None,
            "last_welcomed_at": None,
        })

    def build_welcome_embed(self, member: discord.Member) -> discord.Embed:
        """Create a clean, non-corny welcome embed matching Ascension SMP theme."""
        embed = discord.Embed(
            title="⚔️ Welcome to Ascension SMP",
            description=(
                f"Welcome, {member.mention}.\n\n"
                f"Before venturing in, make sure to read the essentials:\n"
                f"📜 **Rules** • <#{Config.RULES_CHANNEL_ID}>\n"
                f"ℹ️ **Information** • <#{Config.INFO_CHANNEL_ID}>\n\n"
                f"Prepare yourself and enjoy your journey."
            ),
            color=Config.EMBED_COLOR,
            timestamp=datetime.now(timezone.utc),
        )

        # Avatar in the top right corner
        embed.set_thumbnail(url=member.display_avatar.url)

        # Clean footer with member count & server icon
        guild_icon = member.guild.icon.url if member.guild.icon else None
        embed.set_footer(
            text=f"Ascension SMP • Member #{member.guild.member_count}",
            icon_url=guild_icon,
        )

        return embed

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Triggered whenever a new player joins the Discord server."""
        channel_id = Config.WELCOME_CHANNEL_ID
        channel = member.guild.get_channel(channel_id)

        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
                logger.error(f"Failed to find welcome channel ({channel_id}): {e}")
                return

        embed = self.build_welcome_embed(member)

        try:
            await channel.send(content=member.mention, embed=embed)
            logger.info(f"Welcomed {member} ({member.id}) in channel #{channel.name}")

            # Persist statistics in data/welcome_data.json
            data = self.storage.load()
            data["total_welcomes"] = data.get("total_welcomes", 0) + 1
            data["last_welcomed_user"] = f"{member.name} ({member.id})"
            data["last_welcomed_at"] = datetime.now(timezone.utc).isoformat()
            self.storage.save(data)

        except discord.Forbidden:
            logger.error(f"Missing permissions to send messages or embeds in channel #{channel.name} ({channel_id})")
        except Exception as e:
            logger.error(f"Error sending welcome message: {e}")

    @commands.hybrid_command(
        name="testwelcome",
        description="[Admin] Preview the Ascension SMP welcome embed.",
    )
    @commands.has_permissions(administrator=True)
    async def test_welcome(self, ctx: commands.Context, target: discord.Member = None) -> None:
        """Admin command to preview the welcome message in the current channel or welcome channel.
        Usage: /testwelcome or /testwelcome @User
        """
        member = target or ctx.author
        embed = self.build_welcome_embed(member)
        await ctx.send(content=f"*(Test Preview)* {member.mention}", embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Welcome(bot))
