# project/ai_core.py
import pandas as pd
import numpy as np
import os
import requests
import json
from typing import List, Dict, Any, Optional, Literal, Union
from sqlalchemy.orm import Session
from sqlalchemy import text
from sklearn.metrics.pairwise import cosine_similarity
import uuid
import time

# 导入 gTTS
from gtts import gTTS

# 导入文档解析库
from docx import Document as DocxDocument
import PyPDF2
# from unstructured.partition.auto import partition

from models import Student, Project, KnowledgeBase, KnowledgeArticle, Note, Course, KnowledgeDocument, \
    KnowledgeDocumentChunk, UserMcpConfig, UserSearchEngineConfig
from schemas import WebSearchResult, WebSearchResponse, McpToolDefinition, McpStatusResponse

# --- 全局常量 ---
INITIAL_CANDIDATES_K = 50
FINAL_TOP_K = 3

# --- 文件存储路径配置 ---
UPLOAD_DIRECTORY = "uploaded_files"
os.makedirs(UPLOAD_DIRECTORY, exist_ok=True)

# --- 加密库 (用于API密钥，生产环境需要更健壮的方案) ---
SIMPLE_ENCRYPTION_KEY = b"verysecretkey12345"


def _xor_encrypt_decrypt(data_bytes: bytes, key_bytes: bytes) -> bytes:
    return bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data_bytes))


def encrypt_key(plain_key: str) -> str:
    return _xor_encrypt_decrypt(plain_key.encode('utf-8'), SIMPLE_ENCRYPTION_KEY).hex()


def decrypt_key(encrypted_key_hex: str) -> str:
    return _xor_encrypt_decrypt(bytes.fromhex(encrypted_key_hex), SIMPLE_ENCRYPTION_KEY).decode(
        'utf-8')  # 注意这里修正了key的拼写


# --- 硅基流动API配置 (Embedding和Rerank固定模型) ---
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY")
if not SILICONFLOW_API_KEY or SILICONFLOW_API_KEY == "sk-YOUR_SILICONFLOW_API_KEY_HERE":
    print("警告：SILICONFLOW_API_KEY 环境变量未设置或为默认值。AI Embedding/Rerank功能将受限。")
    SILICONFLOW_API_KEY = "dummy_key_for_testing_without_api"

EMBEDDING_API_URL = "https://api.siliconflow.cn/v1/embeddings"
RERANKER_API_URL = "https://api.siliconflow.cn/v1/rerank"
EMBEDDING_MODEL_NAME = "BAAI/bge-m3"  # <--- 固定为 BAAI/bge-m3
RERANKER_MODEL_NAME = "BAAI/bge-reranker-v2-m3"  # <--- 固定为 BAAI/bge-reranker-v2-m3

