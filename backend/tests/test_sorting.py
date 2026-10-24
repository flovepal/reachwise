import pytest

from app import ai
from app.db import GROUP_OF

CASES = [
    # John's real replies
    ("Re: TEEP Research Internship Inquiry",
     "I retire this year. I hope you understand. Thank you for your interest in my lab and research. "
     "You have a very good experience. I hope you can find a suitable professor.", "rejection"),
    ("Re: TEEP Research Internship Inquiry",
     "Good to know that you are interested. But I don't have vacancy. Thanks.", "rejection"),
    # The five test replies suggested for testing
    ("Re: TEEP Research Internship Inquiry – John Paul S",
     "Dear John,\n\nThank you for your email. Your background in deep learning looks relevant to our work. "
     "Could we have a short Google Meet on Tuesday, 3 November at 10:00 Taipei time?\n\nBest regards", "interview"),
    ("RE:[EXTERNAL] Re: [External] TEEP Research Internship Inquiry – John Paul S",
     "Hi John,\n\nI received your email. Before I decide, could you send me your transcript and a short "
     "description of your final-year project?\n\nRegards", "needs_info"),
    ("Automatic reply: TEEP Research Internship Inquiry – John Paul S",
     "I am out of office until 10 November with limited access to email. I will reply when I return.", "auto_reply"),
    ("Re: TEEP Research Internship Inquiry – John Paul S",
     "Dear John,\n\nThank you for your interest. My group does not work on this topic. Please contact "
     "Professor Lin, who leads the deep learning lab, instead.\n\nBest", "redirect"),
    ("Re: TEEP Research Internship Inquiry – John Paul S",
     "Dear John,\n\nI appreciate your interest and your CV is impressive. However, my lab is full for 2027 "
     "and I cannot take new interns.\n\nBest wishes", "rejection"),
    # Positives must stay positive
    ("Re: inquiry", "Thank you. I am interested in your background. Please apply and list me as your advisor.", "interested"),
    ("Re: inquiry", "Sure, let's meet on Zoom on Friday.", "interview"),
    ("Re: inquiry", "Thanks. Please apply through the department admission system and list me as a potential advisor.",
     "interested"),
    ("Re: inquiry", "I have no openings. Please apply through the admission office and contact Prof. Wu instead.", "redirect"),
    ("Re: inquiry", "Unfortunately I am travelling this week, but can we meet on Zoom next Monday?", "interview"),
]


@pytest.mark.parametrize("subject,body,label", CASES)
def test_keyword_sorting(subject, body, label):
    r = ai.keyword_classify(subject, body)
    assert r["label"] == label, (body, r["label"])


def test_groups():
    assert GROUP_OF[ai.keyword_classify("", "I don't have vacancy")["label"]] == "negative"
    assert GROUP_OF[ai.keyword_classify("", "Automatic reply: away")["label"]] == "no_reply"
