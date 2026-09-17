"""The `speak` tool - ORBIT's proper way to reply out loud."""

from . import tool
from ..voice import synthesize_sync


@tool(
    "speak",
    "Send the owner a spoken VOICE message (an audio note that plays in Discord). Use this "
    "whenever they ask you to answer in voice - 'voice msg', 'in voice', 'bolo', 'awaz mein "
    "batao', 'introduce yourself in voice' - or whenever a voice reply clearly fits. Put the "
    "EXACT words to say in `text`, in the owner's language. This is the ONLY correct way to "
    "speak - NEVER use run_powershell or any other tool to make audio. It is fast; keep the "
    "words natural and conversational, like a real person talking. IMPORTANT for Urdu: write "
    "the words in URDU SCRIPT (not Roman/English letters) and set language='ur', so it sounds "
    "like a real Urdu speaker. Still send a short text version of your answer too.",
    {
        "text": {
            "type": "string",
            "description": "Exactly what to say aloud, in the owner's language. Urdu -> Urdu script. "
                           "Speak like a real person, not a news reader: use natural fillers where "
                           "they fit (hmm, umm, achha, ok, arre, theek hai) and contractions. "
                           "You may add emotion cues in square brackets and they will be performed: "
                           "[warmly], [laughs], [sighs], [excited], [thoughtful], [reassuring], "
                           "[whispers]. Use one or two, only where a person would naturally do it - "
                           "do not tag every sentence.",
        },
        "language": {
            "type": "string",
            "enum": ["auto", "en", "ur"],
            "description": "Voice language. 'ur' = Urdu female voice, 'en' = English female voice, "
                           "'auto' = detect. Default auto.",
        },
    },
    required=["text"],
)
def speak(text, language="auto"):
    lang = "" if not language or language == "auto" else language
    mp3 = synthesize_sync(text, lang)
    if not mp3:
        return {"text": "(voice generation failed - answering in text instead)"}
    return {"text": "(voice message sent)", "files": [mp3], "captions": ["🔊"]}
