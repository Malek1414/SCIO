"""Command line entry point. v1: `ember serve`. Plan B adds `observe` and `export`."""
import argparse
from pathlib import Path

from .llm import guard_environment


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ember")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the interview server")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--sessions", type=Path, default=Path("sessions"))
    s.add_argument("--no-warm", action="store_true", help="skip loading the whisper model at start (tests)")
    args = p.parse_args(argv)

    if args.cmd == "serve":
        guard_environment()                       # exits if ANTHROPIC_API_KEY is set; strips CLAUDE* vars
        import uvicorn
        from .bank import load_bank
        from .engine import Engine
        from .llm import LLM
        from .server import create_app
        from .store import SessionStore
        from .stt import Transcriber

        transcriber = Transcriber()
        if not args.no_warm:
            print(f"loading whisper… {transcriber.warm():.1f}s")
        app = create_app(SessionStore(args.sessions), Engine(load_bank(), LLM()), transcriber)
        if args.port == 0:
            return 0
        print(f"subject:  http://127.0.0.1:{args.port}/\noperator: http://127.0.0.1:{args.port}/operator")
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
