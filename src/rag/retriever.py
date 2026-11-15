"""
Backward-Compatible RAG Bridge Module
File: src/rag/retriever.py
"""
from src.graphrag.retriever import (
    AnalystAnswer,
    GraphRAGRetriever,
    _ENTITY_SPECS,
    _IPV4,
    _URL,
    _SHA256,
    _SHA1,
    _MD5,
    _DOMAIN,
    _QUOTED,
    _NAMED,
    _TITLE,
    _STOP,
    _neighborhood_cypher,
    _conflicts_from_claims,
    _node,
    _answer_text,
)

__all__ = ["GraphRAGRetriever", "AnalystAnswer"]
