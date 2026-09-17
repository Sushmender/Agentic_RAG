import os
import requests
from dotenv import load_dotenv

from pathlib import Path

# Load environment variables
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# OpenRouter Settings
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nvidia/llama-nemotron-embed-vl-1b-v2:free")
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "nvidia/llama-nemotron-rerank-vl-1b-v2:free")

# Groq Settings
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL = os.getenv("PRIMARY_LLM_MODEL", "qwen/qwen3.8-27b")



def test_openrouter():
    print(f"\n--- Testing OpenRouter ({OPENROUTER_MODEL}) ---")
    if not OPENROUTER_API_KEY:
        print("[FAIL] OPENROUTER_API_KEY is not set in .env")
        return

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Agentic_RAG",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "user", "content": "Hello! Please reply with a short one sentence greeting."}
        ]
    }
    
    try:
        response = requests.post(f"{OPENROUTER_BASE_URL}/chat/completions", headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        print("[SUCCESS] OpenRouter Test Successful!")
        print("Response:", result["choices"][0]["message"]["content"])
    except Exception as e:
        print("[FAIL] OpenRouter Test Failed!")
        print(f"Error: {e}")
        if 'response' in locals() and hasattr(response, 'text'):
            print(f"Response text: {response.text}")


def test_groq():
    print(f"\n--- Testing Groq ({GROQ_MODEL}) ---")
    if not GROQ_API_KEY:
        print("[FAIL] GROQ_API_KEY is not set in .env")
        return

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "user", "content": "Hello! Please reply with a short one sentence greeting."}
        ]
    }
    
    try:
        response = requests.post(f"{GROQ_BASE_URL}/chat/completions", headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        print("[SUCCESS] Groq Test Successful!")
        print("Response:", result["choices"][0]["message"]["content"])
    except Exception as e:
        print("[FAIL] Groq Test Failed!")
        print(f"Error: {e}")
        if 'response' in locals() and hasattr(response, 'text'):
            print(f"Response text: {response.text}")


def test_openrouter_embedding():
    print(f"\n--- Testing OpenRouter Embedding ({EMBEDDING_MODEL}) ---")
    if not OPENROUTER_API_KEY:
        print("[FAIL] OPENROUTER_API_KEY is not set in .env")
        return

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": EMBEDDING_MODEL,
        "input": "This is a test sentence for embedding."
    }
    
    try:
        response = requests.post(f"{OPENROUTER_BASE_URL}/embeddings", headers=headers, json=data)
        response.raise_for_status()
        print("[SUCCESS] OpenRouter Embedding Test Successful!")
    except Exception as e:
        print("[FAIL] OpenRouter Embedding Test Failed!")
        print(f"Error: {e}")
        if 'response' in locals() and hasattr(response, 'text'):
            print(f"Response text: {response.text}")

def test_openrouter_reranker():
    print(f"\n--- Testing OpenRouter Reranker ({RERANKER_MODEL}) ---")
    if not OPENROUTER_API_KEY:
        print("[FAIL] OPENROUTER_API_KEY is not set in .env")
        return

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # OpenRouter uses the /api/v1/rerank endpoint for rerank models
    data = {
        "model": RERANKER_MODEL,
        "query": "What is the capital of France?",
        "documents": [
            "Paris is the capital of France.",
            "London is the capital of the UK."
        ]
    }
    
    try:
        response = requests.post(f"{OPENROUTER_BASE_URL}/rerank", headers=headers, json=data)
        response.raise_for_status()
        print("[SUCCESS] OpenRouter Reranker Test Successful!")
    except Exception as e:
        print("[FAIL] OpenRouter Reranker Test Failed!")
        print(f"Error: {e}")
        if 'response' in locals() and hasattr(response, 'text'):
            print(f"Response text: {response.text}")


if __name__ == "__main__":
    print("Starting Model Tests...")
    test_openrouter()
    test_groq()
    test_openrouter_embedding()
    test_openrouter_reranker()
    print("\nTests completed.")
