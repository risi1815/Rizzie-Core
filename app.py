import os
import json
import requests
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from groq import Groq
from google import genai
from google.genai import types
from supabase import create_client

app = Flask(__name__)
CORS(app)

# Load Environment Variables from Render
GROQ_API_KEY = (os.environ.get("GROQ_API_KEY") or "").strip()
GEMINI_API_KEY = (os.environ.get("GEMINI_API_KEY") or "").strip()
SARVAM_API_KEY = (os.environ.get("SARVAM_API_KEY") or "").strip()
SUPABASE_URL = (os.environ.get("SUPABASE_URL") or "").strip()
SUPABASE_KEY = (os.environ.get("SUPABASE_KEY") or "").strip()
FAMILY_SECRET_PASSWORD = os.environ.get("FAMILY_SECRET_PASSWORD", "rizzie2026family").strip()

# Initialize AI & Database Clients safely
try:
    groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
except Exception as e:
    print(f"Groq init error: {e}", flush=True)
    groq_client = None

try:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
except Exception as e:
    print(f"Gemini init error: {e}", flush=True)
    gemini_client = None

supabase = None
try:
    if SUPABASE_URL and SUPABASE_KEY and len(SUPABASE_KEY) > 10:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Database vault warning (continuing without vault): {e}", flush=True)

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "Rizzie Family AI Core is online and running 24/7!",
        "features": [
            "Calls, SMS & WhatsApp",
            "Email Composer",
            "YouTube & Maps",
            "Alarms & Reminders",
            "Supabase Family Vault (Auto-Read & Write)"
        ]
    }), 200

