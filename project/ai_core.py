# project/ai_core.py
from fastapi import HTTPException, status
import pandas as pd
import numpy as np
from cryptography.fernet import Fernet
import os, httpx, json, uuid, time, asyncio, ast, re, PyPDF2, requests, io
from typing import List, Dict, Any, Optional, Literal, Union
from sqlalchemy.orm import Session
from sqlalchemy import text
from sklearn.metrics.pairwise import cosine_similarity
from datetime import datetime, timedelta
from gtts import gTTS
from docx import Document as DocxDocument
from models import Student, Project, KnowledgeBase, KnowledgeArticle, Note, Course, KnowledgeDocument, \
    KnowledgeDocumentChunk, UserMcpConfig, UserSearchEngineConfig, CourseMaterial, AIConversationMessage,AIConversationTemporaryFile, AIConversation
from schemas import WebSearchResult, WebSearchResponse, McpToolDefinition, McpStatusResponse, MatchedProject, \
    MatchedStudent, MatchedCourse

# --- 全局常量 ---
INITIAL_CANDIDATES_K = 50
FINAL_TOP_K = 3

# --- 全局辅助函数：技能解析 ---
def _parse_single_skill_entry_to_dict(single_skill_raw_data: Any) -> Optional[Dict]:
    """
    尝试将各种原始技能条目格式 (dict, str, list) 规范化为 {'name': '...', 'level': '...'}.
    特别处理异常字符串化和嵌套的情况。
    """
    default_skill_level = "初窥门径"
    valid_skill_levels = ["初窥门径", "登堂入室", "融会贯通", "炉火纯青"]

    if isinstance(single_skill_raw_data, dict):
        # 如果已经是字典，直接返回（但做一下格式清理）
        name = single_skill_raw_data.get("name")
        level = single_skill_raw_data.get("level", default_skill_level)
        if name and isinstance(name, str) and name.strip():
            formatted_name = name.strip()
            formatted_level = level if level in valid_skill_levels else default_skill_level
            return {"name": formatted_name, "level": formatted_level}
        return None
    elif isinstance(single_skill_raw_data, str):
        processed_str = single_skill_raw_data.strip()
        if not processed_str:  # 如果是空字符串，直接返回None
            return None

        # --- PRE-PARSING CLEANUP ---
        # 尝试剥离外部引号和处理转义符
        initial_str = processed_str
        for _ in range(2):  # 尝试两次以移除多层外部引号
            if (initial_str.startswith(("'", '"')) and initial_str.endswith(("'", '"')) and len(initial_str) > 1):
                initial_str = initial_str[1:-1]
        initial_str = initial_str.replace('\\"', '"').replace("\\'", "'")
        # --- END PRE-PARSING CLEANUP ---

        parsing_attempts = [
            (json.loads, "json.loads"),
            (ast.literal_eval, "ast.literal_eval")
        ]

        for parser, parser_name in parsing_attempts:
            try:
                parsed_content = parser(initial_str)  # 使用清理后的字符串进行解析

                if isinstance(parsed_content, dict) and "name" in parsed_content:
                    name = parsed_content["name"]
                    level = parsed_content.get("level", default_skill_level)
                    if isinstance(name, str) and name.strip():
                        formatted_name = name.strip()
                        formatted_level = level if level in valid_skill_levels else default_skill_level
                        print(f"DEBUG_MATCH_SKILLS: Skill '{processed_str}' successfully parsed by {parser_name}.")
                        return {"name": formatted_name, "level": formatted_level}
                elif isinstance(parsed_content, list) and len(parsed_content) > 0:
                    # 如果字符串解析出来是列表，尝试从中提取第一个有效的技能字典
                    for item in parsed_content:
                        # 递归调用自身来处理列表中的每个项目
                        recursively_parsed_item = _parse_single_skill_entry_to_dict(item)
                        if recursively_parsed_item:
                            print(
                                f"WARNING_MATCH_SKILLS: Skill string '{processed_str}' parsed by {parser_name} to a list. Recursively extracted valid dict: {recursively_parsed_item['name']}. Please check import data formatting.")
                            return recursively_parsed_item  # 返回第一个在列表中找到的有效字典
                    # 如果列表中没有找到有效字典，则记录警告并返回None
                    print(
                        f"WARNING_MATCH_SKILLS: Skill string '{processed_str}' parsed by {parser_name} to a list, but no valid dict found within. Parsed content: {parsed_content}")
            except (json.JSONDecodeError, ValueError, SyntaxError) as e:
                pass  # 继续下一个解析尝试

        # Fallback 3: 如果以上解析都失败，尝试将其作为纯技能名称处理
        if processed_str.strip():
            print(
                f"WARNING_MATCH_SKILLS: SKILL_PARSE_FALLBACK: '{processed_str}' not parsable as valid structured data. Treating as simple name.")
            return {"name": processed_str.strip(), "level": default_skill_level}
        return None  # Fallback for empty/whitespace string

    # 直接处理接收到的列表类型
    elif isinstance(single_skill_raw_data, list):
        print(
            f"WARNING_MATCH_SKILLS: Received a list as a single skill entry: '{single_skill_raw_data}'. Attempting to extract valid dict by iterating.")
        for item in single_skill_raw_data:
            # 递归调用自身来处理列表中的每个项目
            parsed_item = _parse_single_skill_entry_to_dict(item)
            if parsed_item and "name" in parsed_item and parsed_item["name"].strip():
                print(f"DEBUG_MATCH_SKILLS: Successfully extracted skill '{parsed_item['name']}' from nested list.")
                return parsed_item  # 返回第一个在列表中找到的有效字典
        print(
            f"WARNING_MATCH_SKILLS: No valid skill dict found within the received list: {single_skill_raw_data}. Returning None.")
        return None  # 列表中没有找到有效字典

    # Fallback for all other unexpected types (None, int, etc.)
    else:
        print(
            f"WARNING_MATCH_SKILLS: Unexpected single skill entry type: {type(single_skill_raw_data)} -> '{single_skill_raw_data}'. Returning None.")
        return None


def _ensure_top_level_list(raw_input: Any) -> List[Any]:
    """
    确保原始传入的技能列表数据本身是可迭代的 Python 列表
    (例如，如果从数据库读取出来的是字符串化的整个技能列表，如 "'[{...}, {...}]'")
    """
    if isinstance(raw_input, list):
        return raw_input

    if isinstance(raw_input, str):
        processed_input = raw_input.strip()

        for _ in range(2):
            if (processed_input.startswith(("'", '"')) and processed_input.endswith(("'", '"')) and len(
                    processed_input) > 1):
                processed_input = processed_input[1:-1]
        processed_input = processed_input.replace('\\"', '"').replace("\\'", "'")

        try:
            parsed = json.loads(processed_input)
            if isinstance(parsed, list):
                return parsed
            print(
                f"WARNING_MATCH_SKILLS: Top-level string '{raw_input}' is JSON but not a list. Returning empty list.")
            return []
        except json.JSONDecodeError:
            pass

        try:
            parsed = ast.literal_eval(processed_input)
            if isinstance(parsed, list):
                return parsed
            print(
                f"WARNING_MATCH_SKILLS: Top-level string '{raw_input}' is literal but not a list. Returning empty list.")
            return []
        except (ValueError, SyntaxError):
            pass

        print(
            f"WARNING_MATCH_SKILLS: Top-level string '{raw_input}' cannot be parsed as a list. Returning empty list.")
        return []

    if raw_input is None:
        return []

    print(
        f"WARNING_MATCH_SKILLS: Top-level input type '{type(raw_input)}' is unexpected. Value: '{raw_input}'. Returning empty list.")
    return []


# --- 加密库 (用于API密钥) ---
_ENCRYPTION_KEY_STR = os.getenv("ENCRYPTION_KEY")

if not _ENCRYPTION_KEY_STR:
    raise ValueError("ENCRYPTION_KEY 环境变量未设置，加密功能无法初始化。请在 .env 文件中设置。")

try:
    # Fernet 密钥必须是 base64-encoded bytes
    FERNET_KEY = Fernet(_ENCRYPTION_KEY_STR.encode('utf-8')) # <<<< 关键：将字符串编码为字节并初始化Fernet
except Exception as e:
    raise ValueError(f"ENCRYPTION_KEY 格式无效或初始化失败: {e}. 请确保其为32位URL-safe Base64编码的字符串。")

def encrypt_key(key: str) -> str:
    """加密字符串"""
    return FERNET_KEY.encrypt(key.encode('utf-8')).decode('utf-8')

def decrypt_key(encrypted_key: str) -> str:
    """解密字符串"""
    return FERNET_KEY.decrypt(encrypted_key.encode('utf-8')).decode('utf-8')


EMBEDDING_API_URL = "https://api.siliconflow.cn/v1/embeddings"
RERANKER_API_URL = "https://api.siliconflow.cn/v1/rerank"
EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
RERANKER_MODEL_NAME = "BAAI/bge-reranker-v2-m3"

# --- 占位符密钥，用于测试或未配置API时 ---
DUMMY_API_KEY = "dummy_key_for_testing_without_api"

# 全局模型初始化占位符（用于确保返回零向量时不报错） ---
# 这是一个通用占位符，如果 get_embeddings_from_api 无法获取到合适的 key，就会返回这个。
GLOBAL_PLACEHOLDER_ZERO_VECTOR = [0.0] * 1024

# --- 通用大模型 API 配置示例 (回答模型由用户选择) ---
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
# 这些是各TTS提供商的固定API端点、默认模型和可用语音等信息
DEFAULT_TTS_CONFIGS = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "tts_path": "/audio/speech",
        "default_model": "gpt-4o-mini-tts",
        "available_models": ["gpt-4o-mini-tts"],
        "default_voice": "alloy",
        "available_voices": ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
    },
    # 以下提供商需要更复杂的SDK或HTTP API集成
    "gemini": {
        "notes": "Gemini TTS direct API integration not yet implemented. Requires Google Cloud/Vertex AI TTS API setup."
    },
    "aliyun": {
        "notes": "Aliyun TTS direct API integration not yet implemented. Requires Aliyun SDK/API setup."
    },
    "siliconflow": {
        "notes": "SiliconFlow TTS direct API integration not yet implemented. (假设SiliconFlow有独立的TTS服务而非仅LLM)."
    },
    "default_gtts": { # 定义一个表示 gTTS 回退的类型，用作内部标记
        "notes": "Default gTTS fallback, no API key needed."
    }
}


def get_available_llm_configs() -> Dict[str, Dict[str, Any]]:
    configs = {}
    for llm_type, data in DEFAULT_LLM_API_CONFIG.items():
        configs[llm_type] = {
            "default_model": data["default_model"],
            "available_models": data["available_models"],
            "notes": f"请访问 {data['base_url']} 对应的服务商官网获取API密钥。"
        }
        if llm_type == "custom_openai":
            configs[llm_type]["notes"] = "自定义OpenAI兼容服务：需要提供完整的API基础URL、API密钥和模型ID。"
            configs[llm_type]["default_model"] = None # 强调无默认模型
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
        return json.dumps(model_ids_dict, ensure_ascii=False)
    except (TypeError, ValueError):
        return "{}"


async def call_llm_api(
        messages: List[Dict[str, Any]],
        user_llm_api_type: str,
        user_llm_api_key: str,
        user_llm_api_base_url: Optional[str] = None,
        user_llm_model_id: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None
) -> Dict[str, Any]:
    api_base_url_final: str = None
    chat_path_final: str = None
    model_to_use_final: str = None

    # <<<< MODIFICATION: Handle custom_openai type >>>>
    if user_llm_api_type == "custom_openai":
        if not user_llm_api_base_url:
            raise ValueError("对于自定义OpenAI兼容服务 ('custom_openai')，必须提供API基础URL (llm_api_base_url)。")
        if not user_llm_model_id:
            raise ValueError("对于自定义OpenAI兼容服务 ('custom_openai')，必须提供LLM模型ID (llm_model_id)。")

        api_base_url_final = user_llm_api_base_url
        chat_path_final = "/chat/completions"  # OpenAI兼容API的标准路径
        model_to_use_final = user_llm_model_id

        # Check if API Key is a dummy key for custom_openai chat
        if user_llm_api_key == "dummy_key_for_testing_without_api":
            print(
                "WARNING_LLM_CHAT: Custom_openai LLM API Key is a dummy key. LLM chat will be skipped and return placeholder.")
            return {"choices": [{"message": {
                "content": "Custom OpenAI compatible LLM API not configured or key is dummy. Cannot generate dynamic content."}}]}

    else:
        # For known LLM types, retrieve configuration from DEFAULT_LLM_API_CONFIG
        config = DEFAULT_LLM_API_CONFIG.get(user_llm_api_type)
        if not config:
            raise ValueError(f"不支持的LLM类型: {user_llm_api_type}")

        # Choose base_url: user-provided first, then default from config
        api_base_url_final = user_llm_api_base_url or config["base_url"]
        chat_path_final = config["chat_path"]

        # Choose model: user-provided first, then default from config
        model_to_use_final = user_llm_model_id or config["default_model"]

        # Check if API Key is a dummy key for known LLM chat
        if user_llm_api_key == "dummy_key_for_testing_without_api":
            print(
                f"WARNING_LLM_CHAT: LLM API Key for {user_llm_api_type} is a dummy key. LLM chat will be skipped and return placeholder.")
            return {"choices": [
                {"message": {"content": "LLM API not configured or key is dummy. Cannot generate dynamic content."}}]}

    api_url = f"{api_base_url_final}{chat_path_final}"

    headers = {
        "Authorization": f"Bearer {user_llm_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_to_use_final,  # Use the determined model
        "messages": messages,
        "temperature": 0.5,
        "top_p": 0.9
    }

    if tools:
        payload["tools"] = tools
    if tool_choice:
        payload["tool_choice"] = tool_choice

    print(
        f"DEBUG_AI: Calling LLM API: Type={user_llm_api_type}, Model={model_to_use_final}, URL={api_url}, Tools={bool(tools)}")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(api_url, headers=headers, json=payload, timeout=180)
            response.raise_for_status()
            data = response.json()
            return data

        except httpx.RequestError as e:
            print(f"LLM API请求错误 ({user_llm_api_type}): {e}")
            print(f"LLM API响应内容: {getattr(e, 'response', None).text if getattr(e, 'response', None) else '无'}")
            raise
        except KeyError as e:
            print(f"LLM API响应格式错误 ({user_llm_api_type}): {e}. 响应: {data}")
            raise


