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

# ------------------ Environment Variables ------------------
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
PRIVATE_GROUP_ID = os.getenv("PRIVATE_GROUP_ID")
EARNKARO_BOT_USERNAME = os.getenv("EARNKARO_BOT_USERNAME")
PERSONAL_BOT_USERNAME = os.getenv("PERSONAL_BOT_USERNAME")
SOURCE_CHANNEL_USERNAME = os.getenv("SOURCE_CHANNEL_USERNAME")
SESSION_BASE64 = os.getenv("SESSION_BASE64")

MULTI_SOURCE_CHANNELS = os.getenv("MULTI_SOURCE_CHANNELS", "")
MULTI_TARGETS = os.getenv("MULTI_TARGETS", "")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

if not API_ID or not API_HASH:
    logger.error("❌ API_ID or API_HASH missing")
    exit(1)

try:
    API_ID = int(API_ID)
except Exception:
    logger.error("❌ API_ID must be integer")
    exit(1)

if SESSION_BASE64:
    with open("final_session.session", "wb") as f:
        f.write(base64.b64decode(SESSION_BASE64))
    logger.info("✅ final_session.session created from SESSION_BASE64")

# ------------------ Templates ------------------
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

# ------------------ Sets ------------------
SOURCE_IDENTIFIERS = set()
SOURCE_IDS = set()
TARGET_IDENTIFIERS = set()
TARGET_IDS = set()
PERSONAL_BOT_ID = None

def parse_list_env(s):
    return [x.strip() for x in s.split(",") if x.strip()]

if SOURCE_CHANNEL_USERNAME:
    SOURCE_IDENTIFIERS.update(parse_list_env(SOURCE_CHANNEL_USERNAME))
if MULTI_SOURCE_CHANNELS:
    SOURCE_IDENTIFIERS.update(parse_list_env(MULTI_SOURCE_CHANNELS))
if PRIVATE_GROUP_ID:
    TARGET_IDENTIFIERS.add(str(PRIVATE_GROUP_ID))
if EARNKARO_BOT_USERNAME:
    TARGET_IDENTIFIERS.add(EARNKARO_BOT_USERNAME)
if MULTI_TARGETS:
    TARGET_IDENTIFIERS.update(parse_list_env(MULTI_TARGETS))

# ------------------ Helper Functions ------------------
def detect_platform(text):
    if not text:
        return None
    text_lower = text.lower().replace(" ", "").replace("@", "")
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
    follow_line = "👉 Follow @Deallootindia_offical for 🔥 daily loot deals!"
    first_line = f"{TEMPLATES.get(platform, {'emoji':'🔖'})['emoji']} {platform.capitalize() if platform else ''} Loot Deal"
    intro_lines = TEMPLATES.get(platform, {}).get("intro", "").split("\n")
    header = "\n".join([first_line] + intro_lines)
    hashtags = TEMPLATES.get(platform, {}).get("hashtags", "#DealLootIndia #LootDeal")
    return "\n\n".join([header, message_text, follow_line, hashtags])

# ------------------ Sending ------------------
async def send_to_single(target, message_text, media=None):
    try:
        if media:
            caption = message_text[:MAX_CAPTION]
            await client.send_file(target, file=media, caption=caption)
            remaining = message_text[MAX_CAPTION:].strip()
            if remaining:
                for i in range(0, len(remaining), 4000):
                    await client.send_message(target, remaining[i:i+4000])
        else:
            for i in range(0, len(message_text), 4000):
                await client.send_message(target, message_text[i:i+4000])
        logger.info(f"✅ Sent to {target}")
    except Exception as e:
        logger.error(f"❌ Failed sending to {target}: {e}")

async def send_to_targets(message_text, media=None):
    for tid in list(TARGET_IDS):
        await send_to_single(tid, message_text, media)
    for ident in list(TARGET_IDENTIFIERS):
        rid = await resolve_identifier_to_id(ident)
        if rid and rid in TARGET_IDS:
            continue
        await send_to_single(ident, message_text, media)

async def resolve_identifier_to_id(identifier):
    if not identifier:
        return None
    try:
        if re.match(r"^-?\d+$", identifier):
            return int(identifier)
    except:
        pass
    try:
        ent = await client.get_entity(identifier)
        return int(ent.id)
    except Exception as e:
        logger.warning(f"Could not resolve {identifier} to id: {e}")
        return None

async def resolve_all_initial():
    global PERSONAL_BOT_ID
    for ident in list(SOURCE_IDENTIFIERS):
        rid = await resolve_identifier_to_id(ident)
        if rid:
            SOURCE_IDS.add(rid)
    for ident in list(TARGET_IDENTIFIERS):
        rid = await resolve_identifier_to_id(ident)
        if rid:
            TARGET_IDS.add(rid)
    if PERSONAL_BOT_USERNAME:
        pbid = await resolve_identifier_to_id(PERSONAL_BOT_USERNAME)
        if pbid:
            PERSONAL_BOT_ID = pbid
    logger.info(f"Resolved source ids: {SOURCE_IDS}")
    logger.info(f"Resolved target ids: {TARGET_IDS}")
    if PERSONAL_BOT_ID:
        logger.info(f"Resolved personal bot id: {PERSONAL_BOT_ID}")

# ------------------ Message Handler ------------------
@client.on(events.NewMessage())
async def global_message_handler(event):
    if not getattr(event, "message", None):
        return
    chat_id = getattr(event.message, "chat_id", None) or getattr(event, "chat_id", None)
    msg_key = (chat_id, getattr(event.message, "id", None))
    if msg_key in processed_messages:
        return

    message_text = event
