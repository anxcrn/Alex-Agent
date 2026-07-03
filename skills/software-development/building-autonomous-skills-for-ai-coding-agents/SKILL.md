---
name: building-autonomous-skills-for-ai-coding-agents
description: "Write clean tools and custom skills for AI coding agents."
version: 1.0.0
author: Alex Agent (adapted from YouTube tutorial)
license: MIT
platforms: [linux, macos, windows]
metadata:
  alex:
    tags: [skills, agent-authoring, autonomous, coding-agents]
    related_skills: [alex-agent-skill-authoring, plan, requesting-code-review]
---

# Building Autonomous Skills For AI Coding Agents

## Overview

This skill teaches you how to write clean, modular tools and custom skills for AI coding agents. Based on a tutorial covering tool design, skill structure, and integration patterns, it helps you extend agent capabilities without bloating the core.

**What it covers:**
- Tool design principles for AI agents
- Skill structure and lifecycle
- Integration patterns between tools and skills
- Testing and iterating on custom skills

## When to Use

- Creating a new tool or skill for an AI coding agent
- Refactoring an existing tool to be more agent-friendly
- Learning best practices for agent-extensible design
- Reviewing a skill PR against established patterns

## Prerequisites

- Familiarity with the agent's tool registry and SKILL.md format
- Access to the agent's tool directory or skill tree

## Quick Reference

| Concept | Guidance |
|---------|----------|
| Tool footprint | Prefer extending existing code over new core tools |
| Skill structure | SKILL.md with YAML frontmatter + markdown body |
| Integration | Register via registry, wire into toolset |
| Testing | Validate frontmatter, test skill behavior with mock agent |

## Procedure

1. **Understand the agent's extension model.**
   - Tools go in `tools/`, registered via `registry.register()`.
   - Skills go in `skills/<category>/<name>/SKILL.md`.
   - New core tools are high-cost — prefer CLI commands + skills, service-gated tools, plugins, or MCP servers first.

2. **Define the skill's trigger and behavior.**
   - Write a ≤60-char description focused on the trigger class.
   - Identify what agent behavior should change when the skill loads.

3. **Draft the SKILL.md.**
   - Start with `---` at byte 0.
   - Include `name`, `description`, `version`, `author`, `license`, `metadata.alex.tags`, and `metadata.alex.related_skills`.
   - Use sections: Overview, When to Use, Prerequisites, Procedure, Pitfalls, Verification Checklist.

4. **Ship supporting assets.**
   - Scripts → `scripts/`, references → `references/`, templates → `templates/`.
   - Keep SKILL.md focused; push bulky material behind pointers.

5. **Validate before committing.**
   - Frontmatter parses as valid YAML.
   - `name` ≤ 64 chars, `description` ≤ 1024 chars (aim for ≤60).
   - Total file ≤ 100,000 chars.

## Pitfalls

1. **Writing a core tool when a skill would do.** Every core tool ships on every API call. Start with the least-footprint option.
2. **Skipping frontmatter fields.** Missing `version`/`author`/`license`/`metadata` makes the skill look unfinished — peers all have them.
3. **Duplicate descriptions.** Keep the trigger in the description and the behavior in the body; don't repeat.
4. **No-op prose.** Generic advice ("be careful", "be thorough") rarely changes agent behavior. Replace with checkable completion criteria.
5. **Forgetting to commit.** In-repo skills are source code, not runtime state — always `git add` + commit.

## Verification Checklist

- [ ] SKILL.md starts with `---` at byte 0 and closes with `\n---\n`
- [ ] Frontmatter has all peer-standard fields (name, description, version, author, license, metadata)
- [ ] Description ≤ 60 chars, trigger-focused, ends with a period
- [ ] Body follows peer-matched section order
- [ ] No-op prose and duplicated rules removed
- [ ] Supporting files placed in `scripts/`, `references/`, or `templates/`
- [ ] Tool references in prose use backtick names of native Alex tools

## Reference

Original source: [Building Autonomous Skills for AI Coding Agents](https://www.youtube.com/watch?v=agent-skills-builder)
