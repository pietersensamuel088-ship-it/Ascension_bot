import asyncio
import io
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.config import Config
from data.storage import JsonStorage
from cogs.tickets import TicketControlView, update_ticket_data

logger = logging.getLogger("AscensionBot.Bugs")

# Dedicated JSON storage for bug reports
bug_storage = JsonStorage("bug_reports", {
    "counter": 1000,
    "reports": {}
})


def is_staff_or_owner(member: discord.Member) -> bool:
    """Check if member has Staff role, Admin role, or Owner status."""
    if member.id in (Config.OWNER_ID, Config.CO_OWNER_ID):
        return True
    if member.guild_permissions.administrator:
        return True
    return any(r.id in (Config.STAFF_ROLE_ID, Config.ADMIN_ROLE_ID) for r in member.roles)


# ==========================================
# Modal for Submitting Bug Report
# ==========================================
class BugReportModal(discord.ui.Modal, title="Submit Ascension SMP Bug Report"):
    mc_username = discord.ui.TextInput(
        label="Minecraft In-Game Username",
        placeholder="e.g. Steve or Cyntrixza",
        max_length=32,
        required=True,
    )
    bug_title = discord.ui.TextInput(
        label="Short Bug Summary",
        placeholder="Briefly state what the bug is...",
        max_length=100,
        required=True,
    )
    description = discord.ui.TextInput(
        label="What Happened / Steps to Reproduce",
        style=discord.TextStyle.paragraph,
        placeholder="Describe what you were doing when the bug occurred and what happened...",
        max_length=1500,
        required=True,
    )
    evidence = discord.ui.TextInput(
        label="Evidence / Medal Clips (Optional)",
        style=discord.TextStyle.paragraph,
        placeholder="Paste Medal.tv, YouTube, or image links here (if available)...",
        max_length=500,
        required=False,
    )

    def __init__(self, cog: "Bugs"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.handle_bug_submission(
            interaction=interaction,
            mc_username=self.mc_username.value.strip(),
            bug_title=self.bug_title.value.strip(),
            description=self.description.value.strip(),
            evidence=self.evidence.value.strip() or "None provided",
        )


# ==========================================
# Modal for Closing / Dismissing a Bug Report
# ==========================================
class BugCloseModal(discord.ui.Modal, title="Close Bug Report"):
    close_reason = discord.ui.TextInput(
        label="Reason for Closing / Dismissing",
        style=discord.TextStyle.paragraph,
        placeholder="e.g. Duplicate, Cannot Reproduce, Not a Bug, or Resolved in patch...",
        max_length=500,
        required=True,
    )

    def __init__(self, cog: "Bugs", report_id: str, message: discord.Message):
        super().__init__()
        self.cog = cog
        self.report_id = report_id
        self.message = message

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.handle_bug_close(
            interaction=interaction,
            report_id=self.report_id,
            reason=self.close_reason.value.strip(),
            message=self.message,
        )


# ==========================================
# Public View: Submit Bug Report Button
# ==========================================
class BugSubmitView(discord.ui.View):
    def __init__(self, cog: Optional["Bugs"] = None):
        super().__init__(timeout=None)
        self.cog = cog

    def get_cog(self, interaction: discord.Interaction) -> Optional["Bugs"]:
        if self.cog:
            return self.cog
        return interaction.client.get_cog("Bugs")

    @discord.ui.button(
        label="Submit Bug Report",
        style=discord.ButtonStyle.danger,
        emoji="🐛",
        custom_id="bug_submit_btn",
    )
    async def submit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = self.get_cog(interaction)
        if not cog:
            await interaction.response.send_message("❌ Bug system error.", ephemeral=True)
            return
        await interaction.response.send_modal(BugReportModal(cog))


# ==========================================
# Staff Action View: Review / Fix / Ticket / Close
# ==========================================
class BugStaffActionView(discord.ui.View):
    def __init__(self, cog: Optional["Bugs"] = None):
        super().__init__(timeout=None)
        self.cog = cog

    def get_cog(self, interaction: discord.Interaction) -> Optional["Bugs"]:
        if self.cog:
            return self.cog
        return interaction.client.get_cog("Bugs")

    def extract_report_id(self, message: discord.Message) -> Optional[str]:
        if not message.embeds:
            return None
        emb = message.embeds[0]
        # Check title
        if emb.title:
            match = re.search(r"BUG-\d+", emb.title)
            if match:
                return match.group(0)
        # Check fields
        for f in emb.fields:
            if "Report ID" in f.name:
                match = re.search(r"BUG-\d+", f.value)
                if match:
                    return match.group(0)
        return None

    @discord.ui.button(
        label="Mark Fixed",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="bug_action_fixed",
    )
    async def mark_fixed(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not isinstance(member, discord.Member) or not is_staff_or_owner(member):
            await interaction.response.send_message(
                "❌ Only staff members can take action on bug reports.", ephemeral=True
            )
            return

        report_id = self.extract_report_id(interaction.message)
        if not report_id:
            await interaction.response.send_message("❌ Could not determine Bug ID.", ephemeral=True)
            return

        cog = self.get_cog(interaction)
        if cog:
            await cog.handle_bug_fixed(interaction, report_id, interaction.message)

    @discord.ui.button(
        label="Open Ticket",
        style=discord.ButtonStyle.primary,
        emoji="🎫",
        custom_id="bug_action_ticket",
    )
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not isinstance(member, discord.Member) or not is_staff_or_owner(member):
            await interaction.response.send_message(
                "❌ Only staff members can take action on bug reports.", ephemeral=True
            )
            return

        report_id = self.extract_report_id(interaction.message)
        if not report_id:
            await interaction.response.send_message("❌ Could not determine Bug ID.", ephemeral=True)
            return

        cog = self.get_cog(interaction)
        if cog:
            await cog.handle_bug_open_ticket(interaction, report_id, interaction.message)

    @discord.ui.button(
        label="Close / Dismiss",
        style=discord.ButtonStyle.secondary,
        emoji="🔒",
        custom_id="bug_action_close",
    )
    async def close_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not isinstance(member, discord.Member) or not is_staff_or_owner(member):
            await interaction.response.send_message(
                "❌ Only staff members can take action on bug reports.", ephemeral=True
            )
            return

        report_id = self.extract_report_id(interaction.message)
        if not report_id:
            await interaction.response.send_message("❌ Could not determine Bug ID.", ephemeral=True)
            return

        cog = self.get_cog(interaction)
        if cog:
            await interaction.response.send_modal(BugCloseModal(cog, report_id, interaction.message))


# ==========================================
# Main Bugs Cog
# ==========================================
class Bugs(commands.Cog):
    """Ascension SMP Bug Report Cog with staff triage, DM notifications, and ticket linking."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        # Register persistent views for restart resilience
        self.bot.add_view(BugSubmitView(self))
        self.bot.add_view(BugStaffActionView(self))
        logger.info("Registered persistent views for Bug Report System.")

    def get_next_report_id(self) -> str:
        """Increment and return the next sequential Bug ID."""
        data = bug_storage.load()
        if not isinstance(data, dict):
            data = {"counter": 1000, "reports": {}}
        counter = data.get("counter", 1000) + 1
        data["counter"] = counter
        bug_storage.save(data)
        return f"BUG-{counter}"

    async def handle_bug_submission(
        self,
        interaction: discord.Interaction,
        mc_username: str,
        bug_title: str,
        description: str,
        evidence: str,
    ) -> None:
        """Process a submitted bug report, save to JSON, log, and send to staff review channel."""
        guild = interaction.guild
        user = interaction.user
        if not guild:
            return

        report_id = self.get_next_report_id()
        now_unix = int(datetime.now(timezone.utc).timestamp())

        # 1. Build Staff Review Embed
        staff_embed = discord.Embed(
            title=f"🛡️ Bug Report Review — [{report_id}]",
            description=f"**Title:** {bug_title}",
            color=0xE67E22,
            timestamp=datetime.now(timezone.utc),
        )
        staff_embed.add_field(name="Report ID", value=f"`{report_id}`", inline=True)
        staff_embed.add_field(name="Submitter", value=f"{user.mention} (`{user.name}` / `{user.id}`)", inline=True)
        staff_embed.add_field(name="Minecraft IGN", value=f"`{mc_username}`", inline=True)
        staff_embed.add_field(name="Status", value="🟡 **Pending Staff Review**", inline=True)
        staff_embed.add_field(name="Submitted At", value=f"<t:{now_unix}:F> (<t:{now_unix}:R>)", inline=True)
        staff_embed.add_field(name="Description / What Happened", value=description[:1000], inline=False)
        staff_embed.add_field(name="Evidence / Clips", value=evidence[:1000], inline=False)
        staff_embed.set_thumbnail(url=user.display_avatar.url)
        staff_embed.set_footer(text="Ascension SMP • Bug Triage Panel")

        # 2. Post in Staff Channel (1569414620534280293)
        staff_channel = guild.get_channel(Config.BUG_STAFF_CHANNEL_ID)
        if not staff_channel:
            try:
                staff_channel = await self.bot.fetch_channel(Config.BUG_STAFF_CHANNEL_ID)
            except Exception:
                staff_channel = None

        staff_msg = None
        if staff_channel and hasattr(staff_channel, "send"):
            try:
                staff_msg = await staff_channel.send(
                    content=f"🔔 **New Bug Report Received** [{report_id}] <@&{Config.STAFF_ROLE_ID}> <@&{Config.ADMIN_ROLE_ID}>",
                    embed=staff_embed,
                    view=BugStaffActionView(self),
                )
            except Exception as e:
                logger.error(f"Failed to send staff bug review embed: {e}")

        # 3. Post in Bug Reports Log Channel (1569416069024718919)
        log_channel = guild.get_channel(Config.BUG_LOG_CHANNEL_ID)
        if not log_channel:
            try:
                log_channel = await self.bot.fetch_channel(Config.BUG_LOG_CHANNEL_ID)
            except Exception:
                log_channel = None

        log_msg = None
        if log_channel and hasattr(log_channel, "send"):
            log_embed = discord.Embed(
                title=f"🐛 Bug Report Logged — [{report_id}]",
                description=f"**Title:** {bug_title}",
                color=0xE67E22,
                timestamp=datetime.now(timezone.utc),
            )
            log_embed.add_field(name="Report ID", value=f"`{report_id}`", inline=True)
            log_embed.add_field(name="Submitter", value=f"{user.mention} (`{user.name}`)", inline=True)
            log_embed.add_field(name="Minecraft IGN", value=f"`{mc_username}`", inline=True)
            log_embed.add_field(name="Status", value="🟡 Pending Review", inline=True)
            log_embed.add_field(name="Submitted At", value=f"<t:{now_unix}:F>", inline=True)
            log_embed.add_field(name="Description", value=description[:1000], inline=False)
            log_embed.add_field(name="Evidence", value=evidence[:1000], inline=False)
            log_embed.set_thumbnail(url=user.display_avatar.url)
            log_embed.set_footer(text="Ascension SMP • Bug Log")

            try:
                log_msg = await log_channel.send(embed=log_embed)
            except Exception as e:
                logger.error(f"Failed to post to bug log channel: {e}")

        # 4. Save to JSON Storage
        data = bug_storage.load()
        if "reports" not in data:
            data["reports"] = {}
        data["reports"][report_id] = {
            "id": report_id,
            "user_id": user.id,
            "user_name": user.name,
            "mc_username": mc_username,
            "title": bug_title,
            "description": description,
            "evidence": evidence,
            "submitted_at": now_unix,
            "status": "Pending",
            "staff_msg_id": staff_msg.id if staff_msg else None,
            "log_msg_id": log_msg.id if log_msg else None,
        }
        bug_storage.save(data)

        # 5. Acknowledge user
        await interaction.response.send_message(
            f"✅ **Bug Report Submitted!**\n"
            f"Your report **{report_id}** (`{bug_title}`) has been delivered directly to the server development team. "
            f"You will receive a DM notification once an update or fix is available.",
            ephemeral=True,
        )

    async def handle_bug_fixed(
        self,
        interaction: discord.Interaction,
        report_id: str,
        message: discord.Message,
    ) -> None:
        """Mark bug report as fixed, update embeds, and DM user."""
        staff_member = interaction.user
        data = bug_storage.load()
        report = data.get("reports", {}).get(report_id, {})

        # Update JSON status
        report["status"] = "Fixed"
        report["handled_by"] = f"{staff_member.name} ({staff_member.id})"
        report["handled_at"] = int(datetime.now(timezone.utc).timestamp())
        data["reports"][report_id] = report
        bug_storage.save(data)

        # 1. Update Staff Embed
        if message.embeds:
            emb = message.embeds[0]
            emb.color = 0x2ECC71  # Green
            for i, f in enumerate(emb.fields):
                if f.name == "Status":
                    emb.set_field_at(i, name="Status", value=f"🟢 **FIXED** by {staff_member.mention}", inline=True)
                    break
            try:
                await message.edit(embed=emb)
            except Exception:
                pass

        # 2. Update Log Channel Embed
        log_msg_id = report.get("log_msg_id")
        if log_msg_id and Config.BUG_LOG_CHANNEL_ID:
            log_channel = interaction.guild.get_channel(Config.BUG_LOG_CHANNEL_ID)
            if log_channel:
                try:
                    log_msg = await log_channel.fetch_message(log_msg_id)
                    if log_msg and log_msg.embeds:
                        log_emb = log_msg.embeds[0]
                        log_emb.color = 0x2ECC71
                        for i, f in enumerate(log_emb.fields):
                            if f.name == "Status":
                                log_emb.set_field_at(
                                    i, name="Status", value=f"🟢 FIXED by {staff_member.mention}", inline=True
                                )
                                break
                        await log_msg.edit(embed=log_emb)
                except Exception as e:
                    logger.warning(f"Could not update log embed: {e}")

        # 3. DM User
        user_id = report.get("user_id")
        user_dm_sent = False
        if user_id:
            try:
                user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                if user:
                    dm_embed = discord.Embed(
                        title="✅ Ascension SMP — Bug Report Fixed!",
                        description=(
                            f"Hello {user.mention},\n\n"
                            f"Thank you for taking the time to submit bug report **{report_id}** "
                            f"(*{report.get('title', 'Unknown')}*).\n\n"
                            f"Our development team has resolved the issue, and the fix has been applied!\n\n"
                            f"If you come across any another bug, or if this issue still seems to persist, "
                            f"please feel free to submit another bug report in <#{Config.BUG_REPORT_CHANNEL_ID}> "
                            f"or open a support ticket in <#{Config.TICKET_CHANNEL_ID}>.\n\n"
                            f"Thank you for helping us keep **Ascension SMP** fair, clean, and fun!"
                        ),
                        color=0x2ECC71,
                        timestamp=datetime.now(timezone.utc),
                    )
                    dm_embed.add_field(name="Report ID", value=f"`{report_id}`", inline=True)
                    dm_embed.add_field(name="Minecraft IGN", value=f"`{report.get('mc_username', 'Unknown')}`", inline=True)
                    dm_embed.add_field(name="Status", value="🟢 **Resolved & Fixed**", inline=True)
                    if interaction.guild.icon:
                        dm_embed.set_thumbnail(url=interaction.guild.icon.url)
                    dm_embed.set_footer(text="Ascension SMP Development Team")

                    await user.send(embed=dm_embed)
                    user_dm_sent = True
            except Exception as e:
                logger.info(f"Could not DM user {user_id} regarding fixed bug: {e}")

        await interaction.response.send_message(
            f"✅ **[{report_id}]** marked as **FIXED** by {staff_member.mention}! "
            f"({ 'User notified via DM.' if user_dm_sent else 'User DMs disabled.' })"
        )

    async def handle_bug_open_ticket(
        self,
        interaction: discord.Interaction,
        report_id: str,
        message: discord.Message,
    ) -> None:
        """Automatically create a support ticket with the user to gather further details."""
        guild = interaction.guild
        staff_member = interaction.user
        data = bug_storage.load()
        report = data.get("reports", {}).get(report_id, {})
        user_id = report.get("user_id")

        if not user_id:
            await interaction.response.send_message("❌ User ID not found for this report.", ephemeral=True)
            return

        target_member = guild.get_member(user_id)
        if not target_member:
            try:
                target_member = await guild.fetch_member(user_id)
            except Exception:
                target_member = None

        if not target_member:
            await interaction.response.send_message(
                "❌ Submitter is no longer in the Discord server.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Determine Category
        category_channel = guild.get_channel(Config.TICKETS_CATEGORY_ID)
        if not isinstance(category_channel, discord.CategoryChannel):
            category_channel = None

        clean_name = re.sub(r"[^a-zA-Z0-9]", "", target_member.name).lower()[:12] or "user"
        channel_name = f"ticket-{clean_name}-bug"

        # Overwrites
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            target_member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
                manage_channels=True,
                manage_messages=True,
                manage_threads=True,
            ),
        }

        staff_role = guild.get_role(Config.STAFF_ROLE_ID)
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
            )

        admin_role = guild.get_role(Config.ADMIN_ROLE_ID)
        if admin_role:
            overwrites[admin_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
                manage_channels=True,
                manage_messages=True,
            )

        now_unix = int(datetime.now(timezone.utc).timestamp())
        initial_topic = {
            "creator_id": target_member.id,
            "creator_name": target_member.name,
            "opened_at": now_unix,
            "type": f"Bug Inquiry ({report_id})",
            "claimed_by": staff_member.id,
            "notes_thread_id": None,
        }

        try:
            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                category=category_channel,
                overwrites=overwrites,
                topic=json.dumps(initial_topic),
                reason=f"Bug inquiry ticket for {report_id} opened by {staff_member.name}",
            )
            update_ticket_data(ticket_channel, initial_topic)
        except Exception as e:
            logger.error(f"Failed to create bug ticket channel: {e}")
            await interaction.followup.send(f"❌ Failed to create ticket channel: {e}", ephemeral=True)
            return

        # Pinned welcome control embed in new ticket
        welcome_embed = discord.Embed(
            title=f"⚔️ Bug Inquiry Ticket — [{report_id}]",
            description=(
                f"Welcome {target_member.mention}!\n\n"
                f"{staff_member.mention} has opened this support channel to discuss your recent bug report:\n"
                f"**Bug Title:** `{report.get('title', 'Unknown')}`\n"
                f"**Minecraft IGN:** `{report.get('mc_username', 'Unknown')}`\n\n"
                f"Please reply with any additional context, logs, or coordinates requested by the staff team below."
            ),
            color=Config.EMBED_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        welcome_embed.add_field(name="Category", value=f"Bug Inquiry ({report_id})", inline=True)
        welcome_embed.add_field(name="Opened For", value=target_member.mention, inline=True)
        welcome_embed.add_field(name="Claimed By", value=f"{staff_member.mention} ({staff_member.display_name})", inline=True)
        welcome_embed.add_field(name="Report Description", value=report.get("description", "None")[:500], inline=False)
        welcome_embed.set_thumbnail(url=target_member.display_avatar.url)
        welcome_embed.set_footer(text="Ascension SMP • Ticket Controls")

        pings = f"{target_member.mention} {staff_member.mention}"
        try:
            welcome_msg = await ticket_channel.send(
                content=pings,
                embed=welcome_embed,
                view=TicketControlView(),
            )
            await welcome_msg.pin(reason="Bug ticket control embed")
        except Exception as e:
            logger.warning(f"Could not pin welcome embed: {e}")

        # Update staff review card
        if message.embeds:
            emb = message.embeds[0]
            emb.color = 0x3498DB  # Blue
            for i, f in enumerate(emb.fields):
                if f.name == "Status":
                    emb.set_field_at(
                        i,
                        name="Status",
                        value=f"🎫 **Ticket Opened:** {ticket_channel.mention} by {staff_member.mention}",
                        inline=True,
                    )
                    break
            try:
                await message.edit(embed=emb)
            except Exception:
                pass

        await interaction.followup.send(
            f"✅ Ticket successfully created for **{report_id}** in {ticket_channel.mention}!",
            ephemeral=True,
        )

    async def handle_bug_close(
        self,
        interaction: discord.Interaction,
        report_id: str,
        reason: str,
        message: discord.Message,
    ) -> None:
        """Close/Dismiss bug report with a reason and notify submitter."""
        staff_member = interaction.user
        data = bug_storage.load()
        report = data.get("reports", {}).get(report_id, {})

        report["status"] = "Closed"
        report["close_reason"] = reason
        report["handled_by"] = f"{staff_member.name} ({staff_member.id})"
        report["handled_at"] = int(datetime.now(timezone.utc).timestamp())
        data["reports"][report_id] = report
        bug_storage.save(data)

        # 1. Update Staff Embed
        if message.embeds:
            emb = message.embeds[0]
            emb.color = 0x95A5A6  # Grey
            for i, f in enumerate(emb.fields):
                if f.name == "Status":
                    emb.set_field_at(
                        i,
                        name="Status",
                        value=f"🔒 **Closed / Dismissed** by {staff_member.mention}\n*Reason: {reason}*",
                        inline=True,
                    )
                    break
            try:
                await message.edit(embed=emb)
            except Exception:
                pass

        # 2. Update Log Channel Embed
        log_msg_id = report.get("log_msg_id")
        if log_msg_id and Config.BUG_LOG_CHANNEL_ID:
            log_channel = interaction.guild.get_channel(Config.BUG_LOG_CHANNEL_ID)
            if log_channel:
                try:
                    log_msg = await log_channel.fetch_message(log_msg_id)
                    if log_msg and log_msg.embeds:
                        log_emb = log_msg.embeds[0]
                        log_emb.color = 0x95A5A6
                        for i, f in enumerate(log_emb.fields):
                            if f.name == "Status":
                                log_emb.set_field_at(
                                    i, name="Status", value=f"🔒 Closed by {staff_member.mention}", inline=True
                                )
                                break
                        await log_msg.edit(embed=log_emb)
                except Exception:
                    pass

        # 3. DM User
        user_id = report.get("user_id")
        user_dm_sent = False
        if user_id:
            try:
                user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                if user:
                    dm_embed = discord.Embed(
                        title=f"🔒 Ascension SMP — Bug Report Update [{report_id}]",
                        description=(
                            f"Hello {user.mention},\n\n"
                            f"Your bug report **{report_id}** (*{report.get('title', 'Unknown')}*) has been reviewed "
                            f"and closed by our staff team.\n\n"
                            f"**Reason:**\n```{reason}```\n"
                            f"If you believe this was in error or have additional evidence, please open a support ticket "
                            f"in <#{Config.TICKET_CHANNEL_ID}>."
                        ),
                        color=0x95A5A6,
                        timestamp=datetime.now(timezone.utc),
                    )
                    dm_embed.set_footer(text="Ascension SMP Support")
                    await user.send(embed=dm_embed)
                    user_dm_sent = True
            except Exception:
                pass

        await interaction.response.send_message(
            f"🔒 **[{report_id}]** closed by {staff_member.mention}. "
            f"({ 'User notified via DM.' if user_dm_sent else 'User DMs disabled.' })"
        )

    # ==========================================
    # Slash Commands
    # ==========================================
    bug_group = app_commands.Group(name="bug", description="Ascension SMP Bug Report commands")

    @bug_group.command(
        name="setup",
        description="[Admin] Post the interactive Bug Report submission panel.",
    )
    @app_commands.describe(channel="Channel to deploy the panel in (defaults to configured bug report channel)")
    async def bug_setup_command(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ):
        member = interaction.user
        if not isinstance(member, discord.Member) or not is_staff_or_owner(member):
            await interaction.response.send_message(
                "❌ Only Administrators or Staff can deploy the bug report panel.",
                ephemeral=True,
            )
            return

        target_channel = channel or interaction.guild.get_channel(Config.BUG_REPORT_CHANNEL_ID) or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message("❌ Target channel is invalid.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🐛 ASCENSION SMP — BUG REPORTING",
            description=(
                "Encountered a bug, broken mechanic, glitch, or exploit in Ascension SMP?\n\n"
                "Click the button below to submit a formal report directly to our development team. "
                "Please be ready to provide:\n"
                "• Your **Minecraft In-Game Name**\n"
                "• A concise description of what happened\n"
                "• Any **Medal.tv clips**, screenshots, or video links\n\n"
                "Our team investigates all submissions. You will receive an automated DM notification "
                "as soon as your bug is reviewed and fixed!"
            ),
            color=Config.EMBED_COLOR,
        )

        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        embed.set_footer(text="Ascension SMP • Quality & Bug Triage")

        try:
            await target_channel.send(embed=embed, view=BugSubmitView(self))
            await interaction.response.send_message(
                f"✅ Bug report submission panel posted in {target_channel.mention}!",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Failed to post panel: {e}. Check bot permissions in that channel.",
                ephemeral=True,
            )

    @commands.command(name="setupbug")
    async def prefix_bug_setup(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """[Admin] Prefix command to deploy the bug report panel: /setupbug [#channel]"""
        if not is_staff_or_owner(ctx.author):
            await ctx.send("❌ Only Staff or Administrators can use this command.")
            return

        target_channel = channel or ctx.guild.get_channel(Config.BUG_REPORT_CHANNEL_ID) or ctx.channel
        embed = discord.Embed(
            title="🐛 ASCENSION SMP — BUG REPORTING",
            description=(
                "Encountered a bug, broken mechanic, glitch, or exploit in Ascension SMP?\n\n"
                "Click the button below to submit a formal report directly to our development team. "
                "Please be ready to provide:\n"
                "• Your **Minecraft In-Game Name**\n"
                "• A concise description of what happened\n"
                "• Any **Medal.tv clips**, screenshots, or video links\n\n"
                "Our team investigates all submissions. You will receive an automated DM notification "
                "as soon as your bug is reviewed and fixed!"
            ),
            color=Config.EMBED_COLOR,
        )
        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)
        embed.set_footer(text="Ascension SMP • Quality & Bug Triage")

        await target_channel.send(embed=embed, view=BugSubmitView(self))
        await ctx.send(f"✅ Bug report submission panel posted in {target_channel.mention}!")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Bugs(bot))
