import os
import logging
import asyncio
import base64
import re
import requests
import google.generativeai as genai
import json
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaWebPage
from flask import Flask

# ------------------ Constants ------------------
MAX_CAPTION = 1024

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
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Validate required variables
required_vars = [API_ID, API_HASH, PRIVATE_GROUP_ID, EARNKARO_BOT_USERNAME, PERSONAL_BOT_USERNAME, SOURCE_CHANNEL_USERNAME, GEMINI_API_KEY]
if not all(required_vars):
    logger.error("❌ Required environment variables not set (including GEMINI_API_KEY)")
    exit(1)

API_ID = int(API_ID)
PRIVATE_GROUP_ID = int(PRIVATE_GROUP_ID)

# ------------------ Gemini AI कॉन्फ़िगरेशन ------------------
model = None 
try:
    if not GEMINI_API_KEY:
        logger.error("❌ GEMINI_API_KEY is not set. AI features will be disabled.")
    else:
        genai.configure(api_key=GEMINI_API_KEY)
        model_name = 'models/gemini-2.5-flash'
        model = genai.GenerativeModel(model_name)
        logger.info(f"✅ Gemini AI Model ('{model_name}') initialized successfully.")
except Exception as e:
    logger.error(f"❌ Gemini AI को इनिशियलाइज़ करते समय त्रुटि: {e}")

# ------------------ Session File ------------------
if SESSION_BASE64:
    with open("final_session.session", "wb") as f:
        f.write(base64.b64decode(SESSION_BASE64))
    logger.info("✅ final_session.session file created from SESSION_BASE64")

# ------------------ Templates (Fallback के लिए) ------------------
TEMPLATES = {
    "amazon": {"hashtags": "#Amazon #LootDeal #DealLootIndia #Deallootindia_offical"},
    "flipkart": {"hashtags": "#Flipkart #LootDeal #DealLootIndia #Deallootindia_offical"},
    "myntra": {"hashtags": "#Myntra #StyleDeal #DealLootIndia #Deallootindia_offical"},
    "ajio": {"hashtags": "#Ajio #FashionDeal #DealLootIndia #Deallootindia_offical"},
    "meesho": {"hashtags": "#Meesho #BudgetDeal #DealLootIndia #Deallootindia_offical"},
    "jiomart": {"hashtags": "#JioMart #LootDeal #DealLootIndia #Deallootindia_offical"}
}
DEFAULT_HASHTAGS = "#DealLootIndia #LootDeal #OnlineShopping #Deallootindia_offical"


PLATFORM_KEYWORDS = {
    "amazon": ["amazon.in", "amzn.to", "amazon", "amzn", "amazn"],
    "flipkart": ["flipkart.com", "fkrt", "flipkart", "flpkrt", "fkrt.xyz", "fktr.in"],
    "myntra": ["myntra.in", "myntr.it", "myntra", "myntr"],
    "ajio": ["ajio.in", "ajio"],
    "meesho": ["meesho.com", "msho.in", "meesho", "msho"],
    "jiomart": ["jiomart.com", "jiomart"]
}

processed_messages = set()
client = TelegramClient("final_session", API_ID, API_HASH)

# ------------------ Helper Functions ------------------

def resolve_short_link(url):
    try:
        response = requests.head(url, allow_redirects=True, timeout=5)
        return response.url
    except requests.RequestException:
        return url

# --- बदलाव 1: इस फंक्शन को सरल बनाया गया ---
# अब यह सिर्फ दिए गए टेक्स्ट में कीवर्ड्स ढूंढेगा
def detect_platform(text_to_check):
    if not text_to_check: return None
    text_lower = text_to_check.lower().replace(" ", "")
    for platform, keywords in PLATFORM_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return platform
    return None

def get_ai_generated_details(text):
    if not model:
        logger.warning("⚠️ Gemini AI model not available. Using default details.")
        return "Deal", "✨", "⚡ Amazing deal waiting for you!\n🚀 Hurry, grab it now!", None

    # AI को भेजने से पहले टेक्स्ट को थोड़ा साफ करें
    product_info_text = re.sub(r'\[.*?\]', '', text).strip() # [Over] जैसे टैग्स हटा दें
    product_info = "\n".join(product_info_text.split('\n')[:4])

    prompt = f"""
    Analyze the following product information from an Indian shopping deal. Your task is to generate a JSON object with four keys: "category", "emoji", "intro_lines", and "hashtags".
    Instructions:
    1. "category": Determine the most appropriate single-word category (e.g., Electronics, Fashion, Kitchen).
    2. "emoji": Provide a single, suitable emoji that best represents the product.
    3. "intro_lines": Create two short, exciting introductory lines for the deal, separated by a newline (\\n).
    4. "hashtags": Create a single string of 5-7 relevant hashtags. The hashtags should include the product name, brand, category, and ALWAYS end with "#Deallootindia_offical". Separate them with spaces.
    Product: "boAt Airdopes 141, TWS Earbuds with 42H Playtime" -> {{"category": "Electronics", "emoji": "🎧", "intro_lines": "🎶 Immerse yourself in pure sound!\\n🚀 Grab these top-rated earbuds at a steal!", "hashtags": "#boAtAirdopes #Earbuds #AudioDeal #Electronics #LootDeal #Deallootindia_offical"}}
    Product: "Puma Men's Regular Fit T-Shirt, Blue" -> {{"category": "Fashion", "emoji": "👕", "intro_lines": "🔥 Upgrade your style with this classic Puma tee!\\n🚀 Limited stock, shop now!", "hashtags": "#PumaFashion #MensTshirt #FashionDeal #Puma #MyntraDeals #Deallootindia_offical"}}
    Product Information: --- {product_info} ---
    Your JSON Response:
    """
    try:
        response = model.generate_content(prompt)
        match = re.search(r'\{.*\}', response.text, re.DOTALL)
        if match:
            json_text = match.group(0)
            result = json.loads(json_text)
            return (
                result.get("category", "Deal"), 
                result.get("emoji", "🔥"), 
                result.get("intro_lines", "⚡ Amazing deal waiting for you!"),
                result.get("hashtags")
            )
        else:
             raise ValueError("No valid JSON found in the response")
    except Exception as e:
        logger.error(f"❌ Gemini AI Error: {e}")
        return "Deal", "✨", "⚡ Amazing deal waiting for you!\n🚀 Hurry, grab it now!", None

