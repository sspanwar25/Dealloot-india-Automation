import os
import logging
import asyncio
import base64
import re
from threading import Thread
from flask import Flask, request, jsonify
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaWebPage

# ------------------ Logging ------------------
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------------------ Environment Variables (safe parsing) ------------------
API_ID = os.getenv("API_ID")                 # must be provided
API_HASH = os.getenv("API_HASH")             # must be provided
PRIVATE_GROUP_ID = os.getenv("PRIVATE_GROUP_ID")  # optional target (can be numeric)
EARNKARO_BOT_USERNAME = os.getenv("EARNKARO_BOT_USERNAME")
PERSONAL_BOT_USERNAME = os.getenv("PERSONAL_BOT_USERNAME")
SOURCE_CHANNEL_USERNAME = os.getenv("SOURCE_CHANNEL_USERNAME")  # original single source (can be comma list too)
SESSION_BASE64 = os.getenv("SESSION_BASE64")

# NEW optional envs:
MULTI_SOURCE_CHANNELS = os.getenv("MULTI_SOURCE_CHANNELS", "")  # comma separated additional sources (optional)
MULTI_TARGETS = os.getenv("MULTI_TARGETS", "")                 # comma separated additional targets (optional)
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")                     # optional token to protect Flask routes

# Validate minimal required vars
if not API_ID or not API_HASH:
    logger.error("❌ API_ID or API_HASH missing in environment variables. Exiting.")
    exit(1)

try:
    API_ID = int(API_ID)
except Exception:
    logger.error("❌ API_ID must be an integer. Exiting.")
    exit(1)

# SESSION_BASE64 -> write session file if provided
if SESSION_BASE64:
    try:
        with open("final_session.session", "wb") as f:
            f.write(base64.b64decode(SESSION_BASE64))
        logger.info("✅ final_session.session created from SESSION_BASE64")
    except Exception as e:
        logger.error(f"❌ Could not write session from SESSION_BASE64: {e}")

# ------------------ Static template data (unchanged) ------------------
TEMPLATES = {
    "amazon": {"emoji": "🔌", "intro": "⚡ Unbeatable offers waiting for you!\n🚀 Hurry before stock runs out!", "hashtags": "#Amazon #LootDeal #DealLootIndia"},
    "flipkart": {"emoji": "📦", "intro": "⚡ Mega discounts are live now!\n🚀 Grab your favorite products before stock runs out!", "hashtags": "#Flipkart #LootDeal #DealLootIndia"},
    "myntra": {"emoji": "👗", "intro": "⚡ Trendy picks at stunning discounts!\n🚀 Hurry, limited stock available!", "hashtags": "#Myntra #StyleDeal #DealLootIndia"},
    "ajio": {"emoji": "👜", "intro": "⚡ Stylish collections at killer prices!\n🚀 Shop now before the best picks vanish!", "hashtags": "#Ajio #FashionDeal #DealLootIndia"},
    "meesho": {"emoji": "💰", "intro": "⚡ Best budget picks at crazy low prices!\n🚀 Shop more, save more!", "hashtags": "#Meesho #BudgetDeal #DealLootIndia"},
    "jiomart": {"emoji": "🛒", "intro": "⚡ Grocery & essentials at lowest prices!\n🚀 Order now and save big!", "hashtags": "#JioMart #LootDeal #DealLootIndia"}
}

PLATFORM_KEYWORDS = {
    "amazon": ["amazon.in", "amzn.to", "amazon", "amzn", "amazn"],
    "flipkart": ["flipkart.com", "fkrt", "flipkart", "flpkrt", "fkrt.xyz", "fktr.in"],
    "myntra": ["myntra.in", "myntr.it", "myntra", "myntr"],
    "ajio": ["ajio.in", "ajio"],
    "meesho": ["meesho.com", "msho.in", "meesho", "msho"],
    "jiomart": ["jiomart.com", "jiomart"]
}

CATEGORY_KEYWORDS = {
    "electronics": ["air fryer", "watch", "earbuds", "headphones", "electronic", "mobile", "laptop", "tv", "led", "smarttv", "smart tv", "home appliance"],
    "fashion": ["trouser", "shirt", "t-shirt", "dress", "jeans", "fashion", "clothing"],
    "kitchenware": ["cookware", "pan", "cooker", "kitchen", "utensil", "pressure", "oven"],
    "beauty": ["shampoo", "cream", "soap", "makeup", "deodorant", "skincare", "perfume"]
}

