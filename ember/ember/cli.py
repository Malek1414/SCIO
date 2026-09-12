"""Command line entry point: serve · observe · export · calibrate."""
import argparse
from pathlib import Path

from .llm import guard_environment

OBSERVER_TIMEOUT_S = 120.0   # offline scoring at effort high takes 20–40 s; §9's 15 s bound is for the live engine only


def _autoscore(sessions: Path, graph_out: Path, results: Path | None = None):
    """Score a just-closed interview and fold every result back into the cohort page.

    Runs on the server's background-task threadpool once the closing screen has gone out, so a
    ~30 s observer call never makes the subject wait. Failures are reported and dropped: a
    scoring problem must not take the interview down with it.
    """
    from .bank import load_bank
    from .export import collect, write_data_js
    from .llm import LLM
    from .observer import observe_session

    def run(session_id: str) -> None:
        try:
            bank = load_bank()                       # the rubric is shared; German sessions score against it too
            observe_session(Path(sessions) / session_id, bank, LLM(timeout_s=OBSERVER_TIMEOUT_S))
            out = write_data_js(collect(Path(sessions), bank, results_root=results), Path(graph_out))
            print(f"scored {session_id} → {out}")
        except Exception as e:                       # noqa: BLE001 - a bad session must not kill the server
            print(f"autoscore failed for {session_id}: {type(e).__name__}: {e}")

    return run


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ember")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="run the interview server")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--sessions", type=Path, default=Path("sessions"))
    s.add_argument("--no-warm", action="store_true", help="skip loading the whisper model at start (tests)")
    s.add_argument("--graph", type=Path, default=Path("graph/data.js"), help="where the cohort page reads its data")
    s.add_argument("--results", type=Path, default=Path("results"), help="merged contributions from other machines")
    s.add_argument("--no-autoscore", action="store_true",
                   help="do not score and export automatically when an interview closes")

    o = sub.add_parser("observe", help="score a session's transcript.json → observer.json (uses your Claude subscription)")
    o.add_argument("session_dir", type=Path)

    e = sub.add_parser("export", help="fold every observer.json into graph/data.js")
    e.add_argument("--sessions", type=Path, default=Path("sessions"))
    e.add_argument("--out", type=Path, default=Path("graph/data.js"))
    e.add_argument("--results", type=Path, default=Path("results"), help="merged contributions from other machines")

    c = sub.add_parser("calibrate", help="compare observer scores with hand scores")
    c.add_argument("--scores", type=Path, default=Path("calibration/human_scores.yaml"))
    c.add_argument("--sessions", type=Path, default=Path("sessions"))

    n = sub.add_parser("contribute", help="package a scored session and open a pull request with it")
    n.add_argument("session_dir", type=Path)
    n.add_argument("--results", type=Path, default=Path("results"))
    n.add_argument("--no-pr", action="store_true", help="write the result file only; print the git commands")

    v = sub.add_parser("stt-eval", help="measure STT backends against reference clips")
    v.add_argument("--clips", type=Path, default=Path("calibration/stt_clips.yaml"))
    v.add_argument("--lang", default=None, help="restrict to one language")

    args = p.parse_args(argv)

    if args.cmd == "serve":
        guard_environment()                       # exits if ANTHROPIC_API_KEY is set; strips CLAUDE* vars
        import uvicorn
        from .bank import load_bank
        from .engine import Engine
        from .llm import LLM
        from .server import create_app
        from .store import SessionStore
        from .stt import for_language

        from .bank import LANGUAGES
        transcribers = {lang: for_language(lang) for lang in LANGUAGES}
        if not args.no_warm:
            for lang, t in transcribers.items():
                print(f"loading {lang} speech model… {t.warm():.1f}s")
        engines = {lang: Engine(load_bank(lang), LLM()) for lang in LANGUAGES}
        on_close = None if args.no_autoscore else _autoscore(args.sessions, args.graph, args.results)
        app = create_app(SessionStore(args.sessions), engines, transcribers, on_close=on_close)
        if args.port == 0:
            return 0
        print(f"subject:  http://127.0.0.1:{args.port}/\noperator: http://127.0.0.1:{args.port}/operator")
        print("autoscore: off" if args.no_autoscore else f"autoscore: on — closing an interview scores it and rewrites {args.graph}")
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
        return 0

    if args.cmd == "observe":
        guard_environment()
        import json
        from .bank import load_bank
        from .llm import LLM
        from .observer import observe_session

        out = observe_session(args.session_dir, load_bank(), LLM(timeout_s=OBSERVER_TIMEOUT_S))
        r = json.loads(out.read_text(encoding="utf-8"))
        print(f"wrote {out}")
        for cid, cs in r["constructs"].items():
            print(f"  {cid}  {cs['score']}  {cs['signal']:4s}  {cs['note'][:70]}")
        if r["declined"]:
            print("  declined:", ", ".join(r["declined"]))
        for f in r["flags"]:
            print("  flag:", f)
        return 0

    if args.cmd == "export":
        from .bank import load_bank
        from .export import collect, write_data_js

        data = collect(args.sessions, load_bank(), results_root=args.results)
        out = write_data_js(data, args.out)
        print(f"{len(data['subjects'])} subject(s) → {out}   (open graph/index.html)")
        return 0

    if args.cmd == "calibrate":
        from .calibrate import agreement, load_human_scores, render
        from .observer import load_results

        rep = agreement(load_results(args.sessions), load_human_scores(args.scores))
        print(render(rep))
        return 0 if rep.passed else 1

    if args.cmd == "contribute":
        from .contribute import ContributeError, build_result, open_pull_request, repo_root_for, write_result

        try:
            result = build_result(args.session_dir)
            out = write_result(result, args.results)
        except ContributeError as e:
            print(e)
            return 1
        print(f"wrote {out}  ({result['subject_code']} · {result['language']})")
        if args.no_pr:
            print("\nnext, by hand:\n"
                  f"  git checkout -b contribution/{result['session_id']}\n"
                  f"  git add {out}\n"
                  f"  git commit -m 'Contribute scored interview {result['session_id']}'\n"
                  "  git push -u origin HEAD && gh pr create --fill")
            return 0
        try:
            url = open_pull_request(out, result["session_id"], repo_root=repo_root_for(out))
        except ContributeError as e:
            print(f"{e}\n\nthe result file is written — open the pull request by hand, or rerun with --no-pr")
            return 1
        print(f"pull request: {url}")
        return 0

    if args.cmd == "stt-eval":
        from .stt_eval import DEFAULT_BACKENDS, evaluate, load_clips, render

        clips = [c for c in load_clips(args.clips) if args.lang is None or c.language == args.lang]
        if not clips:
            print(f"no clips in {args.clips}" + (f" for language {args.lang}" if args.lang else ""))
            return 1
        print(render(evaluate(clips, DEFAULT_BACKENDS)))
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
