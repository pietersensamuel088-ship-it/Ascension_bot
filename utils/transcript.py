import html
import re
from datetime import datetime, timezone
from typing import List, Optional
import discord


def format_duration(seconds: float) -> str:
    """Format seconds into readable human time (e.g. '1h 24m 10s')."""
    seconds = int(max(0, seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")

    return " ".join(parts)


def markdown_to_html(text: str) -> str:
    """Safely convert basic Discord markdown into clean HTML."""
    if not text:
        return ""

    # Escape HTML characters first
    escaped = html.escape(text)

    # Multi-line codeblocks: ```lang\ncode``` or ```code```
    escaped = re.sub(
        r"```(?:[a-zA-Z0-9_-]+\n)?(.*?)```",
        r"<pre><code>\1</code></pre>",
        escaped,
        flags=re.DOTALL,
    )

    # Inline code: `code`
    escaped = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", escaped)

    # Bold: **text**
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)

    # Underline: __text__
    escaped = re.sub(r"__([^_]+)__", r"<u>\1</u>", escaped)

    # Italic: *text* or _text_
    escaped = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", escaped)
    escaped = re.sub(r"_([^_]+)_", r"<em>\1</em>", escaped)

    # Strikethrough: ~~text~~
    escaped = re.sub(r"~~([^~]+)~~", r"<del>\1</del>", escaped)

    # Blockquotes: &gt; quote
    escaped = re.sub(r"(?:^|\n)&gt; (.*?)(?=\n|$)", r"<blockquote>\1</blockquote>", escaped)

    # Mentions: &lt;@!?(\d+)&gt;
    escaped = re.sub(r"&lt;@!?(\d+)&gt;", r'<span class="mention">@User(\1)</span>', escaped)
    escaped = re.sub(r"&lt;@&amp;(\d+)&gt;", r'<span class="mention">@Role(\1)</span>', escaped)
    escaped = re.sub(r"&lt;#(\d+)&gt;", r'<span class="mention">#channel(\1)</span>', escaped)

    # URLs
    escaped = re.sub(
        r"(https?://[^\s<]+)",
        r'<a href="\1" target="_blank" rel="noopener noreferrer">\1</a>',
        escaped,
    )

    # Newlines
    escaped = escaped.replace("\n", "<br>")

    return escaped


def render_message_html(msg: discord.Message) -> str:
    """Render a single discord.Message into an HTML message block."""
    author_name = html.escape(msg.author.display_name or msg.author.name)
    timestamp_str = msg.created_at.strftime("%b %d, %Y - %I:%M:%S %p UTC")
    avatar_url = (
        msg.author.display_avatar.url
        if hasattr(msg.author, "display_avatar")
        else "https://cdn.discordapp.com/embed/avatars/0.png"
    )

    bot_badge = '<span class="bot-badge">BOT</span>' if msg.author.bot else ""
    content_html = markdown_to_html(msg.content)

    # Attachments
    attachments_html = ""
    for att in msg.attachments:
        att_filename = html.escape(att.filename)
        is_image = any(
            att.filename.lower().endswith(ext)
            for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp")
        )
        if is_image:
            attachments_html += (
                f'<div class="attachment-preview">'
                f'<a href="{att.url}" target="_blank">'
                f'<img src="{att.url}" alt="{att_filename}" class="attachment-img" loading="lazy" />'
                f'</a></div>'
            )
        else:
            attachments_html += (
                f'<div class="attachment-file">'
                f'📎 <a href="{att.url}" target="_blank">{att_filename}</a>'
                f'</div>'
            )

    # Embeds
    embeds_html = ""
    for emb in msg.embeds:
        border_color = f"#{emb.color.value:06x}" if emb.color else "#C48F3F"
        title_html = (
            f'<div class="embed-title">{html.escape(emb.title)}</div>' if emb.title else ""
        )
        desc_html = (
            f'<div class="embed-description">{markdown_to_html(emb.description)}</div>'
            if emb.description
            else ""
        )
        fields_html = ""
        for f in emb.fields:
            fields_html += (
                f'<div class="embed-field">'
                f'<div class="embed-field-name">{html.escape(f.name)}</div>'
                f'<div class="embed-field-value">{markdown_to_html(f.value)}</div>'
                f'</div>'
            )

        embeds_html += (
            f'<div class="embed-box" style="border-left-color: {border_color};">'
            f'{title_html}{desc_html}{fields_html}'
            f'</div>'
        )

    return f"""
    <div class="message-row">
        <img class="avatar" src="{avatar_url}" alt="{author_name}" />
        <div class="message-content-wrapper">
            <div class="message-header">
                <span class="username">{author_name}</span>
                {bot_badge}
                <span class="timestamp">{timestamp_str}</span>
            </div>
            {f'<div class="message-text">{content_html}</div>' if content_html else ''}
            {attachments_html}
            {embeds_html}
        </div>
    </div>
    """


def generate_html_transcript(
    ticket_name: str,
    category: str,
    creator_name: str,
    creator_id: int,
    claimer_name: str,
    closer_name: str,
    opened_at_unix: int,
    closed_at_unix: int,
    reason: str,
    main_messages: List[discord.Message],
    notes_messages: Optional[List[discord.Message]] = None,
) -> str:
    """Generate a complete, self-contained HTML transcript with Discord Dark Theme."""
    opened_dt = datetime.fromtimestamp(opened_at_unix, tz=timezone.utc)
    closed_dt = datetime.fromtimestamp(closed_at_unix, tz=timezone.utc)
    duration_str = format_duration(closed_at_unix - opened_at_unix)

    total_msg_count = len(main_messages) + (len(notes_messages) if notes_messages else 0)

    # Render main messages
    main_feed_html = "".join(render_message_html(msg) for msg in main_messages)
    if not main_feed_html:
        main_feed_html = '<div class="no-messages">No messages recorded in main ticket.</div>'

    # Render staff notes section
    notes_section_html = ""
    if notes_messages:
        notes_feed_html = "".join(render_message_html(msg) for msg in notes_messages)
        notes_section_html = f"""
        <details class="staff-notes-details">
            <summary class="staff-notes-summary">
                🔒 <strong>Private Staff Notes</strong> ({len(notes_messages)} internal messages recorded)
            </summary>
            <div class="staff-notes-content">
                {notes_feed_html}
            </div>
        </details>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Transcript - {html.escape(ticket_name)}</title>
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            background-color: #313338;
            color: #dbdee1;
            font-family: "gg sans", "Noto Sans", "Helvetica Neue", Helvetica, Arial, sans-serif;
            font-size: 15px;
            line-height: 1.45;
            padding: 24px;
        }}
        .container {{
            max-width: 1000px;
            margin: 0 auto;
        }}
        /* Header Card */
        .header-card {{
            background-color: #2b2d31;
            border-radius: 8px;
            padding: 20px 24px;
            margin-bottom: 24px;
            border-left: 5px solid #C48F3F;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
        }}
        .header-title {{
            font-size: 22px;
            font-weight: 700;
            color: #f2f3f5;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .header-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 12px;
            margin-top: 14px;
            padding-top: 14px;
            border-top: 1px solid #3f4147;
            font-size: 13.5px;
        }}
        .header-item strong {{
            color: #C48F3F;
            display: block;
            font-size: 11.5px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 2px;
        }}
        /* Message Rows */
        .message-feed {{
            background-color: #2b2d31;
            border-radius: 8px;
            padding: 16px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        }}
        .message-row {{
            display: flex;
            gap: 16px;
            padding: 10px 12px;
            border-radius: 4px;
            transition: background-color 0.15s ease;
        }}
        .message-row:hover {{
            background-color: #2e3035;
        }}
        .avatar {{
            width: 42px;
            height: 42px;
            border-radius: 50%;
            object-fit: cover;
            flex-shrink: 0;
        }}
        .message-content-wrapper {{
            flex-grow: 1;
            min-width: 0;
            word-wrap: break-word;
        }}
        .message-header {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 4px;
        }}
        .username {{
            font-weight: 600;
            color: #f2f3f5;
            font-size: 14.5px;
        }}
        .bot-badge {{
            background-color: #5865f2;
            color: #ffffff;
            font-size: 10px;
            font-weight: 700;
            padding: 1px 4px;
            border-radius: 3px;
            letter-spacing: 0.3px;
        }}
        .timestamp {{
            font-size: 11.5px;
            color: #949ba4;
        }}
        .message-text {{
            color: #dbdee1;
            font-size: 14.5px;
            line-height: 1.5;
        }}
        /* Markdown formatting */
        pre {{
            background-color: #1e1f22;
            border-radius: 4px;
            padding: 8px 12px;
            margin: 6px 0;
            overflow-x: auto;
            border: 1px solid #35363c;
        }}
        code {{
            font-family: "Consolas", "Courier New", monospace;
            background-color: #1e1f22;
            padding: 2px 4px;
            border-radius: 3px;
            font-size: 13px;
        }}
        blockquote {{
            border-left: 4px solid #4e5058;
            padding-left: 10px;
            margin: 6px 0;
            color: #b5bac1;
        }}
        a {{
            color: #00a8fc;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        .mention {{
            background-color: rgba(88, 101, 242, 0.15);
            color: #c9cdfb;
            padding: 1px 5px;
            border-radius: 3px;
            font-weight: 500;
        }}
        /* Attachments */
        .attachment-preview {{
            margin-top: 8px;
            max-width: 400px;
        }}
        .attachment-img {{
            max-width: 100%;
            max-height: 350px;
            border-radius: 6px;
            border: 1px solid #35363c;
            display: block;
        }}
        .attachment-file {{
            background-color: #1e1f22;
            border-radius: 4px;
            padding: 8px 12px;
            margin-top: 6px;
            font-size: 13px;
            display: inline-block;
            border: 1px solid #35363c;
        }}
        /* Embeds */
        .embed-box {{
            background-color: #1e1f22;
            border-left: 4px solid #C48F3F;
            border-radius: 4px;
            padding: 12px 14px;
            margin-top: 8px;
            max-width: 520px;
        }}
        .embed-title {{
            font-weight: 700;
            color: #f2f3f5;
            margin-bottom: 6px;
        }}
        .embed-description {{
            font-size: 13.5px;
            color: #dbdee1;
            margin-bottom: 8px;
        }}
        .embed-field {{
            margin-top: 6px;
        }}
        .embed-field-name {{
            font-weight: 600;
            font-size: 12.5px;
            color: #b5bac1;
        }}
        .embed-field-value {{
            font-size: 13px;
            color: #dbdee1;
        }}
        /* Staff Notes Accordion */
        .staff-notes-details {{
            background-color: #232428;
            border: 1px solid #C48F3F;
            border-radius: 6px;
            margin-bottom: 20px;
            overflow: hidden;
        }}
        .staff-notes-summary {{
            padding: 14px 18px;
            background-color: #1e1f22;
            cursor: pointer;
            font-size: 14.5px;
            user-select: none;
            color: #f2f3f5;
        }}
        .staff-notes-summary:hover {{
            background-color: #2b2d31;
        }}
        .staff-notes-content {{
            padding: 14px;
        }}
        .no-messages {{
            text-align: center;
            padding: 30px;
            color: #949ba4;
            font-style: italic;
        }}
        .footer {{
            margin-top: 24px;
            text-align: center;
            font-size: 12px;
            color: #949ba4;
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Ticket Header Card -->
        <div class="header-card">
            <div class="header-title">
                <span>🎫</span>
                <span>{html.escape(ticket_name)}</span>
            </div>
            <div class="header-grid">
                <div class="header-item">
                    <strong>Category</strong>
                    <span>{html.escape(category)}</span>
                </div>
                <div class="header-item">
                    <strong>Creator</strong>
                    <span>{html.escape(creator_name)} ({creator_id})</span>
                </div>
                <div class="header-item">
                    <strong>Claimed By</strong>
                    <span>{html.escape(claimer_name)}</span>
                </div>
                <div class="header-item">
                    <strong>Closed By</strong>
                    <span>{html.escape(closer_name)}</span>
                </div>
                <div class="header-item">
                    <strong>Opened At</strong>
                    <span>{opened_dt.strftime("%b %d, %Y - %I:%M %p UTC")}</span>
                </div>
                <div class="header-item">
                    <strong>Closed At</strong>
                    <span>{closed_dt.strftime("%b %d, %Y - %I:%M %p UTC")}</span>
                </div>
                <div class="header-item">
                    <strong>Duration</strong>
                    <span>{duration_str}</span>
                </div>
                <div class="header-item">
                    <strong>Total Messages</strong>
                    <span>{total_msg_count}</span>
                </div>
                <div class="header-item" style="grid-column: 1 / -1;">
                    <strong>Closure Reason</strong>
                    <span>{html.escape(reason)}</span>
                </div>
            </div>
        </div>

        <!-- Optional Staff Notes Collapsible Section -->
        {notes_section_html}

        <!-- Message Feed -->
        <div class="message-feed">
            {main_feed_html}
        </div>

        <div class="footer">
            Ascension SMP Ticket System • Generated at {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}
        </div>
    </div>
</body>
</html>"""
