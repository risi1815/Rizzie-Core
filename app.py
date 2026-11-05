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

GROQ_API_KEY = (os.environ.get("GROQ_API_KEY") or "").strip()
GEMINI_API_KEY = (os.environ.get("GEMINI_API_KEY") or "").strip()
SARVAM_API_KEY = (os.environ.get("SARVAM_API_KEY") or "").strip()
SUPABASE_URL = (os.environ.get("SUPABASE_URL") or "").strip()
SUPABASE_KEY = (os.environ.get("SUPABASE_KEY") or "").strip()
FAMILY_SECRET_PASSWORD = os.environ.get("FAMILY_SECRET_PASSWORD", "rizzie2026family").strip()

try:
    groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
except Exception as e:
    groq_client = None

try:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
except Exception as e:
    gemini_client = None

supabase = None
if SUPABASE_URL and SUPABASE_KEY and len(SUPABASE_KEY) > 10:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

family_memory = {
    "Rishikesh": [], "Mom": [], "Sister": [], "Auto": []
}

def get_system_prompt(speaker, current_time, vault_data):
    base_prompt = f"""You are Rizzie, a private, hyper-personalized AI assistant for Rishikesh's family.
    Current Date & Time: {current_time}.
    Location: Bengaluru (Bommasandra, Electronic City).
    Family Vault (Contacts, Relations): {vault_data}
    
    You understand colloquial Tamil, Tanglish, and English fluently. Reply warmly and concisely.
    """
    
    # Context-Aware Speaker Auto-Detection
    if speaker == "Auto":
        base_prompt += """
        The active speaker is unknown. You must INFER who is speaking based on the context of their query:
        - If the query is about the Pulsar N250, mechanical engineering, SolidWorks, PC gaming, or messaging Julie, assume the speaker is Rishikesh (Admin).
        - If the query is about household management or health, assume it is Mom.
        - If the query is casual or mentions the 3-year-old niece, assume it is Sister.
        Adapt your response naturally based on who you think it is.
        """
    elif "Rishikesh" in speaker:
        base_prompt += "\nYou are speaking to Rishikesh (Admin). You know he is a Mechanical Design Engineer, rides a black Bajaj Pulsar N250, commutes 30km daily, follows a high-protein diet (legumes/eggs), and builds automation using SolidWorks/Python. Focus on engineering logic, bike maintenance, fitness goals, and direct action. You know his close friend Julie has a B.A. in Psychology."
    elif "Mom" in speaker:
        base_prompt += "\nYou are speaking to Mom. Be highly respectful, warm, and helpful."
    elif "Sister" in speaker:
        base_prompt += "\nYou are speaking to Sister. Be friendly and casual."

    base_prompt += """
    Analyze the user's request and return a STRICT JSON object with these exact 6 keys:
    1. "action": "NONE", "OPEN_APP", "MAKE_CALL", "SEND_SMS", "SEND_WHATSAPP", "PLAY_YOUTUBE", "NAVIGATE_MAPS"
    2. "target":
       - For MAKE_CALL / SEND_SMS / SEND_WHATSAPP: MUST be a 10-digit number. If they say a name (like Julie), pull her number from the Family Vault. If not in vault, return the name so the app can open the contact book.
       - For NAVIGATE_MAPS: Destination name (e.g., "Phoenix Marketcity Whitefield").
       - Otherwise: ""
    3. "subject": ""
    4. "body": ""
    5. "extra_param": ""
    6. "spoken_reply": A warm, natural, brief spoken confirmation. Speak in Tanglish/Tamil or English.
    """
    return base_prompt

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "Rizzie is online."}), 200

@app.route("/rizzie", methods=["POST"])
def rizzie_handler():
    data = request.get_json(silent=True) or {}
    if data.get("password") != FAMILY_SECRET_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 403

    user_speaker = data.get("speaker", "Auto")
    user_query = data.get("query", "")
    speaker_name = user_speaker.split(" ")[0]
    
    if speaker_name not in family_memory:
        family_memory[speaker_name] = []

    family_context = "No vault entries loaded."
    if supabase:
        try:
            res = supabase.table("family_vault").select("*").execute()
            family_context = json.dumps(res.data, ensure_ascii=False)
        except:
            pass

    current_time_str = datetime.now().strftime("%A, %d %B %Y, %I:%M %p")
    system_prompt = get_system_prompt(user_speaker, current_time_str, family_context)
    history = family_memory[speaker_name]
    ai_output = None

    if groq_client:
        try:
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(history)
            messages.append({"role": "user", "content": user_query})
            completion = groq_client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=messages,
                temperature=0.7,
                max_completion_tokens=2048,
                response_format={"type": "json_object"}
            )
            ai_output = json.loads(completion.choices[0].message.content)
        except:
            pass

    if not ai_output and gemini_client:
        try:
            gemini_contents = []
            for msg in history:
                role = "user" if msg["role"] == "user" else "model"
                gemini_contents.append({"role": role, "parts": [{"text": msg["content"]}]})
            gemini_contents.append({"role": "user", "parts": [{"text": user_query}]})
            response = gemini_client.models.generate_content(
                model="gemini-3.5-flash",
                contents=gemini_contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json"
                )
            )
            ai_output = json.loads(response.text)
        except:
            pass

    if not ai_output:
        return jsonify({"action": "NONE", "spoken_reply": "AI processing error."}), 500

    history.append({"role": "user", "content": user_query})
    history.append({"role": "assistant", "content": ai_output.get("spoken_reply", "Done.")})
    if len(history) > 10:
        history = history[-10:]
    family_memory[speaker_name] = history

    return jsonify(ai_output), 200

@app.route("/speak", methods=["POST"])
def sarvam_speak():
    data = request.get_json(silent=True) or {}
    text_to_speak = data.get("text", "")
    if not text_to_speak or not SARVAM_API_KEY:
        return jsonify({"error": "Missing text or key"}), 400

    payload = {
        "inputs": [text_to_speak],
        "target_language_code": "ta-IN",
        "speaker": "vijay_ta_narration",
        "speech_sample_rate": 16000,
        "enable_preprocessing": True,
        "model": "bulbul:v4-flash"
    }
    headers = {"api-subscription-key": SARVAM_API_KEY, "Content-Type": "application/json"}
    
    try:
        response = requests.post("https://api.sarvam.ai/text-to-speech", json=payload, headers=headers)
        audio_base64 = response.json()["audios"][0]
        return send_file(
            io.BytesIO(base64.b64decode(audio_base64)),
            mimetype="audio/wav",
            as_attachment=False,
            download_name="rizzie_voice.wav"
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
