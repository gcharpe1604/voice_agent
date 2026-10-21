import io
import streamlit as st
from google import genai
from google.genai import types

MODEL = "gemini-3.5-flash-lite"
VOICE = "JBFqnCBsd6RMkjVDRZzb"  # ElevenLabs 'George', on every free account
MAX_TURNS = 20  # each turn spends YOUR credits, and anyone with the link can talk to it

st.set_page_config(page_title="My voice agent", page_icon="🎙️")


def secret(name):
    """A key from Streamlit's Secrets box (never from the code), or None if it isn't there."""
    try:
        return st.secrets.get(name)
    except Exception:  # no Secrets at all
        return None


if not secret("GEMINI_API_KEY"):
    st.error("No GEMINI_API_KEY in this app's Secrets. On share.streamlit.io: your app → ⋮ → Settings → Secrets.")
    st.stop()


@st.cache_resource  # one Gemini client, created once, not on every click
def gemini():
    return genai.Client(api_key=secret("GEMINI_API_KEY"))


gem = gemini()

# Streamlit re-runs this whole file on every click. st.session_state is what survives, per visitor.
for key, start in {
    "todos": [],
    "history": [],
    "log": [],
    "turn": 0,
    "reply_audio": None
}.items():
    if key not in st.session_state:
        st.session_state[key] = start

TODOS = st.session_state.todos  # your tools read and change this list


# ==================== PASTE FROM COLAB: START ====================

# COPY THIS (1 of 2): who the agent is

AGENT_NAME = "Pip"

SYSTEM_PROMPT = """You are Pip, a voice to-do assistant for a busy student.
Everything you say is read aloud, so: one or two short sentences, no lists, no markdown, no emojis.
Use your tools to add, read and finish to-dos. Never say you did something unless a tool did it.
If the user asks for something none of your tools can do, say so plainly and do nothing."""


# COPY THIS (2 of 2): what the agent can do

def add_todo(task: str) -> str:
    """Add a task to the user's to-do list."""
    TODOS.append({"task": task, "done": False})
    return f"Added: {task}. The list has {len(TODOS)} items."


def list_todos() -> str:
    """Read the user's to-do list: each item's number, the task, and whether it is done."""
    if not TODOS:
        return "The list is empty."

    return "\n".join(
        f"{i + 1}. {t['task']} ({'done' if t['done'] else 'open'})"
        for i, t in enumerate(TODOS)
    )


def mark_done(number: int) -> str:
    """Mark a to-do as done, by its number in the list (the first item is 1)."""
    if not 1 <= number <= len(TODOS):
        return f"There is no item {number}. The list has {len(TODOS)} items."

    TODOS[number - 1]["done"] = True
    return f"Done: {TODOS[number - 1]['task']}."


TOOLS = [add_todo, list_todos, mark_done]

# ==================== PASTE FROM COLAB: END ====================


if not all(name in globals() for name in ["SYSTEM_PROMPT", "TOOLS"]):
    st.error("Nothing pasted yet (or not all of it). Paste the two COPY THIS cells from Colab into app.py.")
    st.stop()


def hear(audio_bytes):
    """Ears: Gemini listens to the recording and writes down the words."""
    r = gem.models.generate_content(
        model=MODEL,
        contents=[
            types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"),
            "Transcribe this audio exactly. Output only the words. If nobody speaks, output nothing."
        ]
    )
    return (r.text or "").strip()


def think(text):
    """Brain: Gemini with your prompt, your tools and the conversation so far."""
    chat = gem.chats.create(
        model=MODEL,
        history=st.session_state.history,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=TOOLS,
            max_output_tokens=300
        )
    )

    reply = chat.send_message(text).text or "Sorry, I didn't catch that."
    new = chat.get_history()[len(st.session_state.history):]
    st.session_state.history = chat.get_history()

    used = [
        f"{p.function_call.name}({', '.join(f'{k}={v!r}' for k, v in (p.function_call.args or {}).items())})"
        for c in new
        for p in (c.parts or [])
        if p.function_call
    ]

    return reply, used
  
def speak(text):
    """Mouth: ElevenLabs if you added its key in Secrets, otherwise the free gTTS voice."""
    if secret("ELEVEN_API_KEY"):
        try:
            from elevenlabs.client import ElevenLabs
            eleven = ElevenLabs(api_key=secret("ELEVEN_API_KEY"))
            return b"".join(
                eleven.text_to_speech.convert(
                    voice_id=VOICE,
                    text=text,
                    model_id="eleven_flash_v2_5"
                )
            )
        except Exception:
            st.toast("ElevenLabs didn't answer (out of credits?). Using the free voice.")

    from gtts import gTTS
    buf = io.BytesIO()
    gTTS(text).write_to_fp(buf)
    return buf.getvalue()

# ========================= the page =========================

st.title("🎙️ " + globals().get("AGENT_NAME", "My voice agent"))
st.caption("Tap the mic, speak, tap again to stop. Or type at the bottom.")

with st.sidebar:
    st.subheader("To-do list")

    if not TODOS:
        st.caption("Empty")

    for t in TODOS:
        st.markdown(
            f"✅ ~~{t['task']}~~" if t["done"] else f"⬜ {t['task']}"
        )

    st.caption(f"Turns used: {st.session_state.turn} of {MAX_TURNS}")

    if st.button("Start over"):
        for key in ["todos", "history", "log", "turn", "reply_audio"]:
            del st.session_state[key]
        st.rerun()


for who, text, used in st.session_state.log:
    with st.chat_message("user" if who == "you" else "assistant"):
        st.write(text)

        for u in used:
            st.caption(f"🔧 {u}")


if st.session_state.reply_audio:  # play the newest reply once
    st.audio(
        st.session_state.reply_audio,
        format="audio/mp3",
        autoplay=True
    )
    st.session_state.reply_audio = None

audio = st.audio_input("Talk to it", key=f"mic{st.session_state.turn}")
typed = st.chat_input("...or type here")

said = None

if audio:
    with st.spinner("Listening..."):
        said = hear(audio.getvalue())

    if not said:
        st.warning("I didn't hear any words. Try again, a little closer to the mic.")

elif typed:
    said = typed

if said:
    if st.session_state.turn >= MAX_TURNS:
        st.warning("This demo has used all its turns. Press Start over in the sidebar.")
        st.stop()

    with st.spinner("Thinking..."):
        reply, used = think(said)

    with st.spinner("Speaking..."):
        st.session_state.reply_audio = speak(reply)

    st.session_state.log += [
        ("you", said, []),
        ("agent", reply, used)
    ]

    st.session_state.turn += 1
    st.rerun()
