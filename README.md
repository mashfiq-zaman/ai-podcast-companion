https://ai-podcast-companion-7qnzsveizrryperdgz9ypk.streamlit.app/


AI Podcast Companion

Paste a podcast transcript and get back an episode summary, a set of chapters, and a quiz you can actually take. Any one of the three can be revised on its own without regenerating the other two.

Built for the Thealon Animation Studios AI Engineering Challenge, October 2026.

Live app: (paste your Streamlit URL here)

Engineering notes: ENGINEERING_NOTES.md — tool comparison, architecture, debugging, reliability, cost, and next steps.

What it does

Summary — a short overview of the episode, the main themes, and specific takeaways.

Chapters — the episode split where the topic actually changes, each with a title and a description. If the transcript has time markers, each chapter also gets a start time.

Quiz — multiple-choice comprehension questions with answers, and the transcript sentence each answer came from.

Revision — ask for a change to any one of those three ("make the quiz harder", "shorter summary") and only that section is regenerated.

Export — download everything as Markdown or JSON.

What it accepts

Plain text transcripts between 200 and 120,000 characters, roughly 2 to 200 minutes of speech.

Timestamps are supported when the transcript carries time markers on their own lines, which is the format YouTube's transcript panel produces:

0:00
English Leap Podcast
0:02
Welcome back to the show.

Those markers are stripped before anything reaches the model and kept in a separate index. Chapter times are then derived from where each chapter's quoted opening line falls in the text. The model is never asked to produce a timestamp, so a wrong one is not possible — only a missing one.

A transcript without markers still works. Chapters are listed in order with no times, and the app says so rather than inventing them.

Audio upload is not supported. The reasoning is in the engineering notes.

Running it locally
bash
git clone https://github.com/mashfiq-zaman/ai-podcast-companion.git
cd ai-podcast-companion

python -m venv myvenv
myvenv\Scripts\activate          # Windows
# source myvenv/bin/activate     # macOS / Linux

pip install -r requirements.txt

copy .env.example .env           # Windows
# cp .env.example .env           # macOS / Linux

Open .env and add your keys, then:

bash
streamlit run app.py
Running the pipeline without the UI

pipeline.py works on its own, which is how the prompts were developed:

bash
python pipeline.py sample_transcript.txt --parallel
python pipeline.py sample_transcript.txt --only quiz

It prints the summary, chapters and quiz, plus a grounding check that verifies every quoted fragment actually appears in the transcript.

Configuration
Variable	Required	What it does
GOOGLE_API_KEY	yes	Gemini, the primary model
GROQ_API_KEY	no	fallback provider; without it the app runs on Gemini alone
CACHE_LLM	no	true caches identical calls to a local file. Development only

Get a Gemini key at https://aistudio.google.com/apikey and a Groq key at https://console.groq.com/keys. Both have free tiers and neither needs a card.

Locally these come from .env. In deployment they come from Streamlit Cloud's secrets manager. .env is gitignored and no key is in the repository.

Leave CACHE_LLM unset in deployment. With it on, clicking Generate twice on the same transcript returns the identical cached result, which looks like a broken button.

Project layout
app.py              Streamlit interface: input, state, display
pipeline.py         All generation. No Streamlit imports, runnable alone
requirements.txt
.env.example

Two files by design. pipeline.py has no idea the UI exists, which is why it could be built and tested from the terminal before any interface existed.

Known limitations
Chapter times depend on the transcript carrying time markers.
On a 22-minute test episode, six chapters covered 2:00 to 13:15 and left the last eight minutes uncovered. Raising the chapter count helps but does not guarantee full coverage.
Output quality is bounded by transcript quality. Auto-generated captions contain transcription errors, and the model reproduces them faithfully.
Nothing is stored. Refreshing the page loses the results.
Prompts and output are English only.
Transcripts over 120,000 characters are rejected rather than chunked.