CATEGORY_TEMPLATES = {
    "electronics": {"emoji": "🔌", "intro": ["⚡ Amazing electronics deals!", "🚀 Grab them before they run out!"]},
    "fashion": {"emoji": "👗", "intro": ["⚡ Trendy picks at stunning discounts!", "🚀 Hurry, limited stock available!"]},
    "kitchenware": {"emoji": "🍳", "intro": ["⚡ Cookware & kitchen essentials at best prices!", "🚀 Upgrade your kitchen today!"]},
    "beauty": {"emoji": "💄", "intro": ["⚡ Beauty & personal care deals!", "🚀 Pamper yourself with best offers!"]}
}

MAX_CAPTION = 1024
processed_messages = set()

# ------------------ Telegram Client ------------------
client = TelegramClient("final_session", API_ID, API_HASH)

# Runtime sets (resolved IDs)
SOURCE_IDENTIFIERS = set()   # original text identifiers (usernames or ids)
SOURCE_IDS = set()           # resolved numeric ids
TARGET_IDENTIFIERS = set()
TARGET_IDS = set()
PERSONAL_BOT_ID = None

# Fill initial identifier sets from env (allow comma-lists)
def parse_list_env(s):
    return [x.strip() for x in s.split(",") if x.strip()]

if SOURCE_CHANNEL_USERNAME:
    SOURCE_IDENTIFIERS.update(parse_list_env(SOURCE_CHANNEL_USERNAME))
if MULTI_SOURCE_CHANNELS:
    SOURCE_IDENTIFIERS.update(parse_list_env(MULTI_SOURCE_CHANNELS))

# targets: PRIVATE_GROUP_ID (may be numeric), EARNKARO_BOT_USERNAME, MULTI_TARGETS
if PRIVATE_GROUP_ID:
    TARGET_IDENTIFIERS.add(str(PRIVATE_GROUP_ID))
if EARNKARO_BOT_USERNAME:
    TARGET_IDENTIFIERS.add(EARNKARO_BOT_USERNAME)
if MULTI_TARGETS:
    TARGET_IDENTIFIERS.update(parse_list_env(MULTI_TARGETS))

# ------------------ Helper utilities ------------------
def is_protected(req):
    if not ADMIN_TOKEN:
        return True  # no protection enabled
    token = req.args.get("token") or req.headers.get("X-ADMIN-TOKEN")
    return token == ADMIN_TOKEN

async def resolve_identifier_to_id(identifier):
    """
    identifier can be:
      - numeric string like -1001234567890 or -4785179729  -> convert to int
      - username like @channelname or channelname -> use client.get_entity
    Returns int id or None
    """
    if not identifier:
        return None
    # numeric?
    try:
        if re.match(r"^-?\d+$", identifier):
            return int(identifier)
        # sometimes provided with -100 prefix etc
    except Exception:
        pass
    try:
        ent = await client.get_entity(identifier)
        return int(ent.id)
    except Exception as e:
        logger.warning(f"Could not resolve {identifier} to id: {e}")
        return None

async def resolve_all_initial():
    global PERSONAL_BOT_ID
    # resolve sources
    for ident in list(SOURCE_IDENTIFIERS):
        rid = await resolve_identifier_to_id(ident)
        if rid:
            SOURCE_IDS.add(rid)
    # resolve targets
    for ident in list(TARGET_IDENTIFIERS):
        rid = await resolve_identifier_to_id(ident)
        if rid:
            TARGET_IDS.add(rid)
    # personal bot id
    if PERSONAL_BOT_USERNAME:
        pbid = await resolve_identifier_to_id(PERSONAL_BOT_USERNAME)
        if pbid:
            PERSONAL_BOT_ID = pbid
    logger.info(f"Resolved source ids: {SOURCE_IDS}")
    logger.info(f"Resolved target ids: {TARGET_IDS}")
    if PERSONAL_BOT_ID:
        logger.info(f"Resolved personal bot id: {PERSONAL_BOT_ID}")