async def call_web_search_api(
        query: str,
        search_engine_type: str,
        api_key: str,
        base_url: Optional[str] = None
) -> List[WebSearchResult]:
    results: List[WebSearchResult] = []
    async with httpx.AsyncClient() as client:
        headers = {"Content-Type": "application/json"}

        if search_engine_type == "bing":
            search_url = base_url or "https://api.bing.microsoft.com/v7.0/search"
            headers["Ocp-Apim-Subscription-Key"] = api_key
            params = {"q": query, "count": 5}
            try:
                response = await client.get(search_url, headers=headers, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                for webpage in data.get("webPages", {}).get("value", []):
                    results.append(WebSearchResult(
                        title=webpage.get("name", "无标题"),
                        url=webpage.get("url", "#"),
                        snippet=webpage.get("snippet", "无摘要")
                    ))
                print(f"DEBUG_SEARCH: Bing search successful for '{query}'. Found {len(results)} results.")
            except httpx.RequestError as e:
                print(
                    f"ERROR_SEARCH: Bing search failed: {e}. Response: {getattr(e, 'response', None).text if getattr(e, 'response', None) else 'N/A'}")
                raise

        elif search_engine_type == "tavily":
            search_url = base_url or "https://api.tavily.com/rpc/rawsearch"
            payload = {
                "api_key": api_key,
                "query": query,
                "search_depth": "basic",
                "include_answer": False,
                "max_results": 5
            }
            try:
                response = await client.post(search_url, headers=headers, json=payload, timeout=10)
                response.raise_for_status()
                data = response.json()
                for item in data.get("results", []):
                    results.append(WebSearchResult(
                        title=item.get("title", "无标题"),
                        url=item.get("url", "#"),
                        snippet=item.get("content", "无摘要")
                    ))
                print(f"DEBUG_SEARCH: Tavily search successful for '{query}'. Found {len(results)} results.")
            except httpx.RequestError as e:
                print(
                    f"ERROR_SEARCH: Tavily search failed: {e}. Response: {getattr(e, 'response', None).text if getattr(e, 'response', None) else 'N/A'}")
                raise

        elif search_engine_type == "baidu" or search_engine_type == "google_cse" or search_engine_type == "custom":
            print(
                f"WARNING_SEARCH: {search_engine_type.capitalize()} search is simulated. Requires actual API integration and possibly custom base_url handling.")
            results.append(WebSearchResult(
                title=f"{search_engine_type.capitalize()} 搜索模拟结果：{query}",
                url=base_url or "#",
                snippet=f"这是{search_engine_type.capitalize()}搜索的模拟结果，实际API接入需要合法授权和开发。"
            ))

        else:
            raise ValueError(f"不支持的搜索引擎类型: {search_engine_type}")

    return results


async def synthesize_speech(
        text: str,
        lang: str = 'zh-CN',  # 基础语言代码，用于 gTTS 和某些 API
        tts_type: Optional[str] = None,  # 语音提供商类型
        api_key: Optional[str] = None,  # 用户提供的 API 密钥
        base_url: Optional[str] = None,  # API 基础 URL
        model_id: Optional[str] = None,  # 特定模型 ID
        voice_name: Optional[str] = None  # 特定语音名称/ID
) -> str:
    """
    根据用户配置的TTS类型和参数将文本转换为语音文件，并返回文件路径。
    如果未配置或配置无效，则回退到gTTS。
    """
    tts_audio_dir = "temp_audio"
    os.makedirs(tts_audio_dir, exist_ok=True)
    audio_filename = f"tts_{uuid.uuid4().hex}.mp3"
    audio_filepath = os.path.join(tts_audio_dir, audio_filename)

    # 默认使用 gTTS 回退机制
    use_gtts_fallback = True
    provider_config = DEFAULT_TTS_CONFIGS.get(tts_type)

    # 检查是否配置了有效API密钥和支持的提供商
    if tts_type and provider_config and api_key and api_key != "dummy_key_for_testing_without_api":
        use_gtts_fallback = False  # 尝试使用配置的提供商

        if tts_type == "openai":
            openai_tts_config = DEFAULT_TTS_CONFIGS["openai"]
            tts_base_url = base_url or openai_tts_config["base_url"]
            tts_api_url = f"{tts_base_url}{openai_tts_config['tts_path']}"
            tts_model = model_id or openai_tts_config["default_model"]
            tts_voice = voice_name or openai_tts_config["default_voice"]

            # 简单的语音名称验证
            if tts_voice not in openai_tts_config["available_voices"]:
                print(
                    f"WARNING_TTS: OpenAI voice '{tts_voice}' not recognized or available. Falling back to default: {openai_tts_config['default_voice']}.")
                tts_voice = openai_tts_config["default_voice"]

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": tts_model,
                "input": text,
                "voice": tts_voice,
                # "response_format": "mp3" # 默认就是mp3
            }

            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(tts_api_url, headers=headers, json=payload, timeout=30)
                    response.raise_for_status()  # 检查HTTP响应状态码

                    # OpenAI TTS 返回音频流，直接写入文件
                    with open(audio_filepath, "wb") as f:
                        for chunk in response.iter_bytes(chunk_size=8192):  # 迭代写入大文件
                            f.write(chunk)

                    print(
                        f"DEBUG_TTS: OpenAI TTS successful using model '{tts_model}', voice '{tts_voice}'. Saved to {audio_filepath}.")
                    return audio_filepath
            except httpx.RequestError as e:
                print(
                    f"ERROR_TTS: OpenAI TTS API request failed: {e}. Response: {getattr(e, 'response', None).text if getattr(e, 'response', None) else 'N/A'}")
                use_gtts_fallback = True  # API 调用失败，回退到 gTTS
            except Exception as e:
                print(f"ERROR_TTS: OpenAI TTS processing failed: {e}")
                use_gtts_fallback = True  # 其他处理失败，回退到 gTTS

        # 对于其他提供商，目前仅打印警告并回退，或抛出未实现异常
        elif tts_type in ["gemini", "aliyun", "siliconflow"]:
            print(
                f"WARNING_TTS: TTS provider '{tts_type}' is registered but its API integration is not yet fully implemented in ai_core.py. Falling back to gTTS.")
            use_gtts_fallback = True
            # 如果不想回退，可以抛出异常：
        else:
            print(f"WARNING_TTS: Unknown TTS provider type '{tts_type}' configured. Falling back to gTTS.")
            use_gtts_fallback = True
    else:
        print("DEBUG_TTS: No valid TTS API configuration found or dummy key used. Proceeding with gTTS fallback.")
        # use_gtts_fallback 已经为 True

    # gTTS Fallback
    if use_gtts_fallback:
        try:
            # gTTS 有其支持的语言列表，我们只使用其支持的语言
            gtts_lang = lang if lang in ['zh-CN', 'en', 'zh_CN', 'en_US', 'en_GB'] else 'zh-CN'  # 更精确的gTTS语言匹配
            print(f"DEBUG_TTS: Using gTTS fallback with language: {gtts_lang}.")

            # gTTS 不支持选择特定语音，voice_name 和 model_id 将被忽略
            # gTTS.save 是同步IO操作。在高度并发的应用中，这应该使用 asyncio.to_thread 运行。
            # 当前为了简化，直接调用。
            tts = gTTS(text=text, lang=gtts_lang)
            tts.save(audio_filepath)

            print(f"DEBUG_TTS: gTTS fallback successful. Saved to {audio_filepath}.")
            return audio_filepath
        except Exception as e:
            print(f"ERROR_TTS: gTTS fallback failed: {e}. Unable to synthesize speech.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail=f"文本转语音失败: {e}. 请联系管理员。")


# --- 嵌入向量生成函数 (仅在满足条件下调用硅基流动的API) ---
async def get_embeddings_from_api(
        texts: List[str],
        api_key: Optional[str] = None,  # 用户传入的 (解密后的) API key
        llm_type: Optional[str] = None,  # 用户配置的 LLM 类型
        llm_base_url: Optional[str] = None,  # 用户配置的 LLM base_url (这里不用于嵌入URL，但作为上下文)
        llm_model_id: Optional[str] = None  # 用户配置的 LLM model_id (这里不用于嵌入模型名，但作为上下文)
) -> List[List[float]]:
    """
    根据给定的文本生成嵌入向量。
    优先使用用户配置的'siliconflow'埋点API Key和其专有模型。
    如果用户未配置'siliconflow'LLM或提供的密钥无效，则返回零向量。
    """
    if not texts:
        return []

    # 只有当用户LLM类型为'siliconflow'且提供了有效的API Key时，才进行实际API调用
    if llm_type == "siliconflow" and api_key and api_key != DUMMY_API_KEY:
        final_api_key = api_key
        final_base_url = EMBEDDING_API_URL
        final_model_name = EMBEDDING_MODEL_NAME

        headers = {
            "Authorization": f"Bearer {final_api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Apikey": final_api_key  # SiliconFlow也支持X-DashScope-Apikey
        }
        payload = {
            "model": final_model_name,
            "input": texts
        }

        print(
            f"DEBUG_EMBEDDING_API: Calling SiliconFlow embedding API ({llm_type}): URL={final_base_url}, Model={final_model_name}")

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(final_base_url, headers=headers, json=payload, timeout=30)
                response.raise_for_status()
                data = response.json()
                embeddings = [item["embedding"] for item in data["data"]]
                return embeddings
            except httpx.RequestError as e:
                print(f"ERROR_EMBEDDING_API: Request failed for '{final_model_name}': {e}. Returning zero vectors.")
                # 这里只打印错误，并返回零向量，确保不中断后续流程
                return [GLOBAL_PLACEHOLDER_ZERO_VECTOR for _ in texts]
            except KeyError as e:
                print(
                    f"ERROR_EMBEDDING_API: Response format error for '{final_model_name}': {e}. Response: {data}. Returning zero vectors.")
                return [GLOBAL_PLACEHOLDER_ZERO_VECTOR for _ in texts]
    else:
        # 如果用户未配置siliconflow LLM或API key无效，则返回零向量。
        # 不再依赖环境变量中的默认嵌入密钥。
        print(
            f"INFO_EMBEDDING_API: User's LLM config is not SiliconFlow or API key is missing/dummy. Returning zero embedding vector.")
        return [GLOBAL_PLACEHOLDER_ZERO_VECTOR for _ in texts]


# --- 重排分数生成函数 (仅在满足条件下调用硅基流动的API) ---
async def get_rerank_scores_from_api(
        query: str,
        texts: List[str],
        api_key: Optional[str] = None,  # 用户传入的 (解密后的) API key
        llm_type: Optional[str] = None,  # 用户配置的 LLM 类型
        llm_base_url: Optional[str] = None,  # 虽然 reranker 不用 base_url，但保持参数一致性
        fallback_to_similarity: bool = False  # 是否回退到文本相似度
) -> List[float]:
    """
    根据查询和文本列表生成重排分数。
    优先使用用户配置的'siliconflow'重排API Key和其专有模型。
    如果用户未配置'siliconflow'LLM或提供的密钥无效，则返回零分数或回退到文本相似度。
    """
    if not texts:
        return []

    # 只有当用户LLM类型为'siliconflow'且提供了有效的API Key时，才进行实际API调用
    if llm_type == "siliconflow" and api_key and api_key != DUMMY_API_KEY:
        final_api_key = api_key
        final_base_url = RERANKER_API_URL
        final_model_name = RERANKER_MODEL_NAME

        headers = {
            "Authorization": f"Bearer {final_api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Apikey": final_api_key  # SiliconFlow也支持X-DashScope-Apikey
        }
        payload = {
            "model": final_model_name,
            "query": query,
            "documents": texts
        }

        print(
            f"DEBUG_RERANKER_API: Calling SiliconFlow reranker API ({llm_type}): URL={final_base_url}, Model={final_model_name}")

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(final_base_url, headers=headers, json=payload, timeout=30)
                response.raise_for_status()
                data = response.json()
                scores = [item["score"] for item in data["results"]]
                print(f"DEBUG_RERANKER_API: Successfully got {len(scores)} rerank scores")
                return scores
            except httpx.RequestError as e:
                print(f"ERROR_RERANKER_API: Request failed for '{final_model_name}': {e}")
                if fallback_to_similarity:
                    print(f"INFO_RERANKER_API: Falling back to text similarity calculation")
                    return _calculate_text_similarity_scores(query, texts)
                return [0.0] * len(texts)
            except KeyError as e:
                print(f"ERROR_RERANKER_API: Response format error for '{final_model_name}': {e}. Response: {data}")
                if fallback_to_similarity:
                    print(f"INFO_RERANKER_API: Falling back to text similarity calculation")
                    return _calculate_text_similarity_scores(query, texts)
                return [0.0] * len(texts)
            except Exception as e:
                print(f"ERROR_RERANKER_API: Unexpected error: {e}")
                if fallback_to_similarity:
                    print(f"INFO_RERANKER_API: Falling back to text similarity calculation")
                    return _calculate_text_similarity_scores(query, texts)
                return [0.0] * len(texts)
    else:
        # 如果用户未配置siliconflow LLM或API key无效
        if fallback_to_similarity:
            print(f"INFO_RERANKER_API: User's LLM config is not SiliconFlow, using text similarity fallback")
            return _calculate_text_similarity_scores(query, texts)
        else:
            print(f"INFO_RERANKER_API: User's LLM config is not SiliconFlow or API key is missing/dummy. Returning zero reranker scores.")
            return [0.0] * len(texts)


def _calculate_text_similarity_scores(query: str, texts: List[str]) -> List[float]:
    """简单的文本相似度计算作为回退"""
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        
        # 使用TF-IDF计算文本相似度
        all_texts = [query] + texts
        vectorizer = TfidfVectorizer(stop_words=None, max_features=1000)
        tfidf_matrix = vectorizer.fit_transform(all_texts)
        
        # 计算查询与每个文档的余弦相似度
        query_vector = tfidf_matrix[0:1]
        doc_vectors = tfidf_matrix[1:]
        similarities = cosine_similarity(query_vector, doc_vectors)[0]
        
        # 归一化到0-1范围
        max_sim = similarities.max() if similarities.max() > 0 else 1.0
        normalized_scores = (similarities / max_sim).tolist()
        
        print(f"DEBUG_RERANKER_FALLBACK: Calculated text similarity scores for {len(texts)} documents")
        return normalized_scores
    except ImportError:
        print(f"WARNING_RERANKER_FALLBACK: sklearn not available, using simple scoring")
        # 如果sklearn不可用，使用简单的字符串匹配评分
        scores = []
        query_words = set(query.lower().split())
        for text in texts:
            text_words = set(text.lower().split())
            if query_words and text_words:
                intersection = query_words.intersection(text_words)
                score = len(intersection) / len(query_words.union(text_words))
            else:
                score = 0.0
            scores.append(score)
        return scores
    except Exception as e:
        print(f"ERROR_RERANKER_FALLBACK: Text similarity calculation failed: {e}")
        return [0.1] * len(texts)  # 返回小的非零值而不是零值


def extract_text_from_document(file_content_bytes: bytes, file_type: str) -> str:
    # 保持同步，因为它涉及到本地文件IO和CPU密集型操作
    text_content = ""
    if not file_content_bytes:
        print(f"WARNING_DOC_PARSE: Received empty file content bytes for type {file_type}.")
        raise ValueError("文件内容为空。")

    # 使用 io.BytesIO 将字节流包装成文件对象，以便 PyPDF2 和 docx 库可以读取它
    file_like_object = io.BytesIO(file_content_bytes)

    if file_type == "application/pdf":
        try:
            # 修改: 使用 file_like_object 代替 filepath
            reader = PyPDF2.PdfReader(file_like_object)
            for page_num in range(len(reader.pages)):
                page = reader.pages[page_num]
                text_content += page.extract_text() or ""
            print(f"DEBUG_DOC_PARSE: Successfully extracted text from PDF (from bytes).")
        except Exception as e:
            print(f"ERROR_DOC_PARSE: Failed to extract text from PDF (from bytes): {e}")
            raise ValueError(f"无法解析PDF文件：{e}")
    elif file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":  # .docx
        try:
            # 修改: 使用 file_like_object 代替 filepath
            doc = DocxDocument(file_like_object)
            for paragraph in doc.paragraphs:
                text_content += paragraph.text + "\n"
            print(f"DEBUG_DOC_PARSE: Successfully extracted text from DOCX (from bytes).")
        except Exception as e:
            print(f"ERROR_DOC_PARSE: Failed to extract text from DOCX (from bytes): {e}")
            raise ValueError(f"无法解析DOCX文件：{e}")
    elif file_type.startswith("text/"):  # .txt 或其他纯文本
        try:
            # 直接解码字节流为文本
            text_content = file_content_bytes.decode('utf-8')
            print(f"DEBUG_DOC_PARSE: Successfully extracted text from TXT (from bytes).")
        except UnicodeDecodeError:
            try: # 尝试其他编码
                text_content = file_content_bytes.decode('gbk', errors='ignore')
                print(f"DEBUG_DOC_PARSE: Successfully extracted text from TXT (from bytes) with GBK encoding.")
            except Exception as e:
                print(f"ERROR_DOC_PARSE: Failed to decode text content from bytes: {e}")
                raise ValueError(f"无法解码文本文件内容：{e}")
        except Exception as e:
            print(f"ERROR_DOC_PARSE: Failed to extract text from TXT (from bytes): {e}")
            raise ValueError(f"无法解析TXT文件：{e}")
    else:
        print(
            f"WARNING_DOC_PARSE: Unsupported file type for text extraction from bytes: {file_type}. Attempting basic text decode."
        )
        try:
            text_content = file_content_bytes.decode('utf-8', errors='ignore')
        except Exception as e:
            raise ValueError(f"不支持的文件类型或无法提取文本 ({file_type})：{e}。")

    if not text_content.strip():
        print(f"WARNING_DOC_PARSE: Extracted content is empty for file of type {file_type}")
        raise ValueError("文件内容为空或无法提取有效文本。")

    return text_content


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    # 保持同步，通常是CPU密集型操作
    if not text:
        return []

    chunks = []
    current_position = 0
    while current_position < len(text):
        end_position = min(current_position + chunk_size, len(text))
        chunk = text[current_position:end_position]
        chunks.append(chunk)
        current_position += (chunk_size - overlap)
        if current_position >= len(text):
            break
    print(f"DEBUG_DOC_PARSE: Text successfully chunked into {len(chunks)} parts.")
    return chunks


# --- Agent工具定义和执行器 ---
# 定义通用的工具Schema for LLM function calling
WEB_SEARCH_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "执行在线网络搜索以获取实时信息或最新数据。当问题涉及到时效性、事实查询、最新新闻、热门话题或无法从已知文档中找到答案时非常有用。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "用于网络搜索的查询关键词或短语。"
                },
                "search_engine_config_id": {
                    "type": "integer",
                    "description": "要使用的搜索引擎配置ID。如果用户未明确指定，应从用户默认配置中选择一个活跃的搜索引擎。"
                }
            },
            "required": ["query", "search_engine_config_id"]
        }
    }
}

RAG_KNOWLEDGE_BASE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "rag_knowledge_base",
        "description": "从用户已上传的知识库文档和笔记中检索信息来回答问题。当问题涉及用户私人文档、特定领域知识、历史笔记或需要参考内部资料时使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "用于在知识库中检索的查询问题。"
                },
                "kb_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "要在其中检索的知识库ID列表。如果用户未明确指定，应使用用户默认的知识库ID。"
                },
                "note_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "要在其中检索的笔记ID列表。如果用户未明确指定，应使用用户默认的笔记ID（如果有的话）。"
                }
            },
            "required": ["query"]
        }
    }
}


