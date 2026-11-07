"""Rules checked in code on student messages that the storage layer relies on.

The coach itself (prompts, reply checks, persona) is owned by the coach work;
this module only holds the rule coach_store needs to decide the mode:

  * an honest attempt must actually attempt something: "idk", "?", one word
    or "just give me the answer" does not count towards unlocking explain
    mode, so the rule cannot be gamed by sending filler three times
"""

import re

ANSWER_SEEKING = [
    r"\b(just |please )?(give|tell|show) me the (full |final |whole )?(answer|solution|code)\b",
    r"\bwhat('s| is) the (final )?answer\b",
    r"\b(solve|do|write|finish) (it|this|the (question|task|coursework)) for me\b",
]
LOW_EFFORT = {"idk", "i don't know", "i dont know", "dunno", "no idea", "not sure", "?", "??", "help", "ok", "yes", "no", "what"}


def is_honest_attempt(text: str) -> bool:
    cleaned = " ".join(text.lower().split()).strip(" .!")
    if cleaned in LOW_EFFORT or any(re.search(p, text, re.I) for p in ANSWER_SEEKING):
        return False
    words = re.findall(r"\w+", cleaned)
    return len(words) >= 2 and len(cleaned) >= 6