# --- 通用大模型 API 配置示例 (回答模型由用户选择) ---
DEFAULT_LLM_API_CONFIG = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "chat_path": "/chat/completions",
        "default_model": "gpt-3.5-turbo",
        "available_models": ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo", "gpt-4o", "gpt-4o-mini"]
    },
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "chat_path": "/chat/completions",
        "default_model": "glm-4",
        "available_models": ["glm-4", "glm-4v", "glm-3-turbo", "glm-4-air", "glm-4-flash"]
    },
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1",
        "chat_path": "/chat/completions",
        "default_model": "deepseek-ai/DeepSeek-V3",  # <--- 硅基流动默认回答模型：deepseek-ai/DeepSeek-V3
        "available_models": ["deepseek-ai/DeepSeek-R1", "deepseek-ai/DeepSeek-V3"]  # <--- 硅基流动支持的回答模型列表
    },
    "huoshanengine": {
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "chat_path": "/chat/completions",
        "default_model": "Doubao-lite-llm-128k",
        "available_models": ["Doubao-lite-llm-128k", "Doubao-pro-llm-128k", "Doubao-pro-4k", "Doubao-pro-32k"]
    },
    "kimi": {
        "base_url": "https://api.moonshot.cn/v1",
        "chat_path": "/chat/completions",
        "default_model": "moonshot-v1-8k",
        "available_models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"]
    },
    "deepseek": {  # 保持 DeepSeek 原生通道配置，用户可以选择使用
        "base_url": "https://api.deepseek.com/v1",
        "chat_path": "/chat/completions",
        "default_model": "deepseek-chat",
        "available_models": ["deepseek-chat", "deepseek-coder"]
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
    return configs


async def call_llm_api(
        messages: List[Dict[str, Any]],
        user_llm_api_type: str,
        user_llm_api_key: str,
        user_llm_api_base_url: Optional[str] = None,
        user_llm_model_id: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None
) -> Dict[str, Any]:
    config = DEFAULT_LLM_API_CONFIG.get(user_llm_api_type)
    if not config:
        raise ValueError(f"不支持的LLM类型: {user_llm_api_type}")

    api_base_url = user_llm_api_base_url or config.get("base_url")
    chat_path = config.get("chat_path")

    # 优先使用用户在请求中指定的模型ID，否则使用LLM类型对应的默认模型
    model_to_use = user_llm_model_id or config.get("default_model")
    if model_to_use not in config.get("available_models", []):
        raise ValueError(f"指定模型 '{model_to_use}' 不受LLM类型 '{user_llm_api_type}' 支持，或不在可用模型列表中。")

    api_url = f"{api_base_url}{chat_path}"

    headers = {
        "Authorization": f"Bearer {user_llm_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_to_use,
        "messages": messages,
        "temperature": 0.5,
        "top_p": 0.9
    }

    if tools:
        payload["tools"] = tools
    if tool_choice:
        payload["tool_choice"] = tool_choice

    print(
        f"DEBUG_AI: Calling LLM API: Type={user_llm_api_type}, Model={model_to_use}, URL={api_url}, Tools={bool(tools)}")

    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=180)  # 超时时间
        response.raise_for_status()
        data = response.json()

        return data

    except requests.exceptions.RequestException as e:
        print(f"LLM API请求错误 ({user_llm_api_type}): {e}")
        print(f"LLM API响应内容: {response.text if 'response' in locals() else '无'}")
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
    headers = {"Content-Type": "application/json"}

    if search_engine_type == "bing":
        search_url = base_url or "https://api.bing.microsoft.com/v7.0/search"
        headers["Ocp-Apim-Subscription-Key"] = api_key
        params = {"q": query, "count": 5}
        try:
            response = requests.get(search_url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            for webpage in data.get("webPages", {}).get("value", []):
                results.append(WebSearchResult(
                    title=webpage.get("name", "无标题"),
                    url=webpage.get("url", "#"),
                    snippet=webpage.get("snippet", "无摘要")
                ))
            print(f"DEBUG_SEARCH: Bing search successful for '{query}'. Found {len(results)} results.")
        except requests.exceptions.RequestException as e:
            print(f"ERROR_SEARCH: Bing search failed: {e}. Response: {getattr(e.response, 'text', 'N/A')}")
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
            response = requests.post(search_url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
            for item in data.get("results", []):
                results.append(WebSearchResult(
                    title=item.get("title", "无标题"),
                    url=item.get("url", "#"),
                    snippet=item.get("content", "无摘要")
                ))
            print(f"DEBUG_SEARCH: Tavily search successful for '{query}'. Found {len(results)} results.")
        except requests.exceptions.RequestException as e:
            print(f"ERROR_SEARCH: Tavily search failed: {e}. Response: {getattr(e.response, 'text', 'N/A')}")
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


async def synthesize_speech(text: str, lang: str = 'zh-CN') -> str:
    """
    使用gTTS将文本转换为语音文件，并返回文件路径。
    """
    tts_audio_dir = "temp_audio"
    os.makedirs(tts_audio_dir, exist_ok=True)

    audio_filename = f"tts_{uuid.uuid4().hex}.mp3"
    audio_filepath = os.path.join(tts_audio_dir, audio_filename)

    try:
        print(f"DEBUG_TTS: Synthesizing speech for text (first 50 chars): '{text[:50]}'")
        start_time = time.time()

        tts = gTTS(text=text, lang=lang)
        tts.save(audio_filepath)

        end_time = time.time()
        print(
            f"DEBUG_TTS: Speech synthesis complete. Saved to {audio_filepath}. Time taken: {end_time - start_time:.2f}s")

        return audio_filepath
    except Exception as e:
        print(f"ERROR_TTS: Speech synthesis failed: {e}")
        raise


def get_embeddings_from_api(texts: List[str]) -> List[List[float]]:
    # Embedding 模型固定使用 BAAI/bge-m3
    if not SILICONFLOW_API_KEY or SILICONFLOW_API_KEY == "dummy_key_for_testing_without_api":
        print("API密钥未配置，无法获取嵌入。")
        return []

    headers = {
        "Authorization": f"Bearer {SILICONFLOW_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": EMBEDDING_MODEL_NAME,  # <--- 使用固定的 Embedding 模型
        "input": texts
    }
    try:
        response = requests.post(EMBEDDING_API_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        embeddings = [item['embedding'] for item in data['data']]
        return embeddings
    except requests.exceptions.RequestException as e:
        print(f"API请求错误 (Embedding): {e}")
        print(f"响应内容: {response.text if 'response' in locals() else '无'}")
        raise
    except KeyError as e:
        print(f"API响应格式错误 (Embedding): {e}. 响应: {data}")
        raise


def get_rerank_scores_from_api(query: str, documents: List[str]) -> List[float]:
    # Reranker 模型固定使用 BAAI/bge-reranker-v2-m3
    if not SILICONFLOW_API_KEY or SILICONFLOW_API_KEY == "dummy_key_for_testing_without_api":
        print("API密钥未配置，无法获取重排分数。")
        return [0.0] * len(documents)

    headers = {
        "Authorization": f"Bearer {SILICONFLOW_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": RERANKER_MODEL_NAME,  # <--- 使用固定的 Rerank 模型
        "query": query,
        "documents": documents
    }
    try:
        response = requests.post(RERANKER_API_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        scores = [item['relevance_score'] for item in data['results']]
        return scores
    except requests.exceptions.RequestException as e:
        print(f"API请求错误 (Reranker): {e}")
        print(f"响应内容: {response.text if 'response' in locals() else '无'}")
        raise
    except KeyError as e:
        print(f"API响应格式错误 (Reranker): {e}. 响应: {data}")
        raise


def extract_text_from_document(filepath: str, file_type: str) -> str:
    """
    根据文件类型从文档中提取文本内容。
    """
    text_content = ""
    if file_type == "application/pdf":
        try:
            with open(filepath, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                for page_num in range(len(reader.pages)):
                    page = reader.pages[page_num]
                    text_content += page.extract_text() or ""
            print(f"DEBUG_DOC_PARSE: Successfully extracted text from PDF: {filepath}")
        except Exception as e:
            print(f"ERROR_DOC_PARSE: Failed to extract text from PDF {filepath}: {e}")
            raise ValueError(f"无法解析PDF文件：{e}")
    elif file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":  # .docx
        try:
            doc = DocxDocument(filepath)
            for paragraph in doc.paragraphs:
                text_content += paragraph.text + "\n"
            print(f"DEBUG_DOC_PARSE: Successfully extracted text from DOCX: {filepath}")
        except Exception as e:
            print(f"ERROR_DOC_PARSE: Failed to extract text from DOCX {filepath}: {e}")
            raise ValueError(f"无法解析DOCX文件：{e}")
    elif file_type.startswith("text/"):  # .txt 或其他纯文本
        try:
            with open(filepath, 'r', encoding='utf-8') as file:
                text_content = file.read()
            print(f"DEBUG_DOC_PARSE: Successfully extracted text from TXT: {filepath}")
        except Exception as e:
            print(f"ERROR_DOC_PARSE: Failed to extract text from TXT {filepath}: {e}")
            raise ValueError(f"无法解析TXT文件：{e}")
    else:
        print(
            f"WARNING_DOC_PARSE: Unsupported file type for text extraction: {file_type} for {filepath}. Attempting basic text read.")
        try:
            with open(filepath, 'r', encoding='utf-8') as file:
                text_content = file.read()
        except Exception as e:
            raise ValueError(f"不支持的文件类型或无法提取文本：{file_type}。错误：{e}")

    if not text_content.strip():
        print(f"WARNING_DOC_PARSE: Extracted content is empty for {filepath} of type {file_type}")
        raise ValueError("文件内容为空或无法提取有效文本。")

    return text_content


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """
    将长文本分割成固定大小的文本块，并带有重叠。
    """
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
    """
    根据 LLM 决定的工具名称和参数执行对应的工具。
    返回工具执行的结果。
    """
    print(f"DEBUG_TOOL: 尝试执行工具：{tool_call_name}，参数：{tool_call_args}")

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

        if not kb_ids:
            user_kbs = db.query(KnowledgeBase).filter(KnowledgeBase.owner_id == user_id).all()
            kb_ids = [kb.id for kb in user_kbs]
            if not kb_ids:
                return "错误：未指定知识库ID，且用户没有创建任何知识库。无法执行知识库检索。"

        if not note_ids:
            user_notes = db.query(Note).filter(Note.owner_id == user_id).all()
            note_ids = [note.id for note in user_notes]

        context_docs = []
        source_articles_info = []

        articles_candidate = db.query(KnowledgeArticle).filter(
            KnowledgeArticle.kb_id.in_(kb_ids),
            KnowledgeArticle.author_id == user_id
        ).all()
        for article in articles_candidate:
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
                KnowledgeDocumentChunk.kb_id == doc.kb_id
            ).all()
            for chunk in doc_chunks:
                context_docs.append({
                    "content": chunk.content,
                    "type": "knowledge_document",
                    "id": doc.id,
                    "chunk_index": chunk.chunk_index,
                    "title": doc.file_name
                })

        if note_ids:
            notes_candidate = db.query(Note).filter(
                Note.id.in_(note_ids),
                Note.owner_id == user_id
            ).all()
            for note in notes_candidate:
                context_docs.append({
                    "content": note.title + "\n" + note.content,
                    "type": "note",
                    "id": note.id,
                    "title": note.title
                })

        if not context_docs:
            return "知识库或笔记中没有找到与问题相关的文档信息。"

        candidate_contents = [doc["content"] for doc in context_docs]
        if not candidate_contents:  # 再次检查空内容
            return "知识库或笔记中找到的文档内容为空，无法提取信息。"

        reranked_scores = get_rerank_scores_from_api(rag_query, candidate_contents)

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
            return "虽然在知识库中找到了一些文档，但未能提炼出足够相关或有用的信息来回答问题。"

        retrieved_content = "\n\n".join([doc["content"] for doc in context_for_llm])

        for doc in context_for_llm:
            source_doc_info = {
                "id": doc["id"],
                "title": doc["title"],
                "type": doc["type"],
                "chunk_index": doc.get("chunk_index")
            }
            source_articles_info.append(source_doc_info)

        return {"context": retrieved_content, "sources": source_articles_info}

    elif tool_call_name.startswith("mcp_"):
        parts = tool_call_name.split("_")
        if len(parts) < 3:
            return f"错误：MCP工具调用格式不正确: {tool_call_name}"

        mcp_config_id = int(parts[1])
        mcp_tool_id = "_".join(parts[2:])

        mcp_config = db.query(UserMcpConfig).filter(
            UserMcpConfig.id == mcp_config_id,
            UserMcpConfig.owner_id == user_id,
            UserMcpConfig.is_active == True
        ).first()

        if not mcp_config:
            return f"错误：MCP配置ID {mcp_config_id} 未找到、未启用或无权访问。"

        decrypted_key = ""
        if mcp_config.api_key_encrypted:
            try:
                decrypted_key = decrypt_key(mcp_config.api_key_encrypted)
            except Exception:
                return "错误：无法解密MCP API 密钥，请检查配置。"

        if mcp_tool_id == "visual_chart_generator":
            chart_type = tool_call_args.get("chart_type")
            data_points = tool_call_args.get("data_points")
            title = tool_call_args.get("title", "")

            print(f"DEBUG_TOOL: 调用MCP可视化图表工具: Type={chart_type}, Data={data_points}, Title={title}")

            if chart_type and data_points:
                img_url = f"https://example.com/charts/{chart_type}_{uuid.uuid4().hex}.png"
                return f"可视化图表已生成：{img_url}。标题：{title}。数据：{data_points}"
            else:
                return "生成可视化图表所需参数不完整。"
        elif mcp_tool_id == "image_generator":
            prompt = tool_call_args.get("prompt")
            style = tool_call_args.get("style", "realistic")

            print(f"DEBUG_TOOL: 调用MCP图像生成工具: Prompt='{prompt}', Style='{style}'")
            img_url = f"https://example.com/images/{style}_{uuid.uuid4().hex}.png"
            return f"图像已生成：{img_url}。基于描述：'{prompt}'。"
        else:
            return f"错误：不支持的MCP工具ID: {mcp_tool_id} (所属MCP配置: {mcp_config.name})。请检查ai_core.py中的 execute_tool。"

    else:
        return f"错误：未知工具：{tool_call_name}"


async def get_all_available_tools_for_llm(db: Session, user_id: int) -> List[Dict[str, Any]]:
    """
    汇集所有可用工具的定义（包括通用工具和用户自定义MCP工具）。
    返回 LLM 能够理解的工具定义列表。
    """
    tools = []

    # 1. 添加通用的内置工具
    tools.append(WEB_SEARCH_TOOL_SCHEMA)
    tools.append(RAG_KNOWLEDGE_BASE_TOOL_SCHEMA)

    # 2. 添加用户自定义且活跃的 MCP 工具
    active_mcp_configs = db.query(UserMcpConfig).filter(
        UserMcpConfig.owner_id == user_id,
        UserMcpConfig.is_active == True
    ).all()

    for config in active_mcp_configs:

        if "modelscope" in (config.base_url or "").lower() and (config.protocol_type or "").lower() == "sse":
            if "图表" in config.name or "chart" in (config.name or "").lower() or "visual" in (
                    config.name or "").lower():
                tools.append({
                    "type": "function",
                    "function": {
                        "name": f"mcp_{config.id}_visual_chart_generator",
                        "description": f"通过MCP服务 {config.name} ({config.base_url}) 将数据转换为多种类型的图表，支持折线图、柱状图、饼图等。",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "chart_type": {"type": "string", "enum": ["line", "bar", "pie"],
                                               "description": "图表类型"},
                                "data_points": {"type": "array", "items": {"type": "object",
                                                                           "properties": {"label": {"type": "string"},
                                                                                          "value": {
                                                                                              "type": "number"}}}},
                                "title": {"type": "string", "description": "图表标题", "nullable": True}
                            },
                            "required": ["chart_type", "data_points"]
                        }
                    }
                })
            if "图像生成" in config.name or "image" in (config.name or "").lower() or "gen" in (
                    config.name or "").lower():
                tools.append({
                    "type": "function",
                    "function": {
                        "name": f"mcp_{config.id}_image_generator",
                        "description": f"通过MCP服务 {config.name} ({config.base_url}) 根据文本描述生成高质量图像。",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "prompt": {"type": "string", "description": "生成图像的文本提示词"},
                                "style": {"type": "string", "enum": ["realistic", "cartoon", "abstract"],
                                          "description": "图像风格", "nullable": True}
                            },
                            "required": ["prompt"]
                        }
                    }
                })
        elif "my_private_mcp" == (config.mcp_type or ""):
            tools.append({
                "type": "function",
                "function": {
                    "name": f"mcp_{config.id}_text_summary_tool",
                    "description": f"通过您定义的MCP服务 {config.name} 对长文本进行概括总结。",
                    "parameters": {"type": "object",
                                   "properties": {"text": {"type": "string", "description": "待摘要的文本"}},
                                   "required": ["text"]},
                }
            })

    print(f"DEBUG_TOOL: 为用户 {user_id} 汇集了 {len(tools)} 个可用工具。")
    return tools


