import os
import json
import base64
import io
import requests
from datetime import datetime
from flask import Flask, request, jsonify, send_file
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

# ---------------------------------------------------------
# RIZZIE'S SHORT-TERM MEMORY BANK
# Stores the last 5 conversation pairs for each speaker
# ---------------------------------------------------------
family_memory = {
    "Rishikesh": [],
    "Mom": [],
    "Sister": []
}

def get_system_prompt(speaker, current_time, vault_data):
    """Dynamic Family Brain System Prompt"""
    base_prompt = f"""You are Rizzie, a private, hyper-personalized AI assistant for a specific family. 
    You manage their schedules, provide technical/mechanical advice, and execute device actions.
    Keep responses extremely concise, warm, and natural. Do not act like a corporate bot.
    You understand colloquial Tamil, Tanglish, and English fluently.
    
    Current Date & Time: {current_time}.
    Location: Bengaluru (Bommasandra, Electronic City).
    Family Vault Database (Contacts, Relations, Birthdays, Notes): {vault_data}
    
    CRITICAL: If the user asks a math question, a science question, or general knowledge, calculate and provide the correct answer immediately within the 'spoken_reply' using action 'NONE'.

    Analyze the user's request and return a STRICT JSON object with these exact 6 keys:
    1. "action": Must be one of:
       - "NONE" (general conversation, answering math/facts, checking vault info)
       - "OPEN_APP" (opening a general app on the phone)
       - "MAKE_CALL" (phone call)
       - "SEND_SMS" (normal text message)
       - "SEND_WHATSAPP" (WhatsApp message)
       - "SEND_EMAIL" (sending an email)
       - "PLAY_YOUTUBE" (searching or playing a video/song on YouTube)
       - "NAVIGATE_MAPS" (directions or finding a place on Google Maps)
       - "SET_ALARM" (setting a clock alarm)
       - "SET_REMINDER" (setting a reminder or calendar event)
       - "SAVE_VAULT" (saving new info to the database)
       - "EMERGENCY_SOS" (urgent help needed)

    2. "target":
       - For OPEN_APP: The exact name of the app (e.g., "Instagram", "Calculator", "Spotify").
       - For MAKE_CALL / SEND_SMS / SEND_WHATSAPP: 10-digit number or Contact Name.
       - For PLAY_YOUTUBE: The exact YouTube search query.
       - For NAVIGATE_MAPS: Destination name or address.
       - For SET_ALARM: 24-hour hour integer as string.
       - Otherwise: ""

    3. "subject": Email subject line (Otherwise: "").
    4. "body": Message text or vault details (Otherwise: "").
    5. "extra_param": Minute string for alarm, time/date for reminder (Otherwise: "").
    6. "spoken_reply": A warm, natural, brief spoken confirmation or direct answer.
    """
    
    # Hyper-Personalized Context based on Speaker
    if "Rishikesh" in speaker:
        base_prompt += "\n\nYou are speaking to Rishikesh (Admin). You know he is a Mechanical Design Engineer, rides a black Bajaj Pulsar N250, commutes 30km daily, follows a high-protein diet (legumes/eggs), and builds automation using SolidWorks/Python. Focus on engineering logic, bike maintenance, fitness goals, and direct action. You know his close friend Julie has a B.A. in Psychology."
    elif "Mom" in speaker:
        base_prompt += "\n\nYou are speaking to Mom. Be highly respectful, warm, and helpful with household, health, or family scheduling."
    elif "Sister" in speaker:
        base_prompt += "\n\nYou are speaking to Sister. Be friendly, casual, and assist with her daily routines or ideas for the 3-year-old niece."

    return base_prompt

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "Rizzie Family AI Core is online and running 24/7!",
        "features": [
            "All-Rounder General Knowledge & Math",
            "App Launching & Media Controls",
            "Calls, SMS & WhatsApp",
            "Sarvam TTS Engine Audio Export",
            "Short-Term Context Memory"
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

    # Extract clean name for memory tracking (e.g. "Rishikesh" from "Rishikesh (Admin)")
    speaker_name = user_speaker.split(" ")[0]
    if speaker_name not in family_memory:
        family_memory[speaker_name] = []

    # 1. Fetch Vault Data
    family_context = "No vault entries loaded."
    if supabase:
        try:
            res = supabase.table("family_vault").select("*").execute()
            family_context = json.dumps(res.data, ensure_ascii=False)
        except Exception as e:
            family_context = f"Vault read note: {str(e)}"

    current_time_str = datetime.now().strftime("%A, %d %B %Y, %I:%M %p")
    system_prompt = get_system_prompt(user_speaker, current_time_str, family_context)
    
    groq_err = "Not configured"
    gemini_err = "Not configured"
    ai_output = None

    # Retrieve short-term memory for this specific speaker
    history = family_memory[speaker_name]

    # -----------------------------------------------------
    # AI Logic: Try Groq First
    # -----------------------------------------------------
    if groq_client:
        try:
            # Build Groq message array (System -> History -> Current Prompt)
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(history)
            messages.append({"role": "user", "content": user_query})

            completion = groq_client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=messages,
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

    # -----------------------------------------------------
    # Fallback to Gemini if Groq failed
    # -----------------------------------------------------
    if not ai_output and gemini_client:
        try:
            valid_gemini_models = [
                m.name.replace("models/", "") for m in gemini_client.models.list()
                if "flash" in m.name.lower() and not any(x in m.name.lower() for x in ["tts", "image", "audio", "embedding", "2.5"])
            ]
            target_gemini = "gemini-3.5-flash"
            if valid_gemini_models and target_gemini not in valid_gemini_models:
                target_gemini = valid_gemini_models[0]

            # Build Gemini history format (user vs model)
            gemini_contents = []
            for msg in history:
                role = "user" if msg["role"] == "user" else "model"
                gemini_contents.append({"role": role, "parts": [{"text": msg["content"]}]})
            gemini_contents.append({"role": "user", "parts": [{"text": user_query}]})

            response = gemini_client.models.generate_content(
                model=target_gemini,
                contents=gemini_contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json"
                )
            )
            ai_output = json.loads(response.text)
        except Exception as e:
            gemini_err = str(e)
            print(f"Gemini API error: {gemini_err}", flush=True)

    # -----------------------------------------------------
    # Handle Failures & Update Memory Bank
    # -----------------------------------------------------
    if not ai_output:
        return jsonify({
            "action": "NONE",
            "spoken_reply": "Sorry, both of my AI brains encountered an error.",
            "debug_groq_error": groq_err,
            "debug_gemini_error": gemini_err
        }), 500

    # Save interaction to memory
    ai_spoken_reply = ai_output.get("spoken_reply", "Done.")
    history.append({"role": "user", "content": user_query})
    history.append({"role": "assistant", "content": ai_spoken_reply})
    
    # Cap memory at the last 10 messages (5 interactions) to prevent token limits
    if len(history) > 10:
        history = history[-10:]
    
    family_memory[speaker_name] = history

    return jsonify(ai_output), 200

