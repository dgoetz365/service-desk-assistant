"""Run with Python 3.12: python app.py serve, or python app.py ask 'question'."""
import argparse
import json

from service_assistant.assistant import Assistant
from service_assistant.providers import OllamaProvider
from service_assistant.server import make_server


def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--model", default="qwen3:4b", help="An already installed local Ollama model")
    common.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    common.add_argument("--timeout", type=float, default=30, help="Seconds per local model request (1–120)")
    parser = argparse.ArgumentParser(description="Synthetic bicycle repair assistant; no messages are sent.")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", parents=[common], help="Serve the local web interface")
    serve.add_argument("--port", type=int, default=8765)
    ask = commands.add_parser("ask", parents=[common], help="Ask once and print JSON")
    ask.add_argument("question")
    ask.add_argument("--mode", choices=("offline", "ollama"), default="offline")
    args = parser.parse_args()
    try:
        provider = OllamaProvider(args.model, args.ollama_url, args.timeout)
        assistant = Assistant(provider=provider)
        if args.command == "ask":
            result = assistant.run(args.question, args.mode)
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return 0 if result["status"] == "complete" else 2
        if not 1 <= args.port <= 65535:
            parser.error("Port must be between 1 and 65535.")
        server = make_server(assistant, args.port)
        print(f"Spoke & Spanner: http://127.0.0.1:{server.server_port}")
        print("Synthetic records only. Offline demo is the default. Press Ctrl+C to stop.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
