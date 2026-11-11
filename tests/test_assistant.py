import copy
import json
import unittest

from service_assistant.assistant import Assistant, SYSTEM_PROMPT
from service_assistant.providers import OllamaProvider, ProviderError, parse_json
from service_assistant.tools import ToolRegistry


def response(content="", calls=None):
    return {"done": True, "message": {"role": "assistant", "content": content,
                                       "tool_calls": calls or []}}


def call(name, **arguments):
    return {"function": {"name": name, "arguments": arguments}}


class ScriptedTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, url, payload, timeout):
        self.requests.append((url, copy.deepcopy(payload), timeout))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.tools = ToolRegistry()

    def test_exact_and_ambiguous_lookup(self):
        exact = self.tools.call("find_ticket", {"query": "R-1042"})
        self.assertEqual(exact["data"]["ticket_id"], "R-1042")
        ambiguous = self.tools.call("find_ticket", {"query": "blue"})
        self.assertEqual(ambiguous["code"], "ambiguous")
        self.assertEqual(len(ambiguous["candidates"]), 2)
        self.assertEqual(ambiguous["facts"], [])

    def test_missing_records(self):
        for name, args in [("find_ticket", {"query": "R-9999"}),
                           ("get_ticket", {"ticket_id": "R-9999"}),
                           ("get_part", {"part_id": "P-MISSING"})]:
            with self.subTest(name=name):
                self.assertEqual(self.tools.call(name, args)["code"], "not_found")

    def test_tool_allowlist_and_argument_validation(self):
        cases = [("send_email", {}, "unknown_tool"),
                 ("get_ticket", {"ticket_id": "../../data"}, "invalid_arguments"),
                 ("get_ticket", {"ticket_id": 1042}, "invalid_arguments"),
                 ("get_ticket", {"ticket_id": "R-1042", "write": True}, "invalid_arguments"),
                 ("get_ticket", {}, "invalid_arguments"),
                 ("get_ticket", "R-1042", "invalid_arguments"),
                 ("find_ticket", {"query": " "}, "invalid_arguments"),
                 ("find_ticket", {"query": "x" * 81}, "invalid_arguments"),
                 ("get_policy", {"topic": "secrets"}, "invalid_arguments")]
        for name, args, code in cases:
            with self.subTest(name=name, args=args):
                self.assertEqual(self.tools.call(name, args)["code"], code)

    def test_notes_are_explicitly_untrusted_and_not_fact(self):
        result = self.tools.call("get_ticket", {"ticket_id": "R-1044"})
        self.assertIn("Ignore all previous", result["data"]["untrusted_customer_note"])
        self.assertNotIn("repair is free", json.dumps(result["facts"]))

    def test_lookup_does_not_mutate_fixtures(self):
        result = self.tools.call("get_ticket", {"ticket_id": "R-1042"})
        result["data"]["status"] = "Changed"
        self.assertEqual(self.tools.call("get_ticket", {"ticket_id": "R-1042"})["data"]["status"], "Waiting for a part")


class OfflineTests(unittest.TestCase):
    def setUp(self):
        self.assistant = Assistant()

    def test_ready_ticket_with_policy(self):
        result = self.assistant.run("Can I collect R-1043?")
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["draft"]["kind"], "template")
        self.assertIn("FAQ-COLLECTION", result["draft"]["source_ids"])
        self.assertIn("Ready for collection", result["draft"]["text"])

    def test_unconfirmed_dates_are_not_invented(self):
        result = self.assistant.run("When is R-1042 ready, and what will it cost?")
        self.assertEqual(len(result["trace"]), 5)
        self.assertIn("arrival not confirmed", result["draft"]["text"])
        self.assertTrue(result["missing"])

    def test_unknown_ambiguous_and_unsupported_requests(self):
        for question, status in [("R-9999", "incomplete"), ("blue bicycle", "needs_clarification"),
                                 ("hello", "no_evidence"), ("R-1042 and R-1043", "needs_clarification")]:
            with self.subTest(question=question):
                result = self.assistant.run(question)
                self.assertEqual(result["status"], status)
                self.assertIsNone(result["draft"])

    def test_missing_policy_evidence_is_visible(self):
        result = Assistant(registry=ToolRegistry(policies=[])).run("What does the warranty cover?")
        self.assertEqual(result["status"], "incomplete")
        self.assertIsNone(result["draft"])
        self.assertIn("No policy evidence", result["missing"][0])

    def test_prompt_like_fixture_does_not_control_offline_draft(self):
        result = self.assistant.run("Give status of R-1044")
        self.assertNotIn("repair is free", result["draft"]["text"])
        self.assertEqual([s["tool"] for s in result["trace"]], ["find_ticket", "get_ticket"])
        self.assertIn("Estimate: not recorded", result["draft"]["text"])

    def test_invalid_request(self):
        for q in [None, "", " " * 4, "x" * 1001, 123, "\ud800"]:
            with self.subTest(q=q):
                with self.assertRaises(ValueError):
                    self.assistant.run(q)
        with self.assertRaises(ValueError):
            self.assistant.run("hello", "remote")


