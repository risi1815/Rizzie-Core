import os
import json
import requests
from flask import Flask, request, jsonify
from groq import Groq
from google import genai
from google.genai import types
from supabase import create_client

app = Flask(__name__)

# Load Environment Variables from Render
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
FAMILY_SECRET_PASSWORD = os.environ.get("FAMILY_SECRET_PASSWORD", "rizzie2026family")

# Initialize AI & Database Clients safely
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "Rizzie Family AI Core is online and running 24/7!",
        "features": ["Groq Router", "Gemini Reasoning", "Sarvam Tamil Voice", "Supabase Family Vault"]
    }), 200

@app.route("/rizzie", methods=["POST"])
def rizzie_handler():
    data = request.json or {}
    
    # Security Check: Ensure family password matches via JSON body or Header
    auth_password = data.get("password") or request.headers.get("X-Family-Password")
    if auth_password != FAMILY_SECRET_PASSWORD:
        return jsonify({"error": "Unauthorized family member access."}), 403

    user_speaker = data.get("speaker", "Family Member") # e.g., Amma, Akka, Rishikesh
    user_query = data.get("query", "")

    if not user_query:
        return jsonify({"error": "No query provided."}), 400

    # 1. Fetch Family Tree & Context from Supabase Vault
    family_context = "Family vault connected."
    if supabase:
        try:
            res = supabase.table("family_vault").select("*").execute()
            family_context = str(res.data)
        except Exception as e:
            family_context = f"Vault note: {str(e)}"

    # System instruction for Rizzie's personality and rules
    system_prompt = f"""
    You are Rizzie, a warm, loyal personal family companion and assistant for Rishikesh's family in Bengaluru.
    You understand colloquial Tamil, Tanglish ('Pavithra ku call pannu'), and English fluently.
    You know the family tree and context: {family_context}
    
    The person speaking to you right now is: {user_speaker}.
    
    Analyze their request. If it is a direct command requiring an action (like calling someone, opening YouTube, navigating Maps, sending WhatsApp, or Emergency SOS), output a strict JSON response.
    If it is a general question, story, or conversational topic, handle it gracefully.
    
    Return a strict JSON object containing:
    1. 'action': One of ['NONE', 'MAKE_CALL', 'PLAY_YOUTUBE', 'NAVIGATE_MAPS', 'SEND_WHATSAPP', 'EMERGENCY_SOS']
    2. 'target': Name, phone number, or search term if an action is required (otherwise empty string).
    3. 'spoken_reply': A natural, warm reply spoken back in colloquial Tamil/Tanglish or English addressing {user_speaker}.
    """

    try:
        # Try Groq Llama 3.3 first for ultra-fast action routing and response
        if groq_client:
            completion = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_query}
                ],
                response_format={"type": "json_object"}
            )
            ai_output = json.loads(completion.choices[0].message.content)
            return jsonify(ai_output)
            
    except Exception as groq_error:
        # Fallback to Gemini 2.5 Flash if Groq fails or hits a rate limit
        try:
            if gemini_client:
                response = gemini_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=user_query,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        response_mime_type="application/json"
                    )
                )
                ai_output = json.loads(response.text)
                return jsonify(ai_output)
        except Exception as gemini_error:
            return jsonify({
                "action": "NONE", 
                "spoken_reply": f"Sorry, both of my AI brains encountered an error."
            }), 500

    return jsonify({"action": "NONE", "spoken_reply": "No AI clients configured."}), 500

# Dedicated Sarvam AI Text-to-Speech Endpoint for Rizzie's Tamil Voice
@app.route("/speak", methods=["POST"])
def sarvam_speak():
    data = request.json or {}
    text_to_speak = data.get("text", "")
    
    if not SARVAM_API_KEY:
        return jsonify({"error": "Sarvam API Key not configured."}), 500
        
    url = "https://api.sarvam.ai/text-to-speech"
    payload = {
        "inputs": [text_to_speak],
        "target_language_code": "ta-IN",  # Tamil
        "speaker": "meera",  # Natural Indian voice profile on Sarvam
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
        return jsonify(response.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)