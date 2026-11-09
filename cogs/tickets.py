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
from utils.transcript import generate_html_transcript, format_duration
from data.storage import JsonStorage

logger = logging.getLogger("AscensionBot.Tickets")

# Dedicated JSON storage for active ticket state to eliminate Discord channel.edit() rate limits
ticket_storage = JsonStorage("tickets_data", {})


def is_owner(user_id: int) -> bool:
    """Check if the user is the Owner or Co-Owner."""
    return user_id in (Config.OWNER_ID, Config.CO_OWNER_ID)


def is_admin(member: discord.Member) -> bool:
    """Check if member has Admin role, Owner status, or Administrator permissions."""
    if is_owner(member.id):
        return True
    if member.guild_permissions.administrator:
        return True
    return any(r.id == Config.ADMIN_ROLE_ID for r in member.roles)


def is_staff(member: discord.Member) -> bool:
    """Check if member has Staff role, Admin role, or Owner status."""
    if is_admin(member):
        return True
    return any(r.id == Config.STAFF_ROLE_ID for r in member.roles)


def parse_topic_data(topic: Optional[str]) -> Optional[dict]:
    """Parse JSON metadata stored in channel topic."""
    if not topic:
        return None
    try:
        data = json.loads(topic)
        if isinstance(data, dict) and "creator_id" in data:
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def get_ticket_data(channel: discord.TextChannel) -> dict:
    """Retrieve ticket metadata from local JSON storage or fallback to channel topic."""
    ch_id_str = str(channel.id)
    cached = ticket_storage.get(ch_id_str)
    if cached and isinstance(cached, dict) and "creator_id" in cached:
        return cached

    topic_data = parse_topic_data(channel.topic) or {}
    if topic_data:
        ticket_storage.set(ch_id_str, topic_data)
        return topic_data
    return {}


def update_ticket_data(channel: discord.TextChannel, updates: dict) -> dict:
    """Update ticket metadata in local JSON storage without calling channel.edit().
    (Prevents Discord 429 rate limits on PATCH /channels/{id} which is limited to 2 per 10 mins).
    """
    ch_id_str = str(channel.id)
    data = get_ticket_data(channel)
    data.update(updates)
    ticket_storage.set(ch_id_str, data)
    return data


def delete_ticket_data(channel_id: int) -> None:
    """Clean up ticket data when closed."""
    all_data = ticket_storage.load()
    if isinstance(all_data, dict) and str(channel_id) in all_data:
        all_data.pop(str(channel_id), None)
        ticket_storage.save(all_data)


def get_staff_notes_thread(
    channel: discord.TextChannel, notes_thread_id: Optional[int] = None
) -> Optional[discord.Thread]:
    """Find the private staff notes thread for a ticket channel without rate limits."""
    # 1. By ID if known
    if notes_thread_id:
        th = channel.get_thread(notes_thread_id)
        if th and not th.archived:
            return th
        for th in channel.guild.threads:
            if th.id == notes_thread_id and not th.archived:
                return th

    # 2. Search active threads in channel
    for th in channel.threads:
        if th.name.startswith("staff-notes-") and not th.archived:
            return th

    # 3. Search guild cached threads
    for th in channel.guild.threads:
        if th.parent_id == channel.id and th.name.startswith("staff-notes-") and not th.archived:
            return th

    return None


# ==========================================
# Modal for Ticket Close Reason
# ==========================================
class CloseReasonModal(discord.ui.Modal, title="Close Support Ticket"):
    reason_input = discord.ui.TextInput(
        label="Reason for Closing",
        style=discord.TextStyle.paragraph,
        placeholder="Briefly describe why this ticket is being closed (optional)...",
        required=False,
        max_length=500,
    )

    def __init__(self, cog: "Tickets", channel: discord.TextChannel):
        super().__init__()
        self.cog = cog
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        reason = self.reason_input.value.strip() or "No reason provided."
        await interaction.response.send_message(
            f"🔒 Closing ticket with reason: *{reason}*...", ephemeral=True
        )
        await self.cog.execute_ticket_close(
            channel=self.channel,
            closed_by=interaction.user,
            reason=reason,
        )


