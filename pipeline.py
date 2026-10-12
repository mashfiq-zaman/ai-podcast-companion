from __future__ import annotations
import json
import os , argparse, time
import difflib, re
from dotenv import load_dotenv
from langchain_core.globals import set_llm_cache
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableParallel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

load_dotenv()

gemini_model='models/gemini-3.5-flash-lite'  ## 500 req/day on free
groq_model='llama-3.3-70b-versatile'    ##fallback backup
 
timeout_seconds=60
max_chars=120_000
min_chars=200

## this is only for development as im using free API,cant waste it

if os.environ.get('CACHE_LLM','').lower()=='true':
    from langchain_community.cache import SQLiteCache
    set_llm_cache(SQLiteCache(database_path='.llm_cache.db'))  
    print('[cache on - repeated calls will not hit API]')

##schemas
class summary(BaseModel):
    overview : str= Field(description='2-3 sentence overview of the episode')

    themes: list[str]=Field(description='3-5 main themes discussed')
    takeaways: list[str]= Field(description='2-3 specefic, valid takesaways')

class chapter(BaseModel):
       title: str = Field(description='short descriptive and creative title,3-8 words')
       description: str = Field(description='one or two sentences on what is covered')

       opening_line:str =Field(description='The first few words of this section, copied exactly from the transcript')

class chapters(BaseModel):
    chapters: list[chapter]
 
 
class quizquestion(BaseModel):
    question: str
    options: list[str] = Field(description="Exactly 4 options")
    answer: str = Field(description="The correct option, copied exactly from options")
    evidence: str = Field(
        description="The transcript sentence that supports the answer, quoted exactly"
    )
 
 
class quiz(BaseModel):
    questions: list[quizquestion]   



##models

def build_gemini():
     '''the main model'''
     api_key=os.environ.get('GOOGLE_API_KEY')
     
     if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not set")
 
     return ChatGoogleGenerativeAI(
        model=gemini_model,
        google_api_key=api_key,
        timeout=timeout_seconds,
    )


def build_groq():
    """The fallback model. Returns None if no Groq key is configured."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None
 
    return ChatGroq(
        model=groq_model,
        api_key=api_key,
        timeout=timeout_seconds,
    )


def build_resilient_model(schema):
    '''build a model that returns schema, retries on failure and falls back
    written as separate step rather than one long chain so each line can be read'''

    gemini=build_gemini().with_structured_output(schema)

    gemini=gemini.with_retry(stop_after_attempt=3)  ##retry transient failures

    groq=build_groq()
    if groq is not None:
        backup=groq.with_structured_output(schema).with_retry(stop_after_attempt=2)
        gemini=gemini.with_fallbacks([backup])

    return gemini

##prompt
grounding = (
    "You are analysing a podcast transcript.\n"
    "Use ONLY what is in the transcript. Do not add outside knowledge and do "
    "not infer facts that are not stated. If the transcript does not contain "
    "enough material for part of your answer, say so in that field rather "
    "than inventing content."
)
 
summary_prompt = """Produce an episode overview of this transcript.
 
The overview should tell someone who has not listened what the episode is
about. Themes are the subjects discussed. Takeaways are specific points a
listener would want to remember, not generic advice.
 
TRANSCRIPT:
{transcript}"""
 
chapters_prompt = """Divide this transcript into about {count} chapters.
 
Split where the topic actually changes, not at even intervals. Each title
should say what that section is specifically about — avoid generic titles
like "Introduction" or "Discussion". For opening_line, copy the first eight to twelve words of the section exactly as they appear in the transcript, character for character. Do not tidy the wording, fix grammar, or change punctuation..If the speakers work through a numbered list or a series of distinct points, give each point its own chapter rather than grouping them.
 
TRANSCRIPT:
{transcript}"""
 
quiz_prompt = """Write {count} multiple-choice comprehension questions about
this transcript, at {difficulty} difficulty.
 
Every question must be answerable from the transcript alone. The three wrong
options should be plausible but clearly wrong to someone who listened. For evidence, copy the sentence from the transcript that makes the correct answer correct, character for character. Do not tidy the wording, fix grammar, or change pronouns. If you cannot find such a sentence, do not ask that question.. If you cannot find one, do not ask that question.Wrong options must be clearly distinct from the correct answer — not near-duplicates or partial versions of it.
 
