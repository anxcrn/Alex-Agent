<p align="center">
  <img src="assets/banner.png" alt="Alex Agent" width="100%">
</p>

# Alex Agent ☤
<p align="center">
  <a href="https://hermes-agent.nousresearch.com/">Alex Agent</a> | <a href="https://hermes-agent.nousresearch.com/">Alex Desktop</a>
</p>
<p align="center">
  <a href="https://hermes-agent.nousresearch.com/docs/"><img src="https://img.shields.io/badge/Docs-alex--agent-FFD700?style=for-the-badge" alt="Documentation"></a>
  <a href="https://discord.gg/NousResearch"><img src="https://img.shields.io/badge/Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="README.zh-CN.md"><img src="https://img.shields.io/badge/Lang-中文-red?style=for-the-badge" alt="中文"></a>
  <a href="README.ur-pk.md"><img src="https://img.shields.io/badge/Lang-اردو-green?style=for-the-badge" alt="اردو"></a>
  <a href="README.es.md"><img src="https://img.shields.io/badge/Lang-Español-orange?style=for-the-badge" alt="Español"></a>
</p>

**The self-improving and self-evolving AI agent.** It's the only agent with a built-in auto-evolution loop (**Project Nexus**) — it crawls the web for new skills/tools, verifies them in isolated sandboxes, checks security using AST parsers, and automatically merges them into its own codebase. It creates skills from experience, improves them during use, searches its own past conversations, and builds a deepening model of who you are across sessions. Run it on a $5 VPS, a GPU cluster, or serverless infrastructure that costs nearly nothing when idle. Talk to it from Telegram, Discord, or the CLI while it works on a cloud VM.

Use any model you want — [Nous Portal](https://portal.nousresearch.com), [OpenRouter](https://openrouter.ai) (200+ models), [NovitaAI](https://novita.ai), [NVIDIA NIM](https://build.nvidia.com), OpenAI, or your own endpoint. Switch with `hermes model` — no code changes, no lock-in.

<table>
<tr><td><b>Autonomous Evolution (Project Nexus)</b></td><td>Crawls the web (GitHub, PyPI, npm, HN, Reddit, ArXiv, docs) for new capabilities, validates them in a sandbox, scans code via AST, and merges upgrades directly into its codebase.</td></tr>
<tr><td><b>A real terminal interface</b></td><td>Full TUI with multiline editing, slash-command autocomplete, conversation history, interrupt-and-redirect, and streaming tool output.</td></tr>
<tr><td><b>Lives where you do</b></td><td>Telegram, Discord, Slack, WhatsApp, Signal, and CLI — all from a single gateway process. Voice memo transcription, cross-platform conversation continuity.</td></tr>
<tr><td><b>A closed learning loop</b></td><td>Agent-curated memory with periodic nudges. Autonomous skill creation after complex tasks. Skills self-improve during use. FTS5 session search with LLM summarization.</td></tr>
<tr><td><b>Scheduled automations</b></td><td>Built-in cron scheduler with delivery to any platform. Daily reports, nightly backups, weekly audits — all in natural language, running unattended.</td></tr>
<tr><td><b>Delegates and parallelizes</b></td><td>Spawn isolated subagents for parallel workstreams. Write Python scripts that call tools via RPC, collapsing multi-step pipelines into zero-context-cost turns.</td></tr>
<tr><td><b>Runs anywhere, not just your laptop</b></td><td>Six terminal backends — local, Docker, SSH, Singularity, Modal, and Daytona. Daytona and Modal offer serverless persistence.</td></tr>
</table>

---

## 🚀 Project Nexus: The Self-Evolution Engine

Alex Agent features **Project Nexus**, an autonomous, background-running system that continuously scans the web to discover, learn, test, and merge new skills, tools, and Model Context Protocol (MCP) servers.

```mermaid
graph TD
    A[Crawlers: GitHub/PyPI/npm/HN/ArXiv] -->|Discover| B[(Knowledge Base)]
    B -->|Deduplicate & Score| C[Learner: Skill/Tool Builder]
    C -->|Stage code| D[Verifier: Sandbox & AST Security Scanner]
    D -->|Test & Safe Check| E[Evolver: Code Writer & Merger]
    E -->|Hot reload| F[Alex Agent Core]
    E -->|Backup| G[Rollback Manager]
```

### Key Capabilities:
*   **Auto-Discovery Crawlers**: 10 distinct, rate-limited background crawlers that monitor GitHub, PyPI, npm, Hacker News, Reddit, YouTube transcripts, ArXiv papers, and documentation changelogs.
*   **Structured Analysis & Learning**: Translates raw developer posts, papers, and packages into structured knowledge (relevance scoring, capabilities, and API usage guides).
*   **Dynamic Code Generation**: Compiles ready-to-run Python tools, `SKILL.md` documents, and MCP server configuration blocks.
*   **Sandbox & AST Verification**: Runs generated code inside temporary, isolated sandboxes and parses code structures using Abstract Syntax Trees (AST) to block malicious syntax (e.g. `eval`, `exec`, `shell=True`).
*   **Atomic Merging & Rollback**: Backs up changed files, writes code atomically, hot-reloads the agent registry, and supports immediate rollback.

### Control Commands:
Interact with the evolution engine directly from the chat:
*   `nexus status` — Print status, database statistics, and evolution changelogs.
*   `nexus scan_now` — Force an immediate crawler and self-evolution run.
*   `nexus pause` — Pause the background engine and trigger the kill switch.
*   `nexus resume` — Resume the background engine.
*   `nexus rollback --token <token>` — Revert the codebase to a specific backup point.

---

## Quick Install

### Linux, macOS, WSL2, Termux

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```

### Windows (native, PowerShell)

Run this in PowerShell:

```powershell
iex (irm https://hermes-agent.nousresearch.com/install.ps1)
```

The installer handles everything: uv, Python 3.11, Node.js, ripgrep, ffmpeg, and portable Git Bash.

After installation:

```bash
source ~/.bashrc    # reload shell
python cli.py       # start chatting!
```

---

## Configuration

Nexus configuration is managed under `~/.hermes/nexus.yaml` (Windows: `%LOCALAPPDATA%\hermes\nexus.yaml`):

```yaml
enabled: false                    # Set to true to start the background daemon
mode: full_auto                   # full_auto | semi_auto | cautious
scan_interval_minutes: 30
max_evolutions_per_day: 50
safety:
  require_sandbox: true
  security_scan: true
  backup_before_modify: true
  kill_switch: false
sources:
  github: true
  pypi: true
  npm: true
  arxiv: true
  hackernews: true
```