async def execute_tool(
        db: Session,
        tool_call_name: str,
        tool_call_args: Dict[str, Any],
        user_id: int
) -> Union[str, List[Dict[str, Any]], Dict[str, Any]]:
    if tool_call_name == "web_search":
        search_query = tool_call_args.get("query")
        search_engine_config_id = tool_call_args.get("search_engine_config_id")

        if not search_engine_config_id:
            default_search_config = db.query(UserSearchEngineConfig).filter(
                UserSearchEngineConfig.owner_id == user_id,
                UserSearchEngineConfig.is_active == True
            ).first()
            if default_search_config:
                search_engine_config_id = default_search_config.id
            else:
                return f"错误：未指定搜索引擎配置ID，且用户未配置活跃的默认搜索引擎。无法执行网络搜索。"

        search_config = db.query(UserSearchEngineConfig).filter(
            UserSearchEngineConfig.id == search_engine_config_id,
            UserSearchEngineConfig.owner_id == user_id,
            UserSearchEngineConfig.is_active == True
        ).first()

        if not search_config:
            return f"错误：搜索引擎配置ID {search_engine_config_id} 未找到、未启用或无权访问。"

        decrypted_key = ""
        if search_config.api_key_encrypted:
            try:
                decrypted_key = decrypt_key(search_config.api_key_encrypted)
            except Exception:
                return "错误：无法解密搜索引擎 API 密钥，请检查配置。"

        try:
            results = await call_web_search_api(
                query=search_query,
                search_engine_type=search_config.engine_type,
                api_key=decrypted_key,
                base_url=getattr(search_config, 'base_url', None)
            )
            formatted_results = []
            for i, res in enumerate(results[:3]):
                formatted_results.append(f"结果 {i + 1}: 标题: {res.title}, 摘要: {res.snippet}, 链接: {res.url}")
            return "网络搜索结果:\n" + "\n".join(formatted_results) if formatted_results else "没有找到相关网络搜索结果。"
        except Exception as e:
            return f"错误：执行网络搜索失败：{e}"

    elif tool_call_name == "rag_knowledge_base":
        rag_query = tool_call_args.get("query")
        kb_ids = tool_call_args.get("kb_ids")
        note_ids = tool_call_args.get("note_ids")
        temp_file_ids = tool_call_args.get("temp_file_ids")
        conversation_id_from_args = tool_call_args.get("conversation_id") # 获取conversation_id

        user_llm_api_key = None
        user_llm_type = None
        user_llm_base_url = None
        user_llm_model_id = None
        user_obj = db.query(Student).filter(Student.id == user_id).first()
        if user_obj and user_obj.llm_api_type == "siliconflow" and user_obj.llm_api_key_encrypted:
            try:
                user_llm_api_key = decrypt_key(user_obj.llm_api_key_encrypted)
                user_llm_type = user_obj.llm_api_type
                user_llm_base_url = user_obj.llm_api_base_url
                # 优先使用新的多模型配置，fallback到原模型ID
                user_llm_model_id = get_user_model_for_provider(
                    user_obj.llm_model_ids, 
                    user_obj.llm_api_type, 
                    user_obj.llm_model_id
                )
            except Exception as e:
                pass

        context_docs = []
        source_articles_info = []

        # 权限验证：验证知识库访问权限
        if kb_ids:
            from sqlalchemy import or_
            accessible_kbs = db.query(KnowledgeBase).filter(
                KnowledgeBase.id.in_(kb_ids),
                or_(
                    KnowledgeBase.owner_id == user_id,
                    KnowledgeBase.access_type == "public"
                )
            ).all()
            kb_ids = [kb.id for kb in accessible_kbs]
            print(f"DEBUG_RAG_TOOL: 验证后可访问的知识库: {kb_ids}")
        else:
            user_kbs = db.query(KnowledgeBase).filter(KnowledgeBase.owner_id == user_id).all()
            kb_ids = [kb.id for kb in user_kbs]
            if not kb_ids:
                pass


        if kb_ids:
            articles_candidate = db.query(KnowledgeArticle).filter(
                KnowledgeArticle.kb_id.in_(kb_ids),
                KnowledgeArticle.author_id == user_id,
                KnowledgeArticle.content.isnot(None)
            ).all()
            for article in articles_candidate:
                if article.content and article.content.strip():
                    context_docs.append({
                        "content": article.title + "\n" + article.content,
                        "type": "knowledge_article",
                        "id": article.id,
                        "title": article.title
                    })

            documents_candidate = db.query(KnowledgeDocument).filter(
                KnowledgeDocument.kb_id.in_(kb_ids),
                KnowledgeDocument.owner_id == user_id,
                KnowledgeDocument.status == "completed"
            ).all()
            for doc in documents_candidate:
                doc_chunks = db.query(KnowledgeDocumentChunk).filter(
                    KnowledgeDocumentChunk.document_id == doc.id,
                    KnowledgeDocumentChunk.owner_id == user_id,
                    KnowledgeDocumentChunk.kb_id == doc.kb_id,
                    KnowledgeDocumentChunk.content.isnot(None),
                    KnowledgeDocumentChunk.embedding.isnot(None)  # 确保有embedding
                ).order_by(KnowledgeDocumentChunk.chunk_index).all()  # 按顺序排列
                combined_doc_content = "\n".join([chunk.content for chunk in doc_chunks if chunk.content])
                if combined_doc_content.strip():
                    context_docs.append({
                        "content": doc.file_name + "\n" + combined_doc_content,
                        "type": "knowledge_document",
                        "id": doc.id,
                        "title": doc.file_name
                    })

        # 权限验证：验证笔记访问权限
        if not note_ids:
            user_notes = db.query(Note).filter(
                Note.owner_id == user_id,
                Note.content.isnot(None)
            ).all()
            note_ids = [note.id for note in user_notes]
        else:
            # 验证用户对这些笔记的访问权限
            user_notes = db.query(Note).filter(
                Note.id.in_(note_ids),
                Note.owner_id == user_id,
                Note.content.isnot(None)
            ).all()
            note_ids = [note.id for note in user_notes]

        if note_ids:
            notes_candidate = db.query(Note).filter(
                Note.id.in_(note_ids),
                Note.owner_id == user_id
            ).all()
            for note in notes_candidate:
                full_note_content = note.title + "\n" + (note.content or "")
                if note.media_url and (note.media_type == "text" or not note.content):
                    full_note_content += f"\n附件链接: {note.media_url}"
                if full_note_content.strip():
                    context_docs.append({
                        "content": full_note_content,
                        "type": "note",
                        "id": note.id,
                        "title": note.title
                    })

        # 权限验证：验证临时文件访问权限
        if temp_file_ids and conversation_id_from_args:
            print(f"DEBUG_RAG_TOOL: 检查 {len(temp_file_ids)} 个临时文件...")
            # 验证临时文件属于指定对话且用户有权限访问
            conversation = db.query(AIConversation).filter(
                AIConversation.id == conversation_id_from_args,
                AIConversation.user_id == user_id
            ).first()
            
            if not conversation:
                print(f"WARNING_RAG_TOOL: 用户 {user_id} 无权访问对话 {conversation_id_from_args}")
                temp_file_ids = []  # 清空临时文件ID列表
            else:
                temp_files_candidate = db.query(AIConversationTemporaryFile).filter(
                    AIConversationTemporaryFile.id.in_(temp_file_ids),
                    AIConversationTemporaryFile.conversation_id == conversation_id_from_args
                ).all()
                
                # 打印所有临时文件的状态
                processing_files = []
                failed_files = []
                
                for temp_file in temp_files_candidate:
                    print(f"DEBUG_RAG_TOOL: 临时文件 {temp_file.id} - 状态: {temp_file.status}, 文件名: {temp_file.original_filename}")
                    if temp_file.status == "completed" and temp_file.extracted_text and temp_file.extracted_text.strip():
                        context_docs.append({
                            "content": temp_file.original_filename + "\n" + temp_file.extracted_text,
                            "type": "ai_temp_file",
                            "id": temp_file.id,
                            "title": temp_file.original_filename
                        })
                        print(f"DEBUG_RAG_TOOL: 临时文件 {temp_file.id} 已添加到上下文")
                    elif temp_file.status == "failed":
                        failed_files.append(temp_file)
                        print(f"WARNING_RAG_TOOL: 临时文件 {temp_file.id} 处理失败: {temp_file.processing_message}")
                    elif temp_file.status in ["pending", "processing"]:
                        processing_files.append(temp_file)
                        print(f"WARNING_RAG_TOOL: 临时文件 {temp_file.id} 仍在处理中，状态: {temp_file.status}")
                    else:
                        print(f"WARNING_RAG_TOOL: 临时文件 {temp_file.id} 内容为空或无法使用")
                
                # 如果有正在处理的文件，给出提示
                if processing_files:
                    processing_names = [f.original_filename for f in processing_files]
                    processing_message = f"正在处理文件：{', '.join(processing_names)}。请稍后再试，或者您可以继续提问，我会基于其他可用信息回答。"
                    # 将处理中的文件信息添加到对话中
                    context_docs.append({
                        "content": processing_message,
                        "type": "system_message", 
                        "id": "processing_files",
                        "title": "文件处理状态"
                    })
                    print(f"DEBUG_RAG_TOOL: 添加了处理中文件的提示信息")
                
                # 如果有处理失败的文件，给出提示
                if failed_files:
                    failed_names = [f"{f.original_filename} ({f.processing_message})" for f in failed_files]
                    failed_message = f"以下文件处理失败：{'; '.join(failed_names)}。我将基于其他可用信息回答您的问题。"
                    context_docs.append({
                        "content": failed_message,
                        "type": "system_message",
                        "id": "failed_files", 
                        "title": "文件处理错误"
                    })
                    print(f"DEBUG_RAG_TOOL: 添加了处理失败文件的提示信息")

        print(f"DEBUG_RAG_TOOL: Collected {len(context_docs)} candidate documents for RAG prior to reranking.")
        if context_docs:
            for i, doc in enumerate(context_docs[:5]):  # 仅打印前5个文档的摘要信息
                content_snippet = doc['content'][:100] + '...' if doc['content'] else 'None'
                print(
                    f"DEBUG_RAG_TOOL_CANDIDATE #{i + 1}: Type: {doc['type']}, Title: {doc.get('title', 'N/A')}, Content snippet: {content_snippet}")
            if len(context_docs) > 5:
                print(f"DEBUG_RAG_TOOL: ... {len(context_docs) - 5} more candidate documents.")
        else:
            print("INFO_RAG_TOOL: No candidate documents (KB, Notes, Temp Files) found for RAG.")


        if not context_docs:
            return "知识库、笔记或临时文件中没有找到与问题相关的文档信息。"

        # 向量相似度预筛选（如果用户配置了有效的embedding API）
        if user_llm_type == "siliconflow" and user_llm_api_key and user_llm_api_key != DUMMY_API_KEY:
            print(f"DEBUG_RAG_TOOL: 开始向量相似度预筛选，候选文档数量: {len(context_docs)}")
            
            # 1. 生成查询向量
            query_embedding_list = await get_embeddings_from_api(
                [rag_query],
                api_key=user_llm_api_key,
                llm_type=user_llm_type,
                llm_base_url=user_llm_base_url,
                llm_model_id=user_llm_model_id
            )
            
            if query_embedding_list and query_embedding_list[0] != GLOBAL_PLACEHOLDER_ZERO_VECTOR:
                query_vector = np.array(query_embedding_list[0]).reshape(1, -1)
                doc_vectors = []
                valid_docs = []
                
                # 2. 收集文档向量
                for doc in context_docs:
                    doc_embedding = None
                    
                    if doc['type'] == 'knowledge_document':
                        # 获取文档块的平均向量
                        doc_chunks = db.query(KnowledgeDocumentChunk).filter(
                            KnowledgeDocumentChunk.document_id == doc['id'],
                            KnowledgeDocumentChunk.embedding.isnot(None)
                        ).all()
                        
                        if doc_chunks:
                            chunk_embeddings = [chunk.embedding for chunk in doc_chunks if chunk.embedding]
                            if chunk_embeddings:
                                doc_embedding = np.mean(chunk_embeddings, axis=0).tolist()
                    
                    elif doc['type'] == 'knowledge_article':
                        # 获取文章的向量
                        article = db.query(KnowledgeArticle).filter(KnowledgeArticle.id == doc['id']).first()
                        if article and article.embedding:
                            doc_embedding = article.embedding
                    
                    elif doc['type'] == 'note':
                        # 获取笔记的向量
                        note = db.query(Note).filter(Note.id == doc['id']).first()
                        if note and note.embedding:
                            doc_embedding = note.embedding
                    
                    # 对于临时文件或没有embedding的文档，使用零向量
                    if doc_embedding is None:
                        doc_embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR
                    
                    doc_vectors.append(doc_embedding)
                    valid_docs.append(doc)
                
                # 3. 计算相似度并筛选
                if doc_vectors and valid_docs:
                    doc_vectors_np = np.array(doc_vectors)
                    similarities = cosine_similarity(query_vector, doc_vectors_np)[0]
                    
                    # 按相似度排序并取前50个
                    similarity_scores = [(i, sim) for i, sim in enumerate(similarities)]
                    similarity_scores.sort(key=lambda x: x[1], reverse=True)
                    
                    # 取前50个最相似的文档，或者所有文档（如果少于50个）
                    top_k = min(50, len(similarity_scores))
                    top_indices = [idx for idx, _ in similarity_scores[:top_k]]
                    
                    context_docs = [valid_docs[i] for i in top_indices]
                    print(f"DEBUG_RAG_TOOL: 向量预筛选完成，保留前 {len(context_docs)} 个相似文档")
                else:
                    print(f"WARNING_RAG_TOOL: 无法进行向量预筛选，使用所有候选文档")
            else:
                print(f"WARNING_RAG_TOOL: 查询向量生成失败，跳过向量预筛选")
        else:
            print(f"INFO_RAG_TOOL: 用户未配置SiliconFlow API，跳过向量预筛选")

        # 内容长度限制
        MAX_CONTENT_LENGTH = 2000  # 每个文档最大长度
        MAX_TOTAL_LENGTH = 10000   # 总内容最大长度
        
        filtered_docs = []
        total_length = 0
        
        for doc in context_docs:
            content = doc["content"]
            if len(content) > MAX_CONTENT_LENGTH:
                content = content[:MAX_CONTENT_LENGTH] + "..."
                doc["content"] = content
            
            if total_length + len(content) <= MAX_TOTAL_LENGTH:
                filtered_docs.append(doc)
                total_length += len(content)
            else:
                break
        
        context_docs = filtered_docs
        print(f"DEBUG_RAG_TOOL: 内容长度限制后保留 {len(context_docs)} 个文档，总长度: {total_length}")

        candidate_contents = [doc["content"] for doc in context_docs]
        if not candidate_contents:
            return "知识库、笔记或临时文件中找到的文档内容为空，无法提取信息。"

        reranked_scores = await get_rerank_scores_from_api(
            rag_query,
            candidate_contents,
            api_key=user_llm_api_key,
            llm_type=user_llm_type,
            fallback_to_similarity=True  # 启用回退机制
        )

        scored_candidates = sorted(
            zip(context_docs, reranked_scores),
            key=lambda x: x[1],
            reverse=True
        )

        context_for_llm = []
        current_context_len = 0
        max_context_len = 3000

        for doc, score in scored_candidates:
            if not doc["content"] or not doc["content"].strip():
                continue
            if current_context_len + len(doc["content"]) <= max_context_len:
                context_for_llm.append(doc)
                current_context_len += len(doc["content"])
            else:
                break

        if not context_for_llm:
            return "虽然在知识库、笔记或临时文件中找到了一些文档，但未能提炼出足够相关或有用的信息来回答问题。"

        retrieved_content = "\n\n".join([doc["content"] for doc in context_for_llm])

        for doc in context_for_llm:
            source_doc_info = {
                "id": doc["id"],
                "title": doc["title"],
                "type": doc["type"],
                "chunk_index": doc.get("chunk_index")
            }
            if doc["type"] == "ai_temp_file":
                temp_file_obj = db.query(AIConversationTemporaryFile).filter(AIConversationTemporaryFile.id == doc["id"]).first()
                if temp_file_obj and hasattr(temp_file_obj, 'oss_object_name'):
                     source_doc_info["file_path"] = f"{os.getenv('OSS_BASE_URL').rstrip('/')}/{temp_file_obj.oss_object_name}"
            source_articles_info.append(source_doc_info)

        return {"context": retrieved_content, "sources": source_articles_info}

    elif tool_call_name.startswith("mcp_"):
        parts = tool_call_name.split("_")
        if len(parts) < 3:
            return f"错误：MCP工具调用格式不正确"

        try:
            mcp_config_id = int(parts[1])
        except (ValueError, TypeError):
            return f"错误：MCP配置ID格式无效"
        
        mcp_tool_id = "_".join(parts[2:])
        
        # 验证工具ID格式，只允许字母、数字和下划线
        import re
        if not re.match(r'^[a-zA-Z0-9_]+$', mcp_tool_id):
            return f"错误：MCP工具ID格式无效"

        mcp_config = db.query(UserMcpConfig).filter(
            UserMcpConfig.id == mcp_config_id,
            UserMcpConfig.owner_id == user_id,
            UserMcpConfig.is_active == True
        ).first()

        if not mcp_config:
            return f"错误：MCP配置未找到或无权访问"

        decrypted_key = ""
        if mcp_config.api_key_encrypted:
            try:
                decrypted_key = decrypt_key(mcp_config.api_key_encrypted)
            except Exception:
                return "错误：无法解密MCP API密钥"

        if mcp_tool_id == "visual_chart_generator":
            chart_type = tool_call_args.get("chart_type")
            data_points = tool_call_args.get("data_points")
            title = tool_call_args.get("title", "")

            if chart_type and data_points:
                img_url = f"https://example.com/charts/{chart_type}_{uuid.uuid4().hex}.png"
                return f"可视化图表已生成：{img_url}。标题：{title}。数据：{data_points}"
            else:
                return "生成可视化图表所需参数不完整。"
        elif mcp_tool_id == "image_generator":
            prompt = tool_call_args.get("prompt")
            style = tool_call_args.get("style", "realistic")

            img_url = f"https://example.com/images/{style}_{uuid.uuid4().hex}.png"
            return f"图像已生成：{img_url}。基于描述：'{prompt}'。"
        elif mcp_tool_id == "generic_tool":
            task = tool_call_args.get("task")
            input_data = tool_call_args.get("input_data")
            
            # 模拟通用MCP工具执行
            result_id = uuid.uuid4().hex[:8]
            return f"MCP服务 {mcp_config.name} 已处理任务 '{task}'，结果ID: {result_id}。输入数据: {input_data[:100]}..."
        else:
            return f"错误：不支持的MCP工具类型"

    else:
        return f"错误：未知工具：{tool_call_name}"



async def get_all_available_tools_for_llm(db: Session, user_id: int) -> List[Dict[str, Any]]:
    tools = []

    # 1. 添加通用的内置工具
    tools.append(WEB_SEARCH_TOOL_SCHEMA)
    tools.append(RAG_KNOWLEDGE_BASE_TOOL_SCHEMA)

    # 2. 添加用户定义和活动的 MCP 工具
    active_mcp_configs = db.query(UserMcpConfig).filter(
        UserMcpConfig.owner_id == user_id,
        UserMcpConfig.is_active == True
    ).all()

    for config in active_mcp_configs:
        # 为每个活跃的MCP配置生成至少一个通用工具，确保不会因为命名问题而无法使用
        has_generated_tool = False
        
        # 1. 检查ModelScope特殊配置
        if "modelscope" in (config.base_url or "").lower() and (config.protocol_type or "").lower() == "sse":
            # 图表生成工具
            if "chart" in (config.name or "").lower() or "visual" in (config.name or "").lower() or "图表" in (config.name or ""):
                tools.append({
                    "type": "function",
                    "function": {
                        "name": f"mcp_{config.id}_visual_chart_generator",
                        "description": f"Generates various chart types (line, bar, pie) from data using MCP service {config.name} ({config.base_url}).",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "chart_type": {"type": "string", "enum": ["line", "bar", "pie"],
                                               "description": "Chart type"},
                                "data_points": {"type": "array", "items": {"type": "object",
                                                                           "properties": {"label": {"type": "string"},
                                                                                          "value": {
                                                                                              "type": "number"}}}},
                                "title": {"type": "string", "description": "Chart title", "nullable": True}
                            },
                            "required": ["chart_type", "data_points"]
                        }
                    }
                })
                has_generated_tool = True
            
            # 图像生成工具
            if "image" in (config.name or "").lower() or "gen" in (config.name or "").lower() or "图像" in (config.name or "") or "生成" in (config.name or ""):
                tools.append({
                    "type": "function",
                    "function": {
                        "name": f"mcp_{config.id}_image_generator",
                        "description": f"Generates high-quality images from text descriptions using MCP service {config.name} ({config.base_url}).",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "prompt": {"type": "string", "description": "Text prompt for image generation"},
                                "style": {"type": "string", "enum": ["realistic", "cartoon", "abstract"],
                                          "description": "Image style", "nullable": True}
                            },
                            "required": ["prompt"]
                        }
                    }
                })
                has_generated_tool = True
                
        # 2. 检查私有MCP配置
        elif "my_private_mcp" == (config.mcp_type or ""):
            tools.append({
                "type": "function",
                "function": {
                    "name": f"mcp_{config.id}_text_summary_tool",
                    "description": f"Summarizes long text using your defined MCP service {config.name}.",
                    "parameters": {"type": "object",
                                   "properties": {"text": {"type": "string", "description": "Text to summarize"}},
                                   "required": ["text"]},
                }
            })
            has_generated_tool = True
        
        # 3. 为没有匹配到特定类型的MCP配置生成通用工具，确保每个配置都能被使用
        if not has_generated_tool:
            tools.append({
                "type": "function",
                "function": {
                    "name": f"mcp_{config.id}_generic_tool",
                    "description": f"Generic MCP tool for {config.name} service. Can handle various tasks based on the service capabilities.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task": {"type": "string", "description": "The task to perform"},
                            "input_data": {"type": "string", "description": "Input data for the task"}
                        },
                        "required": ["task", "input_data"]
                    }
                }
            })
            print(f"DEBUG_TOOL: Generated generic tool for MCP config {config.id} ({config.name})")

    print(f"DEBUG_TOOL: Assembled {len(tools)} available tools for user {user_id}.")
    return tools


