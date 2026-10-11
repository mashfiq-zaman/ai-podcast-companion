import os
import time

import streamlit as st

st.set_page_config(page_title='Podcast Companion',page_icon="🎧")

st.title("🎧 AI Podcast Companion")
st.caption('deployment check')



def get_api_key() ->str | None :
    '''Read the key from Streamlit secrets first, then the local environment.
    On Streamlit Cloud the key lives in the secrets manager. Locally it comes
    from .env. Neither path puts it in the repository.'''

    try:
        key=st.secrets.get('GOOGLE_API_KEY')
        if key :
            return key
    except Exception:
        pass

    from dotenv import load_dotenv
    load_dotenv()
    return os.environ.get('GOOGLE_API_KEY')

MODEL_NAME = "models/gemini-3.5-flash-lite"
 
api_key = get_api_key()
 
col1, col2 = st.columns(2)
col1.metric("API key configured", "yes" if api_key else "NO")
col2.metric("Model", MODEL_NAME.split("/")[-1])
 
if not api_key:
    st.error(
        "GOOGLE_API_KEY not found.\n\n"
        "Locally: add it to a `.env` file.\n"
        "On Streamlit Cloud: add it under Settings → Secrets."
    )
    st.stop()
 
st.divider()
st.write("Click below to make one real API call and confirm the key works.")
 
if st.button("Run test call", type="primary"):
    with st.spinner("Calling Gemini…"):
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
 
            model = ChatGoogleGenerativeAI(
                model=MODEL_NAME,
                google_api_key=api_key,
                timeout=30,
            )
 
            started = time.perf_counter()
            response = model.invoke("Reply with exactly: OK")
            elapsed = time.perf_counter() - started
 
            # Gemini can return content as blocks rather than a plain string
            content = response.content
            if isinstance(content, list):
                content = "".join(
                    b.get("text", "")
                    for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                )
 
            st.success(f"Call succeeded in {elapsed:.2f}s")
            st.code(content.strip() or "(empty response)")
 
        except Exception as exc:
            st.error(f"{type(exc).__name__}: {exc}")
            st.info(
                "429 means the daily quota is gone — check which model the key "
                "is actually hitting at https://ai.dev/rate-limit"
            )
 
st.divider()
st.caption(
    "Supported input (from Phase 1): plain text transcripts. "
    "Audio upload is out of scope — see README for the reasoning."
)

