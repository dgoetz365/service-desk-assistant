# Validation record

Validation date: 2026-11-11. This records demonstrated behavior, not production readiness.

## Executed

| Check | Result |
| --- | --- |
| Python 3.12.14: `python -m unittest discover -s tests -v` | 31 tests passed |
| Python 3.15.2: same suite | 30 tests passed before the final additional malformed-header subcases; final suite verified on 3.12.14 |
| `node --check service_assistant/static/app.js` with Node 22.23.3 | Passed; syntax only |
| CLI: `python app.py ask "When will R-1042 be ready, and what will it cost?"` | Exit 0; offline mode; five lookups; four sources; template draft; two unknown timing fields |
| Impeccable source detector on the three frontend files | Returned no findings; source check only |

The unittest suite creates real loopback HTTP servers on ephemeral ports, sends requests, and closes them after the run. No browser or real model is involved. The native Ollama HTTP protocol is exercised against a local test stub, not an installed Ollama runtime.

## Covered boundaries

- Exact, unknown, and ambiguous ticket lookup; missing policy evidence; unknown inventory items.
- Read-only tool allowlist, exact required fields, string/length/identifier/enum validation, and rejected extra arguments.
- Preserved unknown dates and estimates; source IDs attached to recorded facts.
- Customer notes retained as explicitly untrusted data, excluded from authoritative facts. A simulated model's attempt to call an unavailable email tool is rejected.
- Native Ollama request structure, assistant/tool message ordering, fake-transport errors, malformed tool calls and final JSON, source validation, and bounded rounds/calls.
- Real app requests for static files, configuration, health, and assistant output.
- Invalid hosts, origins, request tokens, fetch-site values, duplicate headers, overlarge body lengths, extra fields, duplicate JSON keys, invalid Unicode, and unsupported content types.
- Early-rejection JSON responses after POST bodies are drained, with a 64 KiB ceiling and a total 100 ms drain deadline; a missing body cannot hold the response indefinitely.
- Strict JSON parser checks for non-finite numbers and excessive nesting.
- Fixed static-route allowlist rejects traversal and attempts to read source or configuration files.

## Not verified

- **Live Ollama/model behavior:** no runtime or model was installed, started, or called. Tool-call reliability, model memory needs, inference speed, and response quality remain unverified.
- **Browser behavior and visual layout:** no browser was used. The HTML/CSS/JavaScript were source-reviewed and the JavaScript syntax checked, but no rendered screenshot, responsive interaction pass, clipboard permission test, keyboard walkthrough, or screen-reader test was performed.
- **Semantic grounding of model prose:** source-ID validation cannot prove that each generated claim is supported. The UI always labels model wording unverified and requires human review.
- **General injection resistance:** adversarial fixture tests show that notes cannot add tool authority; they are not a comprehensive model safety evaluation.
- **Public hosting or production use:** no authentication, tenant isolation, durable storage, monitoring, load test, or deployment was built or claimed. The standard-library server binds only to loopback.
- **Separate runtime configuration:** the app restricts its own traffic to loopback. It cannot attest to forwarding configured inside another locally running process.

To repeat the supported checks, run the unittest command above. Node is optional and is not needed to run the app.
