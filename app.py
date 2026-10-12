

import json

import streamlit as st

from pipeline import (
   max_chars,
   min_chars,
    chapter_times,
    generate_all,
    validate_transcript,
)

st.set_page_config(page_title="AI Podcast Companion", page_icon="🎧", layout="centered")



# State
# Separate slots per artifact. Each can be replaced on its own, which is what
# makes the revision feature possible without regenerating everything.

for slot in ["transcript", "segments", "summary", "chapters", "quiz"]:
    st.session_state.setdefault(slot, None)

st.session_state.setdefault("quiz_checked", False)


def clear_results() -> None:
    """A new transcript invalidates everything generated from the old one."""
    st.session_state.summary = None
    st.session_state.chapters = None
    st.session_state.quiz = None
    st.session_state.quiz_checked = False


def has_results() -> bool:
    return st.session_state.summary is not None


# Export helpers

def results_as_markdown() -> str:
    summary = st.session_state.summary
    chapters = st.session_state.chapters
    quiz = st.session_state.quiz
    times = chapter_times(chapters, st.session_state.transcript,
                          st.session_state.segments or [])

    lines = ["# Episode companion", "", "## Summary", "", summary.overview, "",
             "### Themes", ""]
    lines += [f"- {theme}" for theme in summary.themes]
    lines += ["", "### Takeaways", ""]
    lines += [f"- {takeaway}" for takeaway in summary.takeaways]

    lines += ["", "## Chapters", ""]
    for number, (chapter, label) in enumerate(zip(chapters.chapters, times), start=1):
        stamp = f"`{label}` " if label else ""
        lines += [f"**{number}. {stamp}{chapter.title}**", "", chapter.description, ""]

    lines += ["## Quiz", ""]
    for number, item in enumerate(quiz.questions, start=1):
        lines += [f"**Q{number}. {item.question}**", ""]
        lines += [f"- {option}" for option in item.options]
        lines += ["", f"Answer: {item.answer}", f'Source: "{item.evidence}"', ""]

    return "\n".join(lines)


def results_as_json() -> str:
    chapters = st.session_state.chapters
    times = chapter_times(chapters, st.session_state.transcript,
                          st.session_state.segments or [])

    return json.dumps(
        {
            "summary": st.session_state.summary.model_dump(),
            "chapters": [
                {**chapter.model_dump(), "start_time": label}
                for chapter, label in zip(chapters.chapters, times)
            ],
            "quiz": st.session_state.quiz.model_dump(),
        },
        indent=2,
    )


# Header and input

st.title("🎧 AI Podcast Companion")
st.caption("Paste a podcast transcript and get a summary, chapters and a quiz.")

with st.expander("What this accepts", expanded=not has_results()):
    st.markdown(
        f"""
        **Input:** plain text transcripts, between {min_chars:,} and
        {max_chars:,} characters (roughly 2 to 200 minutes of speech).

        **Timestamps:** if the transcript carries time markers on their own
        lines, the format YouTube's transcript panel produces, chapter start
        times are derived from them. Without markers, chapters are listed in
        order with no times. Times are never invented.

        Not supported: audio file upload.

        Content is sent to the Gemini API for processing. Use material you have
        permission to share.
        """
    )

transcript_input = st.text_area(
    "Transcript",
    height=200,
    placeholder="Paste the full transcript here…",
    label_visibility="collapsed",
)

characters = len(transcript_input.strip())

left, right = st.columns([3, 1])
with left:
    if characters:
        st.caption(f"{characters:,} characters")
with right:
    generate_clicked = st.button(
        "Generate", type="primary", use_container_width=True,
        disabled=characters == 0,
    )



# Generate


if generate_clicked:
    try:
        transcript, segments = validate_transcript(transcript_input)
    except ValueError as exc:
        st.warning(str(exc))
        st.stop()

    clear_results()

    with st.spinner("Reading the episode…"):
        try:
            results = generate_all(transcript)
        except Exception as exc:
            st.error(
                "The episode could not be processed. "
                "This is usually a temporary API problem — try again in a moment."
            )
            with st.expander("Technical detail"):
                st.code(f"{type(exc).__name__}: {exc}")
            st.stop()

    st.session_state.transcript = transcript
    st.session_state.segments = segments
    st.session_state.summary = results["summary"]
    st.session_state.chapters = results["chapters"]
    st.session_state.quiz = results["quiz"]


# Results


if has_results():
    st.divider()

    if st.session_state.segments:
        st.caption(
            f"{len(st.session_state.segments)} time markers found — "
            f"chapter times derived from the transcript."
        )

    summary_tab, chapters_tab, quiz_tab = st.tabs(["Summary", "Chapters", "Quiz"])

    # ---- Summary
    with summary_tab:
        summary = st.session_state.summary

        st.write(summary.overview)

        st.subheader("Themes")
        for theme in summary.themes:
            st.markdown(f"- {theme}")

        st.subheader("Takeaways")
        for takeaway in summary.takeaways:
            st.markdown(f"- {takeaway}")

    # ---- Chapters
    with chapters_tab:
        chapters = st.session_state.chapters
        times = chapter_times(chapters, st.session_state.transcript,
                              st.session_state.segments or [])

        if not st.session_state.segments:
            st.caption(
                "No time markers in this transcript, so chapters are listed in "
                "order without times."
            )

        for number, (chapter, label) in enumerate(zip(chapters.chapters, times),
                                                  start=1):
            if label:
                st.markdown(f"**{number}. `{label}` {chapter.title}**")
            else:
                st.markdown(f"**{number}. {chapter.title}**")
            st.write(chapter.description)
            st.caption(f'Starts: "{chapter.opening_line}"')
            st.write("")

    # ---- Quiz
    with quiz_tab:
        quiz = st.session_state.quiz

        for number, item in enumerate(quiz.questions, start=1):
            st.markdown(f"**Q{number}. {item.question}**")
            st.radio(
                "Choose an answer",
                item.options,
                index=None,
                key=f"answer_{number}",
                label_visibility="collapsed",
            )

            # Feedback only appears once the user has asked to be marked
            if st.session_state.quiz_checked:
                chosen = st.session_state.get(f"answer_{number}")
                if chosen is None:
                    st.info(f"Not answered. Correct answer: {item.answer}")
                elif chosen == item.answer:
                    st.success("Correct")
                else:
                    st.error(f"Not quite. Correct answer: {item.answer}")

                with st.expander("Where this comes from"):
                    st.caption(f'"{item.evidence}"')

            st.write("")

        check, reset = st.columns(2)
        with check:
            if st.button("Check answers", use_container_width=True):
                st.session_state.quiz_checked = True
                st.rerun()
        with reset:
            if st.button("Clear answers", use_container_width=True):
                st.session_state.quiz_checked = False
                for number in range(1, len(quiz.questions) + 1):
                    st.session_state.pop(f"answer_{number}", None)
                st.rerun()

        if st.session_state.quiz_checked:
            correct = sum(
                1
                for number, item in enumerate(quiz.questions, start=1)
                if st.session_state.get(f"answer_{number}") == item.answer
            )
            st.info(f"Score: {correct} out of {len(quiz.questions)}")

    # ---- Download
    st.divider()

    as_markdown, as_json = st.columns(2)
    with as_markdown:
        st.download_button(
            "Download as Markdown",
            results_as_markdown(),
            file_name="episode_companion.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with as_json:
        st.download_button(
            "Download as JSON",
            results_as_json(),
            file_name="episode_companion.json",
            mime="application/json",
            use_container_width=True,
        )