async def invoke_agent(
        db: Session,
        user_id: int,
        query: str,
        llm_api_type: str,
        llm_api_key: str,
        llm_api_base_url: Optional[str],
        llm_model_id: Optional[str], # 这个llm_model_id是来自main.py的ai_qa请求或用户默认
        kb_ids: Optional[List[int]] = None,
        note_ids: Optional[List[int]] = None,
        preferred_tools: Optional[Union[List[Literal["rag", "web_search", "mcp_tool"]], str]] = None,
        past_messages: Optional[List[Dict[str, Any]]] = None,
        temp_file_ids: Optional[List[int]] = None,
        conversation_id_for_temp_files: Optional[int] = None,
        # >>> 新增参数，直接控制是否启用工具 <<<
        enable_tool_use: bool = False # 默认为False，即默认不启用工具
) -> Dict[str, Any]:
    messages = past_messages if past_messages is not None else []
    messages.append({"role": "user", "content": query})

    current_turn_messages_to_log = []
    current_turn_messages_to_log.append({
        "role": "user",
        "content": query
    })

    response_data = {}

    tools_to_send_to_llm = []
    tool_choice_param = "none" # 默认不选择任何工具，除非明确启用

    # >>> 核心逻辑修改：根据 enable_tool_use 参数决定是否准备工具 <<<
    if enable_tool_use:
        available_tools_for_llm = await get_all_available_tools_for_llm(db, user_id)
        if preferred_tools is not None:  # 明确检查是否为None
            print(f"DEBUG_AGENT: User preferred tools: {preferred_tools}")
            
            # 特殊处理："all" 表示使用所有可用工具
            if preferred_tools == "all":
                tools_to_send_to_llm = available_tools_for_llm
                tool_choice_param = "auto"
                print(f"DEBUG_AGENT: User specified 'all' tools. Using all {len(available_tools_for_llm)} available tools.")
            elif isinstance(preferred_tools, list) and len(preferred_tools) > 0:  # 只处理非空列表
                for tool_def in available_tools_for_llm:
                    tool_name = tool_def["function"]["name"]
                    if ("rag" in preferred_tools and tool_name == "rag_knowledge_base") or \
                       ("web_search" in preferred_tools and tool_name == "web_search") or \
                       ("mcp_tool" in preferred_tools and tool_name.startswith("mcp_")):
                        tools_to_send_to_llm.append(tool_def)
                if tools_to_send_to_llm: # 只有当有工具被选中时，才将tool_choice设为auto
                    tool_choice_param = "auto"
                    print(f"DEBUG_AGENT: Selected {len(tools_to_send_to_llm)} tools based on user preferences.")
                else:
                    print("WARNING_AGENT: User specified preferred tools, but no matching active tools found. Falling back to general Q&A.")
                    # tools_to_send_to_llm 为空，tool_choice_param 仍为 "none"
            else:
                # preferred_tools为空列表或其他情况，不使用任何工具
                print("INFO_AGENT: No valid preferred tools specified. No tools will be used.")
                tools_to_send_to_llm = []
                tool_choice_param = "none"
        else: # 如果 enable_tool_use 为 True，但 preferred_tools 为 None，则不启用任何工具
            tools_to_send_to_llm = []
            tool_choice_param = "none"
            print(f"DEBUG_AGENT: Tool use enabled but no preferred tools specified. No tools will be used.")
    else:
        # 如果 enable_tool_use 为 False，则不发送任何工具
        tools_to_send_to_llm = [] # 确保为空列表
        tool_choice_param = "none" # 确保明确不选择工具
        print(f"DEBUG_AGENT: Tool use explicitly disabled (enable_tool_use is False). Calling LLM without tools.")

    # 调用 LLM API，根据 tools_to_send_to_llm 和 tool_choice_param 传递参数
    llm_response_data = await call_llm_api(
        messages,
        llm_api_type,
        llm_api_key,
        llm_api_base_url,
        llm_model_id, # 确保这里传递的是 invoke_agent 接收到的llm_model_id
        tools=tools_to_send_to_llm if tools_to_send_to_llm else None, # 如果列表为空，则传递None
        tool_choice=tool_choice_param
    )

    choice = llm_response_data['choices'][0]
    message_content = choice['message']

    response_data["answer"] = ""
    response_data["answer_mode"] = ""

    if message_content.get('tool_calls'):
        print(f"DEBUG_AGENT: LLM decided to call tool(s): {message_content['tool_calls']}")
        tool_outputs_for_second_turn = []
        response_data["answer_mode"] = "Tool_Use_mode"
        current_turn_messages_to_log.append({
            "role": "tool_call",
            "content": f"LLM决定调用工具，工具调用详情：{json.dumps(message_content['tool_calls'], ensure_ascii=False)}",
            "tool_calls_json": message_content['tool_calls'],
            "llm_type_used": llm_api_type,
            "llm_model_used": llm_model_id
        })

        for tc in message_content['tool_calls']:
            tool_call_id = tc.get('id')
            tool_name = tc['function']['name']
            tool_args = json.loads(tc['function']['arguments'])

            tool_output_result = None
            try:
                if tool_name == "rag_knowledge_base":
                    executed_output = await execute_tool(
                        db=db,
                        tool_call_name=tool_name,
                        tool_call_args={
                            "query": tool_args.get("query"),
                            "kb_ids": kb_ids,
                            "note_ids": note_ids,
                            "temp_file_ids": temp_file_ids,
                            "conversation_id": conversation_id_for_temp_files
                        },
                        user_id=user_id
                    )
                    rag_context = executed_output.get("context", "") if isinstance(executed_output, dict) else str(
                        executed_output)
                    response_data["source_articles"] = executed_output.get("sources", []) if isinstance(executed_output,
                                                                                                        dict) else []
                    tool_output_result = {"context": rag_context,
                                          "sources": response_data["source_articles"]}

                elif tool_name == "web_search":
                    executed_output = await execute_tool(
                        db=db,
                        tool_call_name=tool_name,
                        tool_call_args={"query": tool_args.get("query"),
                                        "search_engine_config_id": tool_args.get("search_engine_config_id")},
                        user_id=user_id
                    )
                    response_data["search_results"] = []
                    results_list = []
                    if isinstance(executed_output, str) and executed_output.startswith("网络搜索结果:\n"):
                        lines = executed_output.strip().split("\n")
                        for line in lines[1:]:
                            if "标题:" in line and "链接:" in line and "摘要:" in line:
                                try:
                                    title = line.split("标题:")[1].split(", 摘要:")[0].strip()
                                    snippet = line.split("摘要:")[1].split(", 链接:")[0].strip()
                                    url = line.split("链接:")[1].strip()
                                    results_list.append({"title": title, "snippet": snippet, "url": url})
                                except Exception as parse_e:
                                    print(f"WARNING: Could not parse search result string: {parse_e}")
                                    results_list.append({"raw": line})
                    response_data["search_results"] = results_list
                    tool_output_result = {"raw_string_output": executed_output,
                                          "parsed_results": results_list}

                elif tool_name.startswith("mcp_"):
                    executed_output = await execute_tool(
                        db=db,
                        tool_call_name=tool_name,
                        tool_call_args=tool_args,  # 使用解析后的参数字典
                        user_id=user_id
                    )
                    tool_output_result = executed_output

                else:
                    tool_output_result = f"Error: LLM attempted to call an unexpected tool: {tool_name}"
                    print(tool_output_result)

                output_content_str = str(tool_output_result)
                current_turn_messages_to_log.append({
                    "role": "tool_output",
                    "content": f"工具 {tool_name} 执行结果: {output_content_str[:500]}...",
                    "tool_output_json": tool_output_result
                })
                tool_outputs_for_second_turn.append({
                    "tool_call_id": tool_call_id,
                    "output": output_content_str
                })

                print(f"DEBUG_AGENT: Tool '{tool_name}' executed successfully, output: {output_content_str[:100]}...")
            except Exception as e:
                error_msg = f"Tool '{tool_name}' execution failed: {e}"
                tool_outputs_for_second_turn.append({
                    "tool_call_id": tool_call_id,
                    "output": error_msg
                })
                current_turn_messages_to_log.append({
                    "role": "tool_output",
                    "content": f"工具 {tool_name} 执行失败: {error_msg}",
                    "tool_output_json": {"error": str(e)}
                })
                print(f"ERROR_AGENT: {error_msg}")

        messages.append(message_content)
        for output in tool_outputs_for_second_turn:
            messages.append({"role": "tool", "tool_call_id": output["tool_call_id"], "content": output["output"]})

        print(f"DEBUG_AGENT: Sending tool output back to LLM for final answer.")

        final_llm_response = await call_llm_api(
            messages,
            llm_api_type,
            llm_api_key,
            llm_api_base_url,
            llm_model_id,
            tools=None,
            tool_choice="none"
        )
        final_answer_content = final_llm_response['choices'][0]['message'].get('content')
        if final_answer_content:
            response_data["answer"] = final_answer_content
            response_data["answer_mode"] = "Tool_Use_mode"
            current_turn_messages_to_log.append({
                "role": "assistant",
                "content": final_answer_content,
                "llm_type_used": llm_api_type,
                "llm_model_used": llm_model_id
            })
        else:
            response_data[
                "answer"] = "Tool call completed, but LLM failed to generate a clear answer. Please try a more specific question."
            response_data["answer_mode"] = "Tool_Use_Failed_Answer"
            current_turn_messages_to_log.append({
                "role": "assistant",
                "content": "LLM未能生成明确答案。",
                "llm_type_used": llm_api_type,
                "llm_model_used": llm_model_id
            })

    else:
        print(f"DEBUG_AGENT: LLM did not call any tools, returning direct answer.")
        final_answer_content = message_content.get('content')
        if final_answer_content:
            response_data["answer"] = final_answer_content
            response_data["answer_mode"] = "General_mode"
            current_turn_messages_to_log.append({
                "role": "assistant",
                "content": final_answer_content,
                "llm_type_used": llm_api_type,
                "llm_model_used": llm_model_id
            })
        else:
            response_data["answer"] = "AI failed to generate a clear answer. Please retry or rephrase the question."
            response_data["answer_mode"] = "Failed_General_mode"
            current_turn_messages_to_log.append({
                "role": "assistant",
                "content": "LLM未能生成明确答案。",
                "llm_type_used": llm_api_type,
                "llm_model_used": llm_model_id
            })

    response_data["llm_type_used"] = llm_api_type
    response_data["llm_model_used"] = llm_model_id
    response_data["turn_messages_to_log"] = current_turn_messages_to_log

    return response_data


# --- 新增函数：通过LLM生成对话标题 ---
async def generate_conversation_title_from_llm(
        messages: List[Dict[str, Any]],
        user_llm_api_type: str,
        user_llm_api_key: str,
        user_llm_api_base_url: Optional[str] = None,
        user_llm_model_id: Optional[str] = None
) -> str:
    """
    根据对话消息内容，调用LLM自动生成一个简洁的对话标题。
    最多取最近的10条消息作为输入。
    """
    if not messages:
        print("WARNING_LLM_TITLE: 对话消息为空，无法生成标题。")
        return "无题对话"

    # 提取最近的10条消息进行总结，并且只保留 'user' 和 'assistant' 角色，仅保留 'content' 字段
    # 需要将 tool_call 和 tool_output 类型的消息内容也整合进 'content'，方便LLM理解上下文
    llm_context_messages = []
    for msg in messages[-10:]:  # 取最近10条消息
        if msg["role"] == "user":
            llm_context_messages.append({"role": "user", "content": msg["content"]})
        elif msg["role"] == "assistant":
            llm_context_messages.append({"role": "assistant", "content": msg["content"]})
        elif msg["role"] == "tool_call":
            # 将工具调用信息总结为文本
            tool_info = json.dumps(msg.get("tool_calls_json", msg.get("tool_calls", {})), ensure_ascii=False)[:200]
            llm_context_messages.append({"role": "assistant", "content": f"（AI决定调用工具: {tool_info}...）"})
        elif msg["role"] == "tool_output":
            # 将工具输出信息总结为文本
            output_info = json.dumps(msg.get("tool_output_json", {}), ensure_ascii=False)[:300]
            llm_context_messages.append({"role": "assistant", "content": f"（工具结果: {output_info}...）"})

    if not llm_context_messages:
        print("WARNING_LLM_TITLE: 过滤后没有有效的对话消息作为生成标题的上下文。")
        return "新对话"

    # 构建发送给LLM的完整消息，要求生成标题
    system_prompt = """你是一个专业的对话总结助手。请简洁地总结提供的对话内容，生成一个长度为3到15个汉字的对话标题。标题应准确反映对话的核心主题，不要包含任何标点符号。直接给出标题，不要有其他前缀或解释。"""

    # 将对话历史作为用户消息的一部分传递给LLM，并在最后添加一个指令让它生成标题
    llm_input_messages = [{"role": "system", "content": system_prompt}] + llm_context_messages
    llm_input_messages.append({"role": "user", "content": "请根据以上对话内容，生成一个简洁的标题。"})

    print(f"DEBUG_LLM_TITLE: 准备调用LLM生成标题，消息数量: {len(llm_input_messages)}")

    try:
        llm_response = await call_llm_api(
            messages=llm_input_messages,
            user_llm_api_type=user_llm_api_type,
            user_llm_api_key=user_llm_api_key,
            user_llm_api_base_url=user_llm_api_base_url,
            user_llm_model_id=user_llm_model_id
        )

        generated_title = llm_response['choices'][0]['message'].get('content', '').strip()

        # 清理生成的标题，去除标点符号，限制长度
        clean_title = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s]', '', generated_title)  # 仅保留中英文、数字和空格
        clean_title = clean_title.replace(' ', '')  # 移除空格
        if len(clean_title) > 15:
            clean_title = clean_title[:15]
        if not clean_title:  # 如果清理后变为空，给一个默认标题
            clean_title = "无标题对话"

        print(f"DEBUG_LLM_TITLE: LLM成功生成标题: '{clean_title}'")
        return clean_title
    except Exception as e:
        print(f"ERROR_LLM_TITLE: 调用LLM生成标题失败: {e}. 返回默认标题。")
        return "新对话"


# --- 辅助函数：将古文优雅度转换为数值权重 ---
def _get_safe_embedding_np(raw_embedding: Any, entity_type: str, entity_id: Any) -> Optional[np.ndarray]:
    """
    尝试将各种原始嵌入格式 (str, list, np.ndarray, None) 转换为一个干净的
    np.ndarray (float32) 尺寸为 1024，并检查 NaN/Inf 值。
    如果有效则返回 np.ndarray，否则返回 None。
    """
    np_embedding = None

    # 1. 处理已经是 numpy 数组的情况 (pgvector可能直接返回)
    if isinstance(raw_embedding, np.ndarray):
        np_embedding = raw_embedding
    # 2. 处理 JSON 字符串 (从 JSONB 字段读取时可能出现)
    elif isinstance(raw_embedding, str):
        try:
            parsed_embedding = json.loads(raw_embedding)
            # 确保解析后是列表且所有元素都是数值
            if isinstance(parsed_embedding, list) and all(isinstance(x, (float, int)) for x in parsed_embedding):
                np_embedding = np.array(parsed_embedding, dtype=np.float32)
            else:
                print(f"WARNING_AI_MATCHING: {entity_type} {entity_id} 嵌入字符串解析后不是浮点数列表。")
                return None  #
        except json.JSONDecodeError:
            print(f"WARNING_AI_MATCHING: {entity_type} {entity_id} 嵌入字符串JSON解码失败。")
            return None
    # 3. 处理 Python 浮点数列表
    elif isinstance(raw_embedding, list):
        if all(isinstance(x, (float, int)) for x in raw_embedding):
            np_embedding = np.array(raw_embedding, dtype=np.float32)
        else:
            print(f"WARNING_AI_MATCHING: {entity_type} {entity_id} 嵌入列表包含非数值元素。")
            return None
    # 4. 处理 None 或其他未知类型
    elif raw_embedding is None:
        print(f"WARNING_AI_MATCHING: {entity_type} {entity_id} 嵌入向量为None。")
        return None
    else:
        print(f"WARNING_AI_MATCHING: {entity_type} {entity_id} 嵌入向量类型未知: {type(raw_embedding)}。")
        return None

    # 对生成的 numpy 数组进行最终验证
    if np_embedding is not None:
        # 检查维度 (必须是 1D 向量) 和大小 (1024)
        if np_embedding.ndim != 1 or np_embedding.shape[0] != 1024:
            print(
                f"WARNING_AI_MATCHING: {entity_type} {entity_id} 嵌入向量维度或大小不正确: shape={np_embedding.shape} (期望 1024)。")
            return None

        # 检查 NaN (Not a Number) 或 Inf (Infinity) 值
        if np.any(np.isnan(np_embedding)) or np.any(np.isinf(np_embedding)):
            print(f"WARNING_AI_MATCHING: {entity_type} {entity_id} 嵌入向量包含 NaN/Inf 值。")
            return None

    return np_embedding  # 安全处理的 numpy 数组