# ==========================================
# In-Channel Persistent Control Buttons
# ==========================================
class TicketControlView(discord.ui.View):
    def __init__(self, cog: Optional["Tickets"] = None):
        super().__init__(timeout=None)
        self.cog = cog

    def get_cog(self, interaction: discord.Interaction) -> Optional["Tickets"]:
        if self.cog:
            return self.cog
        return interaction.client.get_cog("Tickets")

    @discord.ui.button(
        label="Claim Ticket",
        style=discord.ButtonStyle.primary,
        emoji="🙋",
        custom_id="ticket_btn_claim",
    )
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return

        topic_data = get_ticket_data(channel)
        if not topic_data:
            await interaction.response.send_message(
                "❌ This channel is not a valid ticket channel.", ephemeral=True
            )
            return

        member = interaction.user
        if not isinstance(member, discord.Member) or not is_staff(member):
            await interaction.response.send_message(
                "❌ Only staff members can claim tickets.", ephemeral=True
            )
            return

        current_claimer = topic_data.get("claimed_by")
        if current_claimer:
            if current_claimer == member.id:
                await interaction.response.send_message(
                    "⚠️ You have already claimed this ticket!", ephemeral=True
                )
                return
            if not is_admin(member):
                await interaction.response.send_message(
                    f"⚠️ This ticket is already claimed by <@{current_claimer}>.", ephemeral=True
                )
                return

        # Update metadata locally (prevents Discord 429 channel edit rate limits)
        update_ticket_data(channel, {"claimed_by": member.id})

        # Update pinned welcome embed if found
        async for msg in channel.history(limit=15):
            if msg.author == interaction.client.user and msg.embeds:
                emb = msg.embeds[0]
                if emb.title and "Ascension SMP Support Ticket" in emb.title:
                    for i, f in enumerate(emb.fields):
                        if f.name == "Claimed By":
                            emb.set_field_at(
                                i,
                                name="Claimed By",
                                value=f"{member.mention} ({member.display_name})",
                                inline=True,
                            )
                            break
                    try:
                        await msg.edit(embed=emb)
                    except Exception as e:
                        logger.warning(f"Could not update welcome embed: {e}")
                    break

        await interaction.response.send_message(
            f"🙋 {member.mention} has claimed this ticket!"
        )

        # Log to #ticket-logs-claimed
        cog = self.get_cog(interaction)
        if cog:
            now_unix = int(datetime.now(timezone.utc).timestamp())
            log_embed = discord.Embed(
                title="🙋 Ticket Claimed",
                color=0x3498DB,
                timestamp=datetime.now(timezone.utc),
            )
            log_embed.add_field(name="Ticket", value=f"{channel.mention} (`{channel.name}`)", inline=True)
            log_embed.add_field(name="Claimed By", value=f"{member.mention} (`{member.name}`)", inline=True)
            log_embed.add_field(name="Creator", value=f"<@{topic_data.get('creator_id')}>", inline=True)
            log_embed.add_field(name="Timestamp", value=f"<t:{now_unix}:f>", inline=False)
            await cog.send_log(interaction.guild, Config.LOGS_CLAIMED_CHANNEL_ID, embed=log_embed)

    @discord.ui.button(
        label="Release Claim",
        style=discord.ButtonStyle.secondary,
        emoji="🔓",
        custom_id="ticket_btn_release",
    )
    async def release_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return

        topic_data = get_ticket_data(channel)
        if not topic_data:
            await interaction.response.send_message(
                "❌ This channel is not a valid ticket channel.", ephemeral=True
            )
            return

        member = interaction.user
        if not isinstance(member, discord.Member) or not is_staff(member):
            await interaction.response.send_message(
                "❌ Only staff members can release ticket claims.", ephemeral=True
            )
            return

        current_claimer = topic_data.get("claimed_by")
        if not current_claimer:
            await interaction.response.send_message(
                "⚠️ This ticket is not currently claimed.", ephemeral=True
            )
            return

        if current_claimer != member.id and not is_admin(member):
            await interaction.response.send_message(
                f"❌ Only <@{current_claimer}> or an Administrator can release this claim.",
                ephemeral=True,
            )
            return

        # Clear claimer locally (prevents Discord 429 channel edit rate limits)
        update_ticket_data(channel, {"claimed_by": None})

        # Update pinned welcome embed
        async for msg in channel.history(limit=15):
            if msg.author == interaction.client.user and msg.embeds:
                emb = msg.embeds[0]
                if emb.title and "Ascension SMP Support Ticket" in emb.title:
                    for i, f in enumerate(emb.fields):
                        if f.name == "Claimed By":
                            emb.set_field_at(
                                i,
                                name="Claimed By",
                                value="*Unclaimed*",
                                inline=True,
                            )
                            break
                    try:
                        await msg.edit(embed=emb)
                    except Exception as e:
                        logger.warning(f"Could not update welcome embed: {e}")
                    break

        await interaction.response.send_message(
            f"🔓 {member.mention} released the claim on this ticket."
        )

        # Log to #ticket-logs-claimed
        cog = self.get_cog(interaction)
        if cog:
            now_unix = int(datetime.now(timezone.utc).timestamp())
            log_embed = discord.Embed(
                title="🔓 Ticket Claim Released",
                color=0xE67E22,
                timestamp=datetime.now(timezone.utc),
            )
            log_embed.add_field(name="Ticket", value=f"{channel.mention} (`{channel.name}`)", inline=True)
            log_embed.add_field(name="Released By", value=f"{member.mention} (`{member.name}`)", inline=True)
            log_embed.add_field(name="Creator", value=f"<@{topic_data.get('creator_id')}>", inline=True)
            log_embed.add_field(name="Timestamp", value=f"<t:{now_unix}:f>", inline=False)
            await cog.send_log(interaction.guild, Config.LOGS_CLAIMED_CHANNEL_ID, embed=log_embed)

    @discord.ui.button(
        label="Staff Notes",
        style=discord.ButtonStyle.success,
        emoji="📝",
        custom_id="ticket_btn_staff_notes",
    )
    async def staff_notes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return

        topic_data = get_ticket_data(channel)
        if not topic_data:
            await interaction.response.send_message(
                "❌ This channel is not a valid ticket channel.", ephemeral=True
            )
            return

        member = interaction.user
        if not isinstance(member, discord.Member) or not is_staff(member):
            await interaction.response.send_message(
                "❌ Only staff members can open staff notes.", ephemeral=True
            )
            return

        # Check if staff notes thread already exists
        notes_thread_id = topic_data.get("notes_thread_id")
        existing_thread = get_staff_notes_thread(channel, notes_thread_id)
        if existing_thread:
            await interaction.response.send_message(
                f"ℹ️ Staff notes thread already exists: {existing_thread.mention}",
                ephemeral=True,
            )
            return

        creator_name = topic_data.get("creator_name", "user")
        sanitized_name = re.sub(r"[^a-zA-Z0-9]", "", creator_name).lower()[:15] or "user"

        try:
            # Create a Private Discord Thread inside the ticket channel
            thread = await channel.create_thread(
                name=f"staff-notes-{sanitized_name}",
                type=discord.ChannelType.private_thread,
                reason="Private internal staff notes for Ascension SMP ticket",
            )
        except Exception as e:
            logger.error(f"Failed to create private thread: {e}")
            await interaction.response.send_message(
                f"❌ Failed to create private thread: {e}. Check bot permissions ('Manage Threads').",
                ephemeral=True,
            )
            return

        # Store thread ID locally (prevents Discord 429 channel edit rate limits)
        update_ticket_data(channel, {"notes_thread_id": thread.id})

        # Add interacting staff member
        try:
            await thread.add_user(member)
        except Exception:
            pass

        # Send starter message in the private thread pinging Staff & Admin roles
        intro_embed = discord.Embed(
            title="🔒 Private Staff Notes Thread",
            description=(
                "Use this private thread for internal evidence review, discussions, and decisions.\n\n"
                f"⚠️ **Note:** The ticket creator (<@{topic_data.get('creator_id')}>) **cannot** see or access this thread."
            ),
            color=0x9B59B6,
            timestamp=datetime.now(timezone.utc),
        )
        staff_pings = f"<@&{Config.STAFF_ROLE_ID}> <@&{Config.ADMIN_ROLE_ID}>"
        await thread.send(content=staff_pings, embed=intro_embed)

        await interaction.response.send_message(
            f"📝 Private staff notes thread created: {thread.mention}", ephemeral=True
        )

        # Log to #ticket-logs-staff-notes
        cog = self.get_cog(interaction)
        if cog:
            now_unix = int(datetime.now(timezone.utc).timestamp())
            log_embed = discord.Embed(
                title="📝 Staff Notes Initialized",
                color=0x9B59B6,
                timestamp=datetime.now(timezone.utc),
            )
            log_embed.add_field(name="Ticket", value=f"{channel.mention} (`{channel.name}`)", inline=True)
            log_embed.add_field(name="Staff Member", value=f"{member.mention} (`{member.name}`)", inline=True)
            log_embed.add_field(name="Thread", value=f"{thread.name}", inline=True)
            log_embed.add_field(name="Timestamp", value=f"<t:{now_unix}:f>", inline=False)
            await cog.send_log(interaction.guild, Config.LOGS_STAFF_NOTES_CHANNEL_ID, embed=log_embed)

    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="ticket_btn_close",
    )
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return

        topic_data = parse_topic_data(channel.topic)
        if not topic_data:
            await interaction.response.send_message(
                "❌ This channel is not a valid ticket channel.", ephemeral=True
            )
            return

        member = interaction.user
        creator_id = topic_data.get("creator_id")

        # Allowed if Staff, Admin, Owner, or Ticket Creator
        can_close = False
        if isinstance(member, discord.Member) and is_staff(member):
            can_close = True
        elif member.id == creator_id or is_owner(member.id):
            can_close = True

        if not can_close:
            await interaction.response.send_message(
                "❌ You do not have permission to close this ticket.", ephemeral=True
            )
            return

        cog = self.get_cog(interaction)
        if not cog:
            await interaction.response.send_message("❌ Ticket system cog error.", ephemeral=True)
            return

        # Prompt confirmation modal for optional reason
        await interaction.response.send_modal(CloseReasonModal(cog, channel))


