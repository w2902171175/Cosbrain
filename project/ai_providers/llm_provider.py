# ai_providers/llm_provider.py
"""
企业级LLM服务提供者实现
支持多种提供商、监控、缓存、重试、限流等功能
"""
import asyncio
import httpx
import json
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI, APIError, RateLimitError, AuthenticationError

from .ai_base import (
    LLMProvider, 
    with_monitoring, 
    with_retry
)
from .ai_config import DEFAULT_LLM_API_CONFIG

# 企业级功能标志
try:
    from . import ENTERPRISE_FEATURES
except ImportError:
    ENTERPRISE_FEATURES = False


class OpenAIProvider(LLMProvider):
    """OpenAI LLM服务提供者 - 企业级版本"""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None, model: Optional[str] = None):
        super().__init__("openai", api_key, base_url, model)
        
        # 设置默认配置
        if not self.base_url:
            self.base_url = DEFAULT_LLM_API_CONFIG["openai"]["base_url"]
        if not self.model:
            self.model = DEFAULT_LLM_API_CONFIG["openai"]["default_model"]
            
        self.client = AsyncOpenAI(api_key=api_key, base_url=self.base_url)
        
        self.logger.info("OpenAI provider initialized", extra={
            "base_url": self.base_url,
            "model": self.model,
            "api_key": self._sanitize_api_key(api_key)
        })
    
    @with_monitoring("chat_completion")
    @with_retry()
    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        temperature: float = 0.5,
        top_p: float = 0.9,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """使用OpenAI SDK执行聊天完成请求"""
        try:
            # 准备请求参数
            completion_params = {
                "model": model or self.model,
                "messages": messages,
                "temperature": temperature,
                "top_p": top_p
            }
            
            # 如果有工具，添加工具参数
            if tools:
                completion_params["tools"] = tools
                if tool_choice:
                    completion_params["tool_choice"] = tool_choice
            
            self.logger.info(f"Sending chat completion request", extra={
                "model": completion_params["model"],
                "message_count": len(messages),
                "has_tools": bool(tools),
                "temperature": temperature
            })
            
            # 调用OpenAI API
            completion = await self.client.chat.completions.create(**completion_params)
            
            # 转换为字典格式
            result = completion.model_dump()
            
            self.logger.info("Chat completion successful", extra={
                "usage": result.get("usage", {}),
                "model": result.get("model")
            })
            
            return result
            
        except AuthenticationError as e:
            self.logger.error("OpenAI API authentication failed", error=e, extra={
                "api_key": self._sanitize_api_key(self.api_key)
            })
            raise
        except RateLimitError as e:
            self.logger.warning("OpenAI API rate limit exceeded", error=e)
            raise
        except APIError as e:
            self.logger.error("OpenAI API error", error=e)
            raise
        except Exception as e:
            self.logger.error("Unexpected OpenAI API error", error=e)
            raise


class CustomOpenAIProvider(LLMProvider):
    """自定义OpenAI兼容服务提供者 - 企业级版本"""
    
    def __init__(self, api_key: str, base_url: str, model: str):
        super().__init__("custom_openai", api_key, base_url, model)
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        
        self.logger.info("Custom OpenAI provider initialized", extra={
            "base_url": base_url,
            "model": model
        })
    
    @with_monitoring("chat_completion")
    @with_retry()
    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        temperature: float = 0.5,
        top_p: float = 0.9,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """使用自定义OpenAI兼容API执行聊天完成请求"""
        try:
            completion_params = {
                "model": model or self.model,
                "messages": messages,
                "temperature": temperature,
                "top_p": top_p
            }
            
            if tools:
                completion_params["tools"] = tools
                if tool_choice:
                    completion_params["tool_choice"] = tool_choice
            
            self.logger.info(f"Sending request to custom OpenAI API", extra={
                "model": completion_params["model"],
                "message_count": len(messages)
            })
            
            completion = await self.client.chat.completions.create(**completion_params)
            result = completion.model_dump()
            
            self.logger.info("Custom OpenAI API request successful")
            return result
            
        except Exception as e:
            self.logger.error("Custom OpenAI API error", error=e)
            raise


