import discord
from discord.ext import commands
import re
import os
import glob
import asyncio
import yt_dlp
import urllib.parse

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="", intents=intents)
bot.remove_command("help")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TIKTOK_COOKIES = os.path.join(SCRIPT_DIR, "tiktok_cookies.txt")
INSTA_COOKIES = os.path.join(SCRIPT_DIR, "insta_cookies.txt")


class YTDLPLogger:
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): print(f"[yt-dlp ERROR] {msg}")


TIKTOK_RE = r'(?:https?://)?(?:www\.)?(?:tiktok\.com/@[^/\s]+/(?:video|photo)/\d+|tiktok\.com/t/[A-Za-z0-9\-_]+|(?:vm|vt|m)\.tiktok\.com/[A-Za-z0-9\-_]+/?)'
INSTA_RE = r'(?:https?://)?(?:www\.)?(?:instagram\.com/(?:p|reel(?:s?)|tv|share)/[^\s]+|instagr\.am/(?:p|reel(?:s?)|tv|share)/[^\s]+)'
URL_RE = re.compile(f'({TIKTOK_RE}|{INSTA_RE})', re.IGNORECASE)


async def extract_and_download(url: str, base_name: str, cookie_file: str):
    loop = asyncio.get_event_loop()

    cookie_path = None
    if os.path.exists(cookie_file):
        cookie_path = cookie_file
        print(f"[COOKIES] ✓ Using: {os.path.basename(cookie_file)}")
    else:
        print(f"[COOKIES] ✗ NOT FOUND: {cookie_file}")

    probe_opts = {
        'quiet': True,
        'no_warnings': True,
        'cookiefile': cookie_path,
        'logger': YTDLPLogger(),
    }

    info = None
    try:
        with yt_dlp.YoutubeDL(probe_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=False))
    except Exception as e:
        print(f"[EXTRACT ERROR] {e}")
        return []

    if not info:
        return []

    entries = info.get('entries') or [info]
    print(f"[INFO] Found {len(entries)} item(s)")

    dl_opts = {
        'outtmpl': f"{base_name}_%(autonumber)d.%(ext)s",
        'quiet': True,
        'no_warnings': True,
        'cookiefile': cookie_path,
        'logger': YTDLPLogger(),
        'format': 'best',
    }

    downloaded_files = []
    try:
        with yt_dlp.YoutubeDL(dl_opts) as ydl:
            if len(entries) > 1:
                for i, entry in enumerate(entries):
                    entry_url = entry.get('url') or entry.get('webpage_url') or url
                    try:
                        await loop.run_in_executor(None, lambda eu=entry_url: ydl.download([eu]))
                    except Exception as e:
                        print(f"[DL ENTRY ERROR] item {i}: {e}")
            else:
                try:
                    await loop.run_in_executor(None, lambda: ydl.download([url]))
                except Exception as e:
                    print(f"[DL ERROR] {e}")

        for f in glob.glob(f"{base_name}*"):
            if os.path.isfile(f) and os.path.getsize(f) > 1024:
                downloaded_files.append(f)

    except Exception as e:
        print(f"[DOWNLOAD EXCEPTION] {e}")

    return downloaded_files


@bot.event
async def on_ready():
    print("=" * 40)
    print("BOT IS READY!")
    print("=" * 40)
    print(f"Working directory: {SCRIPT_DIR}")
    print(f"TikTok cookies: {'✓ FOUND' if os.path.exists(TIKTOK_COOKIES) else '✗ MISSING'}")
    print(f"Insta cookies:   {'✓ FOUND' if os.path.exists(INSTA_COOKIES) else '✗ MISSING'}")
    print("=" * 40)
    
    if not os.path.exists(TIKTOK_COOKIES):
        print("⚠️  WARNING: tiktok_cookies.txt not found!")
    if not os.path.exists(INSTA_COOKIES):
        print("⚠️  WARNING: insta_cookies.txt not found!")
    print()


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    match = URL_RE.search(message.content)
    if not match:
        return

    raw_url = match.group(1)
    if not raw_url.startswith('http'):
        raw_url = 'https://' + raw_url

    parsed = urllib.parse.urlparse(raw_url)
    clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    is_tiktok = 'tiktok.com' in parsed.netloc
    platform = "TikTok" if is_tiktok else "Instagram"
    
    cookie_file = TIKTOK_COOKIES if is_tiktok else INSTA_COOKIES

    text = f"> {message.author.mention} **Shared a {platform} post.**"

    try:
        await message.delete()
    except discord.Forbidden:
        pass

    base_name = f"temp_{message.id}"
    files = await extract_and_download(clean_url, base_name, cookie_file)

    try:
        if files:
            for i in range(0, len(files), 10):
                chunk = files[i:i+10]
                discord_files = [discord.File(f) for f in chunk]
                if i == 0:
                    await message.channel.send(content=text, files=discord_files)
                else:
                    await message.channel.send(files=discord_files)
        else:
            await message.channel.send(
                content=f"{text}\n\n> ⚠️ Couldn't download media (login required or unsupported post type)."
            )
    except Exception as e:
        print(f"[SEND ERROR] {e}")
        await message.channel.send(content=text)

    finally:
        for f in glob.glob(f"{base_name}*"):
            try:
                os.remove(f)
            except:
                pass


TOKEN = os.environ.get('DISCORD_TOKEN', 'YOUR_BOT_TOKEN')
bot.run(TOKEN)