"""
AI 项目分类器
根据 repo 的名称、描述、topics 判断是否 AI 相关，并打上分类标签
"""

# 各分类的关键词规则，顺序即优先级
CATEGORY_RULES = [
    {
        "slug": "mcp",
        "keywords": [
            "mcp", "model context protocol", "model-context-protocol",
            "mcp-server", "mcp-client", "mcp tool",
        ],
    },
    {
        "slug": "agent",
        "keywords": [
            "agent", "multi-agent", "autonomous agent", "ai agent",
            "agentic", "autoagent", "autogpt", "babyagi", "crewai",
            "langgraph", "agentgpt", "openagents", "superagi",
            "agent framework", "agent workflow",
        ],
    },
    {
        "slug": "rag",
        "keywords": [
            "rag", "retrieval augmented", "retrieval-augmented",
            "vector database", "vector db", "vectordb", "vector store",
            "embedding", "knowledge base", "knowledge graph",
            "semantic search", "document qa", "document chat",
            "chroma", "weaviate", "pinecone", "qdrant", "milvus", "faiss",
            "langchain", "llamaindex", "llama-index",
        ],
    },
    {
        "slug": "llm",
        "keywords": [
            "llm", "large language model", "gpt", "gemini",
            "llama", "mistral", "qwen", "deepseek", "chatgpt",
            "openai api", "anthropic api", "language model", "foundation model",
            "transformer", "bert", "t5",
            "prompt engineering", "chat model", "instruct model",
            "ollama", "vllm", "text generation", "claude api", "claude model",
        ],
    },
    {
        "slug": "vision",
        "keywords": [
            "image generation", "text to image", "text-to-image",
            "stable diffusion", "diffusion model", "midjourney",
            "dall-e", "dalle", "controlnet", "lora", "dreambooth",
            "image recognition", "object detection", "yolo",
            "computer vision", "multimodal", "vision language",
            "vlm", "clip", "sam", "segment anything",
            "image editing", "inpainting", "super resolution",
        ],
    },
    {
        "slug": "audio",
        "keywords": [
            "speech recognition", "asr", "tts", "text to speech",
            "text-to-speech", "voice", "audio generation",
            "music generation", "whisper", "speech synthesis",
            "voice cloning", "audio model", "sound generation",
        ],
    },
    {
        "slug": "training",
        "keywords": [
            "fine-tuning", "finetuning", "fine tuning", "rlhf",
            "reinforcement learning from human feedback",
            "lora", "qlora", "peft", "sft", "dpo", "ppo",
            "model training", "pre-training", "pretraining",
            "dataset", "training data", "annotation",
        ],
    },
    {
        "slug": "inference",
        "keywords": [
            "inference", "model serving", "model deployment",
            "quantization", "int4", "int8", "gguf", "ggml",
            "tensorrt", "onnx", "triton", "model optimization",
            "llm inference", "fast inference", "vllm",
            "model compression", "pruning", "distillation",
        ],
    },
    {
        "slug": "codegen",
        "keywords": [
            "code generation", "code completion", "copilot",
            "coding assistant", "ai coding", "code llm",
            "devin", "cursor", "github copilot", "codegeex",
            "codex", "starcoder", "code model", "programming assistant",
            "automated coding", "code review ai",
        ],
    },
    {
        "slug": "robotics",
        "keywords": [
            "robotics", "robot", "embodied", "embodied ai",
            "reinforcement learning", "rl", "gym", "simulation",
            "autonomous driving", "self-driving", "drone",
            "manipulation", "locomotion",
        ],
    },
    {
        "slug": "safety",
        "keywords": [
            "ai safety", "alignment", "red team", "red teaming",
            "jailbreak", "adversarial", "hallucination",
            "bias", "fairness", "explainability", "interpretability",
            "trustworthy ai", "responsible ai",
        ],
    },
    {
        "slug": "toolchain",
        "keywords": [
            "langchain", "llamaindex", "haystack", "semantic kernel",
            "ai framework", "llm framework", "ai sdk", "ai toolkit",
            "ai platform", "mlops", "llmops", "ai ops",
            "ai workflow", "ai pipeline", "ai application",
            "chatbot", "ai assistant", "ai tool",
            "agentic", "skills framework", "superpowers",
            "claude code", "coding workflow", "vibe coding",
        ],
    },
    {
        "slug": "dataset",
        "keywords": [
            "dataset", "benchmark", "evaluation", "leaderboard",
            "mmlu", "hellaswag", "humaneval", "gsm8k",
            "training data", "data collection", "data annotation",
            "synthetic data",
        ],
    },
]

# 通用 AI 关键词，用于判断是否 AI 相关
AI_GENERAL_KEYWORDS = [
    "ai", "artificial intelligence", "machine learning", "ml",
    "deep learning", "neural network", "nlp", "natural language",
    "generative", "gen ai", "genai",
]


def _normalize(text: str) -> str:
    return text.lower().strip()


def _text_contains(text: str, keyword: str) -> bool:
    """检查文本是否包含关键词（词边界匹配）"""
    normalized = _normalize(text)
    kw = _normalize(keyword)
    # 简单包含检查，对于多词短语直接 in 即可
    return kw in normalized


def classify_repo(
    name: str,
    description: str | None,
    topics: list[str] | None,
) -> dict:
    """
    对一个 repo 进行分类

    Returns:
        {
            "is_ai": bool,
            "category_slug": str | None,   # 主分类
            "sub_categories": list[str],    # 所有匹配的分类
            "ai_score": float,              # 0~1 相关度
            "matched_keywords": list[str],  # 命中的关键词
        }
    """
    # 拼接所有文本用于匹配
    topics_text = " ".join(topics or [])
    full_text = f"{name} {description or ''} {topics_text}"

    matched_categories: list[str] = []
    matched_keywords: list[str] = []

    for rule in CATEGORY_RULES:
        for kw in rule["keywords"]:
            if _text_contains(full_text, kw):
                if rule["slug"] not in matched_categories:
                    matched_categories.append(rule["slug"])
                if kw not in matched_keywords:
                    matched_keywords.append(kw)
                break  # 每个分类命中一个关键词即可

    # 判断是否 AI 相关
    is_ai = len(matched_categories) > 0
    if not is_ai:
        for kw in AI_GENERAL_KEYWORDS:
            if _text_contains(full_text, kw):
                is_ai = True
                matched_keywords.append(kw)
                break

    # 计算 AI 相关度评分（命中分类数 / 总分类数，最高 1.0）
    ai_score = min(len(matched_categories) / 3.0, 1.0) if matched_categories else (
        0.3 if is_ai else 0.0
    )

    return {
        "is_ai": is_ai,
        "category_slug": matched_categories[0] if matched_categories else None,
        "sub_categories": matched_categories,
        "ai_score": round(ai_score, 2),
        "matched_keywords": matched_keywords[:10],  # 最多保留 10 个
    }
