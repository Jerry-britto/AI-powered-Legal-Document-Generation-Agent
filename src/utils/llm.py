"""
LLM Factory supporting Groq and Gemini via LangChain.
"""

import os
from typing import Optional
from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel

load_dotenv()


def get_llm(
    provider: str = "gemini",
    model_name: Optional[str] = None,
    temperature: float = 0.0
) -> BaseChatModel:
    """
    Instantiate and return a LangChain chat model.
    Supported providers: 'groq', 'gemini'.
    """
    provider_clean = provider.strip().lower()

    if provider_clean == "groq":
        from langchain_groq import ChatGroq
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY is not set in environment or .env file.")
        
        target_model = model_name or "qwen/qwen3.8-27b"
        return ChatGroq(
            model=target_model,
            api_key=api_key,
            temperature=temperature,
        )

    elif provider_clean == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set in environment or .env file.")
        
        target_model = model_name or "gemini-3.6-flash"
        return ChatGoogleGenerativeAI(
            model=target_model,
            google_api_key=api_key,
            temperature=temperature,
        )

    else:
        raise ValueError(f"Unsupported LLM provider '{provider}'. Must be 'groq' or 'gemini'.")