TRANSCRIPT:
{transcript}"""
 
revise_prompt= """Here is a {kind} generated from the transcript below, and a
change the user has asked for.
 
Apply the requested change. Keep everything the user did not ask you to
change. Stay grounded in the transcript.
 
CURRENT {kind_upper}:
{current}
 
REQUESTED CHANGE: {instruction}
 
TRANSCRIPT:
{transcript}"""


def build_chain(schema, human_prompt: str):
    '''prompt -> model->validated object'''

    prompt=ChatPromptTemplate.from_messages([
        ('system',grounding),
        ('human', human_prompt)
    ])

    return prompt | build_resilient_model(schema)


##input validation

TIMESTAMP_LINE = re.compile(r"^\d{1,3}:\d{2}(:\d{2})?$")


def parse_transcript(raw):
    """Split a YouTube-style transcript into timed chunks.

    A line that is only a time marker starts a new chunk.
    Everything after it, until the next marker, is that chunk's text.
    """
    segments = []
    current_time = None
    current_text = []

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue

        if TIMESTAMP_LINE.match(line):
            if current_time and current_text:
                segments.append({"label": current_time,
                                 "text": " ".join(current_text)})
            current_time = line
            current_text = []
        else:
            current_text.append(line)

    if current_time and current_text:                      # the last chunk
        segments.append({"label": current_time, "text": " ".join(current_text)})

    if not segments:                                        # no timestamps at all
        return " ".join(raw.split()), []

    # stitch the text back together, noting where each chunk starts
    text = ""
    for segment in segments:
        segment["start_char"] = len(text)
        text += segment["text"] + " "

    return text.strip(), segments

def validate_transcript(raw):
    """Parse, clean and length-check. Returns (clean_text, segments)."""
    text, segments = parse_transcript(raw or "")

    if len(text) < min_chars:
        raise ValueError(
            f"Transcript is too short ({len(text)} characters). "
            f"At least {min_chars} are needed."
        )

    if len(text) > max_chars:
        raise ValueError(
            f"Transcript is too long ({len(text):,} characters). "
            f"The current limit is {max_chars:,}."
        )

    return text, segments


def time_for_position(position, segments):
    """The time label of the chunk containing this character position."""
    found = None
    for segment in segments:
        if segment["start_char"] <= position:
            found = segment["label"]
        else:
            break
    return found


def chapter_times(chapters, text, segments):
    """Work out a start time for each chapter. Nothing is invented —
    a chapter whose opening line can't be found gets None."""
    if not segments:
        return [None] * len(chapters.chapters)

    haystack = text.lower()
    times = []

    for chapter in chapters.chapters:
        needle = chapter.opening_line.lower().strip()[:40]
        position = haystack.find(needle) if needle else -1
        times.append(time_for_position(position, segments) if position >= 0 else None)

    return times


##generators


def generate_summary(transcript: str)-> summary:
    chain=build_chain(summary, summary_prompt)
    return chain.invoke({'transcript': transcript})

def generate_chapters(transcript: str, count: int=6)-> chapters:
    chain = build_chain(chapters,chapters_prompt)
    return chain.invoke({"transcript": transcript, "count": count})

def generate_quiz(transcript: str, count: int = 5, difficulty: str = "moderate") -> quiz:
    chain = build_chain(quiz, quiz_prompt)
    return chain.invoke({
        "transcript": transcript,
        "count": count,
        "difficulty": difficulty,
    })

def generate_all(transcript: str) -> dict:
    """Run all three at once instead of one after another.
    RunnableParallel starts the three chains together, so the total time is
    roughly the slowest one rather than the sum of all three.
    """
    everything = RunnableParallel(
        summary=build_chain(summary, summary_prompt),
        chapters=build_chain(chapters, chapters_prompt),
        quiz=build_chain(quiz,  quiz_prompt),
    )
 
    return everything.invoke({
        "transcript": transcript,
        "count": 6,          # chapters
        "difficulty": "moderate",
    })

schemas={'summary':summary, 'chapters':chapter, 'quiz':quiz}

