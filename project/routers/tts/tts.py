# project/routers/tts.py
"""
TTS模块路由层 - 优化版本
集成优化框架提供高性能的TTS配置管理和语音合成API
"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, Body
from sqlalchemy.orm import Session
import logging

# 核心导入
from project.database import get_db
from project.utils.core.error_decorators import handle_database_errors, database_transaction
from project.utils.optimization.router_optimization import optimized_route
import project.schemas as schemas
from project.services.tts_service import TTSConfigService, TTSSynthesisService, TTSUtilities

# 工具导入
from project.utils.optimization.production_utils import cache_manager
from project.utils import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tts", tags=["TTS语音合成"])

@router.get("/configs", response_model=schemas.PaginatedResponse)
@optimized_route("获取TTS配置列表")
async def get_tts_configs(
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(50, ge=1, le=100, description="返回的记录数"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    获取用户TTS配置列表
    
    - **skip**: 分页跳过的记录数
    - **limit**: 返回的记录数量限制
    """
    try:
        # 检查缓存
        cache_key = f"user_tts_configs_{current_user_id}_{skip}_{limit}"
        cached_result = cache_manager.get(cache_key)
        if cached_result:
            return cached_result
        
        configs, total = TTSConfigService.get_user_tts_configs_optimized(
            db, current_user_id, skip, limit
        )
        
        # 构建响应
        config_list = [TTSUtilities.build_safe_response_dict(config) for config in configs]
        result = {
            "items": config_list,
            "total": total,
            "skip": skip,
            "limit": limit,
            "has_more": skip + limit < total
        }
        
        # 缓存结果
        cache_manager.set(cache_key, result, ttl=300)  # 5分钟缓存
        
        logger.info(f"用户 {current_user_id} 获取TTS配置列表: {len(config_list)} 个配置")
        return result
        
    except Exception as e:
        logger.error(f"获取TTS配置列表失败: {e}")
        raise HTTPException(status_code=500, detail="获取TTS配置列表失败")

