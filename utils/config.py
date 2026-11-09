import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from the project root
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")


def get_int(env_name: str, default: int = 0) -> int:
    val = os.getenv(env_name)
    if val:
        try:
            return int(val)
        except ValueError:
            pass
    return default


def get_hex_color(env_name: str, default: int = 0xC48F3F) -> int:
    val = os.getenv(env_name)
    if val:
        try:
            if val.startswith("#"):
                return int(val[1:], 16)
            elif val.startswith("0x") or val.startswith("0X"):
                return int(val, 16)
            return int(val, 16)
        except ValueError:
            pass
    return default


class Config:
    # Bot Credentials & General
    TOKEN: str = os.getenv("DISCORD_TOKEN", "")
    COMMAND_PREFIX: str = os.getenv("COMMAND_PREFIX", "/")
    BOT_STATUS: str = os.getenv("BOT_STATUS", "dnd").lower()
    BOT_ACTIVITY: str = os.getenv("BOT_ACTIVITY", "Im the real real goat fr")
    EMBED_COLOR: int = get_hex_color("EMBED_COLOR", 0xC48F3F)

    # Server Info & Welcomer Channels
    WELCOME_CHANNEL_ID: int = get_int("WELCOME_CHANNEL_ID", 1557036971623190558)
    RULES_CHANNEL_ID: int = get_int("RULES_CHANNEL_ID", 1557036677245964348)
    INFO_CHANNEL_ID: int = get_int("INFO_CHANNEL_ID", 1569398055873024020)

    # Server Roles & Privileged User IDs
    STAFF_ROLE_ID: int = get_int("STAFF_ROLE_ID", 1557405215739748414)
    ADMIN_ROLE_ID: int = get_int("ADMIN_ROLE_ID", 1557404936906608640)
    OWNER_ID: int = get_int("OWNER_ID", 1552755990284206112)
    CO_OWNER_ID: int = get_int("CO_OWNER_ID", 1162838607220965377)

    # Ticket System Categories & Log Channels
    TICKETS_CATEGORY_ID: int = get_int("TICKETS_CATEGORY_ID", 0)
    LOGS_OPENED_CHANNEL_ID: int = get_int("LOGS_OPENED_CHANNEL_ID", 0)
    LOGS_CLAIMED_CHANNEL_ID: int = get_int("LOGS_CLAIMED_CHANNEL_ID", 0)
    LOGS_CLOSED_CHANNEL_ID: int = get_int("LOGS_CLOSED_CHANNEL_ID", 0)
    LOGS_STAFF_NOTES_CHANNEL_ID: int = get_int("LOGS_STAFF_NOTES_CHANNEL_ID", 0)
    TRANSCRIPTS_CHANNEL_ID: int = get_int("TRANSCRIPTS_CHANNEL_ID", 0)
    TICKET_CHANNEL_ID: int = get_int("TICKET_CHANNEL_ID", 1569403808876986459)

    # Auto-Mod Channels
    AUTOMOD_LOG_CHANNEL_ID: int = get_int("AUTOMOD_LOG_CHANNEL_ID", 1569411948465094716)

    # Bug Reports System Channels
    BUG_REPORT_CHANNEL_ID: int = get_int("BUG_REPORT_CHANNEL_ID", 1569412976967032854)
    BUG_STAFF_CHANNEL_ID: int = get_int("BUG_STAFF_CHANNEL_ID", 1569414620534280293)
    BUG_LOG_CHANNEL_ID: int = get_int("BUG_LOG_CHANNEL_ID", 1569416069024718919)
