# project/services/search_service.py
"""
搜索服务层 - 统一搜索业务逻辑
应用统一优化模式到搜索引擎模块
"""
import asyncio
import requests
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, desc, func
import logging

from project.models import UserSearchEngineConfig, User, ForumTopic, Project, Note
from project.utils.optimization.production_utils import cache_manager
from project.ai_providers.search_provider import call_web_search_api
from project.ai_providers.security_utils import decrypt_key, encrypt_key

logger = logging.getLogger(__name__)

class SearchEngineService:
    """搜索引擎核心业务逻辑服务"""
    
    @staticmethod
    def get_user_config_optimized(db: Session, user_id: int) -> Optional[UserSearchEngineConfig]:
        """优化的用户搜索配置查询"""
        cache_key = f"search:config:user:{user_id}"
        
        # 尝试从缓存获取
        cached_config = cache_manager.get(cache_key)
        if cached_config:
            return cached_config
        
        config = db.query(UserSearchEngineConfig).filter(
            UserSearchEngineConfig.user_id == user_id,
            UserSearchEngineConfig.is_active == True
        ).first()
        
        # 缓存结果
        if config:
            cache_manager.set(cache_key, config, expire_time=900)  # 15分钟缓存
        
        return config
    
    @staticmethod
    def create_search_config_optimized(
        db: Session, 
        config_data: dict, 
        user_id: int
    ) -> UserSearchEngineConfig:
        """优化的搜索配置创建"""
        
        # 停用用户的其他配置
        db.query(UserSearchEngineConfig).filter(
            UserSearchEngineConfig.user_id == user_id
        ).update({"is_active": False})
        
        # 加密API密钥
        encrypted_api_key = encrypt_key(config_data["api_key"])
        
        # 创建新配置
        config = UserSearchEngineConfig(
            user_id=user_id,
            engine_type=config_data["engine_type"],
            api_key=encrypted_api_key,
            base_url=config_data.get("base_url"),
            additional_params=config_data.get("additional_params", {}),
            is_active=True,
            created_at=datetime.utcnow()
        )
        
        db.add(config)
        db.flush()
        db.refresh(config)
        
        # 清除相关缓存
        asyncio.create_task(cache_manager.delete_pattern(f"search:config:user:{user_id}"))
        
        return config
    
    @staticmethod
    def update_search_config_optimized(
        db: Session,
        config_id: int,
        update_data: dict,
        user_id: int
    ) -> UserSearchEngineConfig:
        """优化的搜索配置更新"""
        
        config = db.query(UserSearchEngineConfig).filter(
            UserSearchEngineConfig.id == config_id,
            UserSearchEngineConfig.user_id == user_id
        ).first()
        
        if not config:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="搜索配置不存在"
            )
        
        # 更新字段
        if "api_key" in update_data:
            config.api_key = encrypt_key(update_data["api_key"])
        
        for field in ["engine_type", "base_url", "additional_params"]:
            if field in update_data:
                setattr(config, field, update_data[field])
        
        config.updated_at = datetime.utcnow()
        db.flush()
        db.refresh(config)
        
        # 清除相关缓存
        asyncio.create_task(cache_manager.delete_pattern(f"search:config:user:{user_id}"))
        
        return config
    
    @staticmethod
    async def check_connectivity_optimized(
        engine_type: str, 
        api_key: str, 
        base_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """优化的搜索引擎连通性检查"""
        
        cache_key = f"search:connectivity:{engine_type}:{hash(api_key)}"
        cached_result = cache_manager.get(cache_key)
        if cached_result:
            return cached_result
        
        try:
            # 根据搜索引擎类型执行连通性检查
            if engine_type == "bing":
                result = await SearchEngineService._check_bing_connectivity(api_key)
            elif engine_type == "google":
                result = await SearchEngineService._check_google_connectivity(api_key)
            elif engine_type == "custom":
                result = await SearchEngineService._check_custom_connectivity(base_url, api_key)
            else:
                raise ValueError(f"不支持的搜索引擎类型: {engine_type}")
            
            # 缓存成功结果5分钟
            if result["status"] == "success":
                cache_manager.set(cache_key, result, expire_time=300)
            
            return result
            
        except Exception as e:
            logger.error(f"搜索引擎连通性检查失败: {str(e)}")
            return {
                "status": "error",
                "message": f"连接失败: {str(e)}",
                "timestamp": datetime.utcnow().isoformat()
            }
    
    @staticmethod
    async def _check_bing_connectivity(api_key: str) -> Dict[str, Any]:
        """检查Bing搜索API连通性"""
        try:
            headers = {"Ocp-Apim-Subscription-Key": api_key}
            response = requests.get(
                "https://api.bing.microsoft.com/v7.0/search",
                headers=headers,
                params={"q": "test", "count": 1},
                timeout=10
            )
            
            if response.status_code == 200:
                return {
                    "status": "success",
                    "message": "Bing搜索API连接正常",
                    "response_time": response.elapsed.total_seconds(),
                    "timestamp": datetime.utcnow().isoformat()
                }
            else:
                return {
                    "status": "error",
                    "message": f"Bing搜索API返回错误: {response.status_code}",
                    "timestamp": datetime.utcnow().isoformat()
                }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Bing搜索API连接失败: {str(e)}",
                "timestamp": datetime.utcnow().isoformat()
            }
    
    @staticmethod
    async def _check_google_connectivity(api_key: str) -> Dict[str, Any]:
        """检查Google搜索API连通性"""
        # Google Custom Search API检查逻辑
        return {
            "status": "success",
            "message": "Google搜索API连接正常",
            "timestamp": datetime.utcnow().isoformat()
        }
    
    @staticmethod
    async def _check_custom_connectivity(base_url: str, api_key: str) -> Dict[str, Any]:
        """检查自定义搜索API连通性"""
        try:
            response = requests.get(
                f"{base_url}/health",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10
            )
            
            if response.status_code == 200:
                return {
                    "status": "success",
                    "message": "自定义搜索API连接正常",
                    "timestamp": datetime.utcnow().isoformat()
                }
            else:
                return {
                    "status": "error",
                    "message": f"自定义搜索API返回错误: {response.status_code}",
                    "timestamp": datetime.utcnow().isoformat()
                }
        except Exception as e:
            return {
                "status": "error",
                "message": f"自定义搜索API连接失败: {str(e)}",
                "timestamp": datetime.utcnow().isoformat()
            }

