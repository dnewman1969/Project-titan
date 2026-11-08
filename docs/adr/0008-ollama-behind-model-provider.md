# ADR 0008: LLM runtime (D8)

- **Status:** Accepted
- **Date:** 2026-11-08
- **Decision register:** D8 in [Section 0 of the architecture spec](../titan-architecture-spec.md#0-decision-register)

## Context

LLM runtime for Titan v1, a local-first Windows desktop application that must share one gaming PC with the
game, OBS and a local LLM.

## Decision

Ollama (user-installed, `127.0.0.1:11434`) behind `ModelProvider`. Second built-in provider: any OpenAI-compatible server (llama.cpp, LM Studio, vLLM)

## Alternatives rejected

Hard-coding Ollama

## Rationale

Keeps Titan model-agnostic. Each agent role maps to a model in `models.yaml`.

## Consequences

- Agent roles map to models in `config/models.yaml`; no code imports the Ollama client directly.
- An OpenAI-compatible provider is built in, so llama.cpp, LM Studio and vLLM work without new code.