def _get_skill_level_weight(level: str) -> float:
    """
    将古文优雅的技能熟练度等级转换为数值权重。
    炉火纯青 (4.0) > 融会贯通 (3.0) > 登堂入室 (2.0) > 初窥门径 (1.0)
    """
    weights = {
        "初窥门径": 1.0,
        "登堂入室": 2.0,
        "融会贯通": 3.0,
        "炉火纯青": 4.0
    }
    return weights.get(level, 0.0)  # 如果等级不在列表中，返回0


# --- 辅助函数：计算技能熟练度匹配分数 ---
def _calculate_proficiency_match_score(
        entity1_skills_raw_data: Any,  # 传入的原始学生技能数据
        entity2_required_skills_raw_data: Any  # 传入的原始项目所需技能数据
) -> float:
    """
    计算基于技能名称和熟练度的匹配分数。
    增加了对原始输入数据格式的极致鲁棒性解析，以处理各种可能的字符串化或嵌套 JSON。
    分数越高表示匹配度越高。
    """
    score = 0.0
    MAX_SKILL_LEVEL_DIFF_PENALTY = 0.5
    MIN_LEVEL_MATCH_SCORE = 1.0
    default_skill_level = "初窥门径"

    # 先将整个原始数据确保转换为一个可迭代的列表
    processed_entity1_skills_list_safe = _ensure_top_level_list(entity1_skills_raw_data)
    processed_entity2_required_skills_list_safe = _ensure_top_level_list(entity2_required_skills_raw_data)

    # 构建 entity1 (学生) 技能映射
    entity1_skill_map = {}
    for s_raw_entry in processed_entity1_skills_list_safe:
        s_parsed_dict = _parse_single_skill_entry_to_dict(s_raw_entry)
        if s_parsed_dict and 'name' in s_parsed_dict:
            entity1_skill_map[s_parsed_dict['name']] = _get_skill_level_weight(s_parsed_dict['level'])

    # 遍历 entity2 (项目所需) 技能，计算匹配分数
    for req_skill_raw_entry in processed_entity2_required_skills_list_safe:
        req_skill_parsed_dict = _parse_single_skill_entry_to_dict(req_skill_raw_entry)

        if not (isinstance(req_skill_parsed_dict, dict) and 'name' in req_skill_parsed_dict and req_skill_parsed_dict[
            'name'].strip()):
            print(f"WARNING_MATCH_SKILLS: 所需技能条目格式不正确或缺少有效名称，跳过: {req_skill_raw_entry}")
            continue

        req_name = req_skill_parsed_dict.get('name')
        req_level_weight = _get_skill_level_weight(req_skill_parsed_dict.get('level', default_skill_level))

        if req_name in entity1_skill_map:
            student_level_weight = entity1_skill_map[req_name]

            level_difference = req_level_weight - student_level_weight

            if level_difference <= 0:
                score += req_level_weight
                print(
                    f"DEBUG_MATCH: 技能 '{req_name}' - 学生熟练度 {student_level_weight} >= 项目要求 {req_level_weight}。得分：+{req_level_weight:.2f}")
            else:
                base_score = student_level_weight
                penalty = level_difference * MAX_SKILL_LEVEL_DIFF_PENALTY
                current_skill_score = max(MIN_LEVEL_MATCH_SCORE, base_score - penalty)

                score += current_skill_score
                print(
                    f"DEBUG_MATCH: 技能 '{req_name}' - 学生熟练度 {student_level_weight} < 项目要求 {req_level_weight}。得分：+{current_skill_score:.2f} (惩罚：-{penalty:.2f})")
        else:
            score -= (req_level_weight * 0.75)  # 缺失一项技能的惩罚，可以调整
            print(f"DEBUG_MATCH: 技能 '{req_name}' - 学生不具备。得分：-{req_level_weight * 0.75:.2f}")

    # 计算总可能得分
    total_possible_score = 0.0
    for s_raw_entry in processed_entity2_required_skills_list_safe:
        s_parsed_dict = _parse_single_skill_entry_to_dict(s_raw_entry)
        if s_parsed_dict and 'level' in s_parsed_dict:
            total_possible_score += _get_skill_level_weight(s_parsed_dict['level'])

    if total_possible_score > 0:
        normalized_score = max(0.0, score / total_possible_score)
    else:
        normalized_score = 1.0

    SKILL_MATCH_OVERALL_WEIGHT = 5.0
    return normalized_score * SKILL_MATCH_OVERALL_WEIGHT



# --- 辅助函数：时间与投入度匹配 ---
def _parse_weekly_hours_from_availability(availability_str: Optional[str]) -> Optional[int]:
    """
    从学生 availability 字符串中尝试提取每周小时数。
    支持格式如 "20小时", "15-20小时", ">20小时", "20+小时", "全职"。
    """
    if not availability_str or not isinstance(availability_str, str):
        print(f"DEBUG_TIME_MATCH: 无法解析 availability 字符串或为空: '{availability_str}'")
        return None

    availability_str_lower = availability_str.lower().replace(' ', '')

    # 匹配 "15-20小时" 这种范围
    match = re.search(r'(\d+)-(\d+)(?:小时)?', availability_str_lower)
    if match: return (int(match.group(1)) + int(match.group(2))) // 2

    # 匹配 ">20小时", "20+小时"
    match = re.search(r'[>(\d+)\+?]+(\d+)(?:小时)?', availability_str_lower)  # 匹配 ">20", "20+"
    if match: return int(match.group(1)) + 5  # 假设是最低值加5

    # 匹配 "20小时" 这种单个数字
    match = re.search(r'(\d+)(?:小时)?', availability_str_lower)
    if match: return int(match.group(1))

    # 匹配 "全职" (Full-time), 假设 40小时/周
    if "全职" in availability_str_lower or "full-time" in availability_str_lower:
        return 40

    print(f"DEBUG_TIME_MATCH: 未能从 availability 字符串 '{availability_str}' 中解析出周小时数。")
    return None


def _calculate_time_match_score(student: Student, project: Project) -> float:
    """
    计算基于时间与投入度的匹配分数。
    包括每周小时数匹配和日期/持续时间匹配。
    分数越高表示匹配度越高。
    """
    score_hours = 0.0
    score_dates = 0.0

    # 1. 周小时数匹配 (权重 0.6)
    student_weekly_hours = _parse_weekly_hours_from_availability(student.availability)

    # 项目有明确的小时数要求
    if project.estimated_weekly_hours is not None and project.estimated_weekly_hours > 0:
        if student_weekly_hours is not None:
            if student_weekly_hours >= project.estimated_weekly_hours:
                score_hours = 1.0  # 学生满足或超出要求
                print(
                    f"DEBUG_TIME_MATCH: 周小时数匹配 - 学生 {student_weekly_hours}h >= 项目 {project.estimated_weekly_hours}h。得分：+{score_hours:.2f}")
            else:
                score_hours = max(0.2, student_weekly_hours / project.estimated_weekly_hours)  # 按比例，最低0.2
                print(
                    f"DEBUG_TIME_MATCH: 周小时数匹配 - 学生 {student_weekly_hours}h < 项目 {project.estimated_weekly_hours}h。得分：+{score_hours:.2f}")
        else:
            score_hours = 0.3  # 项目需要，但学生未明确
            print(f"DEBUG_TIME_MATCH: 周小时数匹配 - 项目有要求，学生未明确。得分：+{score_hours:.2f}")
    else:  # 项目没有明确的小时数要求
        if student_weekly_hours is not None:  # 学生有明确，但项目灵活
            score_hours = 0.8
            print(f"DEBUG_TIME_MATCH: 周小时数匹配 - 项目无要求，学生有明确。得分：+{score_hours:.2f}")
        else:
            score_hours = 0.5  # 双方都未明确，中立
            print(f"DEBUG_TIME_MATCH: 周小时数匹配 - 双方均未明确。得分：+{score_hours:.2f}")

    # 2. 日期/持续时间匹配 (权重 0.4)
    # 因学生 availability 是自由文本，这里进行粗略的日期匹配

    student_temporal_keywords = set()
    if student.availability:
        avail_lower = student.availability.lower()
        if "暑假" in avail_lower or "夏季" in avail_lower: student_temporal_keywords.add("summer")
        if "寒假" in avail_lower or "冬季" in avail_lower: student_temporal_keywords.add("winter")
        if "学期内" in avail_lower: student_temporal_keywords.add("semester")  # 学期内 (Spring/Fall)
        if "长期" in avail_lower or "long-term" in avail_lower: student_temporal_keywords.add("long_term")  # Long term
        if "短期" in avail_lower or "short-term" in avail_lower: student_temporal_keywords.add(
            "short_term")  # Short term

    project_has_dates = project.start_date and project.end_date and project.end_date > project.start_date
    project_duration_months = (project.end_date - project.start_date).days / 30 if project_has_dates else None

    if project_has_dates:
        matched_period = False
        project_start_month = project.start_date.month

        # 检查项目开始月份是否与学生的周期关键词匹配
        if "summer" in student_temporal_keywords and 6 <= project_start_month <= 8:
            matched_period = True
        elif "winter" in student_temporal_keywords and (project_start_month == 1 or project_start_month == 12):
            matched_period = True
        elif "semester" in student_temporal_keywords and not (
                6 <= project_start_month <= 8 or project_start_month == 1 or project_start_month == 12):
            matched_period = True

        # 持续时间匹配 (粗略)
        if "long_term" in student_temporal_keywords and project_duration_months is not None and project_duration_months >= 6:
            matched_period = True
        elif "short_term" in student_temporal_keywords and project_duration_months is not None and project_duration_months < 3:
            matched_period = True

        if matched_period:
            score_dates = 1.0  # 良好期间匹配
            print(f"DEBUG_TIME_MATCH: 日期匹配 - 项目有日期，学生时间关键词匹配。得分：+{score_dates:.2f}")
        elif student_temporal_keywords:  # 学生有明确表述，但未直接匹配
            score_dates = 0.5
            print(f"DEBUG_TIME_MATCH: 日期匹配 - 项目有日期，学生时间关键词未直接匹配。得分：+{score_dates:.2f}")
        else:  # 项目有日期，学生未明确周期
            score_dates = 0.2
            print(f"DEBUG_TIME_MATCH: 日期匹配 - 项目有日期，学生未明确周期。得分：+{score_dates:.2f}")
    else:  # 项目没有明确的日期 (灵活)
        if student_temporal_keywords:  # 学生明确了日期，项目灵活
            score_dates = 0.7
            print(f"DEBUG_TIME_MATCH: 日期匹配 - 项目无日期，学生有明确表述。得分：+{score_dates:.2f}")
        else:  # 双方都未明确日期，中立
            score_dates = 0.5
            print(f"DEBUG_TIME_MATCH: 日期匹配 - 双方均未明确日期。得分：+{score_dates:.2f}")

    print(
        f"DEBUG_TIME_MATCH: 学生 '{student.name}' (ID: {student.id}) vs 项目 '{project.title}' (ID: {project.id}) - 周小时数子得分: {score_hours:.2f}, 日期子得分: {score_dates:.2f}")

    # 结合分数并归一化到 0-1 范围，然后乘以一个总权重
    combined_time_score = (score_hours * 0.6) + (score_dates * 0.4)  # 加权平均，范围 0-1

    OVERALL_TIME_MATCH_WEIGHT = 3.0  # 时间匹配在总分中的重要性权重
    return combined_time_score * OVERALL_TIME_MATCH_WEIGHT


# --- 辅助函数：计算地理位置匹配分数 ---
def _calculate_location_match_score(student_location: Optional[str], project_location: Optional[str]) -> float:
    """
    计算学生与项目的地理位置匹配分数。
    分数范围 0-1，越高表示匹配度越高。
    - 完全匹配 (例如: "广州大学城" == "广州大学城"): 1.0
    - 部分匹配 (例如: "广州大学城" 包含 "广州市", "琶洲" 包含 "广州市"): 0.8
    - 城市大区域匹配 (例如: "广州大学城" vs "天河区", 都属于广州): 0.6
    - 同城不同区匹配 (但需定义好城市和区之间的关系, 简化为包含城市名): 0.4
    - 不同城市/未提供信息: 0.1 (基础分，不完全排除)

    简化规则：
    1. 任何一个未提供位置，且另一个提供了：0.3 (比完全不确定好，但比明确匹配差)
    2. 双方都未提供位置：0.2 (最低分，表示无法匹配)
    3. 明确位置匹配：
       a. 完全相同: 1.0
       b. 包含关系 (如 "广州大学城" 和 "广州"): 0.8
       c. 城市层面匹配 (需定义城市列表或通过包含公共关键词判断，暂时简化):
          例如，如果一个在广州，另一个也在广州的不同具体地点。
          这里通过字符串包含来做粗略的城市匹配。

    """
    score = 0.1  # 基础分

    student_loc_lower = (student_location or "").lower().strip()
    project_loc_lower = (project_location or "").lower().strip()

    # 如果双方都未提供位置
    if not student_loc_lower and not project_loc_lower:
        return 0.2

    # 如果其中一方未提供位置
    if not student_loc_lower or not project_loc_lower:
        return 0.3  # 给予一定的基础分，表示有机会，但不如明确匹配

    # 完全相同
    if student_loc_lower == project_loc_lower:
        score = 1.0
        print(f"DEBUG_LOCATION: 位置 '{student_location}' 和 '{project_location}' 完全匹配。得分：{score:.2f}")
        return score

    # 包含关系 (例如 "广州大学城" 包含 "广州")
    if student_loc_lower in project_loc_lower or project_loc_lower in student_loc_lower:
        score = 0.8
        print(f"DEBUG_LOCATION: 位置 '{student_location}' 和 '{project_location}' 包含匹配。得分：{score:.2f}")
        return score

    # 粗略的城市级别匹配：检查是否包含共同的城市关键词
    # 为了简化，我们假设一些主要城市关键词
    major_cities = ['广州', '深圳', '珠海', '佛山', '东莞', '惠州', '中山', '江门', '肇庆', '香港', '澳门']

    student_city_match = None
    project_city_match = None

    for city in major_cities:
        if city.lower() in student_loc_lower:
            student_city_match = city
        if city.lower() in project_loc_lower:
            project_city_match = city
        if student_city_match and project_city_match:  # 找到了双方的城市关键词就跳出
            break

    if student_city_match and project_city_match and student_city_match == project_city_match:
        score = 0.6  # 同一个大城市的粗略匹配
        print(
            f"DEBUG_LOCATION: 位置 '{student_location}' 和 '{project_location}' 同城匹配 ({student_city_match})。得分：{score:.2f}")
        return score

    # 都没有匹配到具体城市，或者匹配到不同城市
    print(f"DEBUG_LOCATION: 位置 '{student_location}' 和 '{project_location}' 无明确匹配，返回基础分。得分：{score:.2f}")
    return score