class HttpxLLMProvider(LLMProvider):
    """基于httpx的通用LLM服务提供者 - 企业级版本"""
    
    def __init__(self, api_key: str, base_url: str, model: str, provider_type: str):
        super().__init__(provider_type, api_key, base_url, model)
        self.provider_type = provider_type
        self.config = DEFAULT_LLM_API_CONFIG.get(provider_type, {})
        self.chat_url = f"{base_url.rstrip('/')}{self.config.get('chat_path', '/chat/completions')}"
        
        self.logger.info(f"HttpxLLM provider initialized", extra={
            "provider_type": provider_type,
            "chat_url": self.chat_url,
            "model": model
        })
    
    @with_monitoring("chat_completion")
    @with_retry()
    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        temperature: float = 0.5,
        top_p: float = 0.9,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """使用httpx执行聊天完成请求"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # 准备请求数据
        data = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p
        }
        
        if tools:
            data["tools"] = tools
            if tool_choice:
                data["tool_choice"] = tool_choice
        
        try:
            # 使用企业级HTTP客户端
            if ENTERPRISE_FEATURES:
                async with await self._get_http_client() as client:
                    self.logger.info(f"Sending request to {self.provider_type}", extra={
                        "url": self.chat_url,
                        "model": data["model"],
                        "message_count": len(messages)
                    })
                    
                    response = await client.post(
                        self.chat_url,
                        headers=headers,
                        json=data
                    )
                    response.raise_for_status()
                    result = response.json()
            else:
                # 基础HTTP客户端
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        self.chat_url,
                        headers=headers,
                        json=data
                    )
                    response.raise_for_status()
                    result = response.json()
            
            self.logger.info(f"{self.provider_type} API request successful", extra={
                "usage": result.get("usage", {})
            })
            
            return result
            
        except httpx.HTTPStatusError as e:
            error_detail = ""
            try:
                error_detail = e.response.text
            except:
                pass
            
            self.logger.error(f"{self.provider_type} API HTTP error", error=e, extra={
                "status_code": e.response.status_code,
                "response_text": error_detail[:500]  # 限制错误文本长度
            })
            raise
            
        except httpx.RequestError as e:
            self.logger.error(f"{self.provider_type} API request error", error=e)
            raise
            
        except Exception as e:
            self.logger.error(f"{self.provider_type} API unexpected error", error=e)
            raise


def create_llm_provider(
    provider_type: str,
    api_key: str,
    base_url: Optional[str] = None,
    model: Optional[str] = None
) -> LLMProvider:
    """
    LLM提供者工厂函数 - 企业级版本
    
    Args:
        provider_type: 提供者类型 (openai, custom_openai, deepseek, siliconflow, etc.)
        api_key: API密钥
        base_url: API基础URL（可选）
        model: 模型名称（可选）
        
    Returns:
        LLM提供者实例
    """
    config = DEFAULT_LLM_API_CONFIG.get(provider_type, {})
    
    # 确定base_url
    if not base_url:
        base_url = config.get("base_url")
    
    # 确定model
    if not model:
        model = config.get("default_model")
    
    if provider_type == "openai":
        return OpenAIProvider(api_key, base_url, model)
    elif provider_type == "custom_openai":
        if not base_url or not model:
            raise ValueError("custom_openai 提供者需要指定 base_url 和 model")
        return CustomOpenAIProvider(api_key, base_url, model)
    else:
        # 对于其他提供者，使用httpx实现
        if not base_url:
            raise ValueError(f"未知的提供者类型: {provider_type}")
        return HttpxLLMProvider(api_key, base_url, model, provider_type)


# 兼容性包装函数
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
    import re
    
    if not messages:
        return "无题对话"

    # 提取最近的10条消息进行总结
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
        return "新对话"

    # 构建发送给LLM的完整消息，要求生成标题
    system_prompt = """你是一个专业的对话总结助手。请简洁地总结提供的对话内容，生成一个长度为3到15个汉字的对话标题。标题应准确反映对话的核心主题，不要包含任何标点符号。直接给出标题，不要有其他前缀或解释。"""

    # 将对话历史作为用户消息的一部分传递给LLM
    llm_input_messages = [{"role": "system", "content": system_prompt}] + llm_context_messages
    llm_input_messages.append({"role": "user", "content": "请根据以上对话内容，生成一个简洁的标题。"})

    try:
        # 创建LLM提供者
        provider = create_llm_provider(
            provider_type=user_llm_api_type,
            api_key=user_llm_api_key,
            base_url=user_llm_api_base_url,
            model=user_llm_model_id
        )

        llm_response = await provider.chat_completion(
            messages=llm_input_messages,
            temperature=0.7
        )

        generated_title = llm_response['choices'][0]['message'].get('content', '').strip()

        # 清理生成的标题，去除标点符号，限制长度
        clean_title = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s]', '', generated_title)  # 仅保留中英文、数字和空格
        clean_title = clean_title.replace(' ', '')  # 移除空格
        if len(clean_title) > 15:
            clean_title = clean_title[:15]
        if not clean_title:  # 如果清理后变为空，给一个默认标题
            clean_title = "无标题对话"

        return clean_title
    except Exception as e:
        print(f"ERROR_LLM_TITLE: 调用LLM生成标题失败: {e}. 返回默认标题。")
        return "新对话"