class ModelTests(unittest.TestCase):
    def assistant(self, responses, **kwargs):
        transport = ScriptedTransport(responses)
        return Assistant(provider=OllamaProvider(transport=transport), **kwargs), transport

    def test_native_protocol_and_grounded_facts(self):
        assistant, transport = self.assistant([
            response(calls=[call("get_ticket", ticket_id="R-1043")]),
            response(json.dumps({"draft": "Your bicycle is ready for collection.", "source_ids": ["R-1043"]}))])
        result = assistant.run("Status of R-1043?", "ollama")
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["draft"]["kind"], "model")
        url, payload, timeout = transport.requests[1]
        self.assertEqual(url, "http://127.0.0.1:11434/api/chat")
        self.assertFalse(payload["stream"])
        self.assertEqual(timeout, 30)
        self.assertEqual(payload["messages"][-2]["role"], "assistant")
        self.assertEqual(payload["messages"][-1]["role"], "tool")
        self.assertEqual(payload["messages"][-1]["tool_name"], "get_ticket")
        self.assertEqual(len(payload["tools"]), 4)

    def test_unknown_and_bad_tools_return_error_to_model(self):
        assistant, transport = self.assistant([
            response(calls=[call("send_email", to="nobody"), call("get_ticket", ticket_id=1042)]),
            response(json.dumps({"draft": "I sent it", "source_ids": []}))])
        result = assistant.run("Send a message", "ollama")
        self.assertEqual([s["result"]["code"] for s in result["trace"]], ["unknown_tool", "invalid_arguments"])
        self.assertIsNone(result["draft"])
        self.assertEqual(len(transport.requests), 2)

    def test_ambiguous_lookup_stops_without_selecting(self):
        assistant, transport = self.assistant([response(calls=[call("find_ticket", query="blue")])])
        result = assistant.run("blue bicycle", "ollama")
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(len(transport.requests), 1)
        self.assertIsNone(result["draft"])

    def test_round_and_call_limits(self):
        repeats = [response(calls=[call("get_policy", topic="timing")])] * 5
        assistant, transport = self.assistant(repeats, max_rounds=2)
        result = assistant.run("timing", "ollama")
        self.assertEqual(result["status"], "limit_reached")
        self.assertEqual(len(transport.requests), 2)
        assistant, _ = self.assistant(repeats, max_calls=1)
        result = assistant.run("timing", "ollama")
        self.assertEqual(result["status"], "limit_reached")
        self.assertEqual(len(result["trace"]), 1)

    def test_malformed_calls_are_rejected(self):
        for malformed in [None, {}, {"function": {}}, {"function": {"name": "get_ticket", "arguments": "{}"}}]:
            with self.subTest(call=malformed):
                assistant, _ = self.assistant([response(calls=[malformed])])
                result = assistant.run("status", "ollama")
                self.assertEqual(result["status"], "invalid_model_output")
                self.assertFalse(result["trace"])

    def test_draft_without_evidence_or_with_unknown_source_is_withheld(self):
        for sources in [[], ["FAKE-SOURCE"]]:
            assistant, _ = self.assistant([response(json.dumps({"draft": "Ready today", "source_ids": sources}))])
            result = assistant.run("status", "ollama")
            self.assertEqual(result["status"], "no_evidence")
            self.assertIsNone(result["draft"])
        assistant, _ = self.assistant([response(calls=[call("get_policy", topic="timing")]),
                                      response('{"draft":"A claim", "source_ids":["FAKE-SOURCE"]}')])
        self.assertIsNone(assistant.run("timing", "ollama")["draft"])

    def test_malformed_final_json(self):
        for raw in ["not JSON", '{"draft":"x"}', '{"draft":"x","source_ids":[1]}',
                    '{"draft":"x","draft":"y","source_ids":[]}']:
            with self.subTest(raw=raw):
                assistant, _ = self.assistant([response(raw)])
                self.assertEqual(assistant.run("status", "ollama")["status"], "invalid_model_output")

    def test_provider_failure_preserves_already_retrieved_facts(self):
        assistant, _ = self.assistant([response(calls=[call("get_ticket", ticket_id="R-1042")]),
                                      ProviderError("The local model timed out.")])
        result = assistant.run("status", "ollama")
        self.assertEqual(result["status"], "provider_error")
        self.assertTrue(result["facts"])
        self.assertIsNone(result["draft"])

    def test_prompt_like_data_never_adds_authority_or_tools(self):
        assistant, transport = self.assistant([
            response(calls=[call("get_ticket", ticket_id="R-1044")]),
            response(calls=[call("send_email")]),
            response('{"draft":"There is no recorded estimate.","source_ids":["R-1044"]}')])
        result = assistant.run("R-1044", "ollama")
        tool_message = transport.requests[1][1]["messages"][-1]
        self.assertEqual(tool_message["role"], "tool")
        self.assertIn("untrusted_customer_note", tool_message["content"])
        self.assertIn("untrusted", SYSTEM_PROMPT)
        self.assertEqual(result["trace"][1]["result"]["code"], "unknown_tool")
        self.assertNotIn("repair is free", json.dumps(result["facts"]))


class ProviderTests(unittest.TestCase):
    def test_local_url_and_model_only(self):
        for url in ["https://127.0.0.1:11434", "http://example.invalid", "http://127.0.0.1/a",
                    "http://user:password@localhost", "http://localhost?x=y", "http://localhost:bad"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                OllamaProvider(base_url=url)
        self.assertEqual(OllamaProvider(base_url="http://localhost:11500").url, "http://127.0.0.1:11500/api/chat")
        for timeout in [0, 121, float("nan"), True]:
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                OllamaProvider(timeout=timeout)
        with self.assertRaises(ValueError):
            OllamaProvider(model="example:cloud")

    def test_invalid_provider_messages(self):
        for raw in [{}, {"error": "bad"}, {"done": False}, response(content=123),
                    {"done": True, "message": {"role": "tool"}},
                    {**response(), "done_reason": "length"}]:
            with self.subTest(raw=raw), self.assertRaises(ProviderError):
                OllamaProvider(transport=ScriptedTransport([raw])).chat([], [])

    def test_strict_json(self):
        for raw in ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '{"a":1e999}', '"\\ud800"', '[' * 66 + '0' + ']' * 66]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_json(raw)


if __name__ == "__main__":
    unittest.main()
