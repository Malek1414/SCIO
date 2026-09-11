"""Every user-facing string on the subject screen, per language (spec §4.3).
German is du throughout — the register the bank uses."""

COPY: dict[str, dict[str, str]] = {
    "en": {
        "consent_title": "Before we start",
        "consent_1": "1. This is a ~7-minute psychological interview. It's recorded and transcribed.",
        "consent_2": "2. Transcript text goes to Anthropic, through Malek's Claude subscription, to pick questions and score. Audio stays on this laptop.",
        "consent_3": "3. Your session goes into a graph Malek reads. Ask him and he'll delete it.",
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
        "consent_2": "2. Der transkribierte Text geht über Maleks Claude-Abo an Anthropic, um Fragen auszuwählen und auszuwerten. Die Audioaufnahme bleibt auf diesem Laptop.",
        "consent_3": "3. Deine Sitzung landet in einer Auswertung, die Malek liest. Sag ihm Bescheid, dann löscht er sie.",
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
