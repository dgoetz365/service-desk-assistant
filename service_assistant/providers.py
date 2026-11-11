"""Minimal native Ollama /api/chat adapter; no SDK, proxy, or redirect support."""
import json
import math
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

MAX_RESPONSE = 1_048_576


class ProviderError(Exception):
    """A safe, user-displayable provider failure."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def parse_json(text):
    def reject_constant(value):
        raise ValueError("Non-finite JSON number")

    def unique_keys(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError("Duplicate JSON key")
            obj[key] = value
        return obj

    result = json.loads(text, parse_constant=reject_constant, object_pairs_hook=unique_keys)
    pending = [(result, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > 64:
            raise ValueError("JSON nesting limit exceeded")
        if isinstance(item, str):
            item.encode("utf-8")  # Reject escaped lone surrogates, which cannot be rendered safely.
        elif isinstance(item, float) and not math.isfinite(item):
            raise ValueError("Non-finite JSON number")
        elif isinstance(item, dict):
            pending.extend((key, depth + 1) for key in item)
            pending.extend((value, depth + 1) for value in item.values())
        elif isinstance(item, list):
            pending.extend((value, depth + 1) for value in item)
    return result


def http_transport(url, payload, timeout):
    request = Request(url, data=json.dumps(payload, allow_nan=False).encode("utf-8"),
                      headers={"Content-Type": "application/json"}, method="POST")
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ProviderError("The local model response exceeded the size limit.")
        return parse_json(raw.decode("utf-8"))
    except HTTPError as exc:
        raise ProviderError(f"The local model returned HTTP {exc.code}. Check its model and server.") from None
    except (URLError, TimeoutError, OSError):
        raise ProviderError("The local model could not be reached or timed out. Check Ollama or use Offline demo.") from None
    except (ValueError, UnicodeError, RecursionError):
        raise ProviderError("The local model returned invalid JSON.") from None


class OllamaProvider:
    def __init__(self, model="qwen3:4b", base_url="http://127.0.0.1:11434", timeout=30,
                 transport=None):
        parsed = urlsplit(base_url)
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
                or parsed.username or parsed.password or parsed.path not in {"", "/"}
                or parsed.query or parsed.fragment):
            raise ValueError("Ollama must use a plain HTTP loopback URL with no path or credentials.")
        try:
            port = parsed.port
        except ValueError:
            raise ValueError("Invalid Ollama port.") from None
        if port is not None and not 1 <= port <= 65535:
            raise ValueError("Invalid Ollama port.")
        if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}", model):
            raise ValueError("Invalid model name.")
        # Cloud-suffixed model names deliberately excluded from this local demonstration.
        if "cloud" in model.casefold():
            raise ValueError("Choose an installed local model, not a cloud model.")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 1 <= timeout <= 120:
            raise ValueError("Timeout must be between 1 and 120 seconds.")
        # Canonicalize localhost so name resolution cannot select a non-loopback address.
        host = "[::1]" if parsed.hostname == "::1" else "127.0.0.1"
        self.url = f"http://{host}:{port or 11434}/api/chat"
        self.model, self.timeout = model, timeout
        self.transport = transport or http_transport

    def chat(self, messages, tools):
        payload = {"model": self.model, "messages": messages, "tools": tools,
                   "stream": False, "options": {"temperature": 0, "num_predict": 2048}}
        try:
            body = self.transport(self.url, payload, self.timeout)
        except ProviderError:
            raise
        except Exception:
            raise ProviderError("The local model transport failed.") from None
        if not isinstance(body, dict) or body.get("error"):
            raise ProviderError("The local model returned an error response.")
        if body.get("done") is not True:
            raise ProviderError("The local model did not complete its response.")
        if body.get("done_reason") == "length":
            raise ProviderError("The local model reached its response length limit.")
        message = body.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            raise ProviderError("The local model returned a malformed assistant message.")
        content = message.get("content", "")
        calls = message.get("tool_calls", [])
        if not isinstance(content, str) or len(content) > 16000 or not isinstance(calls, list) or len(calls) > 8:
            raise ProviderError("The local model returned an invalid or oversized message.")
        # Forward only protocol fields; internal reasoning is neither required nor displayed.
        return {"role": "assistant", "content": content, "tool_calls": calls}
