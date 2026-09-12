"""HTTP surface for the subject screen and the operator view (spec §8, §9)."""
import asyncio
import tempfile
import time
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .audio import to_wav
from .copy import copy_for
from .engine import Engine, Next
from .guards import STT_MIN_WORDS, MAX_RETRIES
from .session import Session, Turn
from .store import SessionStore
from .text import word_count

STATIC = Path(__file__).parent / "static"


class NewSession(BaseModel):
    subject_code: str
    language: str = "en"


def create_app(store: SessionStore, engines: dict, transcribers: dict, *, on_close=None) -> FastAPI:
    """`on_close(session_id)` runs after the closing screen is delivered — see cli.serve, which
    passes the scorer so a finished interview lands on the graph without a second command."""
    app = FastAPI(title="ember")
    app.state.store, app.state.engines, app.state.transcribers = store, engines, transcribers
    app.state.to_wav = to_wav

    def _engine(session: Session) -> Engine:
        return engines.get(session.language, engines["en"])

    def _load(sid: str) -> Session:
        try:
            return store.load(sid)
        except FileNotFoundError:
            raise HTTPException(404, "unknown session")

    def _ask(session: Session, nxt: Next, now: float) -> dict:
        session.pending = Turn(slot=nxt.slot, kind=nxt.kind, question_id=nxt.question_id, question=nxt.text, asked_at=now)
        session.retries = 0
        store.append_engine_log(session.session_id, {"at": now, "kind": nxt.kind, "question_id": nxt.question_id,
                                                     "fallback_used": nxt.fallback_used, **nxt.log})
        store.save(session)
        return {"kind": nxt.kind, "question": nxt.text, "slot": nxt.slot}

    def _close(session: Session, now: float) -> dict:
        out = _engine(session).close(session)
        session.pending = None
        session.closed, session.mirror, session.take_home = True, out.mirror, out.take_home
        store.append_engine_log(session.session_id, {"at": now, "kind": "close", "mirror": out.mirror, "take_home": out.take_home})
        store.save(session)
        return {"kind": "close", "mirror": out.mirror, "take_home": out.take_home}

    @app.get("/api/copy/{lang}")
    def copy(lang: str):
        return copy_for(lang)

    @app.post("/api/session")
    def new_session(body: NewSession):
        now = time.time()
        lang = body.language if body.language in engines else "en"
        session = store.create(body.subject_code, consent_at=now, now=now, language=lang)
        resp = _ask(session, engines[lang].first(), now)
        return {"session_id": session.session_id, "language": lang, **resp}

    @app.post("/api/session/{sid}/answer")
    async def answer(sid: str, background: BackgroundTasks, audio: UploadFile = File(...)):
        session = _load(sid)
        if session.closed or session.pending is None:
            raise HTTPException(409, "session is closed")
        now = time.time()
        idx = len(session.turns) + 1
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            tmp.write(await audio.read())
            src = Path(tmp.name)
        wav = app.state.to_wav(src, store.dir_for(sid) / "audio" / f"q{idx}.wav")
        src.unlink(missing_ok=True)
        transcriber = app.state.transcribers.get(session.language, app.state.transcribers["en"])
        # prime the decoder with the question on screen: it fixes the spelling of words the answer
        # is about to reuse, which is where German was losing the most (spec §3.2)
        text = await asyncio.to_thread(transcriber.transcribe, wav, session.pending.question)

        if word_count(text) < STT_MIN_WORDS:
            session.retries += 1
            if session.retries <= MAX_RETRIES:
                store.save(session)
                return {"retry": True, "question": session.pending.question,
                        "message": copy_for(session.language)["retry"]}
            session.pending.skipped, session.pending.answer, session.pending.answered_at = True, "", now
        else:
            session.pending.answer, session.pending.answered_at = text, now
        session.turns.append(session.pending)
        session.pending, session.retries = None, 0
        store.save(session)

        nxt = await asyncio.to_thread(_engine(session).next, session, now)
        shown_at = time.time()                       # the question is on screen from here, not from request start
        if nxt.kind == "close":
            store.append_engine_log(sid, {"at": shown_at, "kind": "close-decision", **nxt.log})
            out = await asyncio.to_thread(_close, session, shown_at)
            if on_close is not None:
                background.add_task(on_close, sid)     # scoring takes ~30 s; it must not hold the closing screen
            return out
        return _ask(session, nxt, shown_at)

    @app.post("/api/session/{sid}/rephrase")
    def rephrase(sid: str):
        session = _load(sid)
        if session.pending is None:
            raise HTTPException(409, "nothing pending")
        p = session.pending
        if p.kind == "spine":
            bank = _engine(session).bank
            p.question = bank.opener.rephrase if p.question_id is None else bank.by_id(p.question_id).rephrase
        p.rephrased = True
        store.save(session)
        return {"question": p.question}

    @app.post("/api/session/{sid}/resume")
    def resume(sid: str):
        s = _load(sid)
        if s.closed:
            return {"kind": "close", "mirror": s.mirror, "take_home": s.take_home}
        if s.pending is None:
            raise HTTPException(409, "no pending question")
        return {"kind": s.pending.kind, "question": s.pending.question, "slot": s.pending.slot}

    @app.get("/api/session/{sid}/state")
    def state(sid: str):
        s = _load(sid)
        return {"session_id": s.session_id, "subject_code": s.subject_code, "language": s.language,
                "elapsed": time.time() - s.started_at,
                "slot": s.current_slot(), "closed": s.closed, "probes_used": s.probes_used,
                "surfaced_tags": s.surfaced_tags, "retries": s.retries,
                "pending": ({"question_id": s.pending.question_id, "question": s.pending.question, "kind": s.pending.kind}
                            if s.pending else None),
                "last_answer": s.last_answer()[:200], "mirror": s.mirror, "take_home": s.take_home}

    @app.get("/")
    def subject_page():
        return FileResponse(STATIC / "subject.html")

    @app.get("/operator")
    def operator_page():
        return FileResponse(STATIC / "operator.html")

    return app
