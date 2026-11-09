# ⚔️ Ascension SMP Discord Bot

Official Discord bot for **Ascension SMP**. Built with Python and `discord.py` (v2.0+).

---

## 📁 Project Structure

```
C:\Ascension_bot\
├── assets/
│   └── logo.png              # Server fantasy crest / logo
├── cogs/
│   ├── __init__.py
│   ├── welcome.py            # Welcome event listener & preview command
│   └── tickets.py            # Complete database-free ticket system
├── data/
│   ├── __init__.py
│   ├── storage.py            # Safe JSON file storage helper
│   └── welcome_data.json     # Stored welcome statistics & history
├── utils/
│   ├── __init__.py
│   ├── config.py             # Environment config loader
│   └── transcript.py         # Self-contained Discord Dark Theme HTML transcript generator
├── .env                      # Local secret variables (ignored by git)
├── .env.example              # Configuration template
├── .gitignore                # Git ignore rules
├── Dockerfile                # Docker container definition
├── docker-compose.yml        # Docker Compose configuration for Proxmox
├── requirements.txt          # Python dependencies
└── main.py                   # Bot entrypoint & presence setup
```

---

## ⚙️ Discord Server Setup Guide

### 1. Enable Developer Mode in Discord
- In Discord, go to **User Settings** -> **Advanced** -> Turn ON **Developer Mode**.
- This enables right-clicking any channel, category, or role to copy its ID.

### 2. Create Categories & Channels
In your Discord server, create the following:

#### A. Active Tickets Category
- **Create Category:** `🎫 TICKETS`
- Right click -> **Copy Category ID** -> Paste as `TICKETS_CATEGORY_ID` in `.env`.

#### B. Staff Logs Category (Private)
Create a private category `🔒 STAFF LOGS` (hidden from `@everyone`, visible only to Staff and Admin roles), and create these 5 channels inside it:
1. `#ticket-logs-opened` -> Copy Channel ID -> `LOGS_OPENED_CHANNEL_ID` in `.env`.
2. `#ticket-logs-claimed` -> Copy Channel ID -> `LOGS_CLAIMED_CHANNEL_ID` in `.env`.
3. `#ticket-logs-closed` -> Copy Channel ID -> `LOGS_CLOSED_CHANNEL_ID` in `.env`.
4. `#ticket-logs-staff-notes` -> Copy Channel ID -> `LOGS_STAFF_NOTES_CHANNEL_ID` in `.env`.
5. `#ticket-transcripts` -> Copy Channel ID -> `TRANSCRIPTS_CHANNEL_ID` in `.env`.

---

## 🔐 Environment Configuration (`.env`)

Open `.env` in `C:\Ascension_bot` and configure:

```env
# Bot Credentials
DISCORD_TOKEN=your_bot_token_here

# Channel IDs
WELCOME_CHANNEL_ID=1557036971623190558
RULES_CHANNEL_ID=1557036677245964348
INFO_CHANNEL_ID=1569398055873024020

# Bot Presence
BOT_STATUS=dnd
BOT_ACTIVITY=Im the real real goat fr
EMBED_COLOR=0xC48F3F
COMMAND_PREFIX=/

# Server Roles & Privileged User IDs
STAFF_ROLE_ID=1557405215739748414
ADMIN_ROLE_ID=1557404936906608640
OWNER_ID=1552755990284206112
CO_OWNER_ID=1162838607220965377

# Ticket Category & Log Channels (Paste copied IDs here)
TICKETS_CATEGORY_ID=your_tickets_category_id
LOGS_OPENED_CHANNEL_ID=your_opened_logs_channel_id
LOGS_CLAIMED_CHANNEL_ID=your_claimed_logs_channel_id
LOGS_CLOSED_CHANNEL_ID=your_closed_logs_channel_id
LOGS_STAFF_NOTES_CHANNEL_ID=your_staff_notes_logs_channel_id
TRANSCRIPTS_CHANNEL_ID=your_transcripts_channel_id
```