# ==========================================
# Ticket Panel Persistent Dropdown Menu
# ==========================================
class TicketCategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="General Support",
                emoji="💬",
                description="General inquiries, server questions, and gameplay help.",
                value="General Support",
            ),
            discord.SelectOption(
                label="Player Report",
                emoji="🚨",
                description="Report griefing, rule breakers, hacking, or misconduct.",
                value="Player Report",
            ),
            discord.SelectOption(
                label="Appeal",
                emoji="⚖️",
                description="Submit an appeal for a ban, mute, or warning.",
                value="Appeal",
            ),
            discord.SelectOption(
                label="Other",
                emoji="📋",
                description="Miscellaneous assistance or partnership requests.",
                value="Other",
            ),
        ]
        super().__init__(
            placeholder="Select a category to open a ticket...",
            min_values=1,
            max_values=1,
            custom_id="ticket_panel_category_select",
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        category_name = self.values[0]
        cog: Optional["Tickets"] = interaction.client.get_cog("Tickets")
        if not cog:
            await interaction.response.send_message("❌ Ticket cog is not loaded.", ephemeral=True)
            return

        await cog.create_ticket(interaction, category_name)


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketCategorySelect())


# ==========================================
# Main Tickets Cog
# ==========================================
class Tickets(commands.Cog):
    """Ascension SMP Ticket System Cog (Database-free, Channel Metadata)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        # Register persistent views so buttons and select menus work across restarts
        self.bot.add_view(TicketPanelView())
        self.bot.add_view(TicketControlView(self))
        logger.info("Registered persistent views for Ticket System.")

    async def send_log(
        self,
        guild: discord.Guild,
        channel_id: int,
        content: Optional[str] = None,
        embed: Optional[discord.Embed] = None,
        file: Optional[discord.File] = None,
    ) -> Optional[discord.Message]:
        """Safely deliver logs to staff log channels without throwing errors if unconfigured."""
        if not channel_id:
            return None

        channel = guild.get_channel(channel_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception:
                return None

        if channel and hasattr(channel, "send"):
            try:
                return await channel.send(content=content, embed=embed, file=file)
            except Exception as e:
                logger.error(f"Failed to send log to channel {channel_id}: {e}")
        return None

    def find_active_ticket_channel(self, guild: discord.Guild, user_id: int) -> Optional[discord.TextChannel]:
        """Check if user already has an active ticket open."""
        target_category = guild.get_channel(Config.TICKETS_CATEGORY_ID)
        channels = target_category.text_channels if isinstance(target_category, discord.CategoryChannel) else guild.text_channels

        for ch in channels:
            if ch.name.startswith("ticket-"):
                data = get_ticket_data(ch)
                if data and data.get("creator_id") == user_id:
                    return ch
        return None

    async def create_ticket(self, interaction: discord.Interaction, category_name: str) -> None:
        """Handle new ticket creation flow."""
        guild = interaction.guild
        user = interaction.user

        if not guild or not isinstance(user, discord.Member):
            return

        # 1. Check for duplicate ticket
        existing_channel = self.find_active_ticket_channel(guild, user.id)
        if existing_channel:
            await interaction.response.send_message(
                f"❌ You already have an open ticket in {existing_channel.mention}! Please use that channel or close it first.",
                ephemeral=True,
            )
            return

        # Acknowledge interaction while channel creates
        await interaction.response.defer(ephemeral=True)

        # 2. Determine Category
        category_channel = guild.get_channel(Config.TICKETS_CATEGORY_ID)
        if not isinstance(category_channel, discord.CategoryChannel):
            category_channel = None

        # 3. Setup Channel Name & Overwrites
        clean_name = re.sub(r"[^a-zA-Z0-9]", "", user.name).lower()[:15] or str(user.id)
        channel_name = f"ticket-{clean_name}"

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
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

        # Staff Role overwrite
        staff_role = guild.get_role(Config.STAFF_ROLE_ID)
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
            )

        # Admin Role overwrite
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

        # 4. Create Channel
        now_unix = int(datetime.now(timezone.utc).timestamp())
        initial_topic = {
            "creator_id": user.id,
            "creator_name": user.name,
            "opened_at": now_unix,
            "type": category_name,
            "claimed_by": None,
            "notes_thread_id": None,
        }

        try:
            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                category=category_channel,
                overwrites=overwrites,
                topic=json.dumps(initial_topic),
                reason=f"Ascension SMP Ticket opened by {user.name} ({user.id})",
            )
            # Store initial ticket data in local storage
            update_ticket_data(ticket_channel, initial_topic)
        except Exception as e:
            logger.error(f"Failed to create ticket channel: {e}")
            await interaction.followup.send(
                f"❌ Failed to create ticket channel: {e}. Check bot permissions.",
                ephemeral=True,
            )
            return

        # 5. Send Welcome Pinned Control Embed
        welcome_embed = discord.Embed(
            title="⚔️ Ascension SMP Support Ticket",
            description=(
                f"Welcome, {user.mention}!\n\n"
                f"A member of our staff team will assist you shortly. "
                f"Please describe your issue, request, or report in detail below and attach any relevant evidence."
            ),
            color=Config.EMBED_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        welcome_embed.add_field(name="Category", value=category_name, inline=True)
        welcome_embed.add_field(name="Opened By", value=user.mention, inline=True)
        welcome_embed.add_field(name="Claimed By", value="*Unclaimed*", inline=True)
        welcome_embed.set_thumbnail(url=user.display_avatar.url)
        welcome_embed.set_footer(text="Ascension SMP • Ticket Controls", icon_url=guild.icon.url if guild.icon else None)

        pings = f"{user.mention} <@&{Config.STAFF_ROLE_ID}>"
        try:
            welcome_msg = await ticket_channel.send(
                content=pings,
                embed=welcome_embed,
                view=TicketControlView(self),
            )
            await welcome_msg.pin(reason="Ticket control embed")
        except Exception as e:
            logger.warning(f"Failed to send/pin control message: {e}")

        # Respond to user
        await interaction.followup.send(
            f"✅ Your ticket has been created: {ticket_channel.mention}",
            ephemeral=True,
        )

        # 6. Send Opened Ticket Log to #ticket-logs-opened
        open_log_embed = discord.Embed(
            title="🎫 Ticket Opened",
            color=0x2ECC71,
            timestamp=datetime.now(timezone.utc),
        )
        open_log_embed.add_field(name="Ticket", value=f"{ticket_channel.mention} (`{ticket_channel.name}`)", inline=True)
        open_log_embed.add_field(name="Creator", value=f"{user.mention} (`{user.name}` / `{user.id}`)", inline=True)
        open_log_embed.add_field(name="Category", value=category_name, inline=True)
        open_log_embed.add_field(name="Opened At", value=f"<t:{now_unix}:F> (<t:{now_unix}:R>)", inline=False)
        open_log_embed.set_thumbnail(url=user.display_avatar.url)

        await self.send_log(guild, Config.LOGS_OPENED_CHANNEL_ID, embed=open_log_embed)

    async def execute_ticket_close(
        self,
        channel: discord.TextChannel,
        closed_by: discord.User | discord.Member,
        reason: str,
    ) -> None:
        """Handle 5-second countdown, transcript generation, archiving, and channel deletion."""
        guild = channel.guild
        topic_data = get_ticket_data(channel)

        creator_id = topic_data.get("creator_id", 0)
        creator_name = topic_data.get("creator_name", "Unknown")
        category_name = topic_data.get("type", "General Support")
        claimed_by_id = topic_data.get("claimed_by")
        opened_at_unix = topic_data.get("opened_at", int(channel.created_at.timestamp()))
        notes_thread_id = topic_data.get("notes_thread_id")
        closed_at_unix = int(datetime.now(timezone.utc).timestamp())
        duration_text = format_duration(closed_at_unix - opened_at_unix)

        # 1. Post countdown notice
        countdown_embed = discord.Embed(
            title="🔒 Ticket Closing",
            description=(
                f"{closed_by.mention} has closed this ticket.\n"
                f"The channel will be archived and deleted in **5 seconds**...\n\n"
                f"**Reason:** {reason}"
            ),
            color=0xE74C3C,
            timestamp=datetime.now(timezone.utc),
        )
        try:
            await channel.send(embed=countdown_embed)
        except Exception:
            pass

        # 2. Scrape messages from main channel
        main_messages = []
        try:
            async for msg in channel.history(limit=None, oldest_first=True):
                main_messages.append(msg)
        except Exception as e:
            logger.error(f"Error fetching channel history: {e}")

        # 3. Scrape messages from staff notes thread if exists
        notes_messages = []
        thread = get_staff_notes_thread(channel, notes_thread_id)
        if thread and hasattr(thread, "history"):
            try:
                async for msg in thread.history(limit=None, oldest_first=True):
                    notes_messages.append(msg)
            except Exception as e:
                logger.warning(f"Could not fetch staff notes history: {e}")

        # 4. Resolve claimer name
        claimer_name = "Unclaimed"
        if claimed_by_id:
            claimer_member = guild.get_member(claimed_by_id)
            if claimer_member:
                claimer_name = f"{claimer_member.display_name} ({claimer_member.id})"
            else:
                claimer_name = f"User ID {claimed_by_id}"

        # 5. Generate self-contained HTML transcript
        html_content = generate_html_transcript(
            ticket_name=channel.name,
            category=category_name,
            creator_name=creator_name,
            creator_id=creator_id,
            claimer_name=claimer_name,
            closer_name=f"{closed_by.display_name} ({closed_by.id})",
            opened_at_unix=opened_at_unix,
            closed_at_unix=closed_at_unix,
            reason=reason,
            main_messages=main_messages,
            notes_messages=notes_messages,
        )

        transcript_bytes = html_content.encode("utf-8")
        transcript_filename = f"transcript-{channel.name}.html"

        # 6. Upload transcript to #ticket-transcripts
        transcript_msg_url = None
        if Config.TRANSCRIPTS_CHANNEL_ID:
            ts_embed = discord.Embed(
                title=f"📁 Ticket Transcript — {channel.name}",
                description=f"Archive for closed ticket **{channel.name}**.",
                color=Config.EMBED_COLOR,
                timestamp=datetime.now(timezone.utc),
            )
            ts_embed.add_field(name="Category", value=category_name, inline=True)
            ts_embed.add_field(name="Creator", value=f"<@{creator_id}> (`{creator_id}`)", inline=True)
            ts_embed.add_field(name="Closed By", value=f"{closed_by.mention}", inline=True)
            ts_embed.add_field(name="Closed At", value=f"<t:{closed_at_unix}:f>", inline=True)

            ts_file = discord.File(io.BytesIO(transcript_bytes), filename=transcript_filename)
            sent_ts_msg = await self.send_log(
                guild,
                Config.TRANSCRIPTS_CHANNEL_ID,
                embed=ts_embed,
                file=ts_file,
            )
            if sent_ts_msg:
                transcript_msg_url = sent_ts_msg.jump_url

        # 7. Send DM to ticket creator with personal transcript copy, ID, reason, and closer info
        dm_delivered = False
        if creator_id:
            try:
                creator_user = self.bot.get_user(creator_id) or await self.bot.fetch_user(creator_id)
                if creator_user:
                    dm_embed = discord.Embed(
                        title="🔒 Ascension SMP — Ticket Closed",
                        description=(
                            f"Hello {creator_user.mention},\n"
                            f"Your support ticket on **{guild.name}** has been officially closed. "
                            f"A summary of your ticket and your personal transcript archive are provided below."
                        ),
                        color=Config.EMBED_COLOR,
                        timestamp=datetime.now(timezone.utc),
                    )

                    dm_embed.add_field(name="🆔 Ticket ID", value=f"`{channel.id}` (`#{channel.name}`)", inline=True)
                    dm_embed.add_field(name="📋 Category", value=category_name, inline=True)
                    dm_embed.add_field(name="🛡️ Closed By", value=f"{closed_by.mention} (`{closed_by.name}`)", inline=True)
                    dm_embed.add_field(name="⏳ Lifespan", value=duration_text, inline=True)
                    dm_embed.add_field(name="📅 Closed At", value=f"<t:{closed_at_unix}:f> (<t:{closed_at_unix}:R>)", inline=True)
                    dm_embed.add_field(
                        name="🙋 Claimed By",
                        value=f"<@{claimed_by_id}>" if claimed_by_id else "*Unclaimed*",
                        inline=True,
                    )
                    dm_embed.add_field(
                        name="📝 Reason for Closure",
                        value=f"```{reason}```" if len(reason) < 200 else reason,
                        inline=False,
                    )
                    dm_embed.add_field(
                        name="📁 Transcript Archive",
                        value=(
                            "An interactive **.html transcript** is attached below.\n"
                            "You can download it and open it in any web browser to view the complete chat history, messages, and attachments."
                        ),
                        inline=False,
                    )

                    if guild.icon:
                        dm_embed.set_thumbnail(url=guild.icon.url)
                    dm_embed.set_footer(
                        text=f"{guild.name} • Need more help? Open a new ticket anytime!",
                        icon_url=guild.icon.url if guild.icon else None,
                    )

                    dm_file = discord.File(io.BytesIO(transcript_bytes), filename=transcript_filename)
                    await creator_user.send(embed=dm_embed, file=dm_file)
                    dm_delivered = True
                    logger.info(f"Delivered DM transcript and closure notice to user {creator_id}")
            except (discord.Forbidden, discord.HTTPException):
                logger.info(f"Could not deliver DM transcript to user {creator_id} (DMs closed or user not reachable).")

        # 8. Send comprehensive Closed Log to #ticket-logs-closed
        closed_log_embed = discord.Embed(
            title="🔒 Ticket Closed",
            color=0xE74C3C,
            timestamp=datetime.now(timezone.utc),
        )
        closed_log_embed.add_field(name="Ticket Name", value=f"`{channel.name}`", inline=True)
        closed_log_embed.add_field(name="Ticket ID", value=f"`{channel.id}`", inline=True)
        closed_log_embed.add_field(name="Category", value=category_name, inline=True)
        closed_log_embed.add_field(name="Opened By", value=f"<@{creator_id}> (`{creator_id}`)", inline=True)
        closed_log_embed.add_field(
            name="Claimed By",
            value=f"<@{claimed_by_id}>" if claimed_by_id else "*Unclaimed*",
            inline=True,
        )
        closed_log_embed.add_field(name="Closed By", value=f"{closed_by.mention}", inline=True)
        closed_log_embed.add_field(name="Total Messages", value=str(len(main_messages) + len(notes_messages)), inline=True)
        closed_log_embed.add_field(name="Opened At", value=f"<t:{opened_at_unix}:f>", inline=True)
        closed_log_embed.add_field(name="Closed At", value=f"<t:{closed_at_unix}:f>", inline=True)
        closed_log_embed.add_field(name="Lifespan", value=duration_text, inline=True)
        closed_log_embed.add_field(
            name="Opener DM",
            value="✅ Sent with Transcript" if dm_delivered else "⚠️ User DMs Disabled",
            inline=True,
        )
        closed_log_embed.add_field(name="Reason", value=reason, inline=False)

        if transcript_msg_url:
            closed_log_embed.add_field(
                name="Transcript",
                value=f"[Download / View Transcript]({transcript_msg_url})",
                inline=False,
            )
        elif Config.TRANSCRIPTS_CHANNEL_ID:
            closed_log_embed.add_field(
                name="Transcript",
                value=f"Uploaded to <#{Config.TRANSCRIPTS_CHANNEL_ID}>",
                inline=False,
            )

        await self.send_log(guild, Config.LOGS_CLOSED_CHANNEL_ID, embed=closed_log_embed)

        # 9. Wait countdown remainder and delete channel
        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"Ticket closed by {closed_by.name}: {reason}")
            delete_ticket_data(channel.id)
        except Exception as e:
            logger.error(f"Failed to delete ticket channel: {e}")

    # ==========================================
    # Slash Commands & Prefix Commands
    # ==========================================
    ticket_group = app_commands.Group(name="ticket", description="Ascension SMP Ticket System commands")

    @ticket_group.command(
        name="panel",
        description="[Admin] Deploy the Ascension SMP interactive ticket creation panel.",
    )
    @app_commands.describe(channel="Channel to deploy the panel in (defaults to current channel)")
    async def ticket_panel_subcommand(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ):
        await self._deploy_panel(interaction, channel)

    @app_commands.command(
        name="close",
        description="Close the current ticket channel with a 5-second countdown & transcript.",
    )
    @app_commands.describe(reason="Optional reason for closing this ticket")
    async def close_command(
        self,
        interaction: discord.Interaction,
        reason: Optional[str] = "No reason provided.",
    ):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "❌ This command can only be used in a text channel.", ephemeral=True
            )
            return

        topic_data = parse_topic_data(channel.topic)
        if not topic_data:
            await interaction.response.send_message(
                "❌ This channel does not appear to be an active ticket channel.",
                ephemeral=True,
            )
            return

        member = interaction.user
        creator_id = topic_data.get("creator_id")

        can_close = False
        if isinstance(member, discord.Member) and is_staff(member):
            can_close = True
        elif member.id == creator_id or is_owner(member.id):
            can_close = True

        if not can_close:
            await interaction.response.send_message(
                "❌ You do not have permission to close this ticket.", ephemeral=True
            )
            return

        await interaction.response.send_message("🔒 Initiating ticket closure...", ephemeral=True)
        await self.execute_ticket_close(channel, member, reason or "No reason provided.")

    async def _deploy_panel(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ):
        member = interaction.user
        if not isinstance(member, discord.Member) or not is_admin(member):
            await interaction.response.send_message(
                "❌ You need the Administrator role or Owner permission to deploy the ticket panel.",
                ephemeral=True,
            )
            return

        target_channel = channel or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message(
                "❌ Please specify a valid text channel.", ephemeral=True
            )
            return

        panel_embed = discord.Embed(
            title="⚔️ Ascension SMP — Support & Inquiries",
            description=(
                "Need assistance, want to report a rule violation, or submit an appeal?\n"
                "Select the appropriate category from the menu below to open a private ticket with our staff.\n\n"
                "💬 **General Support** — Questions, gameplay help, or general inquiries.\n"
                "🚨 **Player Report** — Report rule breakers, hackers, or griefing.\n"
                "⚖️ **Appeal** — Appeal a ban, mute, or warning.\n"
                "📋 **Other** — Miscellaneous requests or partnership inquiries.\n\n"
                "*Please ensure your inquiry includes all necessary details once opened.*"
            ),
            color=Config.EMBED_COLOR,
        )

        guild = interaction.guild
        if guild and guild.icon:
            panel_embed.set_thumbnail(url=guild.icon.url)
        panel_embed.set_footer(text="Ascension SMP • Official Support System")

        try:
            await target_channel.send(embed=panel_embed, view=TicketPanelView())
            await interaction.response.send_message(
                f"✅ Ticket panel successfully deployed in {target_channel.mention}!",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Failed to send ticket panel: {e}. Check bot permissions in that channel.",
                ephemeral=True,
            )

    # Prefix Commands for quick testing
    @commands.command(name="ticketpanel")
    async def prefix_ticket_panel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """[Admin] Prefix command to deploy the ticket panel: !ticketpanel [#channel]"""
        if not is_admin(ctx.author):
            await ctx.send("❌ You need Admin role or Owner permission to deploy the ticket panel.")
            return

        target_channel = channel or ctx.channel
        panel_embed = discord.Embed(
            title="⚔️ Ascension SMP — Support & Inquiries",
            description=(
                "Need assistance, want to report a rule violation, or submit an appeal?\n"
                "Select the appropriate category from the menu below to open a private ticket with our staff.\n\n"
                "💬 **General Support** — Questions, gameplay help, or general inquiries.\n"
                "🚨 **Player Report** — Report rule breakers, hackers, or griefing.\n"
                "⚖️ **Appeal** — Appeal a ban, mute, or warning.\n"
                "📋 **Other** — Miscellaneous requests or partnership inquiries.\n\n"
                "*Please ensure your inquiry includes all necessary details once opened.*"
            ),
            color=Config.EMBED_COLOR,
        )
        if ctx.guild.icon:
            panel_embed.set_thumbnail(url=ctx.guild.icon.url)
        panel_embed.set_footer(text="Ascension SMP • Official Support System")

        await target_channel.send(embed=panel_embed, view=TicketPanelView())
        await ctx.send(f"✅ Ticket panel deployed in {target_channel.mention}!")

    @commands.command(name="close")
    async def prefix_close(self, ctx: commands.Context, *, reason: Optional[str] = "No reason provided."):
        """Close the ticket: !close [reason]"""
        channel = ctx.channel
        topic_data = parse_topic_data(channel.topic)
        if not topic_data:
            await ctx.send("❌ This channel is not a valid ticket channel.")
            return

        creator_id = topic_data.get("creator_id")
        can_close = is_staff(ctx.author) or ctx.author.id == creator_id or is_owner(ctx.author.id)

        if not can_close:
            await ctx.send("❌ You do not have permission to close this ticket.")
            return

        await self.execute_ticket_close(channel, ctx.author, reason or "No reason provided.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Tickets(bot))
