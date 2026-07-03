#!/usr/bin/env python3
"""
Alex Agent Unified Runner
Coordinates path mapping, environment loading, and bootstraps the AIAgent
with full developer toolsets and agentic workflows.
"""

import os
import sys
import argparse
from pathlib import Path

# Add the agent module directory to the system path
WORKSPACE_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(WORKSPACE_DIR))
print(f"✅ Added {WORKSPACE_DIR.name} to python module paths.")

# Import agent components
try:
    from run_agent import AIAgent
    from toolsets import resolve_toolset, _ALEX_CORE_TOOLS
    print("✅ Successfully imported AIAgent and toolsets modules.")
except ImportError as e:
    print(f"❌ Failed to import agent libraries: {e}")
    sys.exit(1)


def load_env():
    """Loads environment variables from local .env files if present."""
    env_path = WORKSPACE_DIR / ".env"
    
    if env_path.exists():
        print(f"🔌 Loading environment keys from: {env_path.name}")
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip().strip('"').strip("'")
    else:
        print("⚠️ No .env file found. Ensure API keys are set in your shell environment.")


def run_diagnostic():
    """Checks dependencies and model key configurations."""
    print("\n🔍 Running Alex Agent System Diagnostics...")
    load_env()
    
    # Check for keys
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    
    print("-" * 50)
    print(f"Anthropic API Key: {'AVAILABLE' if anthropic_key else 'NOT CONFIGURED'}")
    print(f"OpenAI API Key:    {'AVAILABLE' if openai_key else 'NOT CONFIGURED'}")
    print("-" * 50)
    print(f"Available tools in core schema: {len(_ALEX_CORE_TOOLS)}")
    print("Ready to launch agentic workflows.\n")


def run_agent(query: str, model: str, max_turns: int):
    """Bootstraps and executes a conversation turn with the agent."""
    load_env()
    
    # Initialize the agentic runtime
    print(f"🚀 Bootstrapping Alex Agent [Model: {model}]...")
    try:
        agent = AIAgent(
            model=model,
            max_iterations=max_turns,
            save_trajectories=True,
            verbose_logging=True
        )
    except Exception as e:
        print(f"❌ Failed to initialize Agentic Runtime: {e}")
        sys.exit(1)
        
    print(f"\n📝 Query: {query}")
    print("=" * 60)
    
    # Execute the agent loop
    result = agent.run_conversation(query)
    
    print("=" * 60)
    print("\n📋 Execution Summary:")
    print(f"  Completed: {result['completed']}")
    print(f"  API Calls: {result['api_calls']}")
    print(f"  Messages:  {len(result['messages'])}")
    if result['final_response']:
        print("\n🎯 Final Response:")
        print(result['final_response'])


def main():
    parser = argparse.ArgumentParser(description="Alex Agent Runner Interface")
    parser.add_argument("--query", "-q", type=str, help="Prompt query for the agent to execute")
    parser.add_argument("--model", "-m", type=str, default="claude-3-5-sonnet-20241022", help="Model descriptor (Anthropic/OpenAI/Ollama)")
    parser.add_argument("--max-turns", "-t", type=int, default=30, help="Maximum agent loop iterations")
    parser.add_argument("--diagnostic", "-d", action="store_true", help="Run path and key diagnostics")
    
    args = parser.parse_args()
    
    if args.diagnostic:
        run_diagnostic()
    elif args.query:
        run_agent(args.query, args.model, args.max_turns)
    else:
        # Launch interactive diagnostic prompt helper
        run_diagnostic()
        print("💡 Usage Examples:")
        print("  python alex_agent_runner.py -q \"Create a python server in /tmp/server.py and verify it runs\"")
        print("  python alex_agent_runner.py -m \"gpt-4o\" -q \"Refactor code in my project\"")


if __name__ == "__main__":
    main()