def dedupe_links_and_text(text):
    """
    Remove duplicate URLs if present multiple times and avoid duplicate follow line.
    """
    follow_line = "👉 Follow @Deallootindia_offical for 🔥 daily loot deals!"
    lines = text.splitlines()
    seen_links = set()
    new_lines = []
    for line in lines:
        s = line.strip()
        if s.startswith("http"):
            if s in seen_links:
                continue
            seen_links.add(s)
            new_lines.append(line)
        else:
            new_lines.append(line)
    joined = "\n".join(new_lines).strip()
    # ensure follow_line present exactly once at end
    if follow_line in joined:
        # remove duplicates of follow_line
        joined = joined.replace(follow_line, "").strip()
    final = joined + "\n\n" + follow_line
    return final

def detect_platform(text):
    if not text:
        return None
    text_lower = text.lower().replace(" ", "")
    for platform, keywords in PLATFORM_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                return platform
            pattern = rf"{re.escape(kw)}[\w./-]*"
            if re.search(pattern, text_lower):
                return platform
    return None

def detect_category(text):
    if not text:
        return None
    text_lower = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(k in text_lower for k in keywords):
            return category
    return None

def format_template(platform, category, message_text):
    # keep old template logic but remove duplicate links and follow-line duplicates
    message_text = dedupe_links_and_text(message_text)
    follow_line = "👉 Follow @Deallootindia_offical for 🔥 daily loot deals!"
    if category and category in CATEGORY_TEMPLATES:
        first_line = f"{CATEGORY_TEMPLATES[category]['emoji']} {platform.capitalize()} {category.capitalize()} Deal"
    else:
        first_line = f"{TEMPLATES.get(platform, {'emoji':'🔖'})['emoji']} {platform.capitalize()} Loot Deal" if platform else "Loot Deal"
    intro_lines = TEMPLATES.get(platform, {}).get("intro", "").split("\n") if platform in TEMPLATES else []
    header = "\n".join([first_line] + intro_lines)
    hashtags = TEMPLATES.get(platform, {}).get("hashtags", "#DealLootIndia #LootDeal")
    return "\n\n".join([header, message_text, hashtags])

def chunk_text(text, size=4000):
    for i in range(0, len(text), size):
        yield text[i:i+size]

# ------------------ Sending logic (handles long messages & media) ------------------
async def send_to_single(target, message_text, media=None):
    try:
        if media:
            # send as file with caption first
            caption = message_text[:MAX_CAPTION]
            await client.send_file(target, file=media, caption=caption)
            remaining = message_text[MAX_CAPTION:].strip()
            if remaining:
                # split remaining into chunks
                for chunk in chunk_text(remaining):
                    await client.send_message(target, chunk)
        else:
            # split message into 4000-char chunks
            for chunk in chunk_text(message_text):
                await client.send_message(target, chunk)
        logger.info(f"✅ Sent to {target}")
    except Exception as e:
        logger.error(f"❌ Failed sending to {target}: {e}")

async def send_to_targets(message_text, media=None):
    # TARGET_IDS may have ints; but also keep fallback to TARGET_IDENTIFIERS (strings) if not resolved
    # prefer resolved numeric ids, but attempt sending to identifiers too
    # First try resolved ids
    for tid in list(TARGET_IDS):
        await send_to_single(tid, message_text, media)
    # Then try unresolved identifiers (if any)
    for ident in list(TARGET_IDENTIFIERS):
        # if this identifier resolved to a numeric id, skip
        # otherwise attempt sending by username/identifier
        rid = await resolve_identifier_to_id(ident)
        if rid and rid in TARGET_IDS:
            continue
        await send_to_single(ident, message_text, media)