def _identify_enhancement_opportunities(
        student: Student,
        match_type: Literal["student_to_project", "project_to_student", "student_to_course"],
        project: Optional[Project] = None,
        course: Optional["Course"] = None
) -> Dict[str, Any]:
    """
    识别学生-项目/课程匹配中的增强机会，例如学生缺失的技能、项目需要的角色。
    返回一个字典，包含建议信息，供LLM生成行动建议。
    """
    enhancements = {
        "missing_skills_for_student": [],  # 学生需要提升的技能
        "missing_proficiency_for_student": [],  # 学生熟练度不足的技能
        "required_roles_not_covered_by_student": [],  # 项目/课程所需但学生未声称扮演的角色
        "student_learn_suggestion": "",  # 针对学生的学习建议文本
        "project_recruit_suggestion": ""  # 针对项目的招聘建议文本 (对课程不适用)
    }

    # 用于本地解析技能数据的辅助函数
    default_skill_level = "初窥门径"
    valid_skill_levels = ["初窥门径", "登堂入室", "融会贯通", "炉火纯青"]

    def _parse_single_skill_entry_to_dict_local(single_skill_raw_data: Any) -> Optional[Dict]:
        """
        尝试将各种原始技能条目格式 (dict, str, list) 规范化为 {'name': '...', 'level': '...'}.
        特别处理异常字符串化和嵌套的情况。(本地副本)
        """
        if isinstance(single_skill_raw_data, dict):
            name = single_skill_raw_data.get("name")
            level = single_skill_raw_data.get("level", default_skill_level)
            if name and isinstance(name, str) and name.strip():
                formatted_name = name.strip()
                formatted_level = level if level in valid_skill_levels else default_skill_level
                return {"name": formatted_name, "level": formatted_level}
            return None
        elif isinstance(single_skill_raw_data, str):
            processed_str = single_skill_raw_data.strip()
            if not processed_str:
                return None

            initial_str = processed_str
            for _ in range(2):
                if (initial_str.startswith(("'", '"')) and initial_str.endswith(("'", '"')) and len(initial_str) > 1):
                    initial_str = initial_str[1:-1]
            initial_str = initial_str.replace('\\"', '"').replace("\\'", "'")

            parsing_attempts = [
                (json.loads, "json.loads"),
                (ast.literal_eval, "ast.literal_eval")
            ]

            for parser, parser_name in parsing_attempts:
                try:
                    parsed_content = parser(initial_str)
                    if isinstance(parsed_content, dict) and "name" in parsed_content:
                        name = parsed_content["name"]
                        level = parsed_content.get("level", default_skill_level)
                        if isinstance(name, str) and name.strip():
                            formatted_name = name.strip()
                            formatted_level = level if level in valid_skill_levels else default_skill_level
                            return {"name": formatted_name, "level": formatted_level}
                    elif isinstance(parsed_content, list) and len(parsed_content) > 0:
                        for item in parsed_content:
                            recursively_parsed_item = _parse_single_skill_entry_to_dict_local(item)
                            if recursively_parsed_item:
                                return recursively_parsed_item
                except (json.JSONDecodeError, ValueError, SyntaxError):
                    pass
            if processed_str.strip():
                return {"name": processed_str.strip(), "level": default_skill_level}
            return None
        elif isinstance(single_skill_raw_data, list):
            for item in single_skill_raw_data:
                parsed_item = _parse_single_skill_entry_to_dict_local(item)
                if parsed_item and "name" in parsed_item and parsed_item["name"].strip():
                    return parsed_item
            return None
        else:
            return None

    def _ensure_top_level_list_local(raw_input: Any) -> List[Any]:
        """
        确保原始传入的技能列表数据本身是可迭代的 Python 列表。(本地副本)
        """
        if isinstance(raw_input, list):
            return raw_input

        if isinstance(raw_input, str):
            processed_input = raw_input.strip()
            for _ in range(2):
                if (processed_input.startswith(("'", '"')) and processed_input.endswith(("'", '"')) and len(
                        processed_input) > 1):
                    processed_input = processed_input[1:-1]
            processed_input = processed_input.replace('\\"', '"').replace("\\'", "'")

            try:
                parsed = json.loads(processed_input)
                if isinstance(parsed, list): return parsed
            except json.JSONDecodeError:
                pass

            try:
                parsed = ast.literal_eval(processed_input)
                if isinstance(parsed, list): return parsed
            except (ValueError, SyntaxError):
                pass
            return []

        if raw_input is None: return []

        return []

    # 确定目标项和其所需技能/角色
    target_item_for_skills = None
    target_item_required_roles = []

    if project:
        target_item_for_skills = project
        target_item_required_roles = _ensure_top_level_list_local(project.required_roles)
    elif course:
        target_item_for_skills = course
        # 课程通常没有“角色”，这里将其清空，或者可以扩展为“学习小组角色”等
        target_item_required_roles = []
    else:
        # 如果既不是项目也不是课程，无法识别目标
        print(f"WARNING_ENHANCE: _identify_enhancement_opportunities called without a valid project or course target.")
        return enhancements

    # 1. 解析技能数据 (确保它们是可迭代的列表，内部元素是字典)
    student_skills_processed = [
        _parse_single_skill_entry_to_dict_local(s_item)
        for s_item in _ensure_top_level_list_local(student.skills)
        if _parse_single_skill_entry_to_dict_local(s_item) is not None
    ]

    target_item_required_skills_processed = [
        _parse_single_skill_entry_to_dict_local(r_item)
        for r_item in _ensure_top_level_list_local(target_item_for_skills.required_skills)
        if _parse_single_skill_entry_to_dict_local(r_item) is not None
    ]

    # 构建学生技能映射 (name -> level_weight)
    student_skill_map = {s['name']: _get_skill_level_weight(s['level']) for s in student_skills_processed if
                         'name' in s and 'level' in s}
    student_skill_raw_level_map = {s['name']: s['level'] for s in student_skills_processed if
                                   'name' in s and 'level' in s}

    # 2. 识别缺失技能和熟练度不足
    for req_skill in target_item_required_skills_processed:
        if 'name' not in req_skill or 'level' not in req_skill:
            continue

        req_name = req_skill['name']
        req_level_weight = _get_skill_level_weight(req_skill['level'])

        if req_name not in student_skill_map:
            enhancements["missing_skills_for_student"].append(req_name)
        else:
            student_level_weight = student_skill_map[req_name]
            if student_level_weight < req_level_weight:
                enhancements["missing_proficiency_for_student"].append({
                    "skill": req_name,
                    "student_level": student_skill_raw_level_map.get(req_name, default_skill_level),
                    "project_level": req_skill['level']
                })

    # 3. 识别角色空缺 (仅对项目适用，对课程一般不适用)
    if project:
        student_preferred_role_lower = (student.preferred_role or "").lower()

        for req_role in target_item_required_roles:
            if not isinstance(req_role, str) or not req_role.strip():
                continue

            if req_role.lower() not in student_preferred_role_lower:
                if req_role not in enhancements["required_roles_not_covered_by_student"]:
                    enhancements["required_roles_not_covered_by_student"].append(req_role)

    # 4. 生成文本建议 (供LLM使用)
    if match_type == "student_to_project" or match_type == "student_to_course":
        skill_suggestions = []
        if enhancements["missing_skills_for_student"]:
            skill_suggestions.append(f"学习或提升 {'、'.join(enhancements['missing_skills_for_student'])}")
        if enhancements["missing_proficiency_for_student"]:
            for item in enhancements["missing_proficiency_for_student"]:
                skill_suggestions.append(
                    f"将 {item['skill']} 技能从 {item['student_level']} 提升到 {item['project_level']} ")

        if skill_suggestions:
            item_type_str = "项目" if project else ("课程" if course else "目标")  # 根据哪个对象非None来确定
            enhancements[
                "student_learn_suggestion"] = f"为更好地匹配该{item_type_str}，建议您：{'. '.join(skill_suggestions)}。"

        if enhancements["required_roles_not_covered_by_student"] and project:
            if enhancements["student_learn_suggestion"]:
                enhancements["student_learn_suggestion"] += (
                    f" 此外，您可以拓展您的角色能力，尝试承担 {'、'.join(enhancements['required_roles_not_covered_by_student'])} 等角色职能。")
            else:
                enhancements["student_learn_suggestion"] = (
                    f" 建议您拓展您的角色能力，尝试承担 {'、'.join(enhancements['required_roles_not_covered_by_student'])} 等角色职能。")

    else:
        recruit_suggestions = []
        if enhancements["missing_skills_for_student"]:
            recruit_suggestions.append(f"学生缺少 {'、'.join(enhancements['missing_skills_for_student'])} 技能")
        if enhancements["missing_proficiency_for_student"]:
            for item in enhancements["missing_proficiency_for_student"]:
                recruit_suggestions.append(
                    f"学生在 {item['skill']} 上熟练度 {item['student_level']} 低于项目要求的 {item['project_level']}")

        if recruit_suggestions:
            enhancements[
                "project_recruit_suggestion"] = f"该项目与 {student.name} 的匹配度可以在技能方面通过以下方式提升：{'. '.join(recruit_suggestions)}。"

        if enhancements["required_roles_not_covered_by_student"]:
            if enhancements["project_recruit_suggestion"]:
                enhancements["project_recruit_suggestion"] += (
                    f" 此外，为了确保团队完整性，您可能需要考虑招募能够覆盖 {'、'.join(enhancements['required_roles_not_covered_by_student'])} 角色的人才。"
                )
            else:
                enhancements["project_recruit_suggestion"] = (
                    f" 建议项目方为了确保团队完整性，考虑招募能够覆盖 {'、'.join(enhancements['required_roles_not_covered_by_student'])} 角色的人才。"
                )

    print(f"DEBUG_ENHANCE: 增强机会识别结果 for {match_type}: {enhancements}")
    return enhancements


# --- 辅助函数：使用LLM生成匹配理由 (包含行动建议和地理位置信息) ---
async def _generate_match_rationale_llm(
        student: Student,
        target_item: Union[Project, "Course"], # 接受 Project 或 Course 对象
        sim_score: float,
        proficiency_score: float,
        time_score: float,
        location_score: float,
        enhancement_opportunities: Dict[str, Any],
        match_type: Literal["student_to_project", "project_to_student", "student_to_course"],
        llm_api_key: Optional[str] = None
) -> str:
    """
    根据学生、目标项目/课程的详细信息、匹配分数、地理位置得分以及识别出的增强机会，利用LLM生成匹配理由和可行动建议。
    """
    rationale_text = "AI匹配理由暂不可用。"

    if not llm_api_key or llm_api_key == "dummy_key_for_testing_without_api":
        print("WARNING_LLM_RATIONALE: 未配置LLM API KEY，无法生成动态匹配理由和建议。")
        return rationale_text

    # 构建 LLM 提示
    system_prompt = """
    你是一个智能匹配推荐系统的AI助手，需要为用户提供简洁、有说服力的匹配理由和可行动的建议。
    请根据提供的学生和目标（项目或课程）信息，以及各项匹配得分（内容相关性、技能熟练度、时间匹配、地理位置匹配），总结为什么他们是匹配的。
    强调匹配度高的方面，并对匹配度低的部分提出可行的改进建议（例如学习特定技能、寻找特定人才）。
    回复应简洁精炼，重点突出，不超过250字。建议以“**匹配理由**：...”开头，若有建议以“**行动建议**：...”结尾。
    """

    # 提取增强机会文本
    student_learn_suggestion = enhancement_opportunities.get("student_learn_suggestion", "")
    project_recruit_suggestion = enhancement_opportunities.get("project_recruit_suggestion", "") # 对项目有效，对课程可能不适用

    common_info_section = f"""
    匹配得分:
    内容相关性 (嵌入相似度): {sim_score:.2f}
    技能熟练度匹配: {proficiency_score:.2f}
    时间与投入度匹配: {time_score:.2f}
    地理位置匹配: {location_score:.2f}
    综合得分 (未标准化): {sim_score * 0.5 + proficiency_score * 0.3 + time_score * 0.1 + location_score * 0.1:.2f}
    """

    if match_type == "student_to_project":
        user_prompt = f"""
        学生信息:
        姓名: {student.name}, 专业: {student.major}
        技能: {json.dumps(student.skills, ensure_ascii=False)}
        兴趣: {student.interests or '无'}
        偏好角色: {student.preferred_role or '无'}
        可用时间: {student.availability or '未指定'}
        地理位置: {student.location or '未指定'}

        项目信息:
        标题: {target_item.title}, 描述: {target_item.description}
        所需技能: {json.dumps(target_item.required_skills, ensure_ascii=False)}
        所需角色: {json.dumps(target_item.required_roles, ensure_ascii=False)}
        时间范围: {target_item.start_date.strftime('%Y-%m-%d') if target_item.start_date else '未指定'} 至 {target_item.end_date.strftime('%Y-%m-%d') if target_item.end_date else '未指定'}
        每周预计投入: {target_item.estimated_weekly_hours or '未指定'}小时
        地理位置: {target_item.location or '未指定'}

        {common_info_section}

        **针对学生的学习/提升建议**：{student_learn_suggestion if student_learn_suggestion else '无特殊建议。'}

        请根据以上信息，为学生'{student.name}'推荐项目 '{target_item.title}' 提供匹配理由和可行动的建议。
        """
    elif match_type == "project_to_student":
        user_prompt = f"""
        项目信息:
        标题: {target_item.title}, 描述: {target_item.description}
        所需技能: {json.dumps(target_item.required_skills, ensure_ascii=False)}
        所需角色: {json.dumps(target_item.required_roles, ensure_ascii=False)}
        时间范围: {target_item.start_date.strftime('%Y-%m-%d') if target_item.start_date else '未指定'} 至 {target_item.end_date.strftime('%Y-%m-%d') if target_item.end_date else '未指定'}
        每周预计投入: {target_item.estimated_weekly_hours or '未指定'}小时
        地理位置: {target_item.location or '未指定'}

        学生信息:
        姓名: {student.name}, 专业: {student.major}
        技能: {json.dumps(student.skills, ensure_ascii=False)}
        兴趣: {student.interests or '无'}
        偏好角色: {student.preferred_role or '无'}
        可用时间: {student.availability or '未指定'}
        地理位置: {student.location or '未指定'}

        {common_info_section}

        **针对项目方的招聘/补充建议**：{project_recruit_suggestion if project_recruit_suggestion else '无特殊建议。'}

        请根据以上信息，为项目'{target_item.title}'推荐学生 '{student.name}' 提供匹配理由和可行动的建议。
        """
    # Course 推荐的子类型
    elif match_type == "student_to_course":
        user_prompt = f"""
        学生信息:
        姓名: {student.name}, 专业: {student.major}
        技能: {json.dumps(student.skills, ensure_ascii=False)}
        兴趣: {student.interests or '无'}
        可用时间: {student.availability or '未指定'}
        地理位置: {student.location or '未指定'}

        课程信息:
        标题: {target_item.title}, 描述: {target_item.description}
        课程类型: {target_item.category or '无'}
        所需/教授技能: {json.dumps(target_item.required_skills, ensure_ascii=False)}
        讲师: {target_item.instructor or '未指定'}
        图片链接: {target_item.cover_image_url or '无'}

        {common_info_section}

        **针对学生的学习/提升建议**：{student_learn_suggestion if student_learn_suggestion else '无特殊建议。'}

        请根据以上信息，为学生'{student.name}'推荐课程 '{target_item.title}' 提供匹配理由和可行动的建议。
        """
    else:
        raise ValueError(f"不支持的匹配类型: {match_type}")


    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    try:
        print(f"DEBUG_LLM_RATIONALE: Calling LLM for rationale generation for {match_type}...")
        llm_response = await call_llm_api(
            messages=messages,
            user_llm_api_type="siliconflow",
            user_llm_api_key=llm_api_key,
            user_llm_model_id=DEFAULT_LLM_API_CONFIG["siliconflow"]["default_model"]
        )
        if llm_response and 'choices' in llm_response and llm_response['choices'][0]['message'].get('content'):
            rationale_text = llm_response['choices'][0]['message']['content']
            print(f"DEBUG_LLM_RATIONALE: LLM generated rationale for {match_type} (first 100 chars): {rationale_text[:100]}...")
        else:
            print(f"WARNING_LLM_RATIONALE: LLM response did not contain content. Response: {llm_response}")
            rationale_text = "AI匹配理由生成失败或内容为空。请检查LLM服务。"
    except Exception as e:
        print(f"ERROR_LLM_RATIONALE: 调用LLM生成匹配理由失败: {e}. 将返回通用理由。")
        rationale_text = (
            f"基于AI分析，{student.name} 与 '{target_item.title}' 在以下方面有所匹配：\n"
            f"- 内容相关性得分：{sim_score:.2f}\n"
            f"- 技能匹配得分：{proficiency_score:.2f}\n"
            f"- 时间投入匹配得分：{time_score:.2f}\n"
            f"- 地理位置匹配得分：{location_score:.2f}\n"
            "具体细节请参考各维度得分。若要获得更详细解释，请确保LLM服务可用。"
        )

    return rationale_text