async def invoke_agent(
        db: Session,
        user_id: int,
        query: str,
        llm_api_type: str,
        llm_api_key: str,
        llm_api_base_url: Optional[str],
        llm_model_id: Optional[str],
        kb_ids: Optional[List[int]] = None,
        note_ids: Optional[List[int]] = None,
        preferred_tools: Optional[List[Literal["rag", "web_search", "mcp_tool"]]] = None
) -> Dict[str, Any]:
    """
    调用智能体进行问答，智能体可自主选择和调用工具。
    实现单步工具调用（Tool Use）逻辑。
    """
    messages = [{"role": "user", "content": query}]
    tool_outputs = []
    response_data = {}

    available_tools_for_llm = await get_all_available_tools_for_llm(db, user_id)

    tools_to_send_to_llm = []
    if preferred_tools:
        print(f"DEBUG_AGENT: 用户偏好工具：{preferred_tools}")
        for tool_def in available_tools_for_llm:
            tool_name = tool_def["function"]["name"]
            if ("rag" in preferred_tools and tool_name == "rag_knowledge_base") or \
                    ("web_search" in preferred_tools and tool_name == "web_search") or \
                    ("mcp_tool" in preferred_tools and tool_name.startswith("mcp_")):
                tools_to_send_to_llm.append(tool_def)
        if not tools_to_send_to_llm:
            print("WARNING_AGENT: 用户指定了偏好工具，但未找到匹配的活跃工具。将退化到通用问答。")
            final_llm_response = await call_llm_api(messages, llm_api_type, llm_api_key, llm_api_base_url, llm_model_id)
            if 'choices' in final_llm_response and final_llm_response['choices'][0]['message'].get('content'):
                response_data["answer"] = final_llm_response['choices'][0]['message']['content']
                response_data["answer_mode"] = "General_mode"
            else:
                response_data["answer"] = "服务繁忙，请稍后再试或提供更具体的问题。"
                response_data["answer_mode"] = "Failed_General_mode"
            return response_data
    else:

        tools_to_send_to_llm = available_tools_for_llm
        print(f"DEBUG_AGENT: 自动选择所有工具。")

    llm_response_data = await call_llm_api(
        messages,
        llm_api_type,
        llm_api_key,
        llm_api_base_url,
        llm_model_id,
        tools=tools_to_send_to_llm,
        tool_choice="auto"
    )

    choice = llm_response_data['choices'][0]
    message_content = choice['message']

    if message_content.get('tool_calls'):
        print(f"DEBUG_AGENT: LLM 决定调用工具：{message_content['tool_calls']}")
        tool_outputs_for_second_turn = []
        response_data["answer_mode"] = "Tool_Use_mode"
        response_data["tool_calls"] = []

        for tc in message_content['tool_calls']:
            tool_call_id = tc.get('id')
            tool_name = tc['function']['name']
            tool_args = json.loads(tc['function']['arguments'])

            response_data["tool_calls"].append({
                "tool_name": tool_name,
                "tool_args": tool_args,
                "status": "pending_execution"
            })

            tool_output_result = None
            try:
                if tool_name == "rag_knowledge_base":
                    tool_output_result = await execute_tool(
                        db=db,
                        tool_call_name=tool_name,
                        tool_call_args={"query": tool_args.get("query"), "kb_ids": kb_ids, "note_ids": note_ids},
                        user_id=user_id
                    )
                    rag_context = tool_output_result.get("context", "") if isinstance(tool_output_result,
                                                                                      dict) else str(tool_output_result)
                    response_data["source_articles"] = tool_output_result.get("sources", []) if isinstance(
                        tool_output_result, dict) else []
                    tool_output_result = rag_context

                elif tool_name == "web_search":

                    tool_output_result = await execute_tool(
                        db=db,
                        tool_call_name=tool_name,
                        tool_call_args={"query": tool_args.get("query"),
                                        "search_engine_config_id": tool_args.get("search_engine_config_id")},
                        user_id=user_id
                    )
                    response_data["search_results"] = []
                    results_list = []
                    if isinstance(tool_output_result, str) and tool_output_result.startswith("网络搜索结果:\n"):
                        lines = tool_output_result.strip().split("\n")
                        for line in lines[1:]:
                            if "标题:" in line and "链接:" in line and "摘要:" in line:
                                try:
                                    title = line.split("标题:")[1].split(", 摘要:")[0].strip()
                                    snippet = line.split("摘要:")[1].split(", 链接:")[0].strip()
                                    url = line.split("链接:")[1].strip()
                                    results_list.append({"title": title, "snippet": snippet, "url": url})
                                except Exception as parse_e:
                                    print(f"WARNING: 无法解析搜索结果字符串: {parse_e}")
                                    results_list.append({"raw": line})
                    response_data["search_results"] = results_list

                elif tool_name.startswith("mcp_"):
                    tool_output_result = await execute_tool(
                        db=db,
                        tool_call_name=tool_name,
                        tool_call_args=tc['function']['arguments'],
                        user_id=user_id
                    )
                else:
                    tool_output_result = f"错误：LLM尝试调用一个意外的工具：{tool_name}"
                    print(tool_output_result)

                tool_outputs_for_second_turn.append({
                    "tool_call_id": tool_call_id,
                    "output": tool_output_result
                })
                print(
                    f"DEBUG_AGENT: 工具 '{tool_name}' 执行成功，输出：{str(tool_output_result)[:100]}...")  # 转化成字符串避免TypeError
            except Exception as e:
                error_msg = f"工具 '{tool_name}' 执行失败: {e}"
                tool_outputs_for_second_turn.append({
                    "tool_call_id": tool_call_id,
                    "output": error_msg
                })
                print(f"ERROR_AGENT: {error_msg}")
                response_data["tool_calls"][-1]["status"] = "failed"
                response_data["tool_calls"][-1]["error"] = str(e)

        messages.append(message_content)
        for output in tool_outputs_for_second_turn:
            messages.append({"role": "tool", "tool_call_id": output["tool_call_id"], "content": str(output["output"])})

        print(f"DEBUG_AGENT: 将工具输出发回LLM，要求最终答案。")

        final_llm_response = await call_llm_api(
            messages,
            llm_api_type,
            llm_api_key,
            llm_api_base_url,
            llm_model_id,
            tools=None,
            tool_choice="none"
        )

        if 'choices' in final_llm_response and final_llm_response['choices'][0]['message'].get('content'):
            response_data["answer"] = final_llm_response['choices'][0]['message']['content']
            response_data["answer_mode"] = "Tool_Use_mode"
        else:
            response_data["answer"] = "工具调用完成，但LLM未能生成明确答案。请尝试更具体的问题。"
            response_data["answer_mode"] = "Tool_Use_Failed_Answer"

    else:

        print(f"DEBUG_AGENT: LLM 没有调用工具，直接给出答案。")
        if 'content' in message_content:
            response_data["answer"] = message_content['content']
            response_data["answer_mode"] = "General_mode"
        else:
            response_data["answer"] = "AI未能生成明确答案。请重试或换个问题。"
            response_data["answer_mode"] = "Failed_General_mode"

    response_data["llm_type_used"] = llm_api_type
    response_data["llm_model_used"] = llm_model_id

    return response_data


# --- 智能匹配函数 ---
async def find_matching_projects_for_student(db: Session, student_id: int,
                                             initial_k: int = INITIAL_CANDIDATES_K,
                                             final_k: int = FINAL_TOP_K) -> List[Dict[str, Any]]:
    return []


async def find_matching_students_for_project(db: Session, project_id: int,
                                             initial_k: int = INITIAL_CANDIDATES_K,
                                             final_k: int = FINAL_TOP_K) -> List[Dict[str, Any]]:
    return []