> [!IMPORTANT]
> **Discord Developer Portal Settings:**
> 1. Go to [Discord Developer Portal](https://discord.com/developers/applications).
> 2. Select your application -> **Bot** tab.
> 3. Under **Privileged Gateway Intents**, enable:
>    - **Server Members Intent** *(Mandatory for welcomer & member fetching)*
>    - **Message Content Intent** *(Mandatory for transcript scraping & prefix commands)*
> 4. Save Changes.

---

## 🚀 Running Locally (PC Testing)

1. Start the bot:
   ```powershell
   cd C:\Ascension_bot
   python main.py
   ```
2. **Force-Sync Slash Commands (Instant):**
   In any Discord channel on your server, type:
   ```
   /sync
   ```
   This immediately registers all slash commands (`/ticket panel`, `/close`, `/testwelcome`) to your server.

3. **Available Slash Commands:**
   - `/ticket panel` : Deploys the interactive ticket creation panel.
   - `/close [reason]` : Closes a ticket channel with countdown, transcript, and DM.
   - `/testwelcome` : Previews the welcome embed.
   - `/embed post [template: info | custom]` : Posts the Ascension SMP Server Information embed or a custom embed.
   - `/bug setup` : Deploys the interactive Bug Report submission panel with the `🐛 Submit Bug Report` button.

---

## 🛡️ Auto-Mod (Discord Server Links)

- **Invite Link Detection:** Automatically detects and removes unauthorized Discord server invite links (`discord.gg/...`, `discord.com/invite/...`, etc.).
- **Immunity:** Staff, Admins, and Owners are exempt.
- **Action:**
  - Deletes the message and sends a temporary in-channel warning.
  - Sends a detailed violation log embed to `<#1569411948465094716>` with user details, channel, link found, and message contents.

---

## 📌 Server Information Embed (`/embed post`)

- Deploys the server guide into `<#1569398055873024020>` detailing:
  - Welcome & Owner attribution (**Cyntrixza**).
  - 🎫 Support & Role Applications with direct link to `<#1569403808876986459>` (Script roles, Staff applications, Builder applications).
  - 🐛 Bug Reports with direct link to `<#1569412976967032854>`.
  - ❤️ Heartfelt message: *"God loves you and cares for you!"*.

---

## 🐛 Bug Reports System

1. **Submission (`/bug setup` in `<#1569412976967032854>`):**
   - Players click **"🐛 Submit Bug Report"** to open a modal form:
     - Minecraft In-Game Name
     - Short Bug Summary
     - What Happened / Steps to Reproduce
     - Evidence / Medal Clips (optional)
   - Assigns a sequential tracking ID (e.g. `BUG-1001`).
   - Logs submission to `<#1569416069024718919>`.
2. **Staff Triage Panel (`<#1569414620534280293>`):**
   - Private channel for Owners and High Staff.
   - 3 interactive buttons:
     - **✅ Mark Fixed:** Updates status to Fixed in logs and DMs the player thanking them and confirming the fix with their Report ID.
     - **🎫 Open Ticket:** Automatically opens a private discussion ticket with the player under `🎫 TICKETS` category with bug details pinned.
     - **🔒 Close / Dismiss:** Modal prompts for a closure reason and notifies the player via DM.

---

## 🎟️ Ticket System Features

- **Dropdown Categories:**
  - 💬 **General Support**
  - 🚨 **Player Report**
  - ⚖️ **Appeal**
  - 📋 **Other**
- **Channel Metadata (No Database):**
  - State (creator ID, category, timestamps, claimer, notes thread) is stored directly in channel topic JSON.
- **Persistent In-Channel Controls:**
  - 🙋 **Claim Ticket:** Assigns staff member, updates embed, logs to `#ticket-logs-claimed`.
  - 🔓 **Release Claim:** Unassigns staff member, resets embed, logs to `#ticket-logs-claimed`.
  - 📝 **Staff Notes:** Creates a private thread (`staff-notes-<user>`) hidden from the ticket creator, pings Staff & Admin roles, logs to `#ticket-logs-staff-notes`.
  - 🔒 **Close Ticket:** Modal asks for reason -> 5-second countdown -> generates standalone dark-themed HTML transcript -> uploads to `#ticket-transcripts` -> logs to `#ticket-logs-closed` -> DMs creator with transcript copy -> deletes channel.
- **Slash Commands:**
  - `/ticket panel [channel]`: Deploys the interactive panel.
  - `/close [reason]`: Closes ticket with countdown, transcript, and logs.