# --- 智能匹配函数 ---
async def find_matching_projects_for_student(db: Session, student_id: int,
                                             current_user_api_key: Optional[str] = None,  # 当前用户API Key
                                             initial_k: int = INITIAL_CANDIDATES_K,
                                             final_k: int = FINAL_TOP_K) -> List[MatchedProject]:
    """
    为指定学生推荐项目，考虑技能熟练度。
    """
    print(f"INFO_AI_MATCHING: 为学生 {student_id} 推荐项目。")
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生未找到。")

    # 在 AI 核心函数中，获取学生自己的 API Key，而不是依赖外部传入
    # 推荐时，如果学生自己的嵌入是零向量，但它有配置API Key，则尝试重新生成嵌入。
    # 仅在学生主动触发更新的情况下才会更新到DB。这里只用于当前计算。
    student_api_key_for_embedding_and_rerank = None
    if student.llm_api_type == "siliconflow" and student.llm_api_key_encrypted:
        try:
            student_api_key_for_embedding_and_rerank = decrypt_key(
                student.llm_api_key_encrypted)  # 使用ai_core内部的decrypt_key
            print(f"DEBUG_EMBEDDING_KEY: 学生 {student.id} 配置了硅基流动 API 密钥。")
        except Exception as e:
            print(f"ERROR_EMBEDDING_KEY: 解密学生 {student.id} 的硅基流动 API 密钥失败: {e}。将不使用其密钥。")
            student_api_key_for_embedding_and_rerank = None
    else:
        print(f"DEBUG_EMBEDDING_KEY: 学生 {student.id} 未配置硅基流动 API 类型或密钥。")

    student_embedding_np = _get_safe_embedding_np(student.embedding, "学生", student_id)
    if student_embedding_np is None or (student_embedding_np == np.zeros(1024, dtype=np.float32)).all():
        # 如果学生嵌入向量为None或全零（表示未生成或已失效），尝试用提供的API Key重新生成
        print(f"WARNING_AI_MATCHING: 学生 {student_id} 嵌入向量为None或全零，尝试使用学生自己的API Key重新生成。")
        if student_api_key_for_embedding_and_rerank:
            try:
                re_generated_embedding = await get_embeddings_from_api(
                    [student.combined_text], api_key=student_api_key_for_embedding_and_rerank
                )
                if re_generated_embedding and len(re_generated_embedding) > 0:
                    student_embedding_np = np.array(re_generated_embedding[0], dtype=np.float32)
                    print(f"DEBUG_AI_MATCHING: 学生 {student_id} 嵌入向量已临时重新生成。")
            except Exception as e:
                print(f"ERROR_AI_MATCHING: 临时重新生成学生 {student_id} 嵌入向量失败: {e}。将继续使用零向量。")
        if student_embedding_np is None or (student_embedding_np == np.zeros(1024, dtype=np.float32)).all():
            return []  # 如果重试后仍是None或全零，则无法匹配

    student_embedding = student_embedding_np.reshape(1, -1)
    print(
        f"DEBUG_EMBED_SHAPE: 学生 {student_id} 嵌入向量 shape: {student_embedding.shape}, dtype: {student_embedding.dtype}")

    all_projects = db.query(Project).all()
    if not all_projects:
        print(f"WARNING_AI_MATCHING: 数据库中没有项目可供推荐。")
        return []

    project_embeddings = []
    valid_projects = []

    for p in all_projects:
        safe_p_embedding_np = _get_safe_embedding_np(p.embedding, "项目", p.id)
        if safe_p_embedding_np is None or (safe_p_embedding_np == np.zeros(1024, dtype=np.float32)).all():
            # 如果项目嵌入向量为None或全零，尝试用项目创建者或当前学生的API Key临时重新生成
            project_creator_api_key = None
            if p.creator_id:
                project_creator = db.query(Student).filter(Student.id == p.creator_id).first()
                if project_creator and project_creator.llm_api_type == "siliconflow" and project_creator.llm_api_key_encrypted:
                    try:
                        project_creator_api_key = decrypt_key(project_creator.llm_api_key_encrypted)
                    except Exception:
                        pass  # 解密失败则为None

            key_to_use_for_project_embedding = project_creator_api_key or student_api_key_for_embedding_and_rerank

            if key_to_use_for_project_embedding:
                print(
                    f"WARNING_AI_MATCHING: 项目 {p.id} 嵌入向量为None或全零，尝试使用API Key ({'创建者' if project_creator_api_key else '学生'})重新生成。")
                try:
                    re_generated_embedding = await get_embeddings_from_api(
                        [p.combined_text], api_key=key_to_use_for_project_embedding
                    )
                    if re_generated_embedding and len(re_generated_embedding) > 0:
                        safe_p_embedding_np = np.array(re_generated_embedding[0], dtype=np.float32)
                        print(f"DEBUG_AI_MATCHING: 项目 {p.id} 嵌入向量已临时重新生成。")
                except Exception as e:
                    print(f"ERROR_AI_MATCHING: 临时重新生成项目 {p.id} 嵌入向量失败: {e}。将继续使用零向量。")

        if safe_p_embedding_np is None or (safe_p_embedding_np == np.zeros(1024, dtype=np.float32)).all():
            # 如果即使重试后仍然无效，则跳过此项目
            continue

        project_embeddings.append(safe_p_embedding_np)
        valid_projects.append(p)
        print(
            f"DEBUG_EMBED_SHAPE: 添加项目 {p.id} 嵌入向量 shape: {safe_p_embedding_np.shape}, dtype: {safe_p_embedding_np.dtype}")

    if not valid_projects:
        print(f"WARNING_AI_MATCHING: 所有项目都没有有效嵌入向量可供匹配。")
        return []

    try:
        project_embeddings_array = np.array(project_embeddings, dtype=np.float32)
    except Exception as e:
        print(f"ERROR_AI_MATCHING: 项目嵌入向量列表转换为大型 NumPy 数组失败: {e}")
        return []

    print(
        f"DEBUG_EMBED_SHAPE: 所有项目嵌入数组 shape: {project_embeddings_array.shape}, dtype: {project_embeddings_array.dtype}")

    # 阶段 1: 基于嵌入向量的初步筛选
    try:
        cosine_sims = cosine_similarity(student_embedding, project_embeddings_array)[0]
    except Exception as e:
        print(f"ERROR_AI_MATCHING: 计算余弦相似度失败: {e}. 请检查嵌入向量的尺寸或内容。")
        return []

    initial_candidates_indices = cosine_sims.argsort()[-initial_k:][::-1]
    initial_candidates = [(valid_projects[i], cosine_sims[i]) for i in initial_candidates_indices]
    print(f"DEBUG_AI_MATCHING: 初步筛选 {len(initial_candidates)} 个候选项目。")

    # 阶段 2: 细化匹配分数 (融入技能熟练度、时间与投入度、地理位置等因素)
    refined_candidates = []
    student_skills_data = student.skills
    if isinstance(student_skills_data, str):
        try:
            student_skills_data = json.loads(student_skills_data)
        except json.JSONDecodeError:
            student_skills_data = []
    if student_skills_data is None:
        student_skills_data = []

    for project, sim_score in initial_candidates:
        project_required_skills_data = project.required_skills
        if isinstance(project_required_skills_data, str):
            try:
                project_required_skills_data = json.loads(project_required_skills_data)
            except json.JSONDecodeError:
                project_required_skills_data = []
        if project_required_skills_data is None:
            project_required_skills_data = []

        proficiency_score = _calculate_proficiency_match_score(
            student_skills_data,
            project_required_skills_data
        )

        time_score = _calculate_time_match_score(student, project)
        print(f"DEBUG_MATCH: 项目 {project.id} ({project.title}) - 时间得分: {time_score:.4f}")

        location_score = _calculate_location_match_score(student.location, project.location)
        print(f"DEBUG_MATCH: 项目 {project.id} ({project.title}) - 地理位置得分: {location_score:.4f}")

        combined_score = (sim_score * 0.5) + \
                         (proficiency_score * 0.3) + \
                         (time_score * 0.1) + \
                         (location_score * 0.1)

        print(
            f"DEBUG_MATCH: 项目 {project.id} ({project.title}) - 嵌入相似度: {sim_score:.4f}, 熟练度得分: {proficiency_score:.4f}, 时间得分: {time_score:.4f}, 地理位置得分: {location_score:.4f}, 综合得分: {combined_score:.4f}")

        enhancement_opportunities = _identify_enhancement_opportunities(student=student, project=project,
                                                                        match_type="student_to_project")

        refined_candidates.append({
            "project": project,
            "combined_score": combined_score,
            "sim_score": sim_score,
            "proficiency_score": proficiency_score,
            "time_score": time_score,
            "location_score": location_score,
            "enhancement_opportunities": enhancement_opportunities
        })

    refined_candidates.sort(key=lambda x: x["combined_score"], reverse=True)

    #  阶段 3: Reranking with specialized model
    reranker_documents = [candidate["project"].combined_text or "" for candidate in refined_candidates[:final_k * 2] if
                          candidate["project"].combined_text and candidate["project"].combined_text.strip()]
    reranker_query = student.combined_text or ""

    final_recommendations = []
    if reranker_documents and reranker_query and reranker_query.strip():
        try:
            # 将学生自己的 API Key 传递给 get_rerank_scores_from_api
            rerank_scores = await get_rerank_scores_from_api(
                reranker_query,
                reranker_documents,
                api_key=student_api_key_for_embedding_and_rerank  # 传递学生密钥
            )

            reranked_projects_with_scores = []
            rerank_doc_to_full_candidate_map = {
                (c["project"].combined_text or ""): c  # 确保密钥为非空
                for c in refined_candidates[:final_k * 2]
                if c["project"].combined_text and c["project"].combined_text.strip()
            }

            for score_idx, score_val in enumerate(rerank_scores):
                original_candidate_info = rerank_doc_to_full_candidate_map.get(reranker_documents[score_idx])
                if original_candidate_info:
                    reranked_projects_with_scores.append({
                        "project": original_candidate_info["project"],
                        "relevance_score": score_val,
                        "combined_score_stage2": original_candidate_info["combined_score"],
                        "sim_score": original_candidate_info["sim_score"],
                        "proficiency_score": original_candidate_info["proficiency_score"],
                        "time_score": original_candidate_info["time_score"],
                        "location_score": original_candidate_info["location_score"],
                        "enhancement_opportunities": original_candidate_info["enhancement_opportunities"]
                    })

            reranked_projects_with_scores.sort(key=lambda x: x["relevance_score"], reverse=True)

            for rec in reranked_projects_with_scores[:final_k]:
                # 将学生自己的 API Key 传递给 _generate_match_rationale_llm
                rationale = await _generate_match_rationale_llm(
                    student=student,
                    project=rec["project"],
                    sim_score=rec["sim_score"],
                    proficiency_score=rec["proficiency_score"],
                    time_score=rec["time_score"],
                    location_score=rec["location_score"],
                    enhancement_opportunities=rec["enhancement_opportunities"],
                    match_type="student_to_project",
                    llm_api_key=student_api_key_for_embedding_and_rerank  # 传递学生密钥
                )
                final_recommendations.append(
                    MatchedProject(
                        project_id=rec["project"].id,
                        title=rec["project"].title,
                        description=rec["project"].description,
                        similarity_stage1=rec["combined_score_stage2"],
                        relevance_score=rec["relevance_score"],
                        match_rationale=rationale
                    )
                )
            print(f"INFO_AI_MATCHING: 为学生 {student_id} 推荐了 {len(final_recommendations)} 个项目 (Reranked)。")
        except Exception as e:
            print(f"ERROR_AI_MATCHING: 项目Rerank失败: {e}. 将退回至初步筛选结果。")
            import traceback
            traceback.print_exc()
            for rec in refined_candidates[:final_k]:
                rationale = await _generate_match_rationale_llm(
                    student=student,
                    project=rec["project"],
                    sim_score=rec["sim_score"],
                    proficiency_score=rec["proficiency_score"],
                    time_score=rec["time_score"],
                    location_score=rec["location_score"],
                    enhancement_opportunities=rec["enhancement_opportunities"],
                    match_type="student_to_project",
                    llm_api_key=student_api_key_for_embedding_and_rerank  #  传递学生密钥
                )
                final_recommendations.append(
                    MatchedProject(
                        project_id=rec["project"].id,
                        title=rec["project"].title,
                        description=rec["project"].description,
                        similarity_stage1=rec["combined_score"],
                        relevance_score=rec["combined_score"],
                        match_rationale=rationale
                    )
                )
    else:
        print(
            f"WARNING_AI_MATCHING: 无有效文本进行项目 Rerank (query: '{reranker_query[:50]}', docs_len: {len(reranker_documents)}). 将返回初步筛选结果。")
        for rec in refined_candidates[:final_k]:
            rationale = await _generate_match_rationale_llm(
                student=student,
                project=rec["project"],
                sim_score=rec["sim_score"],
                proficiency_score=rec["proficiency_score"],
                time_score=rec["time_score"],
                location_score=rec["location_score"],
                enhancement_opportunities=rec["enhancement_opportunities"],
                match_type="student_to_project",
                llm_api_key=student_api_key_for_embedding_and_rerank  #  传递学生密钥
            )
            final_recommendations.append(
                MatchedProject(
                    project_id=rec["project"].id,
                    title=rec["project"].title,
                    description=rec["project"].description,
                    similarity_stage1=rec["combined_score"],
                    relevance_score=rec["combined_score"],
                    match_rationale=rationale
                )
            )

    return final_recommendations


async def find_matching_courses_for_student(db: Session, student_id: int,
                                            initial_k: int = INITIAL_CANDIDATES_K,
                                            final_k: int = FINAL_TOP_K) -> List[MatchedCourse]: # 返回 MatchedCourse 列表
    """
    为指定学生推荐课程。
    """
    print(f"INFO_AI_MATCHING: 为学生 {student_id} 推荐课程。")
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生未找到。")

    # 获取学生自己的 API Key，而不是依赖外部传入
    student_api_key_for_embedding_and_rerank = None
    if student.llm_api_type == "siliconflow" and student.llm_api_key_encrypted:
        try:
            student_api_key_for_embedding_and_rerank = decrypt_key(
                student.llm_api_key_encrypted)  # 使用ai_core内部的decrypt_key
            print(f"DEBUG_EMBEDDING_KEY: 学生 {student.id} 配置了硅基流动 API 密钥。")
        except Exception as e:
            print(f"ERROR_EMBEDDING_KEY: 解密学生 {student.id} 的硅基流动 API 密钥失败: {e}。将不使用其密钥。")
            student_api_key_for_embedding_and_rerank = None
    else:
        print(f"DEBUG_EMBEDDING_KEY: 学生 {student.id} 未配置硅基流动 API 类型或密钥。")

    student_embedding_np = _get_safe_embedding_np(student.embedding, "学生", student_id)
    if student_embedding_np is None or (student_embedding_np == np.zeros(1024, dtype=np.float32)).all():
        # 如果学生嵌入向量为None或全零，尝试用提供的API Key重新生成
        print(f"WARNING_AI_MATCHING: 学生 {student_id} 嵌入向量为None或全零，尝试使用学生自己的API Key重新生成。")
        if student_api_key_for_embedding_and_rerank:
            try:
                re_generated_embedding = await get_embeddings_from_api(
                    [student.combined_text], api_key=student_api_key_for_embedding_and_rerank
                )
                if re_generated_embedding and len(re_generated_embedding) > 0:
                    student_embedding_np = np.array(re_generated_embedding[0], dtype=np.float32)
                    print(f"DEBUG_AI_MATCHING: 学生 {student_id} 嵌入向量已临时重新生成。")
            except Exception as e:
                print(f"ERROR_AI_MATCHING: 临时重新生成学生 {student_id} 嵌入向量失败: {e}。将继续使用零向量。")
        if student_embedding_np is None or (student_embedding_np == np.zeros(1024, dtype=np.float32)).all():
            return []  # 如果重试后仍是None或全零，则无法匹配

    student_embedding = student_embedding_np.reshape(1, -1)
    print(f"DEBUG_EMBED_SHAPE: 学生 {student_id} 嵌入向量 shape: {student_embedding.shape}, dtype: {student_embedding.dtype}")

    all_courses = db.query(Course).all() #  查询所有课程
    if not all_courses:
        print(f"WARNING_AI_MATCHING: 数据库中没有课程可供推荐。")
        return []

    course_embeddings = []
    valid_courses = []

    for c in all_courses: # 遍历课程
        safe_c_embedding_np = _get_safe_embedding_np(c.embedding, "课程", c.id) #  针对课程的日志和类型
        if safe_c_embedding_np is None or (safe_c_embedding_np == np.zeros(1024, dtype=np.float32)).all():
            # 如果课程嵌入向量为None或全零，尝试用学生或一个通用API Key临时重新生成
            key_to_use_for_course_embedding = student_api_key_for_embedding_and_rerank # 可以用学生自己的密钥生成课程嵌入

            if key_to_use_for_course_embedding:
                print(f"WARNING_AI_MATCHING: 课程 {c.id} 嵌入向量为None或全零，尝试使用API Key (学生)重新生成。")
                try:
                    re_generated_embedding = await get_embeddings_from_api(
                        [c.combined_text], api_key=key_to_use_for_course_embedding
                    )
                    if re_generated_embedding and len(re_generated_embedding) > 0:
                        safe_c_embedding_np = np.array(re_generated_embedding[0], dtype=np.float32)
                        print(f"DEBUG_AI_MATCHING: 课程 {c.id} 嵌入向量已临时重新生成。")
                except Exception as e:
                    print(f"ERROR_AI_MATCHING: 临时重新生成课程 {c.id} 嵌入向量失败: {e}。将继续使用零向量。")

        if safe_c_embedding_np is None or (safe_c_embedding_np == np.zeros(1024, dtype=np.float32)).all():
            # 如果即使重试后仍然无效，则跳过此课程
            continue

        course_embeddings.append(safe_c_embedding_np)
        valid_courses.append(c) # 添加有效课程
        print(f"DEBUG_EMBED_SHAPE: 添加课程 {c.id} 嵌入向量 shape: {safe_c_embedding_np.shape}, dtype: {safe_c_embedding_np.dtype}")

    if not valid_courses: # 检查有效课程
        print(f"WARNING_AI_MATCHING: 所有课程都没有有效嵌入向量可供匹配。")
        return []

    try:
        course_embeddings_array = np.array(course_embeddings, dtype=np.float32) # 课程嵌入数组
    except Exception as e:
        print(f"ERROR_AI_MATCHING: 课程嵌入向量列表转换为大型 NumPy 数组失败: {e}")
        return []

    print(f"DEBUG_EMBED_SHAPE: 所有课程嵌入数组 shape: {course_embeddings_array.shape}, dtype: {course_embeddings_array.dtype}")

    # 阶段 1: 基于嵌入向量的初步筛选
    try:
        cosine_sims = cosine_similarity(student_embedding, course_embeddings_array)[0] # 学生 vs 课程相似度
    except Exception as e:
        print(f"ERROR_AI_MATCHING: 计算余弦相似度失败: {e}. 请检查嵌入向量的尺寸或内容。")
        return []

    initial_candidates_indices = cosine_sims.argsort()[-initial_k:][::-1]
    initial_candidates = [(valid_courses[i], cosine_sims[i]) for i in initial_candidates_indices] # 课程候选
    print(f"DEBUG_AI_MATCHING: 初步筛选 {len(initial_candidates)} 个候选课程。")

    # 阶段 2: 细化匹配分数 (融入技能熟练度、时间与投入度、地理位置等因素)
    refined_candidates = []
    student_skills_data = student.skills
    if isinstance(student_skills_data, str):
        try:
            student_skills_data = json.loads(student_skills_data)
        except json.JSONDecodeError:
            student_skills_data = []
    if student_skills_data is None:
        student_skills_data = []

    for course, sim_score in initial_candidates: #  遍历课程
        course_required_skills_data = course.required_skills #  课程的 required_skills
        if isinstance(course_required_skills_data, str):
            try:
                course_required_skills_data = json.loads(course_required_skills_data)
            except json.JSONDecodeError:
                course_required_skills_data = []
        if course_required_skills_data is None:
            course_required_skills_data = []

        proficiency_score = _calculate_proficiency_match_score(
            student_skills_data,
            course_required_skills_data # 学生技能 vs 课程所需技能
        )

        time_score = _calculate_time_match_score(student, course) # 学生 vs 课程时间匹配 (如果课程有相关字段)
        # 课程通常没有 estimated_weekly_hours 和 start_date/end_date。
        # _calculate_time_match_score 会根据这些字段缺失返回默认分数 [5.2.4]_calculate_time_match_score。
        print(f"DEBUG_MATCH: 课程 {course.id} ({course.title}) - 时间得分: {time_score:.4f}")

        location_score = _calculate_location_match_score(student.location, course.category) # 简化：学生所在地 vs 课程类别 (可能更有用，或直接用课程地点 if exists)
        # Course 模型目前没有 location 字段，这里简化为用 category 作为文本匹配。
        # 如果需要更精准的地点，需要给 Course model 添加 location 字段
        print(f"DEBUG_MATCH: 课程 {course.id} ({course.title}) - 地理位置得分: {location_score:.4f}")

        # 调整权重，课程推荐可能更注重内容和技能，时间/地点权重可以更低
        # 0.5 (embedding) + 0.3 (skills) + 0.1 (time) + 0.1 (location) 保持和项目推荐一致，或者可以调整
        combined_score = (sim_score * 0.5) + \
                         (proficiency_score * 0.3) + \
                         (time_score * 0.1) + \
                         (location_score * 0.1)

        print(
            f"DEBUG_MATCH: 课程 {course.id} ({course.title}) - 嵌入相似度: {sim_score:.4f}, 熟练度得分: {proficiency_score:.4f}, 时间得分: {time_score:.4f}, 地理位置得分: {location_score:.4f}, 综合得分: {combined_score:.4f}")

        enhancement_opportunities = _identify_enhancement_opportunities(student=student, project=None, course=course,
                                                                        match_type="student_to_course")

        refined_candidates.append({
            "course": course, # 存储课程对象
            "combined_score": combined_score,
            "sim_score": sim_score,
            "proficiency_score": proficiency_score,
            "time_score": time_score,
            "location_score": location_score,
            "enhancement_opportunities": enhancement_opportunities
        })

    refined_candidates.sort(key=lambda x: x["combined_score"], reverse=True)

    # 3: Reranking with specialized model
    reranker_documents = [candidate["course"].combined_text or "" for candidate in refined_candidates[:final_k * 2] if
                          candidate["course"].combined_text and candidate["course"].combined_text.strip()] # 课程的 combined_text
    reranker_query = student.combined_text or ""

    final_recommendations = []
    if reranker_documents and reranker_query and reranker_query.strip():
        try:
            rerank_scores = await get_rerank_scores_from_api(
                reranker_query,
                reranker_documents,
                api_key=student_api_key_for_embedding_and_rerank
            )

            reranked_courses_with_scores = []
            rerank_doc_to_full_candidate_map = {
                (c["course"].combined_text or ""): c
                for c in refined_candidates[:final_k * 2]
                if c["course"].combined_text and c["course"].combined_text.strip()
            }

            for score_idx, score_val in enumerate(rerank_scores):
                original_candidate_info = rerank_doc_to_full_candidate_map.get(reranker_documents[score_idx])
                if original_candidate_info:
                    reranked_courses_with_scores.append({
                        "course": original_candidate_info["course"],
                        "relevance_score": score_val,
                        "combined_score_stage2": original_candidate_info["combined_score"],
                        "sim_score": original_candidate_info["sim_score"],
                        "proficiency_score": original_candidate_info["proficiency_score"],
                        "time_score": original_candidate_info["time_score"],
                        "location_score": original_candidate_info["location_score"],
                        "enhancement_opportunities": original_candidate_info["enhancement_opportunities"]
                    })

            reranked_courses_with_scores.sort(key=lambda x: x["relevance_score"], reverse=True)

            for rec in reranked_courses_with_scores[:final_k]:
                rationale = await _generate_match_rationale_llm(
                    student=student,
                    target_item=rec["course"], # 传入课程对象
                    sim_score=rec["sim_score"],
                    proficiency_score=rec["proficiency_score"],
                    time_score=rec["time_score"],
                    location_score=rec["location_score"],
                    enhancement_opportunities=rec["enhancement_opportunities"],
                    match_type="student_to_course", # 匹配类型
                    llm_api_key=student_api_key_for_embedding_and_rerank
                )
                final_recommendations.append(
                    MatchedCourse( # 返回 MatchedCourse
                        course_id=rec["course"].id,
                        title=rec["course"].title,
                        description=rec["course"].description,
                        instructor=rec["course"].instructor,
                        category=rec["course"].category,
                        cover_image_url=rec["course"].cover_image_url,
                        similarity_stage1=rec["combined_score_stage2"],
                        relevance_score=rec["relevance_score"],
                        match_rationale=rationale
                    )
                )
            print(f"INFO_AI_MATCHING: 为学生 {student_id} 推荐了 {len(final_recommendations)} 个课程 (Reranked)。")
        except Exception as e:
            print(f"ERROR_AI_MATCHING: 课程Rerank失败: {e}. 将退回至初步筛选结果。")
            import traceback
            traceback.print_exc()
            for rec in refined_candidates[:final_k]:
                rationale = await _generate_match_rationale_llm(
                    student=student,
                    target_item=rec["course"], # 传入课程对象
                    sim_score=rec["sim_score"],
                    proficiency_score=rec["proficiency_score"],
                    time_score=rec["time_score"],
                    location_score=rec["location_score"],
                    enhancement_opportunities=rec["enhancement_opportunities"],
                    match_type="student_to_course", #  匹配类型
                    llm_api_key=student_api_key_for_embedding_and_rerank
                )
                final_recommendations.append(
                    MatchedCourse( # 返回 MatchedCourse
                        course_id=rec["course"].id,
                        title=rec["course"].title,
                        description=rec["course"].description,
                        instructor=rec["course"].instructor,
                        category=rec["course"].category,
                        cover_image_url=rec["course"].cover_image_url,
                        similarity_stage1=rec["combined_score"],
                        relevance_score=rec["combined_score"],
                        match_rationale=rationale
                    )
                )
    else:
        print(f"WARNING_AI_MATCHING: 无有效文本进行课程 Rerank (query: '{reranker_query[:50]}', docs_len: {len(reranker_documents)}). 将返回初步筛选结果。")
        for rec in refined_candidates[:final_k]:
            rationale = await _generate_match_rationale_llm(
                student=student,
                target_item=rec["course"], # 传入课程对象
                sim_score=rec["sim_score"],
                proficiency_score=rec["proficiency_score"],
                time_score=rec["time_score"],
                location_score=rec["location_score"],
                enhancement_opportunities=rec["enhancement_opportunities"],
                match_type="student_to_course", #  匹配类型
                llm_api_key=student_api_key_for_embedding_and_rerank
            )
            final_recommendations.append(
                MatchedCourse( # 返回 MatchedCourse
                    course_id=rec["course"].id,
                    title=rec["course"].title,
                    description=rec["course"].description,
                    instructor=rec["course"].instructor,
                    category=rec["course"].category,
                    cover_image_url=rec["course"].cover_image_url,
                    similarity_stage1=rec["combined_score"],
                    relevance_score=rec["combined_score"],
                    match_rationale=rationale
                )
            )

    return final_recommendations


