"use strict";

const byId = (id) => document.getElementById(id);
const form = byId("request-form");
const requestInput = byId("request");
const modeInput = byId("mode");
let config = null;
let busy = false;

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}

function updateMode() {
  byId("mode-help").textContent = modeInput.value === "offline"
    ? "Deterministic routing and a template draft. No model or external request."
    : `Uses your local Ollama server${config ? ` with ${config.model}` : ""}. The runtime and model must already be installed. Draft wording is unverified.`;
}

function updateCount() { byId("character-count").textContent = `${requestInput.value.length} / 1,000`; }

function setBusy(value) {
  busy = value;
  document.querySelector(".answer-panel").setAttribute("aria-busy", String(value));
  byId("submit").disabled = value || !config;
  byId("submit").textContent = value ? "Checking records…" : "Check records & draft";
  byId("reset").disabled = value;
  modeInput.disabled = value;
  document.querySelectorAll(".example").forEach((button) => { button.disabled = value; });
  byId("loading").hidden = !value;
}

async function connect() {
  byId("retry-config").hidden = true;
  byId("error").hidden = true;
  try {
    const response = await fetch("/api/config", { cache: "no-store", signal: AbortSignal.timeout(10000) });
    if (!response.ok) throw new Error("Local app connection failed.");
    config = await response.json();
    byId("submit").disabled = false;
    byId("status").textContent = "Ready. Choose a scenario or write a question.";
    updateMode();
  } catch {
    byId("status").textContent = "The local app is unavailable.";
    byId("error").textContent = "Start the Python server, then reconnect. Your question stays here.";
    byId("error").hidden = false;
    byId("retry-config").hidden = false;
  }
}

function render(result) {
  byId("result").hidden = false;
  byId("result-mode").hidden = false;
  byId("result-mode").textContent = result.mode === "offline" ? "Offline demo result" : "Local model result";
  const statuses = { complete: "Lookup complete. Review the evidence and draft.",
    incomplete: "Some lookups could not be resolved.", needs_clarification: "A clarification is needed.",
    no_evidence: "There is not enough evidence for a draft.", provider_error: "The local model could not complete this request.",
    limit_reached: "The request reached its safety limit.", invalid_model_output: "The model response could not be validated." };
  byId("status").textContent = statuses[result.status] || "Review the result below.";
  byId("result-notice").textContent = result.notice;
  const facts = byId("facts");
  facts.replaceChildren();
  result.facts.forEach((fact) => {
    const row = node("li");
    row.append(node("span", fact.text), node("span", fact.source_id, "source-ref"));
    facts.append(row);
  });
  byId("no-facts").hidden = result.facts.length > 0;
  byId("missing-section").hidden = result.missing.length === 0;
  byId("missing").replaceChildren(...result.missing.map((text) => node("li", text)));
  byId("clarification").hidden = result.candidates.length === 0;
  const candidates = byId("candidates");
  candidates.replaceChildren();
  result.candidates.forEach((candidate) => {
    const button = node("button", `${candidate.id} · ${candidate.bike}`, "secondary");
    button.type = "button";
    button.addEventListener("click", () => {
      requestInput.value = `What is the repair status of ${candidate.id}?`;
      updateCount();
      form.requestSubmit();
    });
    candidates.append(button);
  });
  const draft = result.draft;
  byId("draft-text").value = draft ? draft.text : "";
  byId("draft-text").hidden = !draft;
  byId("no-draft").hidden = Boolean(draft);
  byId("copy-draft").hidden = !draft;
  byId("copy-status").textContent = "";
  byId("draft-warning").textContent = draft && draft.kind === "model"
    ? "Model-generated wording may contain unsupported claims even when source IDs are valid. Compare every claim with the recorded facts."
    : "Template generated from recorded facts. Review relevance, tone, and missing information before sharing.";
  byId("sources").replaceChildren(...result.sources.map((source) => node("p", `${source.id} · ${source.title} · ${source.kind}`)));
  byId("audit-title").textContent = `Sources & tool trace · ${result.sources.length} sources, ${result.trace.length} lookups`;
  byId("trace").replaceChildren(...result.trace.map((step) => {
    const row = node("li");
    const details = node("details");
    details.append(node("summary", `${step.tool} · ${step.result.code}`),
      node("pre", JSON.stringify({ arguments: step.arguments, result: step.result }, null, 2)));
    row.append(details);
    return row;
  }));
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy || !config) return;
  const question = requestInput.value.trim();
  if (!question) { requestInput.focus(); return; }
  byId("error").hidden = true;
  byId("empty").hidden = true;
  byId("result").hidden = true;
  byId("result-mode").hidden = true;
  byId("status").textContent = modeInput.value === "offline" ? "Looking up synthetic records…" : "Waiting for the local model. This can take several minutes on slower hardware…";
  setBusy(true);
  try {
    const timeout = (config.timeout * config.max_rounds + 15) * 1000;
    const response = await fetch("/api/ask", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": config.csrf_token },
      body: JSON.stringify({ question, mode: modeInput.value }), signal: AbortSignal.timeout(timeout) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "The request failed.");
    render(result);
  } catch (error) {
    byId("error").textContent = error.name === "TimeoutError"
      ? "The request timed out. Retry with a narrower question or use Offline demo."
      : `Unable to finish. ${error.message} Check the local server and try again.`;
    byId("error").hidden = false;
    byId("status").textContent = "Request unsuccessful. Your question has been kept.";
  } finally { setBusy(false); }
});

document.querySelectorAll(".example").forEach((button) => button.addEventListener("click", () => {
  requestInput.value = button.dataset.question;
  updateCount();
  requestInput.focus();
}));
byId("reset").addEventListener("click", () => {
  requestInput.value = "";
  updateCount();
  byId("result").hidden = true;
  byId("result-mode").hidden = true;
  byId("error").hidden = true;
  byId("empty").hidden = false;
  byId("draft-text").value = "";
  byId("status").textContent = "Workspace cleared. Ready for another question.";
  requestInput.focus();
});
byId("copy-draft").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(byId("draft-text").value);
    byId("copy-status").textContent = "Draft copied. Nothing was sent.";
  } catch {
    byId("draft-text").focus();
    byId("draft-text").select();
    byId("copy-status").textContent = "Select and copy the draft manually; clipboard access was unavailable.";
  }
});
byId("retry-config").addEventListener("click", connect);
requestInput.addEventListener("input", updateCount);
modeInput.addEventListener("change", updateMode);
connect();
