from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["playground"])

_PLAYGROUND_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RLM Playground</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: system-ui, -apple-system, sans-serif;
    background: #0f1117;
    color: #e0e0e0;
    height: 100vh;
    display: flex;
    flex-direction: column;
  }
  header {
    padding: 12px 20px;
    background: #161822;
    border-bottom: 1px solid #2a2d3a;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
  }
  header h1 { font-size: 16px; font-weight: 600; color: #a0a8c8; }
  header .status { font-size: 12px; color: #666; }
  #output {
    flex: 1;
    overflow-y: auto;
    padding: 16px 20px;
    font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
    font-size: 13px;
    line-height: 1.6;
    white-space: pre-wrap;
    word-break: break-word;
  }
  #output .event { margin-bottom: 8px; }
  #output .event-type {
    font-weight: 600;
    display: inline-block;
    min-width: 90px;
  }
  .ev-started { color: #69db7c; }
  .ev-metadata { color: #91a7ff; }
  .ev-iteration { color: #ffd43b; }
  .ev-completed { color: #69db7c; }
  .ev-failed { color: #ff6b6b; }
  .ev-info { color: #868e96; }
  .result-block {
    margin-top: 12px;
    padding: 12px;
    background: #1a1d2e;
    border: 1px solid #2a2d3a;
    border-radius: 6px;
  }
  .result-block .label { color: #91a7ff; font-weight: 600; margin-bottom: 4px; }
  .result-block .content { color: #e0e0e0; }
  #input-area {
    flex-shrink: 0;
    padding: 12px 20px;
    background: #161822;
    border-top: 1px solid #2a2d3a;
  }
  #input-area form { display: flex; gap: 10px; }
  #prompt {
    flex: 1;
    background: #1a1d2e;
    border: 1px solid #2a2d3a;
    border-radius: 6px;
    color: #e0e0e0;
    font-family: inherit;
    font-size: 14px;
    padding: 10px 14px;
    resize: vertical;
    min-height: 60px;
    max-height: 200px;
  }
  #prompt:focus { outline: none; border-color: #5c6bc0; }
  #prompt::placeholder { color: #555; }
  button {
    background: #5c6bc0;
    color: #fff;
    border: none;
    border-radius: 6px;
    padding: 10px 24px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    align-self: flex-end;
  }
  button:hover { background: #7986cb; }
  button:disabled { background: #3a3d4a; color: #666; cursor: not-allowed; }
  #toolbar {
    display: flex;
    gap: 10px;
    margin-bottom: 8px;
    align-items: center;
  }
  #toolbar label { font-size: 12px; color: #868e96; }
  select {
    background: #1a1d2e;
    border: 1px solid #2a2d3a;
    border-radius: 4px;
    color: #e0e0e0;
    font-size: 13px;
    padding: 4px 8px;
  }
  select:focus { outline: none; border-color: #5c6bc0; }
</style>
</head>
<body>

<header>
  <h1>RLM Playground</h1>
  <span class="status" id="status">Ready</span>
</header>

<div id="output"></div>

<div id="input-area">
  <div id="toolbar">
    <label>Model</label>
    <select id="model-select">
      <optgroup label="OpenAI" data-backend="openai">
        <option value="openai:gpt-4.1" selected>GPT-4.1</option>
        <option value="openai:gpt-4.1-mini">GPT-4.1 Mini</option>
        <option value="openai:gpt-4.1-nano">GPT-4.1 Nano</option>
        <option value="openai:gpt-4o">GPT-4o</option>
        <option value="openai:gpt-4o-mini">GPT-4o Mini</option>
        <option value="openai:o3-mini">o3-mini</option>
      </optgroup>
      <optgroup label="Anthropic" data-backend="anthropic">
        <option value="anthropic:claude-opus-4-6-20250610">Claude Opus 4.6</option>
        <option value="anthropic:claude-sonnet-4-6-20250514">Claude Sonnet 4.6</option>
        <option value="anthropic:claude-haiku-4-5-20251001">Claude Haiku 4.5</option>
      </optgroup>
      <optgroup label="Gemini" data-backend="gemini">
        <option value="gemini:gemini-2.0-flash">Gemini 2.0 Flash</option>
        <option value="gemini:gemini-2.5-pro">Gemini 2.5 Pro</option>
      </optgroup>
      <optgroup label="Cerebras" data-backend="cerebras">
        <option value="cerebras:gpt-oss-120b">GPT-OSS 120B</option>
        <option value="cerebras:llama-4-scout-17b-16e-instruct">Llama 4 Scout 17B</option>
        <option value="cerebras:llama3.3-70b">Llama 3.3 70B</option>
        <option value="cerebras:qwen-3-32b">Qwen 3 32B</option>
      </optgroup>
      <optgroup label="Other">
        <option value="openrouter:" data-backend="openrouter">OpenRouter (custom)</option>
        <option value="litellm:" data-backend="litellm">LiteLLM (custom)</option>
        <option value="vllm:" data-backend="vllm">vLLM (custom)</option>
      </optgroup>
    </select>
  </div>
  <form id="form">
    <textarea id="prompt" rows="2" placeholder="Enter your prompt... (Ctrl+Enter to submit)"></textarea>
    <button type="submit" id="submit-btn">Run</button>
  </form>
</div>

<script>
const API_KEY = "{{API_KEY}}";
const AVAILABLE_BACKENDS = {{AVAILABLE_BACKENDS}};
const BASE = window.location.pathname.replace(/\\/playground\\/?$/, "");

// Remove providers that have no API key configured on the server
(function filterModels() {
  const select = document.getElementById("model-select");
  for (const group of [...select.querySelectorAll("optgroup")]) {
    const backend = group.dataset.backend;
    if (backend && !AVAILABLE_BACKENDS[backend]) {
      group.remove();
      continue;
    }
    // Also filter individual options in the "Other" group
    for (const opt of [...group.querySelectorAll("option[data-backend]")]) {
      if (!AVAILABLE_BACKENDS[opt.dataset.backend]) opt.remove();
    }
    // Remove the group if it has no options left
    if (group.querySelectorAll("option").length === 0) group.remove();
  }
  // If the selected option was removed, select the first available
  if (!select.value || !select.querySelector("option[value='" + CSS.escape(select.value) + "']")) {
    const first = select.querySelector("option");
    if (first) first.selected = true;
  }
})();
const output = document.getElementById("output");
const form = document.getElementById("form");
const prompt = document.getElementById("prompt");
const submitBtn = document.getElementById("submit-btn");
const modelSelect = document.getElementById("model-select");
const status = document.getElementById("status");
let abortCtrl = null;

function log(eventType, text) {
  const div = document.createElement("div");
  div.className = "event";
  const cls = "ev-" + eventType;
  div.innerHTML = `<span class="event-type ${cls}">[${eventType}]</span> ${escapeHtml(text)}`;
  output.appendChild(div);
  output.scrollTop = output.scrollHeight;
}

function showResult(label, content) {
  const div = document.createElement("div");
  div.className = "result-block";
  div.innerHTML = `<div class="label">${escapeHtml(label)}</div><div class="content">${escapeHtml(content)}</div>`;
  output.appendChild(div);
  output.scrollTop = output.scrollHeight;
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function setRunning(running) {
  submitBtn.disabled = running;
  submitBtn.textContent = running ? "Running..." : "Run";
  status.textContent = running ? "Processing..." : "Ready";
}

function cleanup() {
  if (abortCtrl) { abortCtrl.abort(); abortCtrl = null; }
  setRunning(false);
}

function handleSSEEvent(eventType, data) {
  if (eventType === "started") {
    log("started", "Worker picked up job" + (data.data?.worker_id ? " (" + data.data.worker_id + ")" : ""));
  } else if (eventType === "metadata") {
    log("metadata", JSON.stringify(data.data || {}));
  } else if (eventType === "iteration") {
    const iter = data.data || {};
    const num = iter.iteration !== undefined ? iter.iteration : "?";
    const code = iter.code ? "\\n" + iter.code : "";
    const result = iter.result ? "\\n  -> " + iter.result : "";
    log("iteration", "Iteration " + num + code + result);
  } else if (eventType === "completed") {
    const result = data.data || data;
    log("completed", "Job completed");
    if (result.response) showResult("Response", result.response);
    if (result.execution_time) log("info", "Execution time: " + result.execution_time.toFixed(2) + "s");
    if (result.usage_summary) log("info", "Usage: " + JSON.stringify(result.usage_summary));
    cleanup();
  } else if (eventType === "failed") {
    log("failed", "Job failed: " + (data.error || data.data?.error || JSON.stringify(data)));
    cleanup();
  }
}

async function readSSEStream(response) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent = "message";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split("\\n");
    buffer = lines.pop();

    for (const line of lines) {
      if (line.startsWith("event: ")) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        const raw = line.slice(6);
        try {
          const parsed = JSON.parse(raw);
          handleSSEEvent(currentEvent, parsed);
        } catch {}
        currentEvent = "message";
      }
      // ignore comments (lines starting with :) and empty lines
    }
  }
}

function buildRequest(text) {
  const val = modelSelect.value;
  const [backend, model] = val.split(":");
  const req = { prompt: text };
  if (backend) req.backend = backend;
  if (model) req.model_name = model;
  return req;
}

async function submitPrompt(text) {
  cleanup();
  setRunning(true);
  const selected = modelSelect.options[modelSelect.selectedIndex].text;
  log("info", "Submitting prompt (" + selected + ")...");

  let jobId;
  try {
    const res = await fetch(BASE + "/v1/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + API_KEY
      },
      body: JSON.stringify(buildRequest(text))
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      let msg = "";
      try { const j = JSON.parse(text); msg = j.detail || j.error || ""; } catch {}
      throw new Error(msg || res.status + " " + (res.statusText || "Error"));
    }
    const data = await res.json();
    jobId = data.job_id;
    log("info", "Job enqueued: " + jobId);
  } catch (e) {
    log("failed", "Request failed: " + (e.message || e));
    setRunning(false);
    return;
  }

  // Stream SSE via fetch (supports Authorization header unlike EventSource)
  abortCtrl = new AbortController();
  try {
    const sseRes = await fetch(BASE + "/v1/jobs/" + jobId + "/stream", {
      headers: { "Authorization": "Bearer " + API_KEY },
      signal: abortCtrl.signal
    });
    if (!sseRes.ok) {
      const text = await sseRes.text().catch(() => "");
      let msg = "";
      try { const j = JSON.parse(text); msg = j.detail || j.error || ""; } catch {}
      throw new Error(msg || sseRes.status + " " + (sseRes.statusText || "Error"));
    }
    await readSSEStream(sseRes);
  } catch (e) {
    if (e.name !== "AbortError") {
      log("failed", "SSE stream error: " + e.message);
    }
    cleanup();
  }
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = prompt.value.trim();
  if (!text) return;
  submitPrompt(text);
});

prompt.addEventListener("keydown", (e) => {
  if (e.ctrlKey && e.key === "Enter") {
    e.preventDefault();
    form.dispatchEvent(new Event("submit"));
  }
});
</script>

</body>
</html>
"""


@router.get("/playground", response_class=HTMLResponse)
async def playground(request: Request) -> HTMLResponse:
    """Serve the RLM test playground page."""
    import json

    settings = request.app.state.settings
    # Use the first configured API key, fall back to default
    api_key = "rlm-key-change-me"
    if settings.api_keys:
        first = settings.api_keys.split(",")[0].strip()
        if first:
            api_key = first

    # Build map of backend -> available (has API key or base_url configured)
    available = {
        "openai": bool(settings.openai_api_key),
        "anthropic": bool(settings.anthropic_api_key),
        "gemini": bool(settings.gemini_api_key),
        "azure_openai": bool(settings.azure_openai_api_key),
        "cerebras": bool(settings.cerebras_api_key),
        "portkey": bool(settings.portkey_api_key),
        "openrouter": bool(settings.openrouter_api_key),
        "vercel": bool(settings.vercel_api_key),
        "litellm": bool(settings.litellm_api_key),
        "vllm": bool(settings.vllm_base_url),
    }

    html = _PLAYGROUND_HTML.replace("{{API_KEY}}", api_key)
    html = html.replace("{{AVAILABLE_BACKENDS}}", json.dumps(available))
    return HTMLResponse(content=html)
