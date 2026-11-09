import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import discord
from discord.ext import commands

from utils.config import Config

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("AscensionBot")


class AscensionBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True  # Required for welcoming new joins

        status_mapping = {
            "dnd": discord.Status.dnd,
            "do_not_disturb": discord.Status.dnd,
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "invisible": discord.Status.invisible,
        }
        bot_status = status_mapping.get(Config.BOT_STATUS, discord.Status.dnd)
        activity = discord.CustomActivity(name=Config.BOT_ACTIVITY)

        super().__init__(
            command_prefix=Config.COMMAND_PREFIX,
            intents=intents,
            status=bot_status,
            activity=activity,
            help_command=None,
        )

    async def setup_hook(self) -> None:
        """Dynamically load all cogs and sync slash commands."""
        cogs_dir = Path(__file__).parent / "cogs"
        if cogs_dir.exists():
            for file in cogs_dir.glob("*.py"):
                if file.name.startswith("__"):
                    continue
                extension = f"cogs.{file.stem}"
                try:
                    await self.load_extension(extension)
                    logger.info(f"Loaded extension: {extension}")
                except Exception as e:
                    logger.error(f"Failed to load extension {extension}: {e}", exc_info=True)

        # Sync global slash commands
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} global application commands.")
        except Exception as e:
            logger.warning(f"Failed to sync application commands: {e}")

    async def on_ready(self) -> None:
        # Re-apply presence to ensure it sticks across reconnects
        status_mapping = {
            "dnd": discord.Status.dnd,
            "do_not_disturb": discord.Status.dnd,
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "invisible": discord.Status.invisible,
        }
        bot_status = status_mapping.get(Config.BOT_STATUS, discord.Status.dnd)
        activity = discord.CustomActivity(name=Config.BOT_ACTIVITY)
        await self.change_presence(status=bot_status, activity=activity)

        print("\n" + "=" * 60)
        print(f"  ⚡ Ascension SMP Discord Bot is Online! ⚡")
        print(f"  • Logged in as:   {self.user} (ID: {self.user.id})")
        print(f"  • Status:         {bot_status.name.upper()} (Do Not Disturb)")
        print(f"  • Activity:       \"{Config.BOT_ACTIVITY}\"")
        print(f"  • Connected to:   {len(self.guilds)} server(s)")
        print("  • Roles & Permissions:")
        print(f"    - Staff Role:   {Config.STAFF_ROLE_ID}")
        print(f"    - Admin Role:   {Config.ADMIN_ROLE_ID}")
        print(f"    - Owners:       {Config.OWNER_ID}, {Config.CO_OWNER_ID}")
        print("  • Channels:")
        print(f"    - Welcome:      {Config.WELCOME_CHANNEL_ID}")
        print(f"    - Rules / Info: {Config.RULES_CHANNEL_ID} / {Config.INFO_CHANNEL_ID}")
        print(f"    - Ticket Cat:   {Config.TICKETS_CATEGORY_ID or 'Not configured'}")
        print(f"    - AutoMod Log:  {Config.AUTOMOD_LOG_CHANNEL_ID}")
        print(f"    - Bug Report:   {Config.BUG_REPORT_CHANNEL_ID}")
        print(f"    - Bug Staff:    {Config.BUG_STAFF_CHANNEL_ID}")
        print(f"    - Bug Log:      {Config.BUG_LOG_CHANNEL_ID}")
        print("=" * 60 + "\n")

        # Check Server Members Intent
        if not self.intents.members:
            logger.warning(
                "CRITICAL WARNING: 'Server Members Intent' is not enabled! "
                "The bot will NOT detect new player joins until enabled in the Discord Developer Portal."
            )


def main():
    if not Config.TOKEN or Config.TOKEN == "your_bot_token_here":
        print("\n[!] ERROR: No valid DISCORD_TOKEN found in .env!")
        print("    Please open .env and set your bot token: DISCORD_TOKEN=...\n")
        sys.exit(1)

    bot = AscensionBot()

    # Admin sync command to instantly register slash commands in the current test guild
    @bot.command(name="sync")
    async def sync_guild(ctx: commands.Context):
        """Force-sync application commands to the current Discord guild immediately."""
        is_owner_user = ctx.author.id in (Config.OWNER_ID, Config.CO_OWNER_ID)
        is_admin_user = (
            is_owner_user
            or ctx.author.guild_permissions.administrator
            or any(r.id == Config.ADMIN_ROLE_ID for r in getattr(ctx.author, "roles", []))
        )
        if not is_admin_user:
            await ctx.send("❌ Only Administrators or Owners can force-sync commands.")
            return

        msg = await ctx.send("🔄 Syncing slash commands to this server...")
        try:
            bot.tree.copy_global_to(guild=ctx.guild)
            synced = await bot.tree.sync(guild=ctx.guild)
            await msg.edit(content=f"✅ Successfully synced **{len(synced)}** slash commands to this server!")
        except Exception as e:
            await msg.edit(content=f"❌ Failed to sync slash commands: `{e}`")

    try:
        bot.run(Config.TOKEN)
    except discord.LoginFailure:
        logger.error("Invalid Discord Token provided. Check your .env file.")
    except KeyboardInterrupt:
        logger.info("Bot interrupted by user. Shutting down cleanly...")


if __name__ == "__main__":
    main()
