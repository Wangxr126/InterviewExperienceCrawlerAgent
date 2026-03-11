#!/bin/bash
# 以模型常驻显存方式启动 Ollama（OLLAMA_KEEP_ALIVE=-1）
# 首次使用前请先拉取模型：ollama pull qwen2.5:1.5b
export OLLAMA_KEEP_ALIVE=-1
ollama serve
