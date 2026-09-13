"""
Vocalize — a small text-to-speech studio.

Uses edge-tts (Microsoft Edge's free neural TTS service) so no API key is
required, while still getting a real choice of male / female neural voices
per language, plus rate and pitch control. Requires an internet connection
at runtime, since edge-tts calls out to Microsoft's service.
"""
import asyncio
import os
import uuid
from datetime import datetime

import edge_tts
from flask import Flask, render_template, request, jsonify, send_from_directory, abort

APP_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(APP_DIR, "static", "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

MAX_CHARS = 3000
AUDIO_SPEC = "MP3 · 48 kbps · 24 kHz"

# Curated fallback voices — used if the live catalog can't be fetched (e.g. no
# internet yet). Covers common languages with a Male and Female neural voice
# each, which is exactly the male/female choice the UI needs either way.
FALLBACK_VOICES = [
    {"ShortName": "en-US-GuyNeural", "Gender": "Male", "Locale": "en-US", "Language": "English (US)"},
    {"ShortName": "en-US-JennyNeural", "Gender": "Female", "Locale": "en-US", "Language": "English (US)"},
    {"ShortName": "en-US-DavisNeural", "Gender": "Male", "Locale": "en-US", "Language": "English (US)"},
    {"ShortName": "en-US-AriaNeural", "Gender": "Female", "Locale": "en-US", "Language": "English (US)"},
    {"ShortName": "en-GB-RyanNeural", "Gender": "Male", "Locale": "en-GB", "Language": "English (UK)"},
    {"ShortName": "en-GB-SoniaNeural", "Gender": "Female", "Locale": "en-GB", "Language": "English (UK)"},
    {"ShortName": "en-AU-WilliamNeural", "Gender": "Male", "Locale": "en-AU", "Language": "English (Australia)"},
    {"ShortName": "en-AU-NatashaNeural", "Gender": "Female", "Locale": "en-AU", "Language": "English (Australia)"},
    {"ShortName": "en-IN-PrabhatNeural", "Gender": "Male", "Locale": "en-IN", "Language": "English (India)"},
    {"ShortName": "en-IN-NeerjaNeural", "Gender": "Female", "Locale": "en-IN", "Language": "English (India)"},
    {"ShortName": "es-ES-AlvaroNeural", "Gender": "Male", "Locale": "es-ES", "Language": "Spanish (Spain)"},
    {"ShortName": "es-ES-ElviraNeural", "Gender": "Female", "Locale": "es-ES", "Language": "Spanish (Spain)"},
    {"ShortName": "es-MX-JorgeNeural", "Gender": "Male", "Locale": "es-MX", "Language": "Spanish (Mexico)"},
    {"ShortName": "es-MX-DaliaNeural", "Gender": "Female", "Locale": "es-MX", "Language": "Spanish (Mexico)"},
    {"ShortName": "fr-FR-HenriNeural", "Gender": "Male", "Locale": "fr-FR", "Language": "French"},
    {"ShortName": "fr-FR-DeniseNeural", "Gender": "Female", "Locale": "fr-FR", "Language": "French"},
    {"ShortName": "de-DE-ConradNeural", "Gender": "Male", "Locale": "de-DE", "Language": "German"},
    {"ShortName": "de-DE-KatjaNeural", "Gender": "Female", "Locale": "de-DE", "Language": "German"},
    {"ShortName": "it-IT-DiegoNeural", "Gender": "Male", "Locale": "it-IT", "Language": "Italian"},
    {"ShortName": "it-IT-ElsaNeural", "Gender": "Female", "Locale": "it-IT", "Language": "Italian"},
    {"ShortName": "pt-BR-AntonioNeural", "Gender": "Male", "Locale": "pt-BR", "Language": "Portuguese (Brazil)"},
    {"ShortName": "pt-BR-FranciscaNeural", "Gender": "Female", "Locale": "pt-BR", "Language": "Portuguese (Brazil)"},
    {"ShortName": "ja-JP-KeitaNeural", "Gender": "Male", "Locale": "ja-JP", "Language": "Japanese"},
    {"ShortName": "ja-JP-NanamiNeural", "Gender": "Female", "Locale": "ja-JP", "Language": "Japanese"},
    {"ShortName": "ko-KR-InJoonNeural", "Gender": "Male", "Locale": "ko-KR", "Language": "Korean"},
    {"ShortName": "ko-KR-SunHiNeural", "Gender": "Female", "Locale": "ko-KR", "Language": "Korean"},
    {"ShortName": "zh-CN-YunxiNeural", "Gender": "Male", "Locale": "zh-CN", "Language": "Chinese (Mandarin)"},
    {"ShortName": "zh-CN-XiaoxiaoNeural", "Gender": "Female", "Locale": "zh-CN", "Language": "Chinese (Mandarin)"},
    {"ShortName": "hi-IN-MadhurNeural", "Gender": "Male", "Locale": "hi-IN", "Language": "Hindi"},
    {"ShortName": "hi-IN-SwaraNeural", "Gender": "Female", "Locale": "hi-IN", "Language": "Hindi"},
    {"ShortName": "ar-SA-HamedNeural", "Gender": "Male", "Locale": "ar-SA", "Language": "Arabic"},
    {"ShortName": "ar-SA-ZariyahNeural", "Gender": "Female", "Locale": "ar-SA", "Language": "Arabic"},
    {"ShortName": "ru-RU-DmitryNeural", "Gender": "Male", "Locale": "ru-RU", "Language": "Russian"},
    {"ShortName": "ru-RU-SvetlanaNeural", "Gender": "Female", "Locale": "ru-RU", "Language": "Russian"},
    {"ShortName": "tr-TR-AhmetNeural", "Gender": "Male", "Locale": "tr-TR", "Language": "Turkish"},
    {"ShortName": "tr-TR-EmelNeural", "Gender": "Female", "Locale": "tr-TR", "Language": "Turkish"},
    {"ShortName": "nl-NL-MaartenNeural", "Gender": "Male", "Locale": "nl-NL", "Language": "Dutch"},
    {"ShortName": "nl-NL-ColetteNeural", "Gender": "Female", "Locale": "nl-NL", "Language": "Dutch"},
    {"ShortName": "pl-PL-MarekNeural", "Gender": "Male", "Locale": "pl-PL", "Language": "Polish"},
    {"ShortName": "pl-PL-ZofiaNeural", "Gender": "Female", "Locale": "pl-PL", "Language": "Polish"},
]

# Pacing presets shown as quick-select buttons in the UI.
PACING_PRESETS = [
    {"value": "-15%", "label": "0.85x"},
    {"value": "+0%", "label": "1.0x", "default": True},
    {"value": "+10%", "label": "1.1x"},
    {"value": "+25%", "label": "1.25x"},
]

# Pitch presets — subtle shifts so voices stay natural.
PITCH_PRESETS = [
    {"value": "-15Hz", "label": "Low"},
    {"value": "+0Hz", "label": "Normal", "default": True},
    {"value": "+15Hz", "label": "High"},
]

_voice_cache = None


def get_voices():
    """Return the voice catalog, live-fetched once and cached, falling back
    to the curated list if edge-tts can't reach the network."""
    global _voice_cache
    if _voice_cache is not None:
        return _voice_cache
    try:
        raw = asyncio.run(asyncio.wait_for(edge_tts.list_voices(), timeout=6))
        voices = []
        for v in raw:
            if not v["ShortName"].endswith("Neural"):
                continue
            locale = v["Locale"]
            lang_name = v.get("FriendlyName", locale).split(" - ")[0].replace("Microsoft ", "")
            voices.append({
                "ShortName": v["ShortName"],
                "Gender": v["Gender"],
                "Locale": locale,
                "Language": lang_name,
            })
        _voice_cache = voices if voices else FALLBACK_VOICES
    except Exception:
        _voice_cache = FALLBACK_VOICES
    return _voice_cache


history = []

app = Flask(__name__)


@app.route("/")
def index():
    voices = get_voices()
    return render_template(
        "index.html",
        voices=voices,
        pacing_presets=PACING_PRESETS,
        pitch_presets=PITCH_PRESETS,
        max_chars=MAX_CHARS,
        audio_spec=AUDIO_SPEC,
    )


@app.route("/api/generate", methods=["POST"])
def generate():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    voice = (data.get("voice") or "en-US-JennyNeural").strip()
    rate = (data.get("rate") or "+0%").strip()
    pitch = (data.get("pitch") or "+0Hz").strip()

    if not text:
        return jsonify({"error": "Type or paste some text first."}), 400
    if len(text) > MAX_CHARS:
        return jsonify({"error": f"That's {len(text)} characters — keep it under {MAX_CHARS}."}), 400

    known = {v["ShortName"] for v in get_voices()} | {v["ShortName"] for v in FALLBACK_VOICES}
    if voice not in known:
        return jsonify({"error": "Unknown voice."}), 400

    filename = f"{uuid.uuid4().hex}.mp3"
    filepath = os.path.join(AUDIO_DIR, filename)

    async def synthesize():
        communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
        await communicate.save(filepath)

    try:
        asyncio.run(synthesize())
    except Exception as exc:
        return jsonify({"error": f"Couldn't generate audio: {exc}"}), 502

    voice_meta = next((v for v in get_voices() if v["ShortName"] == voice), None) or {}

    entry = {
        "id": filename,
        "text": text,
        "preview": text if len(text) <= 80 else text[:77] + "...",
        "voice": voice,
        "voice_label": voice.split("-")[-1].replace("Neural", ""),
        "gender": voice_meta.get("Gender", ""),
        "language": voice_meta.get("Language", ""),
        "rate": rate,
        "pitch": pitch,
        "url": f"/audio/{filename}",
        "created_at": datetime.now().strftime("%H:%M:%S"),
        "chars": len(text),
    }
    history.insert(0, entry)
    del history[50:]

    return jsonify({"ok": True, "entry": entry})


@app.route("/api/history")
def get_history():
    return jsonify({"history": history})


@app.route("/api/history/<entry_id>", methods=["DELETE"])
def delete_history_entry(entry_id):
    global history
    match = next((e for e in history if e["id"] == entry_id), None)
    if not match:
        return jsonify({"error": "Not found"}), 404
    history = [e for e in history if e["id"] != entry_id]
    filepath = os.path.join(AUDIO_DIR, entry_id)
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except OSError:
            pass
    return jsonify({"ok": True})


@app.route("/audio/<path:filename>")
def serve_audio(filename):
    if "/" in filename or "\\" in filename:
        abort(400)
    return send_from_directory(AUDIO_DIR, filename)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