def revise(kind: str, transcript: str, current, instruction: str):
    if kind not in schemas:
        raise ValueError(f"Unknown artifact '{kind}'. Expected one of {list(schemas)}.")
 
    chain = build_chain(schemas[kind],revise_prompt)
 
    return chain.invoke({
        "transcript": transcript,
        "kind": kind,
        "kind_upper": kind.upper(),
        "current": current.model_dump_json(indent=2),
        "instruction": instruction,
    })

def print_summary(s: summary) -> None:
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"\n{s.overview}\n")
 
    print("Themes:")
    for theme in s.themes:
        print(f"  - {theme}")
 
    print("\nTakeaways:")
    for takeaway in s.takeaways:
        print(f"  - {takeaway}")
 
 
def print_chapters(c: chapters, times=None) -> None:
    print("\n" + "=" * 70)
    print("CHAPTERS")
    print("=" * 70)

    times = times or [None] * len(c.chapters)

    for number, (chapter, label) in enumerate(zip(c.chapters, times), start=1):
        stamp = f"[{label}] " if label else ""
        print(f"\n{number}. {stamp}{chapter.title}")
        print(f"   {chapter.description}")
        print(f'   opens: "{chapter.opening_line[:60]}..."')
 
 
def print_quiz(q: quiz) -> None:
    print("\n" + "=" * 70)
    print("QUIZ")
    print("=" * 70)
 
    for number, item in enumerate(q.questions, start=1):
        print(f"\nQ{number}. {item.question}")
        for option in item.options:
            mark = "*" if option == item.answer else " "
            print(f"   {mark} {option}")
        print(f'   evidence: "{item.evidence[:80]}..."')

# Checking the model stayed grounded

 
import re   # at the top with the other imports


def _normalise(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    text = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    return " ".join(text.split())


def check_grounding(transcript: str, chapters: chapters, quiz: quiz) -> None:
    haystack = _normalise(transcript)
    problems = []

    for chapter in chapters.chapters:
        needle = _normalise(chapter.opening_line)[:40]
        if needle and needle not in haystack:
            problems.append(f"chapter opening not found: {chapter.title}")

    for item in quiz.questions:
        needle = _normalise(item.evidence)[:40]
        if needle and needle not in haystack:
          if needle and needle not in haystack:
            problems.append(f"evidence not found: {item.question[:50]}")

    print("\n" + "=" * 70)
    print("GROUNDING CHECK")
    print("=" * 70)

    if problems:
        print(f"\n{len(problems)} quote(s) not found in the transcript:")
        for problem in problems:
            print(f"  ! {problem}")
    else:
        print("\nAll quoted material was found in the transcript.")


# CLI
# --------------------
 
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("transcript_file")
    parser.add_argument("--only", choices=["summary", "chapters", "quiz"])
    parser.add_argument("--parallel", action="store_true",
                        help="run all three at once")
    args = parser.parse_args()
 
    with open(args.transcript_file, encoding="utf-8") as f:
              transcript, segments = validate_transcript(f.read())
 
    print(f"Transcript: {len(transcript):,} characters")
    if segments:
        print(f"Timestamps: {len(segments)} markers "
              f"({segments[0]['label']} to {segments[-1]['label']})")
    else:
        print("Timestamps: none found - chapters will have no times")
 
    if args.parallel:
        started = time.perf_counter()
        results = generate_all(transcript)
        print(f"[all three in {time.perf_counter() - started:.1f}s]")

        print_summary(results["summary"])
        print_chapters(results["chapters"],
                       chapter_times(results["chapters"], transcript, segments))
        print_quiz(results["quiz"])
        check_grounding(transcript, results["chapters"], results["quiz"])
        return

    jobs = [
        ("summary", generate_summary, print_summary),
        ("chapters", generate_chapters, print_chapters),
        ("quiz", generate_quiz, print_quiz),
    ]
    if args.only:
        jobs = [job for job in jobs if job[0] == args.only]

    for name, generate, show in jobs:
        started = time.perf_counter()
        result = generate(transcript)
        print(f"\n[{name}: {time.perf_counter() - started:.1f}s]")
        if name == "chapters":
            show(result, chapter_times(result, transcript, segments))
        else:
            show(result)
 
 
if __name__ == "__main__":
    main()