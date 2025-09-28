```python
import os
import base64
import logging
from telethon import TelegramClient, events
from flask import Flask
from threading import Thread

# ------------------ Logging ------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ------------------ Environment Variables ------------------
required_vars = {
    "API_ID": os.getenv("API_ID"),
    "API_HASH": os.getenv("API_HASH"),
    "SOURCE_CHANNEL_USERNAME": os.getenv("SOURCE_CHANNEL_USERNAME"),
    "TARGET_CHAT_ID": os.getenv("TARGET_CHAT_ID"),
    "SESSION_BASE64": os.getenv("SESSION_BASE64"),
}

missing = [k for k, v in required_vars.items() if not v]
if missing:
    logger.error(f"❌ Missing environment variables: {', '.join(missing)}")
    exit(1)

API_ID = int(required_vars["API_ID"])
API_HASH = required_vars["API_HASH"]
SOURCE_CHANNELS = [x.strip() for x in required_vars["SOURCE_CHANNEL_USERNAME"].split(",")]
TARGET_CHAT_IDS = [x.strip() for x in required_vars["TARGET_CHAT_ID"].split(",")]
SESSION_BASE64 = required_vars["SESSION_BASE64"]

# ------------------ Debug print ------------------
logger.info(f"🔎 Listening to source channels: {SOURCE_CHANNELS}")
logger.info(f"🎯 Target chat IDs: {TARGET_CHAT_IDS}")

# ------------------ Session Handling ------------------
session_file = "final_session.session"
if not os.path.exists(session_file):
    with open(session_file, "wb") as f:
        f.write(base64.b64decode(SESSION_BASE64))
    logger.info("✅ Session file created from SESSION_BASE64")

# ------------------ Telegram Client ------------------
client = TelegramClient(session_file.replace(".session", ""), API_ID, API_HASH)

async def resolve_targets():
    """Convert usernames to entity IDs if needed"""
    resolved = []
    for chat in TARGET_CHAT_IDS:
        try:
            entity = await client.get_entity(chat)
            resolved.append(entity)
            logger.info(f"✅ Resolved target chat: {chat} -> {entity.id}")
        except Exception as e:
            logger.error(f"❌ Failed to resolve {chat}: {e}")
    return resolved

@client.on(events.NewMessage(chats=SOURCE_CHANNELS))
async def handler(event):
    text = event.raw_text
    logger.info(f"📩 New message from {event.chat.username or event.chat_id}")

    for target in await resolve_targets():
        try:
            await client.send_message(target, text)
            logger.info(f"✅ Forwarded to {getattr(target, 'username', target.id)}")
        except Exception as e:
            logger.error(f"❌ Failed to forward to {target}: {e}")

# ------------------ Flask for Render keepalive ------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    with client:
        logger.info("🚀 Telegram client starting...")
        client.run_until_disconnected()
```