# ------------------ Main message handler (single handler for dynamic sources) ------------------
@client.on(events.NewMessage())
async def global_message_handler(event):
    # guard: must have message and chat id
    if not getattr(event, "message", None):
        return
    chat_id = getattr(event.message, "chat_id", None)
    if chat_id is None:
        # try peer_id
        try:
            chat_id = event.chat_id
        except Exception:
            chat_id = None
    # If this message already processed, skip
    msg_key = (chat_id, getattr(event.message, "id", None))
    if msg_key in processed_messages:
        return

    # Is this from personal bot (manual)? check PERSONAL_BOT_ID if resolved
    if PERSONAL_BOT_ID and chat_id == PERSONAL_BOT_ID:
        # manual flow -> do not mark processed here before we reply (so reply works)
        try:
            message_text = event.message.message or ""
            links = re.findall(r'https?://\S+', message_text)
            if links:
                # append unique links only if not present
                for l in links:
                    if l not in message_text:
                        message_text += "\n" + l
            media = event.message.media
            if isinstance(media, MessageMediaWebPage):
                media = None
            platform = detect_platform(message_text)
            category = detect_category(message_text)
            final_text = format_template(platform, category, message_text)
            await send_to_targets(final_text, media)
            await event.reply("✅ Sent manually to target chats")
            logger.info(f"Manual message forwarded: Platform={platform}, Category={category}")
            processed_messages.add(msg_key)
        except Exception as e:
            logger.error(f"❌ Manual Send Error: {e}")
        return

    # Is this message from any known source?
    if chat_id in SOURCE_IDS:
        # auto flow
        # mark processed
        processed_messages.add(msg_key)
        try:
            message_text = event.message.message or ""
            links = re.findall(r'https?://\S+', message_text)
            if links:
                for l in links:
                    if l not in message_text:
                        message_text += "\n" + l
            media = event.message.media
            if isinstance(media, MessageMediaWebPage):
                media = None
            platform = detect_platform(message_text)
            category = detect_category(message_text)
            final_text = format_template(platform, category, message_text)
            # send to private group & earnkaro (original behavior) by including those in TARGET_IDENTIFIERS
            await send_to_targets(final_text, media)
            logger.info("✅ Auto-forward processed for source id %s", chat_id)
        except Exception as e:
            logger.error(f"❌ Auto forward failed: {e}")
        return

    # if none matched, ignore
    return

# ------------------ Flask app for runtime add/remove ------------------
app = Flask("")

@app.route("/")
def home():
    return "Bot + runtime routes running."

@app.route("/list")
def list_config():
    # return current identifiers + resolved ids
    return jsonify({
        "source_identifiers": list(SOURCE_IDENTIFIERS),
        "source_ids": list(SOURCE_IDS),
        "target_identifiers": list(TARGET_IDENTIFIERS),
        "target_ids": list(TARGET_IDS),
        "personal_bot_username": PERSONAL_BOT_USERNAME,
        "personal_bot_id": PERSONAL_BOT_ID
    })

@app.route("/add_source")
def add_source():
    if not is_protected(request):
        return "Unauthorized", 401
    ch = request.args.get("channel")
    if not ch:
        return "Provide channel param ?channel=@name or id", 400
    SOURCE_IDENTIFIERS.add(ch)
    # schedule resolver
    fut = asyncio.run_coroutine_threadsafe(_add_source_async(ch), MAIN_LOOP)
    res = fut.result(timeout=10)
    return jsonify({"added": ch, "resolved_id": res})

@app.route("/add_target")
def add_target():
    if not is_protected(request):
        return "Unauthorized", 401
    chat = request.args.get("chat")
    if not chat:
        return "Provide chat param ?chat=@name or id", 400
    TARGET_IDENTIFIERS.add(chat)
    fut = asyncio.run_coroutine_threadsafe(_add_target_async(chat), MAIN_LOOP)
    res = fut.result(timeout=10)
    return jsonify({"added": chat, "resolved_id": res})

# async helpers used by Flask endpoints
async def _add_source_async(identifier):
    SOURCE_IDENTIFIERS.add(identifier)
    rid = await resolve_identifier_to_id(identifier)
    if rid:
        SOURCE_IDS.add(rid)
    return rid

async def _add_target_async(identifier):
    TARGET_IDENTIFIERS.add(identifier)
    rid = await resolve_identifier_to_id(identifier)
    if rid:
        TARGET_IDS.add(rid)
    return rid

# ------------------ Main startup ------------------
async def main_startup():
    await client.start()
    logger.info("✅ Telegram client started")
    # resolve initial identifiers -> ids
    await resolve_all_initial()
    # keep client running
    await client.run_until_disconnected()

# We'll create an event loop and keep a reference for Flask thread to use
MAIN_LOOP = None

if __name__ == "__main__":
    # create and set loop
    MAIN_LOOP = asyncio.new_event_loop()
    asyncio.set_event_loop(MAIN_LOOP)

    # start Flask in a separate thread (safe)
    Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080))), daemon=True).start()

    # start telethon client & tasks on the MAIN_LOOP
    MAIN_LOOP.create_task(main_startup())
    logger.info("Starting main event loop")
    MAIN_LOOP.run_forever()