@app.route("/rizzie", methods=["POST"])
def rizzie_handler():
    data = request.get_json(silent=True) or {}

    # Security Check
    auth_password = data.get("password") or request.headers.get("X-Family-Password")
    if auth_password != FAMILY_SECRET_PASSWORD:
        return jsonify({"error": "Unauthorized family member access."}), 403

    user_speaker = data.get("speaker", "Family Member")
    user_query = data.get("query", "")

    if not user_query:
        return jsonify({"error": "No query provided."}), 400

    # 1. Fetch Family Tree, Contacts & Birthdays from Supabase Vault
    family_context = "No vault entries loaded."
    if supabase:
        try:
            res = supabase.table("family_vault").select("*").execute()
            family_context = json.dumps(res.data, ensure_ascii=False)
        except Exception as e:
            family_context = f"Vault read note: {str(e)}"

    current_time_str = datetime.now().strftime("%A, %d %B %Y, %I:%M %p")

    # 2. Universal Action & Memory Prompt
    system_prompt = f"""
    You are Rizzie, a warm, smart personal family companion for Rishikesh's family in Bengaluru.
    Current Date & Time: {current_time_str}.
    Speaker: {user_speaker}.
    Family Vault Database (Contacts, Relations, Birthdays, Notes): {family_context}

    You understand colloquial Tamil, Tanglish ('Pavithra ku call pannu', 'Amma ku WhatsApp anupu', '6:30 ku alarm vai'), and English fluently.

    Analyze the user's request and return a STRICT JSON object with these exact 6 keys:
    1. "action": Must be one of:
       - "NONE" (general conversation, answering questions, checking birthdays/info from the vault)
       - "MAKE_CALL" (phone call)
       - "SEND_SMS" (normal text message)
       - "SEND_WHATSAPP" (WhatsApp message)
       - "SEND_EMAIL" (sending an email)
       - "PLAY_YOUTUBE" (searching or playing a video/song on YouTube)
       - "NAVIGATE_MAPS" (directions or finding a place on Google Maps)
       - "SET_ALARM" (setting a clock alarm)
       - "SET_REMINDER" (setting a reminder or calendar event)
       - "SAVE_VAULT" (when the user asks you to remember a birthday, phone number, relation, or note)
       - "EMERGENCY_SOS" (urgent help needed)

    2. "target":
       - For MAKE_CALL / SEND_SMS / SEND_WHATSAPP: Look up the person's phone number in Family Vault Database. If found, output the exact 10-digit or +91 number. If not in the vault, output their clean Contact Name so the phone can look it up locally.
       - For SEND_EMAIL: Recipient's email address from the vault (or name if unknown).
       - For PLAY_YOUTUBE: The exact YouTube search query (e.g., "Lana Del Rey Summertime Sadness" or "Tamil melody songs").
       - For NAVIGATE_MAPS: Destination name or address.
       - For SET_ALARM: 24-hour hour integer as string (e.g., "6" for 6 AM, "18" for 6 PM).
       - For SET_REMINDER: Reminder title/task description.
       - For SAVE_VAULT: Category name (e.g., "birthday", "contact", "medical", "note").
       - Otherwise: ""

    3. "subject":
       - For SEND_EMAIL: Email subject line.
       - For SAVE_VAULT: Person's name or item title (e.g., "Pavithra", "Niece Birthday").
       - Otherwise: ""

    4. "body":
       - For SEND_SMS / SEND_WHATSAPP / SEND_EMAIL: The message or email body text to send.
       - For SAVE_VAULT: The exact details to store (e.g., "Birthday is Oct 15", "Phone: +919876543210").
       - Otherwise: ""

    5. "extra_param":
       - For SET_ALARM: Minute integer as string (e.g., "30" for 6:30, "0" for on the hour).
       - For SET_REMINDER: Time or date string (e.g., "Tomorrow 9:00 AM").
       - Otherwise: ""

    6. "spoken_reply": A warm, natural, brief spoken confirmation in colloquial Tanglish/Tamil or English addressing {user_speaker}.
    """

    groq_err = "Not configured"
    gemini_err = "Not configured"
    ai_output = None

    # Try Groq First
    if groq_client:
        try:
            completion = groq_client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_query}
                ],
                temperature=0.7,
                max_completion_tokens=2048,
                top_p=1,
                stream=False,
                response_format={"type": "json_object"}
            )
            ai_output = json.loads(completion.choices[0].message.content)
        except Exception as e:
            groq_err = str(e)
            print(f"Groq API error: {groq_err}", flush=True)

    # Fallback to Gemini if Groq failed
    if not ai_output and gemini_client:
        try:
            valid_gemini_models = [
                m.name.replace("models/", "") for m in gemini_client.models.list()
                if "flash" in m.name.lower() and not any(x in m.name.lower() for x in ["tts", "image", "audio", "embedding", "2.5"])
            ]
            target_gemini = "gemini-3.5-flash"
            if valid_gemini_models and target_gemini not in valid_gemini_models:
                target_gemini = valid_gemini_models[0]

            response = gemini_client.models.generate_content(
                model=target_gemini,
                contents=user_query,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json"
                )
            )
            ai_output = json.loads(response.text)
        except Exception as e:
            gemini_err = str(e)
            print(f"Gemini API error: {gemini_err}", flush=True)

    if not ai_output:
        return jsonify({
            "action": "NONE",
            "spoken_reply": "Sorry, both of my AI brains encountered an error.",
            "debug_groq_error": groq_err,
            "debug_gemini_error": gemini_err
        }), 500

    # 3. Auto-Save to Supabase if action is SAVE_VAULT
    if ai_output.get("action") == "SAVE_VAULT" and supabase:
        try:
            supabase.table("family_vault").insert({
                "category": ai_output.get("target", "general"),
                "name": ai_output.get("subject", user_speaker),
                "details": ai_output.get("body", user_query)
            }).execute()
        except Exception as db_err:
            print(f"Supabase insert error: {db_err}", flush=True)

    return jsonify(ai_output), 200

# Dedicated Sarvam AI Text-to-Speech Endpoint
@app.route("/speak", methods=["POST"])
def sarvam_speak():
    data = request.get_json(silent=True) or {}
    text_to_speak = data.get("text", "")

    if not SARVAM_API_KEY:
        return jsonify({"error": "Sarvam API Key not configured."}), 500

    url = "https://api.sarvam.ai/text-to-speech"
    payload = {
        "inputs": [text_to_speak],
        "target_language_code": "ta-IN",
        "speaker": "meera",
        "speech_sample_rate": 8000,
        "enable_preprocessing": True,
        "model": "bulbul:v1"
    }
    headers = {
        "api-subscription-key": SARVAM_API_KEY,
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