# ---------------------------------------------------------
# Sarvam AI TTS Endpoint 
# ---------------------------------------------------------
@app.route("/speak", methods=["POST"])
def sarvam_speak():
    data = request.get_json(silent=True) or {}
    text_to_speak = data.get("text", "")

    if not text_to_speak:
        return jsonify({"error": "No text provided"}), 400

    if not SARVAM_API_KEY:
        return jsonify({"error": "Sarvam API Key not configured."}), 500

    url = "https://api.sarvam.ai/text-to-speech"
    payload = {
        "inputs": [text_to_speak],
        "target_language_code": "ta-IN",
        "speaker": "vijay_ta_narration",  # Valid Tamil male voice from the error list
        "speech_sample_rate": 16000,
        "enable_preprocessing": True,
        "model": "bulbul:v4-flash"        # Required new model version
    }
    headers = {
        "api-subscription-key": SARVAM_API_KEY,
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response_data = response.json()

        # Extract the Base64 audio string from Sarvam's JSON
        if "audios" in response_data and len(response_data["audios"]) > 0:
            audio_base64 = response_data["audios"][0]
            audio_bytes = base64.b64decode(audio_base64)
            
            return send_file(
                io.BytesIO(audio_bytes),
                mimetype="audio/wav",
                as_attachment=False,
                download_name="rizzie_voice.wav"
            )
        else:
            return jsonify({"error": "No audio returned from Sarvam", "details": response_data}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