@router.post("/configs", response_model=schemas.Response)
@optimized_route("创建TTS配置")
@database_transaction
async def create_tts_config(
    config_data: Dict[str, Any] = Body(..., description="TTS配置数据"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    创建新的TTS配置
    
    - **config_data**: TTS配置数据，包含名称、提供商类型、API密钥等
    """
    try:
        # 创建配置
        new_config = TTSConfigService.create_tts_config_optimized(
            db, current_user_id, config_data
        )
        
        # 后台任务：清理相关缓存
        background_tasks.add_task(
            TTSUtilities.clear_user_cache, 
            current_user_id
        )
        
        result = TTSUtilities.build_safe_response_dict(new_config)
        
        logger.info(f"用户 {current_user_id} 创建TTS配置 {new_config.id}")
        return {
            "message": "TTS配置创建成功",
            "data": result
        }
        
    except ValueError as e:
        logger.warning(f"TTS配置创建参数错误: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"创建TTS配置失败: {e}")
        raise HTTPException(status_code=500, detail="创建TTS配置失败")

@router.get("/configs/{config_id}", response_model=schemas.Response)
@optimized_route("获取TTS配置详情")
async def get_tts_config(
    config_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    获取指定的TTS配置详情
    
    - **config_id**: TTS配置ID
    """
    try:
        # 检查缓存
        cache_key = f"tts_config_{config_id}_{current_user_id}"
        cached_result = cache_manager.get(cache_key)
        if cached_result:
            return cached_result
        
        config = TTSConfigService.get_tts_config_optimized(
            db, config_id, current_user_id
        )
        
        if not config:
            raise HTTPException(status_code=404, detail="TTS配置不存在")
        
        result = {
            "message": "获取TTS配置成功",
            "data": TTSUtilities.build_safe_response_dict(config)
        }
        
        # 缓存结果
        cache_manager.set(cache_key, result, ttl=600)  # 10分钟缓存
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取TTS配置失败: {e}")
        raise HTTPException(status_code=500, detail="获取TTS配置失败")

@router.put("/configs/{config_id}", response_model=schemas.Response)
@optimized_route("更新TTS配置")
@database_transaction
async def update_tts_config(
    config_id: int,
    update_data: Dict[str, Any] = Body(..., description="更新数据"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    更新TTS配置
    
    - **config_id**: TTS配置ID
    - **update_data**: 要更新的数据
    """
    try:
        updated_config = TTSConfigService.update_tts_config_optimized(
            db, config_id, current_user_id, update_data
        )
        
        if not updated_config:
            raise HTTPException(status_code=404, detail="TTS配置不存在")
        
        # 后台任务：清理缓存
        background_tasks.add_task(
            TTSUtilities.clear_config_cache, 
            config_id
        )
        background_tasks.add_task(
            TTSUtilities.clear_user_cache, 
            current_user_id
        )
        
        result = TTSUtilities.build_safe_response_dict(updated_config)
        
        logger.info(f"用户 {current_user_id} 更新TTS配置 {config_id}")
        return {
            "message": "TTS配置更新成功",
            "data": result
        }
        
    except ValueError as e:
        logger.warning(f"TTS配置更新参数错误: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新TTS配置失败: {e}")
        raise HTTPException(status_code=500, detail="更新TTS配置失败")

@router.delete("/configs/{config_id}", response_model=schemas.Response)
@optimized_route("删除TTS配置")
@database_transaction
async def delete_tts_config(
    config_id: int,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    删除TTS配置
    
    - **config_id**: 要删除的TTS配置ID
    """
    try:
        success = TTSConfigService.delete_tts_config_optimized(
            db, config_id, current_user_id
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="TTS配置不存在")
        
        # 后台任务：清理缓存
        background_tasks.add_task(
            TTSUtilities.clear_config_cache, 
            config_id
        )
        background_tasks.add_task(
            TTSUtilities.clear_user_cache, 
            current_user_id
        )
        
        logger.info(f"用户 {current_user_id} 删除TTS配置 {config_id}")
        return {"message": "TTS配置删除成功"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除TTS配置失败: {e}")
        raise HTTPException(status_code=500, detail="删除TTS配置失败")

@router.post("/synthesize", response_model=schemas.Response)
@optimized_route("文本转语音合成")
async def synthesize_text(
    synthesis_request: Dict[str, Any] = Body(
        ..., 
        description="语音合成请求",
        example={
            "text": "要转换的文本",
            "voice_config": {
                "voice": "default",
                "speed": 1.0,
                "pitch": 0
            }
        }
    ),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    文本转语音合成
    
    - **text**: 要转换为语音的文本
    - **voice_config**: 语音配置参数（可选）
    """
    try:
        text = synthesis_request.get("text")
        if not text or not text.strip():
            raise HTTPException(status_code=400, detail="文本内容不能为空")
        
        voice_config = synthesis_request.get("voice_config", {})
        
        # 执行语音合成
        synthesis_result = await TTSSynthesisService.synthesize_text_optimized(
            db, current_user_id, text.strip(), voice_config
        )
        
        if synthesis_result.get("status") == "error":
            raise HTTPException(
                status_code=400, 
                detail=synthesis_result.get("message", "语音合成失败")
            )
        
        logger.info(f"用户 {current_user_id} 完成文本转语音: {len(text)} 字符")
        return {
            "message": "语音合成成功",
            "data": synthesis_result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"语音合成失败: {e}")
        raise HTTPException(status_code=500, detail="语音合成服务错误")

@router.get("/providers", response_model=schemas.Response)
@optimized_route("获取TTS提供商列表")
async def get_tts_providers():
    """
    获取支持的TTS提供商列表
    """
    try:
        providers = [
            {
                "name": "Azure Cognitive Services",
                "type": "azure",
                "description": "微软Azure语音服务",
                "features": ["多语言", "自然语音", "SSML支持"]
            },
            {
                "name": "Google Cloud Text-to-Speech",
                "type": "google",
                "description": "谷歌云语音合成服务",
                "features": ["WaveNet", "多语言", "语音调节"]
            },
            {
                "name": "Amazon Polly",
                "type": "amazon",
                "description": "亚马逊Polly语音合成",
                "features": ["Neural TTS", "SSML", "语音标记"]
            },
            {
                "name": "OpenAI TTS",
                "type": "openai",
                "description": "OpenAI文本转语音",
                "features": ["高质量", "多种声音", "实时合成"]
            },
            {
                "name": "ElevenLabs",
                "type": "elevenlabs",
                "description": "ElevenLabs AI语音",
                "features": ["AI克隆", "情感表达", "高质量"]
            }
        ]
        
        return {
            "message": "获取TTS提供商列表成功",
            "data": {
                "providers": providers,
                "total": len(providers)
            }
        }
        
    except Exception as e:
        logger.error(f"获取TTS提供商列表失败: {e}")
        raise HTTPException(status_code=500, detail="获取提供商列表失败")

@router.get("/health", response_model=schemas.Response)
@optimized_route("TTS健康检查")
async def tts_health_check():
    """TTS模块健康检查"""
    try:
        # 检查缓存连接
        cache_status = "healthy" if cache_manager.is_connected() else "error"
        
        health_data = {
            "status": "healthy",
            "module": "TTS",
            "timestamp": logger.info("TTS模块健康检查"),
            "cache_status": cache_status,
            "version": "2.0.0"
        }
        
        return {
            "message": "TTS模块运行正常",
            "data": health_data
        }
        
    except Exception as e:
        logger.error(f"TTS健康检查失败: {e}")
        return {
            "message": "TTS模块健康检查异常",
            "data": {
                "status": "error",
                "error": str(e)
            }
        }

# 模块加载日志
logger.info("🎤 TTS Module - 语音合成模块已加载")
