"""Every user-facing string on the subject screen, per language (spec §4.3).
German is du throughout — the register the bank uses.

The consent lines describe the widest thing that can happen to a session, not the narrowest:
a scored result carries verbatim quotes and may be contributed to the study repository by
pull request (see ember/contribute.py), so the subject is told that before they start.
"""

COPY: dict[str, dict[str, str]] = {
    "en": {
        "consent_title": "Before we start",
        "consent_1": "1. This is a ~7-minute psychological interview. It's recorded and transcribed.",
        "consent_2": "2. Transcript text goes to Anthropic, through the interviewer's Claude subscription, to pick questions and score. The recording itself stays on this laptop and is never uploaded.",
        "consent_3": "3. Your scores, and short quotes from your own answers, may be shared with the study's private repository, where its collaborators can read them. Ask the interviewer and your session gets deleted.",
        "code_label": "Subject code",
        "start": "I understand — start",
        "hint_idle": "Hold space to speak. Release when you're done.",
        "hint_recording": "● recording — release space when done",
        "hint_waiting": "…",
        "retry": "Didn't catch that — once more?",
        "closing": "That's the interview.",
    },
    "de": {
        "consent_title": "Bevor wir anfangen",
        "consent_1": "1. Das ist ein etwa 7-minütiges psychologisches Interview. Es wird aufgenommen und transkribiert.",
        "consent_2": "2. Der transkribierte Text geht über das Claude-Abo des Interviewers an Anthropic, um Fragen auszuwählen und auszuwerten. Die Aufnahme selbst bleibt auf diesem Laptop und wird nicht hochgeladen.",
        "consent_3": "3. Deine Werte und kurze wörtliche Zitate aus deinen Antworten können in das private Repository der Studie hochgeladen werden, wo die Beteiligten sie lesen können. Sag dem Interviewer Bescheid, dann wird deine Sitzung gelöscht.",
        "code_label": "Teilnehmer-Code",
        "start": "Verstanden — los",
        "hint_idle": "Halte die Leertaste gedrückt, um zu sprechen. Loslassen, wenn du fertig bist.",
        "hint_recording": "● Aufnahme läuft — Leertaste loslassen, wenn du fertig bist",
        "hint_waiting": "…",
        "retry": "Das habe ich nicht verstanden — nochmal?",
        "closing": "Das war das Interview.",
    },
}


def copy_for(lang: str) -> dict[str, str]:
    return COPY.get(lang, COPY["en"])
