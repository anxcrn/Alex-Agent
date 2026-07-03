---
name: fullstack-developer
description: "Use all dev tools: git, test, lint, build, debug, deploy, CI."
version: 1.0.0
author: Alex Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  alex:
    tags: [development, git, testing, linting, building, debugging, devops, ci-cd, fullstack]
    related_skills: [test-driven-development, systematic-debugging, requesting-code-review, plan]
---

# Fullstack Developer Skill

## Overview

You have full control of all development tools. Use the `git` tool (structured version control), `dev` tool (test/lint/build/format/install/audit), and `terminal` tool (any other command) to handle every aspect of software development autonomously.

**You can do everything a human developer can do** — version control, testing, linting, building, debugging, profiling, code review, deployment, containerization, database management, API development, documentation, and CI/CD.

## When to Use

- Any software development task across the full stack
- Version control operations (commit, push, branch, merge, PRs)
- Writing, testing, and debugging code in any language
- Building, linting, and formatting projects
- Managing dependencies and auditing for vulnerabilities
- Deploying applications and managing infrastructure
- Code review and quality assurance
- Project scaffolding and migration
- Containerization with Docker
- Database schema and query management

## Priority Tool Selection

| Task | Primary Tool | When to Use |
|------|-------------|-------------|
| Git operations | `git` tool | Always — structured schema, error handling, PR management |
| Test/lint/build/format | `dev` tool | Always — auto-detects project type and toolchain |
| File editing | `write_file`, `patch`, `read_file` | For code changes |
| Code search | `search_files` | For finding definitions, usages, patterns |
| Raw commands | `terminal` | For tools not covered by `git`/`dev` |
| Sub-tasks | `delegate_task` | For parallel or complex sub-tasks |
| Documentation | `web_search`, `web_extract` | For research and docs lookup |

## Version Control

Use the `git` tool for all version control. It supports every standard git operation plus PR management.

**Key operations:**
```
git(operation="status")                    # Check working tree
git(operation="add", args=["."])           # Stage all changes
git(operation="commit", message="feat: ...")  # Commit with message
git(operation="push")                      # Push to remote
git(operation="branch", branch_name="feat-x")  # Create branch
git(operation="checkout", branch_name="feat-x")  # Switch branch
git(operation="pr_create", pr_title="...", pr_body="...")  # Create PR
git(operation="pr_list")                   # List PRs
git(operation="log", args=["--oneline", "-10"])  # View recent history
```

**Merge conflicts:** When `git(operation="merge")` or `git(operation="rebase")` reports conflicts:
1. Run `git(operation="status")` to see conflicted files
2. Read each conflicted file with `read_file`
3. Use `write_file` or `patch` to resolve conflicts
4. Run `git(operation="add", args=["<resolved-file>"])`
5. Run `git(operation="commit", message="Resolve merge conflicts")` or `git(operation="rebase", args=["--continue"])`

## Testing

Use `dev(operation="test")` to run tests — it auto-detects the framework:

| Project Type | Framework Detected | Command Used |
|-------------|-------------------|--------------|
| Python | pytest / unittest | `pytest` or `python -m unittest` |
| JavaScript/TypeScript | jest / vitest / mocha | `npm test` / `yarn test` / `pnpm test` |
| Rust | cargo test | `cargo test` |
| Go | go test | `go test ./...` |
| Java/Kotlin | gradle / maven | `gradle test` / `mvn test` |

**Coverage:** Use `dev(operation="coverage")` to run tests with coverage reporting.

**Target specific tests:** Pass `target="tests/test_file.py"` or `args=["-v", "-k", "pattern"]`.

## Linting & Formatting

Use `dev(operation="lint")` to lint and `dev(operation="format")` to format:

```
dev(operation="lint")                       # Check all files
dev(operation="lint", args=["--select", "F401"])  # Check specific rule
dev(operation="format")                     # Format all files
dev(operation="format", args=["--check"])   # Check formatting without changing
dev(operation="fix")                        # Auto-fix lint issues
```

## Building & Installing

```
dev(operation="build")                      # Build the project
dev(operation="install")                    # Install dependencies
dev(operation="clean")                      # Clean build artifacts
dev(operation="outdated")                   # List outdated dependencies
```

## Security Auditing

```
dev(operation="audit")                      # Run security audit
```

Supported: `npm audit`, `yarn audit`, `pnpm audit`, `pip-audit`, `cargo audit`, `go vulnerability check`.

## Type Checking

```
dev(operation="typecheck")                  # Run type checker
```

Auto-detects: mypy/pyright (Python), tsc (TypeScript), cargo check (Rust), go vet (Go).

