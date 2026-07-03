import os
import json
import urllib.request
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

def get_nexus_llm_client():
    """Get the LLM client and model name for the Nexus evolution engine.
    
    Prefers OpenAI/custom API if keys are set, otherwise falls back to local Ollama.
    """
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("ALEX_LLM_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL") or os.environ.get("ALEX_LLM_BASE_URL")
    model = os.environ.get("ALEX_LLM_MODEL") or "gpt-4o-mini"
    
    if api_key:
        try:
            client = OpenAI(api_key=api_key, base_url=base_url)
            return client, model
        except Exception as e:
            logger.warning("[Nexus/LLM] Failed to initialize OpenAI client: %s", e)
            
    # Fallback to local Ollama
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=1.5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                models = [m['name'] for m in data.get('models', [])]
                if models:
                    # Look for best coding/reasoning model
                    chosen_model = models[0]
                    for m in models:
                        m_lower = m.lower()
                        if "coder" in m_lower or "deepseek" in m_lower or "qwen" in m_lower or "llama" in m_lower:
                            chosen_model = m
                            break
                    logger.info("[Nexus/LLM] Detected local Ollama. Using model: %s", chosen_model)
                    client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
                    return client, chosen_model
    except Exception as e:
        logger.debug("[Nexus/LLM] Local Ollama not detected or reachable: %s", e)
        
    return None, None