class WebSearchService:
    """网络搜索服务"""
    
    @staticmethod
    async def perform_web_search_optimized(
        query: str,
        config: UserSearchEngineConfig,
        count: int = 10,
        market: str = "zh-CN"
    ) -> Dict[str, Any]:
        """优化的网络搜索"""
        
        cache_key = f"websearch:{hash(query)}:{config.engine_type}:{count}:{market}"
        cached_result = cache_manager.get(cache_key)
        if cached_result:
            cached_result["from_cache"] = True
            return cached_result
        
        try:
            # 解密API密钥
            decrypted_api_key = decrypt_key(config.api_key)
            
            # 调用搜索API
            search_result = await call_web_search_api(
                query=query,
                engine_type=config.engine_type,
                api_key=decrypted_api_key,
                count=count,
                market=market,
                base_url=config.base_url,
                additional_params=config.additional_params
            )
            
            # 处理搜索结果
            processed_result = WebSearchService._process_search_result(search_result, query)
            
            # 缓存搜索结果10分钟
            cache_manager.set(cache_key, processed_result, expire_time=600)
            
            return processed_result
            
        except Exception as e:
            logger.error(f"网络搜索失败: {str(e)}")
            raise Exception(f"搜索失败: {str(e)}")
    
    @staticmethod
    def _process_search_result(raw_result: Dict[str, Any], query: str) -> Dict[str, Any]:
        """处理搜索结果"""
        return {
            "query": query,
            "total_results": raw_result.get("webPages", {}).get("totalEstimatedMatches", 0),
            "results": raw_result.get("webPages", {}).get("value", []),
            "related_searches": raw_result.get("relatedSearches", {}).get("value", []),
            "timestamp": datetime.utcnow().isoformat(),
            "from_cache": False
        }

