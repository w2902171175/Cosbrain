# project/services/sharing_service.py
"""
分享服务模块
提供平台内容的转发分享功能业务逻辑
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, or_, func
from fastapi import HTTPException, status

# 核心依赖
from project.models import (
    SharedContent, ShareLog, ShareTemplate,
    User, Project, Course, KnowledgeBase, Folder,
    ForumTopic, ChatRoom, ChatMessage
)
import project.schemas as schemas

# 工具导入
from project.utils.optimization.production_utils import cache_manager
from project.services.forum_service import ForumService
from project.services.chatroom_base_service import ChatRoomBaseService

logger = logging.getLogger(__name__)


class SharingService:
    """分享服务类"""
    
    @staticmethod
    async def create_share(
        db: Session,
        share_request: schemas.ShareContentRequest,
        current_user_id: int
    ) -> schemas.ShareContentResponse:
        """创建分享"""
        try:
            # 验证内容是否存在且可分享
            content_info = await SharingService._validate_shareable_content(
                db, share_request.content_type, share_request.content_id, current_user_id
            )
            
            # 创建分享记录
            shared_content = SharedContent(
                owner_id=current_user_id,
                content_type=share_request.content_type,
                content_id=share_request.content_id,
                content_title=share_request.title or content_info['title'],
                content_description=share_request.description or content_info['description'],
                share_type=share_request.share_type,
                target_id=share_request.target_id,
                is_public=share_request.is_public,
                allow_comments=share_request.allow_comments,
                expires_at=share_request.expires_at,
                content_metadata=content_info.get('metadata', {})
            )
            
            db.add(shared_content)
            db.commit()
            db.refresh(shared_content)
            
            # 记录分享日志
            await SharingService._log_share_action(
                db, shared_content.id, current_user_id, "create"
            )
            
            # 执行具体的分享操作
            if share_request.share_type == "forum_topic":
                await SharingService._share_to_forum(db, shared_content, current_user_id)
            elif share_request.share_type == "chatroom":
                await SharingService._share_to_chatroom(db, shared_content, current_user_id)
            
            logger.info(f"用户 {current_user_id} 创建分享 {shared_content.id}")
            return await SharingService._format_share_response(db, shared_content)
            
        except Exception as e:
            logger.error(f"创建分享失败: {e}")
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="创建分享失败"
            )
    
    @staticmethod
    async def share_to_forum(
        db: Session,
        share_request: schemas.ShareToForumRequest,
        current_user_id: int
    ) -> schemas.ShareToForumResponse:
        """分享到论坛"""
        try:
            # 验证内容
            content_info = await SharingService._validate_shareable_content(
                db, share_request.content_type, share_request.content_id, current_user_id
            )
            
            # 生成论坛话题内容
            topic_content = SharingService._generate_forum_content(
                content_info, share_request.additional_content
            )
            
            # 创建论坛话题
            topic_data = {
                "title": share_request.title or f"分享：{content_info['title']}",
                "content": topic_content,
                "shared_item_type": share_request.content_type,
                "shared_item_id": share_request.content_id,
                "tags": share_request.tags
            }
            
            topic = ForumService.create_topic_optimized(db, topic_data, current_user_id)
            
            # 创建分享记录
            shared_content = SharedContent(
                owner_id=current_user_id,
                content_type=share_request.content_type,
                content_id=share_request.content_id,
                content_title=content_info['title'],
                content_description=content_info['description'],
                share_type="forum_topic",
                target_id=topic.id,
                content_metadata=content_info.get('metadata', {})
            )
            
            db.add(shared_content)
            db.commit()
            db.refresh(shared_content)
            
            # 记录日志
            await SharingService._log_share_action(
                db, shared_content.id, current_user_id, "share_to_forum"
            )
            
            return schemas.ShareToForumResponse(
                topic_id=topic.id,
                share_id=shared_content.id,
                topic_url=f"/forum/topics/{topic.id}"
            )
            
        except Exception as e:
            logger.error(f"分享到论坛失败: {e}")
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="分享到论坛失败"
            )
    
    @staticmethod
    async def share_to_chatroom(
        db: Session,
        share_request: schemas.ShareToChatroomRequest,
        current_user_id: int
    ) -> schemas.ShareToChatroomResponse:
        """分享到聊天室"""
        try:
            # 验证内容
            content_info = await SharingService._validate_shareable_content(
                db, share_request.content_type, share_request.content_id, current_user_id
            )
            
            results = []
            success_count = 0
            failed_count = 0
            
            for chatroom_id in share_request.chatroom_ids:
                try:
                    # 验证聊天室权限
                    chatroom = db.query(ChatRoom).filter(ChatRoom.id == chatroom_id).first()
                    if not chatroom:
                        results.append({
                            "chatroom_id": chatroom_id,
                            "success": False,
                            "error": "聊天室不存在"
                        })
                        failed_count += 1
                        continue
                    
                    # 检查用户是否有权限发送消息
                    if not chatroom.is_member(current_user_id):
                        results.append({
                            "chatroom_id": chatroom_id,
                            "success": False,
                            "error": "没有权限在此聊天室发送消息"
                        })
                        failed_count += 1
                        continue
                    
                    # 生成分享消息内容
                    message_content = SharingService._generate_chatroom_message(
                        content_info, share_request.message
                    )
                    
                    # 发送消息
                    message = await ChatRoomBaseService.create_message_with_cache(
                        db=db,
                        room_id=chatroom_id,
                        sender_id=current_user_id,
                        content=message_content,
                        message_type="share"
                    )
                    
                    # 创建分享记录
                    shared_content = SharedContent(
                        owner_id=current_user_id,
                        content_type=share_request.content_type,
                        content_id=share_request.content_id,
                        content_title=content_info['title'],
                        content_description=content_info['description'],
                        share_type="chatroom",
                        target_id=chatroom_id,
                        content_metadata=content_info.get('metadata', {})
                    )
                    
                    db.add(shared_content)
                    db.commit()
                    db.refresh(shared_content)
                    
                    # 记录日志
                    await SharingService._log_share_action(
                        db, shared_content.id, current_user_id, "share_to_chatroom"
                    )
                    
                    results.append({
                        "chatroom_id": chatroom_id,
                        "chatroom_name": chatroom.name,
                        "message_id": message.id,
                        "share_id": shared_content.id,
                        "success": True
                    })
                    success_count += 1
                    
                except Exception as e:
                    logger.error(f"分享到聊天室 {chatroom_id} 失败: {e}")
                    results.append({
                        "chatroom_id": chatroom_id,
                        "success": False,
                        "error": str(e)
                    })
                    failed_count += 1
            
            return schemas.ShareToChatroomResponse(
                share_results=results,
                success_count=success_count,
                failed_count=failed_count
            )
            
        except Exception as e:
            logger.error(f"分享到聊天室失败: {e}")
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="分享到聊天室失败"
            )
    
    @staticmethod
    async def generate_share_link(
        db: Session,
        content_type: str,
        content_id: int,
        current_user_id: int
    ) -> schemas.ShareLinkResponse:
        """生成分享链接"""
        try:
            # 验证内容
            content_info = await SharingService._validate_shareable_content(
                db, content_type, content_id, current_user_id
            )
            
            # 创建分享记录
            shared_content = SharedContent(
                owner_id=current_user_id,
                content_type=content_type,
                content_id=content_id,
                content_title=content_info['title'],
                content_description=content_info['description'],
                share_type="link",
                content_metadata=content_info.get('metadata', {})
            )
            
            db.add(shared_content)
            db.commit()
            db.refresh(shared_content)
            
            # 生成分享链接
            share_url = SharingService._generate_share_url(shared_content)
            
            # 生成分享文案
            share_text = SharingService._generate_share_text(content_info)
            
            # 记录日志
            await SharingService._log_share_action(
                db, shared_content.id, current_user_id, "generate_link"
            )
            
            return schemas.ShareLinkResponse(
                share_id=shared_content.id,
                share_url=share_url,
                share_text=share_text,
                expires_at=shared_content.expires_at,
                wechat_share=SharingService._generate_wechat_share(content_info, share_url),
                qq_share=SharingService._generate_qq_share(content_info, share_url)
            )
            
        except Exception as e:
            logger.error(f"生成分享链接失败: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="生成分享链接失败"
            )
    
    @staticmethod
    async def quick_share(
        db: Session,
        quick_share_request: schemas.QuickShareRequest,
        current_user_id: int
    ) -> schemas.QuickShareResponse:
        """快速分享到多个平台"""
        try:
            results = []
            success_count = 0
            failed_count = 0
            
            for platform in quick_share_request.platforms:
                try:
                    if platform == "forum":
                        result = await SharingService.share_to_forum(
                            db,
                            schemas.ShareToForumRequest(
                                content_type=quick_share_request.content_type,
                                content_id=quick_share_request.content_id,
                                additional_content=quick_share_request.custom_message
                            ),
                            current_user_id
                        )
                        results.append({
                            "platform": platform,
                            "success": True,
                            "data": result.dict()
                        })
                        success_count += 1
                        
                    elif platform == "link":
                        result = await SharingService.generate_share_link(
                            db, quick_share_request.content_type, 
                            quick_share_request.content_id, current_user_id
                        )
                        results.append({
                            "platform": platform,
                            "success": True,
                            "data": result.dict()
                        })
                        success_count += 1
                        
                    elif platform in ["wechat", "qq"]:
                        # 对于微信和QQ，生成特殊的分享链接
                        link_result = await SharingService.generate_share_link(
                            db, quick_share_request.content_type,
                            quick_share_request.content_id, current_user_id
                        )
                        
                        platform_data = getattr(link_result, f"{platform}_share", {})
                        results.append({
                            "platform": platform,
                            "success": True,
                            "data": {
                                "share_url": link_result.share_url,
                                "share_text": link_result.share_text,
                                "platform_data": platform_data
                            }
                        })
                        success_count += 1
                        
                except Exception as e:
                    logger.error(f"分享到平台 {platform} 失败: {e}")
                    results.append({
                        "platform": platform,
                        "success": False,
                        "error": str(e)
                    })
                    failed_count += 1
            
            return schemas.QuickShareResponse(
                share_results=results,
                success_count=success_count,
                failed_count=failed_count
            )
            
        except Exception as e:
            logger.error(f"快速分享失败: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="快速分享失败"
            )
    
    @staticmethod
    async def repost_forum_topic(
        db: Session,
        repost_request: schemas.ForumTopicRepostRequest,
        current_user_id: int
    ) -> schemas.ForumTopicRepostResponse:
        """论坛话题转发"""
        try:
            # 验证原始话题
            original_topic = db.query(ForumTopic).filter(ForumTopic.id == repost_request.topic_id).first()
            if not original_topic:
                raise HTTPException(status_code=404, detail="原始话题不存在")
            
            if original_topic.status != 'active':
                raise HTTPException(status_code=403, detail="此话题不能转发")
            
            if repost_request.share_type == "forum":
                # 转发到论坛：创建新话题
                repost_content = SharingService._generate_repost_content(original_topic, repost_request.additional_content)
                
                topic_data = {
                    "title": f"转发：{original_topic.title}",
                    "content": repost_content,
                    "shared_item_type": "forum_topic",
                    "shared_item_id": original_topic.id,
                    "tags": original_topic.tags
                }
                
                new_topic = ForumService.create_topic_optimized(db, topic_data, current_user_id)
                
                # 创建分享记录
                shared_content = SharedContent(
                    owner_id=current_user_id,
                    content_type="forum_topic",
                    content_id=original_topic.id,
                    content_title=original_topic.title,
                    content_description=original_topic.content[:500],
                    share_type="forum_topic",
                    target_id=new_topic.id,
                    content_metadata={
                        "original_topic_id": original_topic.id,
                        "repost_content": repost_request.additional_content
                    }
                )
                
                db.add(shared_content)
                db.commit()
                db.refresh(shared_content)
                
                # 记录日志
                await SharingService._log_share_action(
                    db, shared_content.id, current_user_id, "repost_to_forum"
                )
                
                return schemas.ForumTopicRepostResponse(
                    share_type="forum",
                    success=True,
                    message="成功转发到论坛",
                    new_topic_id=new_topic.id,
                    topic_url=f"/forum/topics/{new_topic.id}"
                )
                
            elif repost_request.share_type == "chatroom":
                # 转发到聊天室
                content_info = {
                    "title": original_topic.title,
                    "description": original_topic.content,
                    "author": original_topic.owner.name if original_topic.owner else "未知"
                }
                
                results = []
                success_count = 0
                failed_count = 0
                
                for chatroom_id in repost_request.chatroom_ids:
                    try:
                        # 验证聊天室权限
                        chatroom = db.query(ChatRoom).filter(ChatRoom.id == chatroom_id).first()
                        if not chatroom:
                            results.append({
                                "chatroom_id": chatroom_id,
                                "success": False,
                                "error": "聊天室不存在"
                            })
                            failed_count += 1
                            continue
                        
                        if not chatroom.is_member(current_user_id):
                            results.append({
                                "chatroom_id": chatroom_id,
                                "success": False,
                                "error": "没有权限在此聊天室发送消息"
                            })
                            failed_count += 1
                            continue
                        
                        # 生成转发消息
                        message_content = SharingService._generate_topic_repost_message(
                            original_topic, repost_request.additional_content
                        )
                        
                        # 发送消息
                        message = await ChatRoomBaseService.create_message_with_cache(
                            db=db,
                            room_id=chatroom_id,
                            sender_id=current_user_id,
                            content=message_content,
                            message_type="share"
                        )
                        
                        # 创建分享记录
                        shared_content = SharedContent(
                            owner_id=current_user_id,
                            content_type="forum_topic",
                            content_id=original_topic.id,
                            content_title=original_topic.title,
                            content_description=original_topic.content[:500],
                            share_type="chatroom",
                            target_id=chatroom_id,
                            content_metadata={
                                "original_topic_id": original_topic.id,
                                "repost_content": repost_request.additional_content
                            }
                        )
                        
                        db.add(shared_content)
                        db.commit()
                        db.refresh(shared_content)
                        
                        # 记录日志
                        await SharingService._log_share_action(
                            db, shared_content.id, current_user_id, "repost_to_chatroom"
                        )
                        
                        results.append({
                            "chatroom_id": chatroom_id,
                            "chatroom_name": chatroom.name,
                            "message_id": message.id,
                            "share_id": shared_content.id,
                            "success": True
                        })
                        success_count += 1
                        
                    except Exception as e:
                        logger.error(f"转发到聊天室 {chatroom_id} 失败: {e}")
                        results.append({
                            "chatroom_id": chatroom_id,
                            "success": False,
                            "error": str(e)
                        })
                        failed_count += 1
                
                return schemas.ForumTopicRepostResponse(
                    share_type="chatroom",
                    success=success_count > 0,
                    message=f"成功转发到 {success_count} 个聊天室，失败 {failed_count} 个",
                    chatroom_results=results,
                    success_count=success_count,
                    failed_count=failed_count
                )
        
        except Exception as e:
            logger.error(f"论坛话题转发失败: {e}")
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="论坛话题转发失败"
            )
    
    @staticmethod
    async def create_social_share(
        db: Session,
        social_request: schemas.SocialShareRequest,
        current_user_id: int
    ) -> schemas.SocialShareResponse:
        """创建社交平台分享"""
        try:
            # 验证内容
            content_info = await SharingService._validate_shareable_content(
                db, social_request.content_type, social_request.content_id, current_user_id
            )
            
            # 创建分享记录
            shared_content = SharedContent(
                owner_id=current_user_id,
                content_type=social_request.content_type,
                content_id=social_request.content_id,
                content_title=content_info['title'],
                content_description=content_info['description'],
                share_type=social_request.platform,
                content_metadata=content_info.get('metadata', {})
            )
            
            db.add(shared_content)
            db.commit()
            db.refresh(shared_content)
            
            # 生成分享链接和配置
            share_url = SharingService._generate_share_url(shared_content)
            share_text = SharingService._generate_share_text(content_info)
            
            # 生成平台特定配置
            wechat_config = None
            qq_config = None
            share_instructions = ""
            
            if social_request.platform == "wechat":
                wechat_config = SharingService._generate_wechat_share(content_info, share_url)
                share_instructions = "1. 点击下方链接复制\n2. 打开微信，选择联系人或群聊\n3. 粘贴链接并发送"
                
            elif social_request.platform == "qq":
                qq_config = SharingService._generate_qq_share(content_info, share_url)
                share_instructions = "1. 点击下方链接复制\n2. 打开QQ，选择联系人或群聊\n3. 粘贴链接并发送"
            
            # 记录日志
            await SharingService._log_share_action(
                db, shared_content.id, current_user_id, f"social_share_{social_request.platform}"
            )
            
            return schemas.SocialShareResponse(
                share_id=shared_content.id,
                platform=social_request.platform,
                share_url=share_url,
                share_text=share_text,
                wechat_config=wechat_config,
                qq_config=qq_config,
                share_instructions=share_instructions
            )
            
        except Exception as e:
            logger.error(f"创建社交平台分享失败: {e}")
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="创建社交平台分享失败"
            )
    
    @staticmethod
    async def create_copy_link(
        db: Session,
        copy_request: schemas.CopyLinkRequest,
        current_user_id: int
    ) -> schemas.CopyLinkResponse:
        """创建复制链接分享"""
        try:
            # 验证内容
            content_info = await SharingService._validate_shareable_content(
                db, copy_request.content_type, copy_request.content_id, current_user_id
            )
            
            # 创建分享记录
            shared_content = SharedContent(
                owner_id=current_user_id,
                content_type=copy_request.content_type,
                content_id=copy_request.content_id,
                content_title=content_info['title'],
                content_description=content_info['description'],
                share_type="link",
                content_metadata=content_info.get('metadata', {})
            )
            
            db.add(shared_content)
            db.commit()
            db.refresh(shared_content)
            
            # 生成分享链接
            share_url = SharingService._generate_share_url(shared_content)
            share_text = SharingService._generate_share_text(content_info)
            
            # 生成二维码（如果需要）
            qr_code_url = None
            if copy_request.include_qr:
                qr_code_url = SharingService._generate_qr_code(share_url)
            
            # 记录日志
            await SharingService._log_share_action(
                db, shared_content.id, current_user_id, "copy_link"
            )
            
            return schemas.CopyLinkResponse(
                share_id=shared_content.id,
                share_url=share_url,
                share_text=share_text,
                qr_code_url=qr_code_url,
                copy_success_message="链接已复制成功！",
                sharing_tips=[
                    "可以粘贴分享到微信、QQ等社交平台",
                    "可以通过邮件或短信分享给朋友",
                    "扫描二维码也可以快速访问",
                    "分享链接永久有效，除非手动删除"
                ]
            )
            
        except Exception as e:
            logger.error(f"创建复制链接分享失败: {e}")
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="创建复制链接分享失败"
            )
    
    @staticmethod
    async def get_user_shares(
        db: Session,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
        content_type: Optional[str] = None
    ) -> Tuple[List[schemas.ShareContentResponse], int]:
        """获取用户的分享列表"""
        try:
            query = db.query(SharedContent).filter(SharedContent.owner_id == user_id)
            
            if content_type:
                query = query.filter(SharedContent.content_type == content_type)
            
            total = query.count()
            shares = query.order_by(desc(SharedContent.created_at)).offset(skip).limit(limit).all()
            
            share_responses = []
            for share in shares:
                share_response = await SharingService._format_share_response(db, share)
                share_responses.append(share_response)
            
            return share_responses, total
            
        except Exception as e:
            logger.error(f"获取用户分享列表失败: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="获取分享列表失败"
            )
    
    @staticmethod
    async def get_share_stats(
        db: Session,
        user_id: int
    ) -> schemas.ShareStatsResponse:
        """获取分享统计"""
        try:
            # 基础统计
            total_shares = db.query(SharedContent).filter(SharedContent.owner_id == user_id).count()
            
            # 按类型统计
            shares_by_type = {}
            type_stats = db.query(
                SharedContent.content_type,
                func.count(SharedContent.id)
            ).filter(SharedContent.owner_id == user_id).group_by(SharedContent.content_type).all()
            
            for content_type, count in type_stats:
                shares_by_type[content_type] = count
            
            # 按平台统计
            shares_by_platform = {}
            platform_stats = db.query(
                SharedContent.share_type,
                func.count(SharedContent.id)
            ).filter(SharedContent.owner_id == user_id).group_by(SharedContent.share_type).all()
            
            for share_type, count in platform_stats:
                shares_by_platform[share_type] = count
            
            # 最近分享
            recent_shares_query = db.query(SharedContent).filter(
                SharedContent.owner_id == user_id
            ).order_by(desc(SharedContent.created_at)).limit(5).all()
            
            recent_shares = []
            for share in recent_shares_query:
                share_response = await SharingService._format_share_response(db, share)
                recent_shares.append(share_response)
            
            # 热门分享内容
            top_shared_query = db.query(SharedContent).filter(
                SharedContent.owner_id == user_id
            ).order_by(desc(SharedContent.view_count)).limit(10).all()
            
            top_shared_content = []
            for share in top_shared_query:
                top_shared_content.append({
                    "id": share.id,
                    "title": share.content_title,
                    "type": share.content_type,
                    "view_count": share.view_count,
                    "share_count": share.share_count
                })
            
            return schemas.ShareStatsResponse(
                total_shares=total_shares,
                shares_by_type=shares_by_type,
                shares_by_platform=shares_by_platform,
                recent_shares=recent_shares,
                top_shared_content=top_shared_content
            )
            
        except Exception as e:
            logger.error(f"获取分享统计失败: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="获取分享统计失败"
            )
    
    # ===== 私有辅助方法 =====
    
    @staticmethod
    async def _validate_shareable_content(
        db: Session,
        content_type: str,
        content_id: int,
        user_id: int
    ) -> Dict[str, Any]:
        """验证内容是否可分享"""
        content_info = {}
        
        if content_type == "project":
            project = db.query(Project).filter(Project.id == content_id).first()
            if not project:
                raise HTTPException(status_code=404, detail="项目不存在")
            
            # 检查项目是否公开或用户是否有权限
            if not project.is_public and project.creator_id != user_id:
                # 检查是否是项目成员
                from project.models import ProjectMember
                member = db.query(ProjectMember).filter(
                    and_(ProjectMember.project_id == content_id, ProjectMember.user_id == user_id)
                ).first()
                if not member:
                    raise HTTPException(status_code=403, detail="没有权限分享此项目")
            
            content_info = {
                "title": project.title,
                "description": project.description,
                "author": project.creator.name if project.creator else "未知",
                "is_public": project.is_public,
                "metadata": {
                    "location": project.location,
                    "team_size": project.team_size,
                    "cover_image_url": project.cover_image_url
                }
            }
            
        elif content_type == "course":
            course = db.query(Course).filter(Course.id == content_id).first()
            if not course:
                raise HTTPException(status_code=404, detail="课程不存在")
            
            if not course.is_public and course.creator_id != user_id:
                raise HTTPException(status_code=403, detail="没有权限分享此课程")
            
            content_info = {
                "title": course.title,
                "description": course.description,
                "author": course.instructor or (course.creator.name if course.creator else "未知"),
                "is_public": course.is_public,
                "metadata": {
                    "category": course.category,
                    "total_lessons": course.total_lessons,
                    "avg_rating": course.avg_rating,
                    "cover_image_url": course.cover_image_url
                }
            }
            
        elif content_type == "knowledge_base":
            kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == content_id).first()
            if not kb:
                raise HTTPException(status_code=404, detail="知识库不存在")
            
            if not kb.is_public and kb.owner_id != user_id:
                raise HTTPException(status_code=403, detail="没有权限分享此知识库")
            
            content_info = {
                "title": kb.name,
                "description": kb.description,
                "author": kb.owner.name if kb.owner else "未知",
                "is_public": kb.is_public,
                "metadata": {
                    "access_type": kb.access_type
                }
            }
            
        elif content_type == "note_folder":
            folder = db.query(Folder).filter(Folder.id == content_id).first()
            if not folder:
                raise HTTPException(status_code=404, detail="笔记文件夹不存在")
            
            if not folder.is_public and folder.owner_id != user_id:
                raise HTTPException(status_code=403, detail="没有权限分享此笔记文件夹")
            
            content_info = {
                "title": folder.name,
                "description": folder.description,
                "author": folder.owner.name if folder.owner else "未知",
                "is_public": folder.is_public,
                "metadata": {
                    "color": folder.color,
                    "icon": folder.icon
                }
            }
        
        elif content_type == "forum_topic":
            topic = db.query(ForumTopic).filter(ForumTopic.id == content_id).first()
            if not topic:
                raise HTTPException(status_code=404, detail="论坛话题不存在")
            
            # 论坛话题一般是公开的，任何用户都可以分享
            # 但可以检查话题状态
            if topic.status != 'active':
                raise HTTPException(status_code=403, detail="此话题不能分享")
            
            content_info = {
                "title": topic.title or "论坛话题",
                "description": topic.content[:200] + "..." if len(topic.content) > 200 else topic.content,
                "author": topic.owner.name if topic.owner else "未知",
                "is_public": True,  # 论坛话题默认公开
                "metadata": {
                    "tags": topic.tags,
                    "like_count": topic.like_count,
                    "comment_count": topic.comment_count,
                    "view_count": topic.view_count,
                    "created_at": topic.created_at.isoformat() if topic.created_at else None
                }
            }
            
        else:
            raise HTTPException(status_code=400, detail="不支持的内容类型")
        
        return content_info
    
    @staticmethod
    async def _share_to_forum(db: Session, shared_content: SharedContent, user_id: int):
        """分享到论坛的具体实现"""
        # 这个方法在 share_to_forum 中已经实现了具体逻辑
        pass
    
    @staticmethod
    async def _share_to_chatroom(db: Session, shared_content: SharedContent, user_id: int):
        """分享到聊天室的具体实现"""
        # 这个方法在 share_to_chatroom 中已经实现了具体逻辑
        pass
    
    @staticmethod
    async def _log_share_action(
        db: Session,
        shared_content_id: int,
        user_id: int,
        action_type: str,
        extra_data: Optional[Dict[str, Any]] = None
    ):
        """记录分享操作日志"""
        share_log = ShareLog(
            shared_content_id=shared_content_id,
            action_type=action_type,
            user_id=user_id,
            extra_data=extra_data
        )
        db.add(share_log)
        db.commit()
    
    @staticmethod
    def _generate_forum_content(content_info: Dict[str, Any], additional_content: Optional[str] = None) -> str:
        """生成论坛分享内容"""
        content = f"🎯 **{content_info['title']}**\n\n"
        
        if content_info.get('description'):
            content += f"📝 {content_info['description']}\n\n"
        
        if content_info.get('author'):
            content += f"👤 作者：{content_info['author']}\n\n"
        
        if additional_content:
            content += f"💬 分享者说：{additional_content}\n\n"
        
        content += "---\n*通过平台分享功能分享*"
        
        return content
    
    @staticmethod
    def _generate_chatroom_message(content_info: Dict[str, Any], custom_message: Optional[str] = None) -> str:
        """生成聊天室分享消息"""
        message = ""
        
        if custom_message:
            message += f"{custom_message}\n\n"
        
        message += f"🔗 分享：{content_info['title']}\n"
        
        if content_info.get('description'):
            message += f"📝 {content_info['description'][:100]}{'...' if len(content_info['description']) > 100 else ''}\n"
        
        return message
    
    @staticmethod
    def _generate_share_url(shared_content: SharedContent) -> str:
        """生成分享链接"""
        import os
        base_url = os.getenv("SHARE_BASE_URL") or os.getenv("SITE_BASE_URL")
        if not base_url:
            raise ValueError("未配置分享基础URL，请在.env文件中设置SHARE_BASE_URL或SITE_BASE_URL")
        return f"{base_url}/share/{shared_content.id}"
    
    @staticmethod
    def _generate_share_text(content_info: Dict[str, Any]) -> str:
        """生成分享文案"""
        text = f"推荐一个好内容：{content_info['title']}"
        
        if content_info.get('description'):
            text += f"\n\n{content_info['description'][:200]}{'...' if len(content_info['description']) > 200 else ''}"
        
        text += "\n\n来自 鸿庆书云创新协作平台"
        
        return text
    
    @staticmethod
    def _generate_wechat_share(content_info: Dict[str, Any], share_url: str) -> Dict[str, Any]:
        """生成微信分享数据"""
        return {
            "title": content_info['title'],
            "desc": content_info.get('description', '')[:100],
            "link": share_url,
            "imgUrl": content_info.get('metadata', {}).get('cover_image_url', ''),
            "type": "link"
        }
    
    @staticmethod
    def _generate_qq_share(content_info: Dict[str, Any], share_url: str) -> Dict[str, Any]:
        """生成QQ分享数据"""
        return {
            "title": content_info['title'],
            "summary": content_info.get('description', '')[:100],
            "url": share_url,
            "pics": content_info.get('metadata', {}).get('cover_image_url', ''),
            "flash": "false"
        }
    
    @staticmethod
    def _generate_repost_content(original_topic: ForumTopic, additional_content: Optional[str] = None) -> str:
        """生成论坛转发内容"""
        content = f"🔄 **转发分享**\n\n"
        content += f"**原标题：** {original_topic.title}\n\n"
        content += f"**原作者：** {original_topic.owner.name if original_topic.owner else '未知'}\n\n"
        
        # 显示原内容的片段
        original_content = original_topic.content[:300]
        if len(original_topic.content) > 300:
            original_content += "..."
        content += f"**原内容：**\n{original_content}\n\n"
        
        if additional_content:
            content += f"**转发者说：**\n{additional_content}\n\n"
        
        content += f"---\n"
        content += f"💬 点赞: {original_topic.like_count} | 评论: {original_topic.comment_count} | 浏览: {original_topic.view_count}\n"
        content += f"📅 发布时间: {original_topic.created_at.strftime('%Y-%m-%d %H:%M') if original_topic.created_at else '未知'}\n\n"
        content += f"[查看原话题](/forum/topics/{original_topic.id})"
        
        return content
    
    @staticmethod
    def _generate_topic_repost_message(original_topic: ForumTopic, additional_content: Optional[str] = None) -> str:
        """生成话题转发到聊天室的消息"""
        message = ""
        
        if additional_content:
            message += f"{additional_content}\n\n"
        
        message += f"🔄 转发话题：{original_topic.title}\n"
        message += f"👤 原作者：{original_topic.owner.name if original_topic.owner else '未知'}\n"
        
        # 显示内容片段
        content_preview = original_topic.content[:150]
        if len(original_topic.content) > 150:
            content_preview += "..."
        message += f"📝 {content_preview}\n\n"
        
        message += f"💬 {original_topic.comment_count}评论 👍 {original_topic.like_count}点赞\n"
        message += f"🔗 查看完整话题：/forum/topics/{original_topic.id}"
        
        return message
    
    @staticmethod
    def _generate_qr_code(url: str) -> Optional[str]:
        """生成二维码URL"""
        # 这里应该调用二维码生成服务
        import urllib.parse
        import os
        encoded_url = urllib.parse.quote(url)
        qr_base_url = os.getenv("QR_API_BASE_URL")
        if not qr_base_url:
            raise ValueError("未配置二维码API基础URL，请在.env文件中设置QR_API_BASE_URL")
        return f"{qr_base_url}/generate?data={encoded_url}"
    
    @staticmethod
    async def _format_share_response(db: Session, shared_content: SharedContent) -> schemas.ShareContentResponse:
        """格式化分享响应"""
        # 获取关联信息
        owner_name = shared_content.owner.name if shared_content.owner else None
        target_name = None
        share_url = None
        
        if shared_content.share_type == "chatroom" and shared_content.target_id:
            chatroom = db.query(ChatRoom).filter(ChatRoom.id == shared_content.target_id).first()
            target_name = chatroom.name if chatroom else None
        elif shared_content.share_type == "link":
            share_url = SharingService._generate_share_url(shared_content)
        
        return schemas.ShareContentResponse(
            id=shared_content.id,
            content_type=shared_content.content_type,
            content_id=shared_content.content_id,
            content_title=shared_content.content_title,
            content_description=shared_content.content_description,
            share_type=shared_content.share_type,
            target_id=shared_content.target_id,
            is_public=shared_content.is_public,
            allow_comments=shared_content.allow_comments,
            expires_at=shared_content.expires_at,
            view_count=shared_content.view_count,
            click_count=shared_content.click_count,
            share_count=shared_content.share_count,
            owner_id=shared_content.owner_id,
            status=shared_content.status,
            created_at=shared_content.created_at,
            updated_at=shared_content.updated_at,
            owner_name=owner_name,
            target_name=target_name,
            share_url=share_url
        )


class SharingUtils:
    """分享工具类"""
    
    @staticmethod
    def validate_share_permissions(content_type: str, content_id: int, user_id: int, db: Session) -> bool:
        """验证分享权限"""
        # 这个方法在 SharingService._validate_shareable_content 中已实现
        return True
    
    @staticmethod
    def format_share_preview(content_info: Dict[str, Any]) -> schemas.ShareableContentPreview:
        """格式化分享预览"""
        return schemas.ShareableContentPreview(
            id=content_info.get('id', 0),
            type=content_info.get('type', ''),
            title=content_info.get('title', ''),
            description=content_info.get('description'),
            author=content_info.get('author', ''),
            created_at=content_info.get('created_at', datetime.now()),
            is_public=content_info.get('is_public', False),
            thumbnail=content_info.get('metadata', {}).get('cover_image_url'),
            metadata=content_info.get('metadata')
        )
