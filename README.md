# Service Desk Assistant

Ask about a fictional bicycle repair, inspect the source records, and review a customer response draft.

**Python 3.12+ · JavaScript · Optional Ollama adapter · No Python runtime dependencies**

[Full guide](docs/guide.md) · [Portfolio](https://github.com/dgoetz365) · [MIT license](LICENSE)

The default mode is deterministic and works offline. The optional Ollama adapter uses a separately installed local model; live model inference has not been verified.

## Quick start

```sh
git clone https://github.com/dgoetz365/service-desk-assistant.git
cd service-desk-assistant
python app.py serve
```

Open http://127.0.0.1:8765. The app is branded **Spoke & Spanner**. No account, model download, or key is needed for the default mode. Stop with Ctrl+C.

On Windows, `py -3.12` can replace `python`. If you already cloned the repo, start with the Python commands from its root.

## Try it

Ask **“When will R-1042 be ready, and what will it cost?”** Inspect the recorded facts, missing information, draft, and tool trace. Then ask about **“the blue bicycle”** to see an ambiguous match. The CLI accepts the same requests with `python app.py ask "Check R-1042"`.

## Engineering highlights

- **Evidence first:** recorded facts come from tool results and remain separate from model wording.
- **Bounded tools:** exact argument checks, a read-only allowlist, timeouts, and round limits constrain the optional model path.
- **Visible uncertainty:** missing records, ambiguous matches, and provider failures remain explicit. Drafts require human review.

[Orchestrator](service_assistant/assistant.py) · [Tools](service_assistant/tools.py) · [Provider adapter](service_assistant/providers.py) · [Tests](tests/) · [Validation](VALIDATION.md)

## Tests and scope

```sh
python -m unittest discover -s tests -v
```

Original code and synthetic repair records, parts, and policies. This is a local demonstration without production authentication. Adapter tests use a protocol stub; browser behavior and live Ollama inference are unverified. See the guide for model setup and evidence limitations.

Built by [Daniel Goetz](https://github.com/dgoetz365) as an independent portfolio example. Employer code and data are not included.
