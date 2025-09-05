# project/services/embedding_service.py
"""嵌入向量管理服务"""

import logging
from typing import Optional, List, Dict, Any

from project.ai_providers.ai_config import GLOBAL_PLACEHOLDER_ZERO_VECTOR, get_user_model_for_provider
from project.ai_providers.embedding_provider import get_embeddings_from_api
from project.ai_providers.security_utils import decrypt_key
from project.models import User
from project.utils.auth.auth_utils import build_combined_text

logger = logging.getLogger(__name__)


class EmbeddingService:
    """嵌入向量管理服务"""
    
    @staticmethod
    async def generate_user_embedding(
        user_data: Dict[str, Any],
        api_key: Optional[str] = None,
        llm_type: Optional[str] = None,
        llm_base_url: Optional[str] = None,
        llm_model_id: Optional[str] = None
    ) -> Optional[List[float]]:
        """为新用户生成嵌入向量
        
        Args:
            user_data: 用户数据字典
            api_key: API密钥
            llm_type: LLM类型
            llm_base_url: LLM基础URL
            llm_model_id: LLM模型ID
            
        Returns:
            Optional[List[float]]: 嵌入向量，失败时返回None
        """
        combined_text = build_combined_text(user_data)
        
        if not combined_text:
            logger.warning("用户综合文本为空，无法生成嵌入向量")
            return GLOBAL_PLACEHOLDER_ZERO_VECTOR
        
        try:
            logger.debug("开始生成用户嵌入向量", extra={"text_preview": combined_text[:100]})
            
            embeddings = await get_embeddings_from_api(
                [combined_text],
                api_key=api_key,
                llm_type=llm_type,
                llm_base_url=llm_base_url,
                llm_model_id=llm_model_id
            )
            
            if embeddings:
                logger.info("用户嵌入向量生成成功")
                return embeddings[0]
            else:
                logger.warning("嵌入向量生成返回空结果")
                return GLOBAL_PLACEHOLDER_ZERO_VECTOR
                
        except Exception as e:
            logger.error("生成用户嵌入向量失败", extra={"error": str(e)})
            return GLOBAL_PLACEHOLDER_ZERO_VECTOR
    
    @staticmethod
    async def update_user_embedding(db_student: User) -> None:
        """更新用户嵌入向量
        
        Args:
            db_student: 用户数据库对象
        """
        # 构建用户数据字典
        user_data = {
            'name': db_student.name,
            'major': db_student.major,
            'skills': db_student.skills,
            'interests': db_student.interests,
            'bio': db_student.bio,
            'awards_competitions': db_student.awards_competitions,
            'academic_achievements': db_student.academic_achievements,
            'soft_skills': db_student.soft_skills,
            'portfolio_link': db_student.portfolio_link,
            'preferred_role': db_student.preferred_role,
            'availability': db_student.availability,
            'location': db_student.location
        }
        
        # 获取用户的API配置
        api_key = None
        if db_student.llm_api_key_encrypted:
            try:
                api_key = decrypt_key(db_student.llm_api_key_encrypted)
                logger.debug("使用用户配置的API密钥进行嵌入生成", extra={"user_id": db_student.id})
            except Exception as e:
                logger.error("解密用户API密钥失败", extra={"error": str(e), "user_id": db_student.id})
                api_key = None
        
        # 获取用户的模型配置
        llm_model_id = get_user_model_for_provider(
            db_student.llm_model_ids,
            db_student.llm_api_type,
            db_student.llm_model_id
        )
        
        # 生成新的嵌入向量
        new_embedding = await EmbeddingService.generate_user_embedding(
            user_data=user_data,
            api_key=api_key,
            llm_type=db_student.llm_api_type,
            llm_base_url=db_student.llm_api_base_url,
            llm_model_id=llm_model_id
        )
        
        # 更新用户的嵌入向量
        if new_embedding:
            db_student.embedding = new_embedding
            logger.info("用户嵌入向量更新成功", extra={"user_id": db_student.id})
        else:
            db_student.embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR
            logger.warning("使用零向量作为用户嵌入向量", extra={"user_id": db_student.id})
        
        # 更新combined_text
        db_student.combined_text = build_combined_text(user_data)


# 为了向后兼容，保留原有的类名
EmbeddingManager = EmbeddingService
