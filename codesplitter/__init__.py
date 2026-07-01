"""CodeSplitter: a local-first, repo knowledge base.

Pipeline:
    repos  --split-->  chunks  --embed (Ollama)-->  vectors  --> Chroma store
    question  --embed-->  nearest chunks  --> LLM (Kimi)  --> answer
"""

__version__ = "0.1.0"