def clean_incoming_message(text):
    lines = text.split('\n')
    cleaned_lines = [line for line in lines if "@lootshoppingxyz" not in line]
    cleaned_text = "\n".join(cleaned_lines)
    return cleaned_text.strip()

def format_template(platform, category, emoji, intro_lines, message_text, final_hashtags):
    follow_line = "👉 Follow @Deallootindia_offical for 🔥 daily loot deals!"
    platform_name = platform.capitalize() if platform else "Hot"
    category_name = category.capitalize()
    first_line = f"{emoji} {platform_name} {category_name} Deal"
    header = f"{first_line}\n{intro_lines}"
    template_parts = [header, message_text.strip(), follow_line, final_hashtags]
    return "\n\n".join(filter(None, template_parts))

async def send_smart_message(chat_id, text, media):
    try:
        if media:
            if len(text) > MAX_CAPTION:
                await client.send_file(chat_id, file=media, caption=text[:MAX_CAPTION])
                await client.send_message(chat_id, text[MAX_CAPTION:])
            else:
                await client.send_file(chat_id, file=media, caption=text)
        else:
            await client.send_message(chat_id, text)
        return True
    except Exception as e:
        logger.error(f"❌ Failed sending to {chat_id}: {e}")
        return False

# ------------------ Event Handlers ------------------
async def process_message(event):
    msg_key = (event.message.chat_id, event.message.id)
    if msg_key in processed_messages: return None, None
    processed_messages.add(msg_key)

    message_text = event.message.message or ""
    # यह हमारा फाइनल टेक्स्ट होगा जिसे हम भेजेंगे
    cleaned_message_text = clean_incoming_message(message_text)
    
    media = event.message.media
    if isinstance(media, MessageMediaWebPage): media = None

    # --- बदलाव 2: नया और स्मार्ट लॉजिक ---
    # प्लेटफॉर्म का पता लगाने के लिए एक अलग टेक्स्ट बनाएंगे
    text_for_detection = cleaned_message_text
    urls = re.findall(r'https?://\S+', cleaned_message_text)
    if urls:
        resolved_url = resolve_short_link(urls[0])
        # असली URL को सिर्फ डिटेक्शन के लिए जोड़ेंगे
        text_for_detection += " " + resolved_url 
    
    # अब इस कंबाइंड टेक्स्ट से प्लेटफॉर्म का पता लगाएंगे
    platform = detect_platform(text_for_detection)
    # ------------------------------------

    # AI को हम साफ-सुथरा टेक्स्ट ही भेजेंगे
    category, emoji, intro_lines, ai_hashtags = get_ai_generated_details(cleaned_message_text)
    
    final_hashtags = ai_hashtags or TEMPLATES.get(platform, {}).get("hashtags", DEFAULT_HASHTAGS)
    if ai_hashtags:
        logger.info("✅ AI-generated hashtags used.")
    else:
        logger.warning("⚠️ AI hashtags failed. Using fallback static hashtags.")

    # फाइनल टेम्पलेट बनाने के लिए हम अपना साफ-सुथरा, ओरिजिनल टेक्स्ट ही इस्तेमाल करेंगे
    final_text = format_template(platform, category, emoji, intro_lines, cleaned_message_text, final_hashtags)
    return final_text, media

@client.on(events.NewMessage(chats=SOURCE_CHANNEL_USERNAME))
async def handle_source(event):
    final_text, media = await process_message(event)
    if final_text:
        if await send_smart_message(PRIVATE_GROUP_ID, final_text, media):
            logger.info(f"✅ Forwarded message to private group: {PRIVATE_GROUP_ID}")
        if await send_smart_message(EARNKARO_BOT_USERNAME, final_text, media):
             logger.info("✅ Sent to EarnKaro bot")

@client.on(events.NewMessage(chats=PERSONAL_BOT_USERNAME))
async def handle_manual(event):
    final_text, media = await process_message(event)
    if final_text:
        if await send_smart_message(EARNKARO_BOT_USERNAME, final_text, media):
            await event.reply("✅ Sent manually to EarnKaro bot")
        else:
            await event.reply(f"❌ Manual Send Error")

# ------------------ Keep Alive Flask Server ------------------
app = Flask("")
@app.route("/")
def home():
    return "Bot is alive and running!"

# ------------------ Main ------------------
async def main():
    await client.start()
    logger.info("✅ Telegram client started and bot is ready!")
    await client.run_until_disconnected()

if __name__ == "__main__":
    from threading import Thread
    flask_thread = Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080))))
    flask_thread.daemon = True
    flask_thread.start()
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped manually.")
