---
name: skill-seekers
description: "Convert docs, repos, and PDFs into Claude AI skills."
version: 1.0.0
author: Alex Agent (from yusufkaraaslan/Skill_Seekers)
license: MIT
platforms: [linux, macos, windows]
metadata:
  alex:
    tags: [skills, documentation, github, pdf, claude, mcp, web-scraping]
    related_skills: [research, plan, alex-agent-skill-authoring]
---

# Skill Seekers

## Overview

Convert documentation websites, GitHub repositories, and PDFs into ready-to-use Claude AI skills with automatic conflict detection. Skill Seekers (by yusufkaraaslan) handles multi-source ingestion, conflict resolution, and structured skill output.

**What it does:**
- Scrapes documentation websites and generates structured skills
- Converts GitHub repositories into skill definitions
- Extracts content from PDFs and produces agent-ready skills
- Detects and resolves conflicts between overlapping skill definitions

## When to Use

- Importing an external tool or library's documentation as a reusable agent skill
- Converting a GitHub project into a skill the agent can reference
- Building a skill from a technical PDF or specification document
- Creating skill definitions from multi-source documentation (docs + repo + PDF)

## Prerequisites

- Python 3.10+ with required dependencies (see the Skill Seekers repo)
- Access to the source content (URL, GitHub repo path, or PDF file)
- Output directory for generated skills

## Quick Reference

| Source Type | Command Pattern | Output |
|-------------|----------------|--------|
| Documentation URL | `python -m skill_seekers docs <url>` | SKILL.md from web content |
| GitHub Repository | `python -m skill_seekers repo <owner>/<name>` | SKILL.md from repo analysis |
| PDF File | `python -m skill_seekers pdf <path>` | SKILL.md from PDF content |

## Procedure

1. **Install Skill Seekers.**
   ```bash
   pip install skill-seekers
   ```
   Or clone from [github.com/yusufkaraaslan/Skill_Seekers](https://github.com/yusufkaraaslan/Skill_Seekers).

2. **Choose your source type.**
   - **Website docs:** Point to the documentation root URL.
   - **GitHub repo:** Use `owner/repo` format.
   - **PDF:** Provide a local file path or URL.

3. **Generate the skill.**
   ```bash
   python -m skill_seekers docs https://example.com/docs
   ```

4. **Review the output.**
   - Check generated frontmatter for correct `name`, `description`, `tags`.
   - Verify conflict detection output if ingesting multiple sources.
   - Validate the SKILL.md follows agent skill conventions.

5. **Integrate into the agent's skill tree.**
   - Place under `skills/<category>/<name>/` or `optional-skills/<category>/<name>/`.
   - Ensure the description meets the ≤60-char standard.
   - Add relevant `metadata.alex.tags` and `related_skills`.

## Pitfalls

1. **Generated descriptions are often too long.** Skill Seekers auto-generates descriptions from source content — trim to ≤60 chars.
2. **Missing frontmatter fields.** Auto-generated SKILL.md may omit `version`/`author`/`license` — add them to match peer conventions.
3. **Overlapping skill definitions.** When ingesting multiple sources for the same topic, review conflict detection output carefully before merging.
4. **No agent-tool mapping.** Convert any shell commands in the generated skill to native Alex tool names (`` `terminal` ``, `` `web_extract` ``, `` `read_file` ``).
5. **Forgetting platform gating.** If the generated skill uses POSIX-only primitives, add the appropriate `platforms:` restriction.

## Verification Checklist

- [ ] SKILL.md passes frontmatter validation (name, description, version, author, license)
- [ ] Description ≤ 60 characters and trigger-focused
- [ ] Shell commands in body replaced with native Alex tool references
- [ ] `platforms:` correctly set based on actual dependencies
- [ ] Conflict detection reviewed (if multi-source)
- [ ] Skill placed in correct category directory
- [ ] `metadata.alex.tags` populated with relevant keywords
- [ ] `related_skills` references in-repo skills

## Reference

Original source: [yusufkaraaslan/Skill_Seekers](https://github.com/yusufkaraaslan/Skill_Seekers) — 14.3k stars, Python, AST-based conflict detection.
