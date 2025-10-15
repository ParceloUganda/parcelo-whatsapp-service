# 🚀 Quick Start: WhatsApp Authentication

## ⚡ 5-Minute Setup

### **Step 1: Generate Secret (30 seconds)**

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Copy the output (64-character hex string).

---

### **Step 2: Update .env (1 minute)**

Add to your FastAPI `.env` file:

```bash
NEXTJS_API_URL=https://parceloug.com
SERVICE_SECRET=<paste-the-64-char-string-here>
```

---

### **Step 3: Run Database Migration (1 minute)**

1. Open Supabase SQL Editor
2. Copy contents of `migrations/magic_auth_tokens.sql`
3. Paste and execute

---

### **Step 4: Configure Next.js (1 minute)**

Add to your Next.js `.env.local` file:

```bash
SERVICE_SECRET=<same-64-char-string-as-fastapi>
```

⚠️ **CRITICAL:** The secret MUST be identical in both files!

---

### **Step 5: Restart FastAPI (30 seconds)**

```bash
# Stop current server (Ctrl+C)
# Start again
uvicorn main:app --reload
```

---

### **Step 6: Test (1 minute)**

Send this WhatsApp message to your bot:

```
Can I see my orders on the website?
```

You should receive a response with a magic link!

---

## ✅ That's It!

Your WhatsApp authentication is now live.

---

## 🔍 Verify It's Working

### **Check FastAPI Logs:**
Look for:
```
RequestWebsiteAccess tool invoked
Magic link generated successfully
```

### **Check Next.js Logs:**
Look for:
```
✅ Magic link generated for 256700123456
```

### **Test the Link:**
1. Click the magic link from WhatsApp
2. Browser should open
3. You should be logged in automatically
4. Orders page should load

---

## 🚨 Troubleshooting

### **"Service configuration error"**
→ `SERVICE_SECRET` is empty in `.env`  
→ Add the secret and restart

### **"Failed to generate access link"**
→ Next.js API not responding  
→ Check `NEXTJS_API_URL` is correct  
→ Verify Next.js server is running

### **"Service temporarily unavailable"**
→ Network error connecting to Next.js  
→ Check firewall/network settings  
→ Verify API endpoint is accessible

---

## 📚 Full Documentation

- **Integration Guide:** `WHATSAPP_AUTH_INTEGRATION.md`
- **Implementation Details:** `IMPLEMENTATION_SUMMARY.md`
- **Database Migration:** `migrations/magic_auth_tokens.sql`
- **Environment Template:** `.env.example`

---

## 🎯 What Users Will See

**User:** "Can I see my orders on the website?"

**Bot:**
```
🔐 Access Your Parcelo Account

Click here to view your orders:
https://parceloug.com/auth/magic?token=abc123...

⏰ This link expires in 1 hour
🔒 Secure login - no password needed

Once you click the link:
• Your browser will open automatically
• You'll be logged into your account
• You can view all your orders and quotations

Need help? Just reply and I'll assist you!
```

---

## ✨ Features Enabled

✅ Password-less authentication  
✅ One-click website access from WhatsApp  
✅ Secure 1-hour magic links  
✅ Automatic account creation/linking  
✅ Preserves all customer data  
✅ Works on any device  

---

**You're ready to go! 🎉**
