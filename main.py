from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from telethon import TelegramClient
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN')

bot_client = TelegramClient('bot_session', int(API_ID), API_HASH)

@app.on_event("startup")
async def startup_event():
    await bot_client.start(bot_token=BOT_TOKEN)
    print("Backend Berhasil Online!")

@app.post("/register")
async def register(request: Request):
    data = await request.json()
    nama = data.get("name")
    phone = data.get("phone")
    await bot_client.send_message('me', f"Pendaftar: {nama}\nHP: {phone}")
    return {"status": "success"}

@app.get("/")
async def root():
    return {"message": "Server Aktif!"}