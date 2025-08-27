# ai_providers/config.py
"""
AI服务配置模块
包含所有AI服务的默认配置、API端点、模型列表等常量
"""
from typing import Dict, Any, List, Optional

# --- 全局常量 ---
INITIAL_CANDIDATES_K = 50
FINAL_TOP_K = 3

# --- 占位符密钥，用于测试或未配置API时 ---
DUMMY_API_KEY = "dummy_key"

# 全局模型初始化占位符（用于确保返回零向量时不报错）
GLOBAL_PLACEHOLDER_ZERO_VECTOR = [0.0] * 1024  # 匹配数据库Vector(1024)维度

# --- 通用大模型 API 配置示例 ---
DEFAULT_LLM_API_CONFIG = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "chat_path": "/chat/completions",
        "default_model": "gpt-4o",
        "available_models": ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo", "gpt-4o", "gpt-5-2025-08-07","gpt-5-mini-2025-08-07","gpt-5-nano-2025-08-07"]
    },
     "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "chat_path": "/chat/completions",
        "default_model": "deepseek-chat",
        "available_models": ["deepseek-chat", "deepseek-reasoner"]
    },
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1",
        "chat_path": "/chat/completions",
        "default_model": "deepseek-ai/DeepSeek-V3",
        "available_models": ["deepseek-ai/DeepSeek-R1", "deepseek-ai/DeepSeek-V3","BAAI/bge-m3","BAAI/bge-reranker-v2-m3"]
    },
    "huoshanengine": {
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "chat_path": "/chat/completions",
        "default_model": "doubao-1-5-thinking-pro-250415",
        "available_models": ["doubao-1-5-thinking-pro-250415", "doubao-1-5-thinking-vision-pro-250428", "kimi-k2-250711"]
    },
    "kimi": {
        "base_url": "https://api.moonshot.cn/v1",
        "chat_path": "/chat/completions",
        "default_model": "kimi-k2-0711-preview",
        "available_models": ["kimi-k2-0711-preview", "moonshot-v1-auto"]
    },
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "chat_path": "/chat/completions",
        "default_model": "glm-4.5v",
        "available_models": ["glm-4.5v", "glm-4.5", "glm-4.5-x", "glm-4.5-air", "glm-4-flash"]
    },
    "custom_openai": { # 作为自定义OpenAI兼容服务的模板
            "base_url": None, # 用户必须提供，此处为None表示无默认值
            "chat_path": "/chat/completions", # OpenAI兼容API的标准路径
            "default_model": None, # 用户必须提供，此处为None表示无默认值
            "available_models": ["any_openai_compatible_model"] # 占位符，用户可使用任意模型ID
    }
}

# --- TTS 服务配置常量 ---
DEFAULT_TTS_CONFIGS = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "tts_path": "/audio/speech",
        "default_model": "gpt-4o-mini-tts",
        "available_models": ["gpt-4o-mini-tts"],
        "default_voice": "alloy",
        "available_voices": ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
    },
    "gemini": {
        "notes": "Gemini TTS direct API integration not yet implemented. Requires Google Cloud/Vertex AI TTS API setup."
    },
    "aliyun": {
        "notes": "Aliyun TTS direct API integration not yet implemented. Requires Aliyun SDK/API setup."
    },
    "siliconflow": {
        "notes": "SiliconFlow TTS direct API integration not yet implemented. (假设SiliconFlow有独立的TTS服务而非仅LLM)."
    },
    "default_gtts": {
        "notes": "Default gTTS fallback, no API key needed."
    }
}

# --- 搜索引擎配置 ---
DEFAULT_SEARCH_CONFIGS = {
    "bing": {
        "base_url": "https://api.bing.microsoft.com/v7.0/search",
        "subscription_key_header": "Ocp-Apim-Subscription-Key"
    },
    "tavily": {
        "base_url": "https://api.tavily.com/search",
        "api_key_header": "Api-Key"
    }
}

# --- 嵌入和重排服务配置 ---
DEFAULT_EMBEDDING_CONFIGS = {
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1",
        "embeddings_path": "/embeddings",
        "default_model": "BAAI/bge-m3",
        "available_models": ["BAAI/bge-m3", "text-embedding-3-small", "text-embedding-3-large"]
    }
}

DEFAULT_RERANK_CONFIGS = {
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1",
        "rerank_path": "/rerank", 
        "default_model": "BAAI/bge-reranker-v2-m3",
        "available_models": ["BAAI/bge-reranker-v2-m3"]
    }
}

def get_available_llm_configs() -> Dict[str, Dict[str, Any]]:
    """获取可用的LLM配置信息"""
    configs = {}
    for llm_type, data in DEFAULT_LLM_API_CONFIG.items():
        configs[llm_type] = {
            "default_model": data["default_model"],
            "available_models": data["available_models"],
            "notes": f"请访问 {data['base_url']} 对应的服务商官网获取API密钥。"
        }
        if llm_type == "custom_openai":
            configs[llm_type]["notes"] = "自定义OpenAI兼容服务：需要提供完整的API基础URL、API密钥和模型ID。"
            configs[llm_type]["default_model"] = None
            configs[llm_type]["available_models"] = ["任意兼容OpenAI API的自定义模型"]
    return configs


# --- 多模型ID处理辅助函数 ---
def parse_llm_model_ids(llm_model_ids_json: Optional[str]) -> Dict[str, List[str]]:
    """
    解析存储在数据库中的 JSON 格式的模型ID配置
    返回: {"服务商类型": ["模型ID1", "模型ID2"]}
    """
    if not llm_model_ids_json:
        return {}
    
    try:
        import json
        parsed = json.loads(llm_model_ids_json)
        if isinstance(parsed, dict):
            # 确保值都是列表格式
            result = {}
            for provider, models in parsed.items():
                if isinstance(models, str):
                    result[provider] = [models]
                elif isinstance(models, list):
                    result[provider] = models
                else:
                    result[provider] = []
            return result
        return {}
    except (json.JSONDecodeError, TypeError):
        return {}


def get_user_model_for_provider(llm_model_ids_json: Optional[str], provider: str, fallback_model_id: Optional[str] = None) -> Optional[str]:
    """
    从用户的多模型配置中获取指定服务商的首选模型
    如果没有配置，则使用fallback_model_id或配置中的默认模型
    """
    model_ids_dict = parse_llm_model_ids(llm_model_ids_json)
    
    # 从多模型配置中获取
    provider_models = model_ids_dict.get(provider, [])
    if provider_models:
        return provider_models[0]  # 使用第一个作为默认
    
    # 如果没有配置，尝试使用fallback
    if fallback_model_id:
        return fallback_model_id
        
    # 最后使用系统默认配置
    config = DEFAULT_LLM_API_CONFIG.get(provider)
    if config:
        return config.get("default_model")
    
    return None


def serialize_llm_model_ids(model_ids_dict: Dict[str, List[str]]) -> str:
    """
    将模型ID字典序列化为JSON字符串以存储到数据库
    """
    try:
        import json
        return json.dumps(model_ids_dict, ensure_ascii=False)
    except (TypeError, ValueError):
        return "{}"
