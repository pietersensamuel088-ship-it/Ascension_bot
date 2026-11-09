import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.config import Config

logger = logging.getLogger("AscensionBot.Embeds")


def is_admin(member: discord.Member) -> bool:
    """Check if member has Admin role, Owner status, or Administrator permissions."""
    if member.id in (Config.OWNER_ID, Config.CO_OWNER_ID):
        return True
    if member.guild_permissions.administrator:
        return True
    return any(r.id == Config.ADMIN_ROLE_ID for r in member.roles)


class CustomEmbedModal(discord.ui.Modal, title="Create Custom Embed"):
    embed_title = discord.ui.TextInput(
        label="Embed Title",
        placeholder="Enter the title...",
        max_length=256,
        required=True,
    )
    embed_desc = discord.ui.TextInput(
        label="Description (Markdown supported)",
        style=discord.TextStyle.paragraph,
        placeholder="Enter the embed description here...",
        max_length=4000,
        required=True,
    )
    embed_footer = discord.ui.TextInput(
        label="Footer Text (Optional)",
        placeholder="Footer text...",
        max_length=2048,
        required=False,
    )

    def __init__(self, target_channel: discord.TextChannel):
        super().__init__()
        self.target_channel = target_channel

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=self.embed_title.value,
            description=self.embed_desc.value,
            color=Config.EMBED_COLOR,
        )
        if self.embed_footer.value:
            embed.set_footer(text=self.embed_footer.value)

        try:
            await self.target_channel.send(embed=embed)
            await interaction.response.send_message(
                f"✅ Custom embed successfully posted in {self.target_channel.mention}!",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Failed to send embed to {self.target_channel.mention}: {e}",
                ephemeral=True,
            )


class Embeds(commands.Cog):
    """Cog for posting structured server embeds like the Server Info and custom announcements."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def build_info_embed(self, guild: Optional[discord.Guild] = None) -> discord.Embed:
        """Construct the official Ascension SMP Server Information embed."""
        embed = discord.Embed(
            title="📌 ASCENSION SMP — SERVER INFORMATION",
            description=(
                "Welcome to **ASCENSION SMP**!\n\n"
                "Our server is proudly owned and developed by **Cyntrixza**.\n\n"
                "─────────────────────────────\n\n"
                "### 🎫 Support & Role Applications\n"
                f"Need help or want to apply for a role? Open a ticket in <#{Config.TICKET_CHANNEL_ID}>!\n\n"
                "💻 **Script Roles** – Apply for server script & development positions.\n"
                "🛡️ **Staff Applications** – Apply to become a member of our staff team.\n"
                "🏗️ **Builder Applications** – Apply to join our world construction team.\n\n"
                "─────────────────────────────\n\n"
                "### 🐛 Bug Reports & Glitches\n"
                f"Discovered a glitch, exploit, or broken mechanic? Help us keep the realm flawless by submitting an official report in <#{Config.BUG_REPORT_CHANNEL_ID}>!\n"
                "Our development team reviews every submission and sends you direct updates once resolved.\n\n"
                "─────────────────────────────\n\n"
                "### ❤️ A MESSAGE FROM US\n"
                "> *God loves you and cares for you!*\n\n"
                "Thank you for being part of **ASCENSION SMP**. We hope you enjoy your stay and embark on an unforgettable journey!"
            ),
            color=Config.EMBED_COLOR,
        )

        if guild and guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
            embed.set_footer(text="Ascension SMP • Server Guide & Information", icon_url=guild.icon.url)
        else:
            embed.set_footer(text="Ascension SMP • Server Guide & Information")

        return embed

    embed_group = app_commands.Group(name="embed", description="Ascension SMP embed management commands")

    @embed_group.command(
        name="post",
        description="[Admin] Post a pre-built or custom embed in a designated channel.",
    )
    @app_commands.describe(
        template="Which embed to post (Info Embed or Custom)",
        channel="Channel to post the embed in (defaults to configured channel or current channel)",
    )
    @app_commands.choices(
        template=[
            app_commands.Choice(name="📌 Server Information Embed", value="info"),
            app_commands.Choice(name="📝 Custom Embed (Opens Editor Modal)", value="custom"),
        ]
    )
    async def post_embed_command(
        self,
        interaction: discord.Interaction,
        template: str,
        channel: Optional[discord.TextChannel] = None,
    ):
        member = interaction.user
        if not isinstance(member, discord.Member) or not is_admin(member):
            await interaction.response.send_message(
                "❌ Only Administrators and Owners can post official embeds.", ephemeral=True
            )
            return

        if template == "info":
            target_channel = channel or interaction.guild.get_channel(Config.INFO_CHANNEL_ID) or interaction.channel
            if not isinstance(target_channel, discord.TextChannel):
                await interaction.response.send_message("❌ Target channel is invalid.", ephemeral=True)
                return

            embed = self.build_info_embed(interaction.guild)
            try:
                await target_channel.send(embed=embed)
                await interaction.response.send_message(
                    f"✅ Server Information embed posted in {target_channel.mention}!",
                    ephemeral=True,
                )
            except Exception as e:
                await interaction.response.send_message(
                    f"❌ Failed to post embed: {e}. Check bot permissions in that channel.",
                    ephemeral=True,
                )

        elif template == "custom":
            target_channel = channel or interaction.channel
            if not isinstance(target_channel, discord.TextChannel):
                await interaction.response.send_message("❌ Target channel is invalid.", ephemeral=True)
                return
            await interaction.response.send_modal(CustomEmbedModal(target_channel))

    # Prefix command fallback
    @commands.command(name="postinfo")
    async def prefix_post_info(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """[Admin] Prefix command to post the server info embed: /postinfo [#channel]"""
        if not is_admin(ctx.author):
            await ctx.send("❌ Only Administrators or Owners can use this command.")
            return

        target_channel = channel or ctx.guild.get_channel(Config.INFO_CHANNEL_ID) or ctx.channel
        embed = self.build_info_embed(ctx.guild)
        await target_channel.send(embed=embed)
        await ctx.send(f"✅ Server Information embed posted in {target_channel.mention}!")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Embeds(bot))