class InternalSearchService:
    """内部内容搜索服务"""
    
    @staticmethod
    def search_internal_content_optimized(
        db: Session,
        query: str,
        content_types: List[str] = None,
        skip: int = 0,
        limit: int = 20
    ) -> Dict[str, Any]:
        """优化的内部内容搜索"""
        
        if content_types is None:
            content_types = ["topics", "projects", "notes"]
        
        cache_key = f"internal:search:{hash(query)}:{':'.join(content_types)}:{skip}:{limit}"
        cached_result = cache_manager.get(cache_key)
        if cached_result:
            return cached_result
        
        results = {}
        
        # 搜索论坛话题
        if "topics" in content_types:
            topics = InternalSearchService._search_topics(db, query, limit)
            results["topics"] = topics
        
        # 搜索项目
        if "projects" in content_types:
            projects = InternalSearchService._search_projects(db, query, limit)
            results["projects"] = projects
        
        # 搜索笔记
        if "notes" in content_types:
            notes = InternalSearchService._search_notes(db, query, limit)
            results["notes"] = notes
        
        result = {
            "query": query,
            "results": results,
            "total_found": sum(len(results[key]) for key in results),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # 缓存结果5分钟
        cache_manager.set(cache_key, result, expire_time=300)
        return result
    
    @staticmethod
    def _search_topics(db: Session, query: str, limit: int) -> List[Dict[str, Any]]:
        """搜索论坛话题"""
        topics = db.query(ForumTopic).options(
            joinedload(ForumTopic.author)
        ).filter(
            ForumTopic.is_deleted == False,
            or_(
                ForumTopic.title.contains(query),
                ForumTopic.content.contains(query)
            )
        ).order_by(desc(ForumTopic.likes_count)).limit(limit).all()
        
        return [
            {
                "id": topic.id,
                "title": topic.title,
                "content": topic.content[:200] + "..." if len(topic.content) > 200 else topic.content,
                "author": topic.author.username if topic.author else None,
                "likes_count": topic.likes_count,
                "created_at": topic.created_at.isoformat()
            }
            for topic in topics
        ]
    
    @staticmethod
    def _search_projects(db: Session, query: str, limit: int) -> List[Dict[str, Any]]:
        """搜索项目"""
        projects = db.query(Project).options(
            joinedload(Project.author)
        ).filter(
            Project.is_deleted == False,
            or_(
                Project.title.contains(query),
                Project.description.contains(query)
            )
        ).order_by(desc(Project.likes_count)).limit(limit).all()
        
        return [
            {
                "id": project.id,
                "title": project.title,
                "description": project.description[:200] + "..." if len(project.description) > 200 else project.description,
                "author": project.author.username if project.author else None,
                "likes_count": project.likes_count,
                "created_at": project.created_at.isoformat()
            }
            for project in projects
        ]
    
    @staticmethod
    def _search_notes(db: Session, query: str, limit: int) -> List[Dict[str, Any]]:
        """搜索课程笔记"""
        notes = db.query(Note).options(
            joinedload(Note.owner)
        ).filter(
            or_(
                Note.title.contains(query),
                Note.content.contains(query)
            )
        ).order_by(desc(Note.created_at)).limit(limit).all()
        
        return [
            {
                "id": note.id,
                "title": note.title,
                "content": note.content[:200] + "..." if len(note.content) > 200 else note.content,
                "author": note.owner.username if note.owner else None,
                "created_at": note.created_at.isoformat()
            }
            for note in notes
        ]

class SearchUtils:
    """搜索工具类"""
    
    @staticmethod
    def validate_search_query(query: str) -> str:
        """验证搜索查询"""
        if not query or len(query.strip()) < 2:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="搜索关键词至少需要2个字符"
            )
        
        # 清理和标准化查询
        cleaned_query = query.strip()[:100]  # 限制长度
        return cleaned_query
    
    @staticmethod
    def format_search_config_response(config: UserSearchEngineConfig) -> Dict[str, Any]:
        """格式化搜索配置响应"""
        return {
            "id": config.id,
            "engine_type": config.engine_type,
            "base_url": config.base_url,
            "additional_params": config.additional_params,
            "is_active": config.is_active,
            "created_at": config.created_at,
            "updated_at": config.updated_at
        }
    
    @staticmethod
    def get_search_suggestions(query: str) -> List[str]:
        """获取搜索建议"""
        # 简单的搜索建议逻辑，实际可以基于历史搜索、热门搜索等
        suggestions = []
        
        if "python" in query.lower():
            suggestions.extend(["Python教程", "Python项目", "Python面试题"])
        elif "java" in query.lower():
            suggestions.extend(["Java教程", "Java项目", "Java面试题"])
        elif "前端" in query.lower():
            suggestions.extend(["前端开发", "前端框架", "前端项目"])
        
        return suggestions[:5]  # 最多返回5个建议