## CI Pipeline

```
dev(operation="ci")                         # Run full pipeline: lint → test → typecheck → build
```

## Debugging

See the dedicated debugging skills for structured methodology:
- `systematic-debugging` — 4-phase root-cause analysis
- `python-debugpy` — Python debugging with pdb/debugpy/DAP
- `node-inspect-debugger` — Node.js debugging with --inspect/CDP

For ad-hoc debugging, use:
- `dev(operation="test", args=["-vvs"])` — verbose test output
- `terminal` with language-specific debuggers (gdb, lldb, etc.)
- `read_file` to inspect code, then reason about the bug

## Code Review

See `requesting-code-review` skill for the full pre-commit checklist:
- Security scan for hardcoded secrets, injection risks
- Quality gates (error handling, type safety, edge cases)
- Formatting and lint compliance
- Test coverage verification

## Deployment

For deployment, use `terminal` with the appropriate tools:
- **Docker:** `docker build`, `docker compose up`, `docker push`
- **Cloud CLIs:** `aws`, `gcloud`, `az`, `flyctl`, `railway`, `vercel`
- **SSH:** `ssh user@host` for bare-metal deployment
- **Package publish:** `npm publish`, `twine upload`, `cargo publish`

See `optional-skills/devops/docker-management/` for Docker-specific workflows.

## Containerization (Docker)

```
terminal("docker build -t myapp .")          # Build image
terminal("docker compose up -d")             # Start services
terminal("docker ps")                        # List containers
terminal("docker logs <container>")         # View logs
terminal("docker exec -it <container> sh")  # Shell into container
```

## Database Management

Use `terminal` with database CLIs:
- **SQLite:** `sqlite3 database.db "SELECT * FROM users;"`
- **PostgreSQL:** `psql -d mydb -c "SELECT * FROM users;"`
- **MySQL:** `mysql -e "SELECT * FROM users;" mydb`
- **MongoDB:** `mongosh --eval "db.users.find()"`
- **Redis:** `redis-cli GET key`

For schema migrations, use the project's migration tool (Alembic, Prisma, Sequelize, etc.):
```
terminal("alembic upgrade head")
terminal("npx prisma migrate dev")
```

## Profiling & Performance

```
terminal("python -m cProfile -o profile.out script.py")  # Python profile
terminal("npx react-profile")                             # React profile
terminal("cargo bench")                                   # Rust benchmarks
terminal("go test -bench=. ./...")                        # Go benchmarks
```

Use `dev(operation="coverage")` for test coverage analysis.

## API Development

- **Testing APIs:** `terminal("curl -X POST https://api.example.com/endpoint")`
- **Running dev servers:** `terminal("npm run dev")` or `terminal("uvicorn main:app --reload")`
- **API docs:** Use `web_extract` to read OpenAPI/Swagger docs, then `dev(operation="test")` with API test suites

## Project Scaffolding

```
terminal("npx create-react-app my-app")     # React
terminal("cargo new my-project")            # Rust
terminal("go mod init my-project")          # Go
terminal("npm init")                        # JavaScript/TypeScript
terminal("uv init")                         # Python (with uv)
```

## Common Pitfalls

1. **Using raw terminal for git when `git` tool handles it better.** The `git` tool gives structured results with error context. Use it instead of `terminal("git ...")` for most operations.
2. **Forgetting `dev` tool auto-detection.** The `dev` tool detects your project type and picks the right commands. Don't hardcode `pytest` if the project uses `unittest`.
3. **Running CI step-by-step.** Use `dev(operation="ci")` to run the full pipeline in one call (lint → test → typecheck → build).
4. **Not using `patch` for code changes.** For surgical edits, prefer `patch` over `write_file` to minimize diff and preserve context.
5. **Ignoring existing skills.** Check `skills_list` for specialized skills — debugging, code review, and planning all have dedicated skills.
6. **Skipping `dev(operation="audit")` before publishing.** Always audit dependencies for known vulnerabilities before deploying or publishing.

## Verification Checklist

- [ ] Git operations use the `git` tool with structured parameters
- [ ] Test/lint/build/format use the `dev` tool with auto-detection
- [ ] Code changes go through `read_file` → `patch`/`write_file` cycle
- [ ] Full CI pipeline executed before marking work complete
- [ ] Dependencies audited for vulnerabilities
- [ ] Code review checklist completed (see `requesting-code-review` skill)
- [ ] Tests written or updated for new/changed behavior
- [ ] Linting passes with no errors
- [ ] Build succeeds
- [ ] Changes committed with descriptive message and pushed
