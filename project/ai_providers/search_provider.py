# ai_providers/search_provider.py
"""
搜索服务提供者实现
"""
import httpx
from typing import Dict, Any, Optional, List
from .ai_base import SearchProvider
from .ai_config import DEFAULT_SEARCH_CONFIGS


class BingSearchProvider(SearchProvider):
    """Bing搜索服务提供者"""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None):
        super().__init__(api_key, base_url)
        
        config = DEFAULT_SEARCH_CONFIGS["bing"]
        self.base_url = base_url or config["base_url"]
        self.subscription_key_header = config["subscription_key_header"]
    
    async def search(
        self,
        query: str,
        count: int = 10,
        offset: int = 0,
        language: str = "zh-CN"
    ) -> Dict[str, Any]:
        """执行Bing搜索"""
        headers = {
            self.subscription_key_header: self.api_key,
            "Content-Type": "application/json"
        }
        
        params = {
            "q": query,
            "count": count,
            "offset": offset,
            "mkt": language,
            "responseFilter": "webpages"
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    self.base_url,
                    headers=headers,
                    params=params
                )
                response.raise_for_status()
                return response.json()
                
        except httpx.HTTPStatusError as e:
            print(f"ERROR_BING_SEARCH: HTTP {e.response.status_code} 错误: {e.response.text}")
            return {"webPages": {"value": []}}
        except httpx.RequestError as e:
            print(f"ERROR_BING_SEARCH: 请求错误: {e}")
            return {"webPages": {"value": []}}
        except Exception as e:
            print(f"ERROR_BING_SEARCH: 未知错误: {e}")
            return {"webPages": {"value": []}}


class TavilySearchProvider(SearchProvider):
    """Tavily搜索服务提供者"""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None):
        super().__init__(api_key, base_url)
        
        config = DEFAULT_SEARCH_CONFIGS["tavily"]
        self.base_url = base_url or config["base_url"]
    
    async def search(
        self,
        query: str,
        count: int = 10,
        offset: int = 0,
        language: str = "zh-CN"
    ) -> Dict[str, Any]:
        """执行Tavily搜索"""
        headers = {
            "Content-Type": "application/json"
        }
        
        data = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": count,
            "include_answer": True,
            "include_raw_content": False
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.base_url,
                    headers=headers,
                    json=data
                )
                response.raise_for_status()
                return response.json()
                
        except httpx.HTTPStatusError as e:
            print(f"ERROR_TAVILY_SEARCH: HTTP {e.response.status_code} 错误: {e.response.text}")
            return {"results": []}
        except httpx.RequestError as e:
            print(f"ERROR_TAVILY_SEARCH: 请求错误: {e}")
            return {"results": []}
        except Exception as e:
            print(f"ERROR_TAVILY_SEARCH: 未知错误: {e}")
            return {"results": []}


class GoogleSearchProvider(SearchProvider):
    """Google自定义搜索引擎提供者"""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None):
        self.api_key = api_key
        self.base_url = base_url or "https://www.googleapis.com/customsearch/v1"
        self.search_engine_id = "dummy_search_engine_id"  # 需要配置实际的搜索引擎ID
    
    async def search(
        self, 
        query: str, 
        count: int = 10, 
        offset: int = 0, 
        language: str = "zh-CN"
    ) -> List[Dict[str, Any]]:
        """执行Google搜索"""
        params = {
            "key": self.api_key,
            "cx": self.search_engine_id,
            "q": query,
            "num": min(count, 10),  # Google API限制每次最多10个结果
            "start": offset + 1,    # Google API从1开始计数
            "lr": f"lang_{language[:2]}"
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                data = response.json()
                
                results = []
                if "items" in data:
                    for item in data["items"]:
                        results.append({
                            "title": item.get("title", ""),
                            "url": item.get("link", ""),
                            "snippet": item.get("snippet", ""),
                            "displayUrl": item.get("formattedUrl", "")
                        })
                
                return results
                
        except Exception as e:
            print(f"ERROR_GOOGLE_SEARCH: Google搜索失败: {e}")
            return []


def create_search_provider(
    provider_type: str,
    api_key: str,
    base_url: Optional[str] = None
) -> SearchProvider:
    """
    搜索提供者工厂函数
    
    Args:
        provider_type: 提供者类型
        api_key: API密钥
        base_url: API基础URL（可选）
        
    Returns:
        搜索提供者实例
    """
    if provider_type == "bing":
        return BingSearchProvider(api_key, base_url)
    elif provider_type == "tavily":
        return TavilySearchProvider(api_key, base_url)
    elif provider_type == "google":
        return GoogleSearchProvider(api_key, base_url)
    else:
        raise ValueError(f"不支持的搜索提供者类型: {provider_type}")


# --- 兼容性包装函数 ---
async def call_web_search_api(
    query: str,
    engine_type: str,
    api_key: str,
    base_url: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    向后兼容的网络搜索API调用函数
    保持与原ai_core.call_web_search_api的接口兼容
    """
    try:
        provider = create_search_provider(
            provider_type=engine_type,
            api_key=api_key,
            base_url=base_url
        )
        
        results = await provider.search(query, count=kwargs.get('count', 10))
        return results
        
    except Exception as e:
        print(f"WARNING: 网络搜索失败: {e}")
        return {
            "organic": [],
            "total_results": 0,
            "query": query
        }
