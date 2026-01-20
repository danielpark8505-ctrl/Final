import os, json, logging, asyncio, requests
from flask import Flask
from threading import Thread
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler

# --- LOGGING ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- KEEP ALIVE SERVER ---
server = Flask('')
@server.route('/')
def home(): return "Bot is Online!"
def run_server(): server.run(host='0.0.0.0', port=8080)

# --- CONFIGURATION ---
TOKEN = os.getenv('TOKEN')
ADMIN_ID = 7371674958 
DB_FILE = "pro_db.json"

# Database Loading Logic
if os.path.exists(DB_FILE):
    try:
        with open(DB_FILE, "r") as f: db = json.load(f)
    except: db = {"channels": {}, "req_channels": {}, "post_channel": None, "users": [], "amzn_tag": "", "cue_pub_id": ""}
else:
    db = {"channels": {}, "req_channels": {}, "post_channel": None, "users": [], "amzn_tag": "", "cue_pub_id": ""}

def save_db():
    with open(DB_FILE, "w") as f: json.dump(db, f, indent=4)

# --- LINK CONVERTER ---
def convert_link(url):
    if not url: return url
    if "amazon.in" in url:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}tag={db['amzn_tag']}" if db['amzn_tag'] else url
    elif db["cue_pub_id"] and any(x in url for x in ["myntra", "ajio", "flipkart"]):
        encoded = requests.utils.quote(url)
        return f"https://linksredirect.com/?pub_id={db['cue_pub_id']}&url={encoded}"
    return url

# --- AUTO-SCRAPER ---
async def auto_fetch_deals(context: ContextTypes.DEFAULT_TYPE):
    if not db.get("post_channel"): return
    try:
        res = requests.get("https://www.pricebefore.com/deals/", timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        deal = soup.find('div', class_='deal-item')
        if deal:
            title = deal.find('h3').get_text(strip=True)
            raw_url = deal.find('a')['href']
            price = deal.find('span', class_='price').get_text(strip=True)
            final_url = convert_link(raw_url)
            text = f"🔥 **AUTO LOOT DEAL** 🔥\n\n📦 {title}\n💰 Price: {price}\n\n🛒 [Buy Now]({final_url})"
            await context.bot.send_message(chat_id=db["post_channel"], text=text, parse_mode='Markdown')
    except Exception as e: logging.error(f"Scraper Error: {e}")

# --- KEYBOARDS ---
def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Add Join", callback_data="add_join"), InlineKeyboardButton("🔒 Add Req", callback_data="add_req")],
        [InlineKeyboardButton("🚀 Set Post Ch", callback_data="add_post"), InlineKeyboardButton("🗑️ Delete Menu", callback_data="del_menu")],
        [InlineKeyboardButton("📊 Stats", callback_data="stats"), InlineKeyboardButton("📤 Broadcast", callback_data="broadcast_start")],
        [InlineKeyboardButton("🆔 Set Tags", callback_data="set_tags")]
    ])

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in db["users"]: db["users"].append(uid); save_db()
    
    # Force Join Check
    all_ch = {**db["channels"], **db["req_channels"]}
    for cid in all_ch:
        try:
            m = await context.bot.get_chat_member(chat_id=int(cid), user_id=uid)
            if m.status in ['left', 'kicked']:
                kb = [[InlineKeyboardButton(c['name'], url=c['link'])] for id, c in all_ch.items()]
                await update.message.reply_text("❌ Access Denied! Join all channels first:", reply_markup=InlineKeyboardMarkup(kb))
                return
        except: pass
    await update.message.reply_text("✅ Welcome! You are verified. Use /admin if you are the owner.")

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text("💎 **PRO ADMIN PANEL**", reply_markup=admin_keyboard())

async def cb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "stats":
        txt = f"📊 **Stats**\n\nUsers: {len(db['users'])}\nChannels: {len(db['channels'])+len(db['req_channels'])}\nTag: {db['amzn_tag']}\nCueID: {db['cue_pub_id']}"
        await query.edit_message_text(txt, reply_markup=admin_keyboard())
    
    elif query.data in ["add_join", "add_req", "add_post"]:
        context.user_data['action'] = query.data
        await query.edit_message_text("👉 Ab message **Forward** karein (Bot admin hona chahiye).")
    
    elif query.data == "del_menu":
        buttons = []
        for k, v in db["channels"].items(): buttons.append([InlineKeyboardButton(f"❌ Join: {v['name']}", callback_data=f"del_j_{k}")])
        for k, v in db["req_channels"].items(): buttons.append([InlineKeyboardButton(f"❌ Req: {v['name']}", callback_data=f"del_r_{k}")])
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_admin")])
        await query.edit_message_text("Select channel to delete:", reply_markup=InlineKeyboardMarkup(buttons))

    elif query.data.startswith("del_j_"):
        cid = query.data.replace("del_j_", "")
        if cid in db["channels"]: del db["channels"][cid]
        save_db(); await query.edit_message_text("✅ Deleted!", reply_markup=admin_keyboard())

    elif query.data == "broadcast_start":
        context.user_data['broadcasting'] = True
        await query.edit_message_text("👉 Ab wo message bheinjein jise **Broadcast** karna hai.")
    
    elif query.data == "set_tags":
        await query.edit_message_text("Commands:\n`/set_amzn tag-21`\n`/set_cue id`")
    
    elif query.data == "back_admin":
        await query.edit_message_text("💎 **ADMIN PANEL**", reply_markup=admin_keyboard())

async def msg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    # Broadcast Logic
    if context.user_data.get('broadcasting'):
        for uid in db["users"]:
            try: await update.message.copy(chat_id=uid); await asyncio.sleep(0.05)
            except: pass
        context.user_data['broadcasting'] = False
        await update.message.reply_text("✅ Broadcast Done!")
        return

    # Forward Logic for Adding Channels
    action = context.user_data.get('action')
    if update.message.forward_from_chat and action:
        chat = update.message.forward_from_chat
        link = chat.invite_link or f"https://t.me/{chat.username}"
        if action == "add_join": db["channels"][str(chat.id)] = {"name": chat.title, "link": link}
        elif action == "add_req": db["req_channels"][str(chat.id)] = {"name": chat.title, "link": link}
        elif action == "add_post": db["post_channel"] = chat.id
        save_db(); await update.message.reply_text(f"✅ Saved: {chat.title}"); context.user_data['action'] = None

# --- ID COMMANDS ---
async def set_amzn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID and context.args:
        db["amzn_tag"] = context.args[0]; save_db()
        await update.message.reply_text(f"✅ Amazon Tag: {db['amzn_tag']}")

async def set_cue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID and context.args:
        db["cue_pub_id"] = context.args[0]; save_db()
        await update.message.reply_text(f"✅ Cuelinks ID: {db['cue_pub_id']}")

# --- MAIN ---
if __name__ == '__main__':
    Thread(target=run_server).start()
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('admin', admin_cmd))
    app.add_handler(CommandHandler('set_amzn', set_amzn))
    app.add_handler(CommandHandler('set_cue', set_cue))
    app.add_handler(CallbackQueryHandler(cb_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, msg_handler))
    
    if app.job_queue:
        app.job_queue.run_repeating(auto_fetch_deals, interval=1200, first=10)
    
    print("--- STARTING POLLING ---")
    app.run_polling(drop_pending_updates=True)
