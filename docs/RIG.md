# The rig as discovered (2026-10-29)

Discovered through rig-agent (not assumed): `curl localhost:8080/v1/models`, the llama-swap config, `amd-smi`,
`free -g`, and the rig's own docs (`llm-private-education/en/00`, `02`, `03`).

## Hardware
* `mkoniu-B850-AI-TOP`, LAN 192.168.0.39 (Wi-Fi), Ubuntu 24.04, ROCm 7.2.4, Python 3.12.3, Docker 29.1.
* 4× AMD Radeon AI PRO R9700 (RDNA4, gfx1201), 32,624 MB VRAM each (GPU 0 drives the monitor); GPU 4 = iGPU (2 GB,
  never used for models). Ryzen 7 9700X, 60 GB usable RAM - **the binding limit** (a second large model caused a
  kernel panic on 2026-10-28).

## Served models (llama-swap on :8080, OpenAI-compatible, no key)

| llama-swap id | Engine, GPUs | Speed (1 agent) | Context | Used by the crypto agent as |
|---|---|---:|---:|---|
| `qwen3.8-flash-next` | radiance, GPU 0+1 | 118–145 tok/s | 200k | **analyst, reflector** (thinking on) |
| `qwen3.6-35b-a3b` | vLLM FP8, GPU 2+3 | 138–172 tok/s | 131k | **critic, reader, triage** (thinking off) |
| `gemma-4-26b-a4b` | llama.cpp Vulkan, GPU 2 | 135–175 tok/s | 131k | last-resort fallback (loading it unloads the duo) |
| `qwen3.6-35b-a3b-x4`, `qwen3.8-flash-next-uncensored`, `qwen3.8-flash-next-llamacpp`, `gemma-4-26b-a4b-pool`, `bielik-11b` | various | | | not used |

Groups: **`duo`** = qwen3.8-flash-next + qwen3.6-35b-a3b loaded together (~36–43 GB RAM in use with both; measured
16–22 GB available during our runs). `pedro` = OpenClaw's pair. Groups are exclusive: loading one unloads the
other. TTL 600 s: models unload after 10 minutes idle, so the agent holds the GPUs only during its daily cycle.

## Measured in this project
* Reader (qwen3.6, thinking off): ~0.6–0.9 s per news item warm; first call 104 s (cold vLLM start).
* Analyst (qwen3.8, thinking on): ~1–3 min per sample; GPU 0+1 at 98 % activity during the call (evidence:
  `docs/evidence/gpu_*.txt`).
* Both models obey JSON-schema output; both flagged and ignored an injected instruction in a news item.
* Gotcha found: qwen3.6 with thinking on spent its whole token budget thinking and returned empty content →
  `extra_body: {chat_template_kwargs: {enable_thinking: false}}` for short structured roles, and the router also
  parses JSON out of `reasoning_content`.

## Endpoints used
| What | Where |
|---|---|
| LLMs | `http://localhost:8080/v1` (override with `CRYPTOAGENT_RIG_URL`) |
| Signer | `127.0.0.1:8790` (token in `~/.local/state/cryptoagent/signer.token`, mode 600) |
| Anvil fork | `127.0.0.1:8545` (Docker `cryptoagent-anvil`) |
| Alerts | `msmtp` (already configured on the rig for Netdata) |