async def find_matching_students_for_project(db: Session, project_id: int,
                                             project_creator_api_key: Optional[str] = None,  # 项目创建者API Key
                                             initial_k: int = INITIAL_CANDIDATES_K,
                                             final_k: int = FINAL_TOP_K) -> List[MatchedStudent]:
    """
    为指定项目推荐学生，考虑技能熟练度。
    """
    print(f"INFO_AI_MATCHING: 为项目 {project_id} 推荐学生。")
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目未找到。")

    # 在 AI 核心函数中，获取项目创建者自己的 API Key，而不是依赖外部传入
    # 推荐时，如果项目自己的嵌入是零向量，但它有配置API Key，则尝试重新生成嵌入。
    # 仅在项目主动触发更新的情况下才会更新到DB。这里只用于当前计算。
    project_api_key_for_embedding_and_rerank = None
    if project.creator_id:
        project_creator = db.query(Student).filter(Student.id == project.creator_id).first()
        if project_creator and project_creator.llm_api_type == "siliconflow" and project_creator.llm_api_key_encrypted:
            try:
                project_api_key_for_embedding_and_rerank = decrypt_key(project_creator.llm_api_key_encrypted)
                print(f"DEBUG_EMBEDDING_KEY: 项目创建者 {project_creator.id} 配置了硅基流动 API 密钥。")
            except Exception as e:
                print(
                    f"ERROR_EMBEDDING_KEY: 解密项目创建者 {project_creator.id} 的硅基流动 API 密钥失败: {e}。将不使用其密钥。")
                project_api_key_for_embedding_and_rerank = None
        else:
            print(
                f"DEBUG_EMBEDDING_KEY: 项目创建者 {project_creator.id if project_creator else 'N/A'} 未配置硅基流动 API 类型或密钥。")
    else:
        print(f"DEBUG_EMBEDDING_KEY: 项目 {project.id} 没有关联创建者ID。")

    project_embedding_np = _get_safe_embedding_np(project.embedding, "项目", project_id)
    if project_embedding_np is None or (project_embedding_np == np.zeros(1024, dtype=np.float32)).all():
        # 如果项目嵌入向量为None或全零，尝试用项目创建者自己的API Key重新生成
        print(f"WARNING_AI_MATCHING: 项目 {project_id} 嵌入向量为None或全零，尝试使用项目创建者的API Key重新生成。")
        if project_api_key_for_embedding_and_rerank:
            try:
                re_generated_embedding = await get_embeddings_from_api(
                    [project.combined_text], api_key=project_api_key_for_embedding_and_rerank
                )
                if re_generated_embedding and len(re_generated_embedding) > 0:
                    project_embedding_np = np.array(re_generated_embedding[0], dtype=np.float32)
                    print(f"DEBUG_AI_MATCHING: 项目 {project_id} 嵌入向量已临时重新生成。")
            except Exception as e:
                print(f"ERROR_AI_MATCHING: 临时重新生成项目 {project_id} 嵌入向量失败: {e}。将继续使用零向量。")
        if project_embedding_np is None or (project_embedding_np == np.zeros(1024, dtype=np.float32)).all():
            return []  # 如果重试后仍是None或全零，则无法匹配

    project_embedding = project_embedding_np.reshape(1, -1)
    print(
        f"DEBUG_EMBED_SHAPE: 项目 {project_id} 嵌入向量 shape: {project_embedding.shape}, dtype: {project_embedding.dtype}")

    all_students = db.query(Student).all()
    if not all_students:
        print(f"WARNING_AI_MATCHING: 数据库中没有学生可供推荐。")
        return []

    student_embeddings = []
    valid_students = []
    for s in all_students:
        safe_s_embedding_np = _get_safe_embedding_np(s.embedding, "学生", s.id)
        if safe_s_embedding_np is None or (safe_s_embedding_np == np.zeros(1024, dtype=np.float32)).all():
            # 如果学生嵌入向量为None或全零，尝试用学生自己的API Key临时重新生成
            student_api_key = None
            if s.llm_api_type == "siliconflow" and s.llm_api_key_encrypted:
                try:
                    student_api_key = decrypt_key(s.llm_api_key_encrypted)
                except Exception:
                    pass

            key_to_use_for_student_embedding = student_api_key or project_api_key_for_embedding_and_rerank

            if key_to_use_for_student_embedding:
                print(
                    f"WARNING_AI_MATCHING: 学生 {s.id} 嵌入向量为None或全零，尝试使用API Key ({'学生自己' if student_api_key else '项目创建者'})重新生成。")
                try:
                    re_generated_embedding = await get_embeddings_from_api(
                        [s.combined_text], api_key=key_to_use_for_student_embedding
                    )
                    if re_generated_embedding and len(re_generated_embedding) > 0:
                        safe_s_embedding_np = np.array(re_generated_embedding[0], dtype=np.float32)
                        print(f"DEBUG_AI_MATCHING: 学生 {s.id} 嵌入向量已临时重新生成。")
                except Exception as e:
                    print(f"ERROR_AI_MATCHING: 临时重新生成学生 {s.id} 嵌入向量失败: {e}。将继续使用零向量。")

        if safe_s_embedding_np is None or (safe_s_embedding_np == np.zeros(1024, dtype=np.float32)).all():
            continue

        student_embeddings.append(safe_s_embedding_np)
        valid_students.append(s)
        print(
            f"DEBUG_EMBED_SHAPE: 添加学生 {s.id} 嵌入向量 shape: {safe_s_embedding_np.shape}, dtype: {safe_s_embedding_np.dtype}")

    if not valid_students:
        print(f"WARNING_AI_MATCHING: 所有学生都没有有效嵌入向量可供匹配。")
        return []

    try:
        student_embeddings_array = np.array(student_embeddings, dtype=np.float32)
    except Exception as e:
        print(f"ERROR_AI_MATCHING: 学生嵌入向量列表转换为大型 NumPy 数组失败: {e}")
        return []

    print(
        f"DEBUG_EMBED_SHAPE: 所有学生嵌入数组 shape: {student_embeddings_array.shape}, dtype: {student_embeddings_array.dtype}")

    # 阶段 1: 基于嵌入向量的初步筛选
    try:
        cosine_sims = cosine_similarity(project_embedding, student_embeddings_array)[0]
    except Exception as e:
        print(f"ERROR_AI_MATCHING: 计算余弦相似度失败: {e}. 请检查嵌入向量的尺寸或内容。")
        return []

    initial_candidates_indices = cosine_sims.argsort()[-initial_k:][::-1]
    initial_candidates = [(valid_students[i], cosine_sims[i]) for i in initial_candidates_indices]
    print(f"DEBUG_AI_MATCHING: 初步筛选 {len(initial_candidates)} 个候选学生。")

    #  阶段 2: 细化匹配分数 (融入技能熟练度、时间与投入度、地理位置等因素)
    refined_candidates = []
    project_required_skills_data = project.required_skills
    if isinstance(project_required_skills_data, str):
        try:
            project_required_skills_data = json.loads(project_required_skills_data)
        except json.JSONDecodeError:
            project_required_skills_data = []
    if project_required_skills_data is None:
        project_required_skills_data = []

    for student, sim_score in initial_candidates:
        student_skills_data = student.skills
        if isinstance(student_skills_data, str):
            try:
                student_skills_data = json.loads(student_skills_data)
            except json.JSONDecodeError:
                student_skills_data = []
        if student_skills_data is None:
            student_skills_data = []

        proficiency_score = _calculate_proficiency_match_score(
            student_skills_data,
            project_required_skills_data
        )

        time_score = _calculate_time_match_score(student, project)
        print(f"DEBUG_MATCH: 学生 {student.id} ({student.name}) - 时间得分: {time_score:.4f}")

        location_score = _calculate_location_match_score(student.location, project.location)
        print(f"DEBUG_MATCH: 学生 {student.id} ({student.name}) - 地理位置得分: {location_score:.4f}")

        combined_score = (sim_score * 0.5) + \
                         (proficiency_score * 0.3) + \
                         (time_score * 0.1) + \
                         (location_score * 0.1)

        print(
            f"DEBUG_MATCH: 学生 {student.id} ({student.name}) - 嵌入相似度: {sim_score:.4f}, 熟练度得分: {proficiency_score:.4f}, 时间得分: {time_score:.4f}, 地理位置得分: {location_score:.4f}, 综合得分: {combined_score:.4f}")

        enhancement_opportunities = _identify_enhancement_opportunities(student=student, project=project,
                                                                        match_type="project_to_student")

        refined_candidates.append({
            "student": student,
            "combined_score": combined_score,
            "sim_score": sim_score,
            "proficiency_score": proficiency_score,
            "time_score": time_score,
            "location_score": location_score,
            "enhancement_opportunities": enhancement_opportunities
        })

    refined_candidates.sort(key=lambda x: x["combined_score"], reverse=True)

    #  阶段 3: Reranking with specialized model
    reranker_documents = [candidate["student"].combined_text or "" for candidate in refined_candidates[:final_k * 2] if
                          candidate["student"].combined_text and candidate["student"].combined_text.strip()]
    reranker_query = project.combined_text or ""

    final_recommendations = []
    if reranker_documents and reranker_query and reranker_query.strip():
        try:
            # 将项目创建者自己的 API Key 传递给 get_rerank_scores_from_api
            rerank_scores = await get_rerank_scores_from_api(
                reranker_query,
                reranker_documents,
                api_key=project_api_key_for_embedding_and_rerank  # 传递项目创建者密钥
            )

            reranked_students_with_scores = []
            rerank_doc_to_full_candidate_map = {
                (c["student"].combined_text or ""): c
                for c in refined_candidates[:final_k * 2]
                if c["student"].combined_text and c["student"].combined_text.strip()
            }

            for score_idx, score_val in enumerate(rerank_scores):
                original_candidate_info = rerank_doc_to_full_candidate_map.get(reranker_documents[score_idx])
                if original_candidate_info:
                    reranked_students_with_scores.append({
                        "student": original_candidate_info["student"],
                        "relevance_score": score_val,
                        "combined_score_stage2": original_candidate_info["combined_score"],
                        "sim_score": original_candidate_info["sim_score"],
                        "proficiency_score": original_candidate_info["proficiency_score"],
                        "time_score": original_candidate_info["time_score"],
                        "location_score": original_candidate_info["location_score"],
                        "enhancement_opportunities": original_candidate_info["enhancement_opportunities"]
                    })

            reranked_students_with_scores.sort(key=lambda x: x["relevance_score"], reverse=True)

            for rec in reranked_students_with_scores[:final_k]:
                # MODIFICATION: 将项目创建者自己的 API Key 传递给 _generate_match_rationale_llm
                rationale = await _generate_match_rationale_llm(
                    student=rec["student"],
                    project=project,
                    sim_score=rec["sim_score"],
                    proficiency_score=rec["proficiency_score"],
                    time_score=rec["time_score"],
                    location_score=rec["location_score"],
                    enhancement_opportunities=rec["enhancement_opportunities"],
                    match_type="project_to_student",
                    llm_api_key=project_api_key_for_embedding_and_rerank  # 传递项目创建者密钥
                )
                final_recommendations.append(
                    MatchedStudent(
                        student_id=rec["student"].id,
                        name=rec["student"].name,
                        major=rec["student"].major,
                        skills=rec["student"].skills,
                        similarity_stage1=rec["combined_score_stage2"],
                        relevance_score=rec["relevance_score"],
                        match_rationale=rationale
                    )
                )
            print(f"INFO_AI_MATCHING: 为项目 {project_id} 推荐了 {len(final_recommendations)} 个学生 (Reranked)。")
        except Exception as e:
            print(f"ERROR_AI_MATCHING: 学生Rerank失败: {e}. 将退回至初步筛选结果。")
            import traceback
            traceback.print_exc()
            for rec in refined_candidates[:final_k]:
                rationale = await _generate_match_rationale_llm(
                    student=rec["student"],
                    project=project,
                    sim_score=rec["sim_score"],
                    proficiency_score=rec["proficiency_score"],
                    time_score=rec["time_score"],
                    location_score=rec["location_score"],
                    enhancement_opportunities=rec["enhancement_opportunities"],
                    match_type="project_to_student",
                    llm_api_key=project_api_key_for_embedding_and_rerank  # 传递项目创建者密钥
                )
                final_recommendations.append(
                    MatchedStudent(
                        student_id=rec["student"].id,
                        name=rec["student"].name,
                        major=rec["student"].major,
                        skills=rec["student"].skills,
                        similarity_stage1=rec["combined_score"],
                        relevance_score=rec["combined_score"],
                        match_rationale=rationale
                    )
                )
    else:
        print(
            f"WARNING_AI_MATCHING: 无有效文本进行学生 Rerank (query: '{reranker_query[:50]}', docs_len: {len(reranker_documents)}). 将返回初步筛选结果。")
        for rec in refined_candidates[:final_k]:
            rationale = await _generate_match_rationale_llm(
                student=rec["student"],
                project=project,
                sim_score=rec["sim_score"],
                proficiency_score=rec["proficiency_score"],
                time_score=rec["time_score"],
                location_score=rec["location_score"],
                enhancement_opportunities=rec["enhancement_opportunities"],
                match_type="project_to_student",
                llm_api_key=project_api_key_for_embedding_and_rerank  # 传递项目创建者密钥
            )
            final_recommendations.append(
                MatchedStudent(
                    student_id=rec["student"].id,
                    name=rec["student"].name,
                    major=rec["student"].major,
                    skills=rec["student"].skills,
                    similarity_stage1=rec["combined_score"],
                    relevance_score=rec["combined_score"],
                    match_rationale=rationale
                )
            )

    return final_recommendations