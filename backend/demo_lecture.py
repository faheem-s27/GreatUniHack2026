"""Server-owned slide text for the current web demo (not uploaded lecture search)."""

from guardrails import Slide


DEMO_LECTURE_ID = "demo-calculus"
DEMO_SLIDES = {
    1: Slide(1, "The big picture — Functions of several variables. What happens when an "
                 "output depends on more than one input? Formula: f(x, y) = x² + y²."),
    2: Slide(2, "Meet partial derivatives — Partial derivatives. A partial derivative describes "
                 "how a function changes as one variable changes, while the others stay constant. "
                 "Formula: f(x, y) = x² + y²."),
    3: Slide(3, "A closer look — Holding variables constant. To find the partial derivative "
                 "with respect to x, treat y as a constant. Formula: f(x, y) = x² + y²."),
}


def slides_for(slide_number: int) -> list[Slide]:
    """Put the selected slide first, while allowing citations to other demo slides."""
    return [DEMO_SLIDES[slide_number]] + [
        slide for number, slide in DEMO_SLIDES.items() if number != slide_number
    ]
