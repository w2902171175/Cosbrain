# project/routers/ai/ai.py
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from typing import List, Optional, Dict, Any, Literal
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import time
import asyncio
import json
import os
import uuid
import traceback

from project.database import get_db, SessionLocal
from project.models import Student, Project, Course, KnowledgeBase, KnowledgeDocument, KnowledgeDocumentChunk, Note, AIConversation, AIConversationMessage, AIConversationTemporaryFile
from project.dependencies import get_current_user_id
import project.schemas as schemas

import project.oss_utils as oss_utils
from project.ai_providers.agent_orchestrator import get_all_available_tools_for_llm, invoke_agent
from project.ai_providers.ai_config import GLOBAL_PLACEHOLDER_ZERO_VECTOR, INITIAL_CANDIDATES_K, get_user_model_for_provider
from project.ai_providers.document_processor import extract_text_from_document
from project.ai_providers.embedding_provider import get_embeddings_from_api
from project.ai_providers.llm_provider import generate_conversation_title_from_llm
from project.ai_providers.rerank_provider import get_rerank_scores_from_api
from project.ai_providers.security_utils import decrypt_key

router = APIRouter(
    prefix="/ai",
    tags=["AI智能服务"],
    responses={404: {"description": "资源未找到"}},
)

# 辅助函数：清理可选的 JSON 字符串参数
def _clean_optional_json_string_input(input_str: Optional[str]) -> Optional[str]:
    """
    清理从表单接收到的可选JSON字符串参数。
    将 None, 空字符串, 或常见的默认值字面量转换为 None。

    """
    if input_str is None:
        return None

    stripped_str = input_str.strip()

    # 将空字符串或常见的默认值占位符视为None
    invalid_values = ["", "string", "null", "undefined", "none"]
    if stripped_str.lower() in invalid_values:
        return None

    return stripped_str

# --- 异步处理文档的辅助函数 ---
async def process_ai_temp_file_in_background(
        temp_file_id: int,
        user_id: int,  # 需要用户ID来获取其LLM配置
        oss_object_name: str,
        file_type: str,
        db_session: Session  # 传入会话
):
    """
    在后台处理AI对话的临时上传文件：从OSS下载、提取文本、生成嵌入并更新记录。
    """
    print(f"DEBUG_AI_TEMP_FILE_PROCESS: 开始后台处理AI临时文件 ID: {temp_file_id} (OSS: {oss_object_name})")
    loop = asyncio.get_running_loop()
    db_temp_file_record = None  # 初始化，防止在try块中它未被赋值而finally块需要用

    try:
        print(f"DEBUG_AI_TEMP_FILE_PROCESS: 步骤1 - 获取数据库记录...")
        # 获取临时文件记录 (需要在新的会话中获取，因为这是独立的任务)
        db_temp_file_record = db_session.query(AIConversationTemporaryFile).filter(
            AIConversationTemporaryFile.id == temp_file_id).first()
        if not db_temp_file_record:
            print(f"ERROR_AI_TEMP_FILE_PROCESS: AI临时文件 {temp_file_id} 在后台处理中未找到。")
            return

        print(f"DEBUG_AI_TEMP_FILE_PROCESS: 步骤2 - 更新状态为processing...")
        db_temp_file_record.status = "processing"
        db_temp_file_record.processing_message = "正在从云存储下载文件..."
        db_session.add(db_temp_file_record)
        db_session.commit()  # 立即提交状态更新，让前端能看到

        # 从OSS下载文件内容
        print(f"DEBUG_AI_TEMP_FILE_PROCESS: 开始从OSS下载文件: {oss_object_name}")
        try:
            downloaded_bytes = await oss_utils.download_file_from_oss(oss_object_name)
            if not downloaded_bytes:
                db_temp_file_record.status = "failed"
                db_temp_file_record.processing_message = "从云存储下载文件失败或文件内容为空。"
                db_session.add(db_temp_file_record)
                db_session.commit()
                print(f"ERROR_AI_TEMP_FILE_PROCESS: AI临时文件 {temp_file_id} 从OSS下载失败或内容为空。")
                return
            print(f"DEBUG_AI_TEMP_FILE_PROCESS: OSS下载成功，文件大小: {len(downloaded_bytes)} 字节")
        except Exception as oss_error:
            db_temp_file_record.status = "failed"
            db_temp_file_record.processing_message = f"OSS下载失败: {oss_error}"
            db_session.add(db_temp_file_record)
            db_session.commit()
            print(f"ERROR_AI_TEMP_FILE_PROCESS: AI临时文件 {temp_file_id} OSS下载异常: {oss_error}")
            return

        db_temp_file_record.processing_message = "正在提取文本..."
        db_session.add(db_temp_file_record)
        db_session.commit()

        # 1. 提取文本 (注意：extract_text_from_document 是同步的，需要在线程池中运行)
        try:
            extracted_text = await loop.run_in_executor(
                None,  # 使用默认的线程池执行器
                extract_text_from_document,  # 要执行的同步函数
                downloaded_bytes,
                file_type
            )
            print(
                f"DEBUG_AI_TEMP_FILE_PROCESS: 文件 {temp_file_id} 文本提取成功，长度: {len(extracted_text) if extracted_text else 0}")
        except Exception as extract_error:
            db_temp_file_record.status = "failed"
            db_temp_file_record.processing_message = f"文本提取失败: {extract_error}"
            db_session.add(db_temp_file_record)
            db_session.commit()
            print(f"ERROR_AI_TEMP_FILE_PROCESS: AI临时文件 {temp_file_id} 文本提取异常: {extract_error}")
            return

        if not extracted_text:
            db_temp_file_record.status = "failed"
            db_temp_file_record.processing_message = "文本提取失败或文件内容为空。"
            db_session.add(db_temp_file_record)
            db_session.commit()
            print(f"ERROR_AI_TEMP_FILE_PROCESS: AI临时文件 {temp_file_id} 文本提取失败。")
            return

        # 2. 生成嵌入 (需要获取用户的LLM配置)
        user_obj = db_session.query(Student).filter(Student.id == user_id).first()
        owner_llm_api_key = None
        owner_llm_type = None
        owner_llm_base_url = None
        owner_llm_model_id = None

        if user_obj and user_obj.llm_api_type == "siliconflow" and user_obj.llm_api_key_encrypted:
            try:
                owner_llm_api_key = decrypt_key(user_obj.llm_api_key_encrypted)
                owner_llm_type = user_obj.llm_api_type
                owner_llm_base_url = user_obj.llm_api_base_url
                # 优先使用新的多模型配置，fallback到原模型ID
                owner_llm_model_id = get_user_model_for_provider(
                    user_obj.llm_model_ids,
                    user_obj.llm_api_type,
                    user_obj.llm_model_id
                )
                print(
                    f"DEBUG_AI_TEMP_FILE_EMBEDDING_KEY: 使用用户 {user_id} 配置的硅基流动 API 密钥为临时文件生成嵌入。")
            except Exception as e:
                print(
                    f"ERROR_AI_TEMP_FILE_EMBEDDING_KEY: 解密用户 {user_id} 硅基流动 API 密钥失败: {e}。临时文件嵌入将使用零向量或默认行为。")
                # 即使解密失败，也跳过，使用默认的零向量
        else:
            print(
                f"DEBUG_AI_TEMP_FILE_EMBEDDING_KEY: 用户 {user_id} 未配置硅基流动 API 类型或密钥，临时文件嵌入将使用零向量或默认行为。")

        db_temp_file_record.processing_message = "正在生成嵌入向量..."
        db_session.add(db_temp_file_record)
        db_session.commit()

        try:
            embeddings_list = await get_embeddings_from_api(
                [extracted_text],  # 传入提取的文本
                api_key=owner_llm_api_key,
                llm_type=owner_llm_type,
                llm_base_url=owner_llm_base_url,
                llm_model_id=owner_llm_model_id
            )
            print(f"DEBUG_AI_TEMP_FILE_PROCESS: 文件 {temp_file_id} 嵌入生成成功")
        except Exception as embedding_error:
            print(f"WARNING_AI_TEMP_FILE_PROCESS: 文件 {temp_file_id} 嵌入生成失败: {embedding_error}，使用零向量")
            embeddings_list = []

        final_embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR
        if embeddings_list and len(embeddings_list) > 0:
            final_embedding = embeddings_list[0]
        else:
            print(f"WARNING_AI_TEMP_FILE_EMBEDDING: 临时文件 {temp_file_id} 嵌入生成失败或返回空，使用零向量。")

        # 3. 更新数据库记录
        db_temp_file_record.extracted_text = extracted_text
        db_temp_file_record.embedding = final_embedding
        db_temp_file_record.status = "completed"
        db_temp_file_record.processing_message = "文件处理完成，文本已提取，嵌入已生成。"
        db_session.add(db_temp_file_record)
        db_session.commit()
        print(
            f"DEBUG_AI_TEMP_FILE_PROCESS: AI临时文件 {temp_file_id} 处理完成。提取文本长度: {len(extracted_text)} 字符")
        print(
            f"DEBUG_AI_TEMP_FILE_PROCESS: 文本内容预览: {extracted_text[:200]}..." if extracted_text else "DEBUG_AI_TEMP_FILE_PROCESS: 提取的文本为空")

    except Exception as e:
        print(f"ERROR_AI_TEMP_FILE_PROCESS: 后台处理AI临时文件 {temp_file_id} 发生未预期错误: {type(e).__name__}: {e}")
        # 尝试更新文档状态为失败
        if db_temp_file_record:
            try:
                db_temp_file_record.status = "failed"
                db_temp_file_record.processing_message = f"处理失败: {e}"
                db_session.add(db_temp_file_record)
                db_session.commit()
            except Exception as update_e:
                print(f"CRITICAL_ERROR: 无法更新AI临时文件 {temp_file_id} 的失败状态: {update_e}")
    finally:
        db_session.close()  # 确保会话关闭

@router.post("/semantic_search", response_model=List[schemas.SemanticSearchResult], summary="智能语义搜索")
async def semantic_search(
        search_request: schemas.SemanticSearchRequest,
        current_user_id: int = Depends(get_current_user_id),  # 依赖注入提供用户ID
        db: Session = Depends(get_db)
):
    """
    通过语义搜索，在用户可访问的项目、课程、知识库文章和笔记中查找相关内容。
    """
    print(f"DEBUG: 用户 {current_user_id} 语义搜索: {search_request.query}，范围: {search_request.item_types}")

    # 记录搜索开始时间
    search_start_time = time.time()

    # 从数据库中加载完整的用户对象
    user = db.query(Student).filter(Student.id == current_user_id).first()
    if not user:
        # 理论上 get_current_user_id 已经验证了用户存在，但这里是安全校验
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="当前用户未找到。")

    searchable_items = []

    target_types = search_request.item_types if search_request.item_types else ["project", "course",
                                                                                "knowledge_document", "note"]

    if "project" in target_types:
        # 获取所有项目。如果项目有权限控制，这里需要细化筛选逻辑。
        # 暂时简化为所有用户可见所有项目的文本信息。（可根据实际需求调整为只获取自己创建的或公开的项目）
        projects = db.query(Project).all()
        for p in projects:
            if p.embedding is not None:
                searchable_items.append({"obj": p, "type": "project"})

    if "course" in target_types:
        # 获取所有课程。课程通常也是公开的。
        courses = db.query(Course).all()
        for c in courses:
            if c.embedding is not None:
                searchable_items.append({"obj": c, "type": "course"})

    if "knowledge_document" in target_types:
        # 获取用户拥有或公开的知识库中的文档块（重构后的知识库内容）
        kbs = db.query(KnowledgeBase).filter(
            (KnowledgeBase.owner_id == current_user_id) | (KnowledgeBase.access_type == "public")
        ).all()
        for kb in kbs:
            document_chunks = db.query(KnowledgeDocumentChunk).filter(
                KnowledgeDocumentChunk.kb_id == kb.id,
                KnowledgeDocumentChunk.embedding.isnot(None)
            ).all()
            for chunk in document_chunks:
                searchable_items.append({"obj": chunk, "type": "knowledge_document"})

    if "note" in target_types:
        # 只获取当前用户自己的笔记
        notes = db.query(Note).filter(Note.owner_id == current_user_id).all()
        for note in notes:
            if note.embedding is not None:
                searchable_items.append({"obj": note, "type": "note"})

    if not searchable_items:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到可搜索的内容或指定类型无数据。")

    # 2. 获取查询嵌入 (使用当前用户的LLM配置)
    user_llm_type = user.llm_api_type
    user_llm_base_url = user.llm_api_base_url
    user_llm_model_id = user.llm_model_id
    user_llm_api_key = None
    if user.llm_api_key_encrypted:
        try:
            user_llm_api_key = decrypt_key(user.llm_api_key_encrypted)
        except Exception as e:
            print(f"WARNING_SEMANTIC_SEARCH: 解密用户 {current_user_id} LLM API Key失败: {e}. 语义搜索将无法使用嵌入。")
            user_llm_api_key = None  # 解密失败，不要使用

    query_embedding_list = await get_embeddings_from_api(
        [search_request.query],
        api_key=user_llm_api_key,
        llm_type=user_llm_type,
        llm_base_url=user_llm_base_url,
        llm_model_id=user_llm_model_id
    )
    # 检查是否成功获得了非零嵌入向量。如果返回零向量，说明嵌入服务不可用或未配置。
    if not query_embedding_list or query_embedding_list[0] == GLOBAL_PLACEHOLDER_ZERO_VECTOR:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="无法生成查询嵌入，请确保您的LLM配置正确，LLM类型为硅基流动且API密钥有效。")
    query_embedding_np = np.array(query_embedding_list[0]).reshape(1, -1)

    # 3. 粗召回 (Embedding Similarity)
    item_combined_texts = [item['obj'].combined_text for item in searchable_items]
    item_embeddings_np = np.array([item['obj'].embedding for item in searchable_items])

    similarities = cosine_similarity(query_embedding_np, item_embeddings_np)[0]

    initial_candidates = []
    for i, sim in enumerate(similarities):
        initial_candidates.append({
            'obj': searchable_items[i]['obj'],
            'type': searchable_items[i]['type'],
            'similarity_stage1': float(sim)
        })
    initial_candidates.sort(key=lambda x: x['similarity_stage1'], reverse=True)
    initial_candidates = initial_candidates[:INITIAL_CANDIDATES_K]

    if not initial_candidates:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到与查询相关的初步结果。")

    # 4. 精排 (Reranker) - 同样使用用户的LLM配置
    rerank_candidate_texts = [c['obj'].combined_text for c in initial_candidates]
    print(f"DEBUG_AI: 正在对 {len(rerank_candidate_texts)} 个候选搜索结果进行重排...")

    rerank_scores = await get_rerank_scores_from_api(
        search_request.query,
        rerank_candidate_texts,
        api_key=user_llm_api_key,  # 传入用户的解密Key
        llm_type=user_llm_type,  # 传入用户的LLM Type
        llm_base_url=user_llm_base_url,  # 尽管 reranker API 不直接用 base_url，但保持参数一致性
        fallback_to_similarity=True  # 启用回退机制
    )
    # 检查返回的rerank_scores是否是零分数（表示API调用失败或未配置）
    if all(score == 0.0 for score in rerank_scores):
        print(f"WARNING_AI: 重排服务未能返回有效分数，使用嵌入相似度作为最终分数。")
        # 如果重排失败，回退到使用粗召回的相似度作为最终相关性得分
        for i, score in enumerate(rerank_scores):  # 遍历所有候选者
            initial_candidates[i]['relevance_score'] = initial_candidates[i]['similarity_stage1']
    else:
        print(f"DEBUG_AI: 重排服务返回有效分数，使用重排结果。")
        for i, score in enumerate(rerank_scores):
            initial_candidates[i]['relevance_score'] = float(score)

    initial_candidates.sort(key=lambda x: x['relevance_score'], reverse=True)

    # 5. 格式化最终结果
    final_results = []
    for item in initial_candidates[:search_request.limit]:
        obj = item['obj']
        content_snippet = ""
        # 尝试从不同的属性中提取内容摘要
        if hasattr(obj, 'content') and obj.content:
            content_snippet = obj.content[:150] + "..." if len(obj.content) > 150 else obj.content
        elif hasattr(obj, 'description') and obj.description:
            content_snippet = obj.description[:150] + "..." if len(obj.description) > 150 else obj.description
        elif hasattr(obj, 'bio') and obj.bio and item['type'] == 'student':  # 针对学生（如果语义搜索也搜索学生）
            content_snippet = obj.bio[:150] + "..." if len(obj.bio) > 150 else obj.bio

        final_results.append(schemas.SemanticSearchResult(
            id=obj.id,
            title=obj.title if hasattr(obj, 'title') else obj.name if hasattr(obj, 'name') else str(obj.id),
            # Fallback to name or ID
            type=item['type'],
            content_snippet=content_snippet,
            relevance_score=item['relevance_score']
        ))

    print(f"DEBUG_AI: 语义搜索完成，返回 {len(final_results)} 个结果。")

    # 记录搜索性能
    search_end_time = time.time()
    search_duration = search_end_time - search_start_time
    print(
        f"PERFORMANCE_AI: 语义搜索耗时 {search_duration:.2f}秒，处理了 {len(searchable_items)} 个候选项，返回 {len(final_results)} 个结果")

    return final_results

@router.get("/mcp_available_tools", response_model=Dict[str, Any], summary="获取智库聊天可用的MCP工具列表")
async def get_mcp_available_tools(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取当前用户在智库聊天中可用的MCP工具列表。
    包括通用内置工具（网络搜索、知识库检索）和用户配置的活跃MCP工具。
    """
    print(f"DEBUG: 获取用户 {current_user_id} 的MCP可用工具列表")
    
    try:
        available_tools = await get_all_available_tools_for_llm(db, current_user_id)
        
        return {
            "status": "success",
            "tools_count": len(available_tools),
            "available_tools": available_tools,
            "description": "当前用户可用的MCP工具列表，包括内置工具和用户配置的MCP服务工具"
        }
    except Exception as e:
        print(f"ERROR: 获取MCP工具列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取MCP工具列表时发生错误"
        )

@router.get("/conversations/{conversation_id}/files/status", response_model=Dict[str, Any], summary="查询对话中文件处理状态")
def get_conversation_files_status(
        conversation_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """查询指定对话中所有临时文件的处理状态"""
    # 验证对话归属
    conversation = db.query(AIConversation).filter(
        AIConversation.id == conversation_id,
        AIConversation.user_id == current_user_id
    ).first()

    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话不存在或无权访问")

    # 获取对话中的所有临时文件
    temp_files = db.query(AIConversationTemporaryFile).filter(
        AIConversationTemporaryFile.conversation_id == conversation_id
    ).all()

    files_status = []
    for tf in temp_files:
        files_status.append({
            "id": tf.id,
            "filename": tf.original_filename,
            "status": tf.status,
            "processing_message": tf.processing_message,
            "created_at": tf.created_at.isoformat() if tf.created_at else None,
            "has_content": bool(tf.extracted_text and tf.extracted_text.strip())
        })

    return {
        "conversation_id": conversation_id,
        "files_count": len(files_status),
        "files": files_status
    }

@router.post("/qa", response_model=schemas.AIQAResponse, summary="AI智能问答 (通用、RAG或工具调用)")
async def ai_qa(
        query: str = Form(..., description="用户的问题文本"),
        conversation_id: Optional[int] = Form(None, description="要继续的对话Session ID。如果为空，则开始新的对话。"),
        kb_ids_json: Optional[str] = Form(None, description="要检索的知识库ID列表，格式为JSON字符串。例如: '[1, 2, 3]'"),
        use_tools: Optional[bool] = Form(False, description="是否启用AI智能工具调用"),
        preferred_tools_json: Optional[str] = Form(None,
                                                   description="AI在工具模式下偏好使用的工具类型。支持: JSON数组('[\"rag\", \"mcp_tool\"]')、'All'(所有工具)、或None(无工具)"),
        llm_model_id: Optional[str] = Form(None, description="本次会话使用的LLM模型ID"),  # <- 这里会从表单接收
        uploaded_file: Optional[UploadFile] = File(None,
                                                   description="可选：上传文件（图片或文档）对AI进行提问"),
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    使用LLM进行问答，并支持对话历史记录。
    支持上传文件或图片作为临时上下文对AI进行提问。

    - `query`：用户的问题文本。
    - `conversation_id`：如果为空，则开始新的对话。否则，加载指定对话的历史记录作为LLM的上下文。
    - `use_tools` 为 `False`：通用问答。
    - `use_tools` 为 `True`：启用工具模式，具体行为取决于 `preferred_tools_json`：
      * `preferred_tools_json` = `None`：不启用任何工具
      * `preferred_tools_json` = `"All"`：启用所有可用工具（RAG、网络搜索、MCP工具）
      * `preferred_tools_json` = `'["rag", "mcp_tool"]'`：只启用指定的工具类型
      * `preferred_tools_json` = `'[]'`：明确不启用任何工具
    """
    # 文件上传验证
    if uploaded_file:
        # 检查文件大小（限制为50MB）
        MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
        if hasattr(uploaded_file, 'size') and uploaded_file.size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="文件大小超过限制（50MB）"
            )
        
        # 检查文件类型
        ALLOWED_CONTENT_TYPES = [
            'image/jpeg', 'image/png', 'image/gif', 'image/webp',
            'application/pdf', 'text/plain', 'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        ]
        if uploaded_file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"不支持的文件类型: {uploaded_file.content_type}"
            )

    print(
        f"DEBUG: 用户 {current_user_id} 提问: {query}，使用工具模式: {use_tools}，偏好工具(json): {preferred_tools_json}，文件: {uploaded_file.filename if uploaded_file else '无'}")

    user = db.query(Student).filter(Student.id == current_user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户未找到")

    kb_ids_json = _clean_optional_json_string_input(kb_ids_json)
    preferred_tools_json = _clean_optional_json_string_input(preferred_tools_json)
    # --- 新增 --- 对 llm_model_id 进行清理，解决 "string" 的问题
    llm_model_id = _clean_optional_json_string_input(llm_model_id)
    # -------------

    actual_kb_ids: Optional[List[int]] = None
    if kb_ids_json:
        try:
            actual_kb_ids = json.loads(kb_ids_json)
            if not isinstance(actual_kb_ids, list) or not all(isinstance(x, int) for x in actual_kb_ids):
                raise ValueError("kb_ids 必须是一个整数列表格式的JSON字符串。")
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"kb_ids 格式不正确: {e}。应为 JSON 整数列表。")

    actual_preferred_tools: Optional[List[Literal["rag", "web_search", "mcp_tool"]]] = None
    # 只有在启用工具时才解析preferred_tools_json，避免不必要的处理
    if use_tools and preferred_tools_json:
        try:
            # 特殊处理："All" 表示使用所有可用工具
            if preferred_tools_json.strip().lower() == "all":
                actual_preferred_tools = "all"  # 特殊标记，表示使用所有工具
                print(f"DEBUG: 用户选择启用所有可用工具")
            else:
                parsed_tools = json.loads(preferred_tools_json)

                # 改进：处理 JSON null 值
                if parsed_tools is None:
                    actual_preferred_tools = None
                    print(f"DEBUG: 用户提供了 JSON null 值，视为不使用任何工具")
                elif not isinstance(parsed_tools, list):
                    raise ValueError("偏好工具配置必须是工具名称列表（如 '[\"rag\", \"mcp_tool\"]'）或 'All'。")
                elif not all(isinstance(x, str) for x in parsed_tools):
                    raise ValueError("偏好工具配置中的所有工具名称必须是字符串。")
                elif len(parsed_tools) == 0:
                    # 如果解析后是空数组，视为None处理
                    actual_preferred_tools = None
                    print(f"DEBUG: 用户提供了空的工具列表，视为不使用任何工具")
                else:
                    valid_tool_types = ["rag", "web_search", "mcp_tool"]
                    invalid_tools = [tool for tool in parsed_tools if tool not in valid_tool_types]
                    if invalid_tools:
                        raise ValueError(f"包含不支持的工具类型：{invalid_tools}。支持的工具类型：{valid_tool_types}")
                    actual_preferred_tools = parsed_tools
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"偏好工具配置格式错误：{str(e)} 请使用工具名称的JSON数组格式（如 '[\"rag\", \"mcp_tool\"]'）或 'All' 表示所有工具。")
    elif use_tools and not preferred_tools_json:
        # 改进：当工具启用但没有提供偏好工具配置时，给出更明确的提示
        actual_preferred_tools = None
        print(
            f"DEBUG: 用户 {current_user_id} 启用了工具模式但未指定偏好工具，将不启用任何工具。建议明确指定工具类型或使用 'All'。")
    elif not use_tools and preferred_tools_json:
        # 当工具未启用但提供了偏好工具配置时，给出警告信息
        print(f"WARNING: 用户 {current_user_id} 提供了偏好工具配置但未启用工具模式，偏好工具配置将被忽略。")

    # 1. 获取或创建 AI Conversation
    db_conversation: AIConversation
    past_messages_for_llm: List[Dict[str, Any]] = []

    # 标识是否是新创建的对话，用于决定是否在第一轮问答后生成标题
    is_new_and_first_message_exchange = False

    if conversation_id:
        db_conversation = db.query(AIConversation).filter(
            AIConversation.id == conversation_id,
            AIConversation.user_id == current_user_id
        ).first()
        if not db_conversation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="指定的对话未找到或无权访问。")

        # 加载历史消息作为LLM的上下文，并转换为字典格式
        raw_past_messages = db.query(AIConversationMessage).filter(
            AIConversationMessage.conversation_id == db_conversation.id
        ).order_by(AIConversationMessage.sent_at).limit(20).all()  # 限制为最近20条消息

        past_messages_for_llm = [msg.to_dict() for msg in raw_past_messages]

        print(f"DEBUG_AI_CONV: 加载了 {len(past_messages_for_llm)} 条历史消息作为上下文。")

    else:
        # 创建新对话时，标题先为 None，表示等待AI生成
        db_conversation = AIConversation(user_id=current_user_id, title=None)
        db.add(db_conversation)
        db.flush()  # 这里刷新一次以获取新对话的 ID
        is_new_and_first_message_exchange = True  # 标记为新对话的首次消息交换
        print(f"DEBUG_AI_CONV: 创建了新的对话 session ID: {db_conversation.id}，标题待生成。")

    # --- LLM配置变量的初始化，确保作用域和默认值 ---
    user_llm_api_type: Optional[str] = None
    user_llm_api_key: Optional[str] = None
    user_llm_api_base_url: Optional[str] = None
    user_llm_model_id_configured: Optional[str] = None

    # 从用户配置中获取LLM信息
    user_llm_api_type = user.llm_api_type
    user_llm_api_base_url = user.llm_api_base_url
    user_llm_model_id_configured = user.llm_model_id  # 用户配置的模型ID（兼容性）

    # 优先级：1. 请求指定的模型 2. 用户多模型配置 3. 用户单模型配置
    if llm_model_id:
        llm_model_id_final = llm_model_id
    else:
        llm_model_id_final = get_user_model_for_provider(
            user.llm_model_ids,
            user.llm_api_type,
            user.llm_model_id
        )

    if not user_llm_api_type or not user.llm_api_key_encrypted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="User has not configured LLM API type or key. Please configure it in user settings.")

    try:
        user_llm_api_key = decrypt_key(user.llm_api_key_encrypted)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to decrypt LLM API key. Please reconfigure.")

    # 文件上传处理逻辑
    temp_file_ids_for_context: List[int] = []
    if uploaded_file:
        allowed_mime_types = [
            "text/plain", "text/markdown", "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp"
        ]
        if uploaded_file.content_type not in allowed_mime_types:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"不支持的文件类型: {uploaded_file.content_type}。仅支持文本、PDF、DOCX和图片文件。")

        file_bytes = await uploaded_file.read()
        file_extension = os.path.splitext(uploaded_file.filename)[1]

        oss_object_name = f"ai_chat_temp_files/{uuid.uuid4().hex}{file_extension}"

        try:
            await oss_utils.upload_file_to_oss(
                file_bytes=file_bytes,
                object_name=oss_object_name,
                content_type=uploaded_file.content_type
            )
            print(f"DEBUG_AI_QA: 文件 '{uploaded_file.filename}' 上传到OSS成功: {oss_object_name}")

            temp_file_record = AIConversationTemporaryFile(
                conversation_id=db_conversation.id,
                oss_object_name=oss_object_name,
                original_filename=uploaded_file.filename,
                file_type=uploaded_file.content_type,
                status="pending",
                processing_message="文件已上传，等待处理文本和生成嵌入..."
            )
            db.add(temp_file_record)
            db.flush()  # 获取ID

            # 立即提交这条记录，确保后台任务能够看到它
            db.commit()

            temp_file_ids_for_context.append(temp_file_record.id)

            # 创建一个独立的会话用于后台任务，避免与当前请求事务冲突
            background_db_session = SessionLocal()

            # 立即启动后台任务并添加错误处理
            task = asyncio.create_task(
                process_ai_temp_file_in_background(
                    temp_file_record.id,
                    current_user_id,
                    oss_object_name,
                    uploaded_file.content_type,
                    background_db_session
                )
            )

            # 添加任务完成回调来处理异常
            def task_done_callback(task_result):
                try:
                    if task_result.exception():
                        print(f"ERROR_AI_TEMP_FILE_TASK: 后台任务异常: {task_result.exception()}")
                    else:
                        print(f"DEBUG_AI_TEMP_FILE_TASK: 后台任务完成")
                except Exception as e:
                    print(f"ERROR_AI_TEMP_FILE_TASK: 任务回调异常: {e}")

            task.add_done_callback(task_done_callback)

            print(f"DEBUG_AI_QA: 后台文件处理任务已启动，任务ID: {temp_file_record.id}")

            file_link = f"{oss_utils.S3_BASE_URL.rstrip('/')}/{oss_object_name}"
            # 将文件信息加入当前查询，提示LLM
            file_prompt = f"\n\n[用户上传了一个文件，名为 '{uploaded_file.filename}' ({uploaded_file.content_type})。链接: {file_link}。请尝试利用其内容。文件内容将通过RAG工具提供。]"
            query += file_prompt

        except Exception as e:
            db.rollback()
            print(f"ERROR_AI_QA: 处理上传文件失败: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"处理上传文件失败: {e}")

    # --- 优化：快速检查文件处理状态，不长时间等待 ---
    if temp_file_ids_for_context:
        print(f"DEBUG_AI_QA: 检查 {len(temp_file_ids_for_context)} 个临时文件的初始状态...")

        # 快速检查一次，不等待
        completed_files = db.query(AIConversationTemporaryFile).filter(
            AIConversationTemporaryFile.id.in_(temp_file_ids_for_context),
            AIConversationTemporaryFile.status == "completed"
        ).all()

        pending_files = db.query(AIConversationTemporaryFile).filter(
            AIConversationTemporaryFile.id.in_(temp_file_ids_for_context),
            AIConversationTemporaryFile.status.in_(["pending", "processing"])
        ).all()

        failed_files = db.query(AIConversationTemporaryFile).filter(
            AIConversationTemporaryFile.id.in_(temp_file_ids_for_context),
            AIConversationTemporaryFile.status == "failed"
        ).all()

        print(
            f"DEBUG_AI_QA: 文件状态统计 - 已完成: {len(completed_files)}, 处理中: {len(pending_files)}, 失败: {len(failed_files)}")

        # 如果有文件正在处理，只等待很短时间（最多5秒）
        if pending_files:
            print(f"DEBUG_AI_QA: 有文件正在处理中，等待最多5秒...")
            wait_count = 0
            max_quick_wait = 5  # 最多等待5秒

            while wait_count < max_quick_wait and pending_files:
                await asyncio.sleep(1)
                wait_count += 1

                # 重新检查状态
                pending_files = db.query(AIConversationTemporaryFile).filter(
                    AIConversationTemporaryFile.id.in_(temp_file_ids_for_context),
                    AIConversationTemporaryFile.status.in_(["pending", "processing"])
                ).all()

                if not pending_files:
                    print(f"DEBUG_AI_QA: 所有文件处理完成，用时 {wait_count} 秒")
                    break

            if pending_files:
                print(f"DEBUG_AI_QA: 快速等待结束，仍有 {len(pending_files)} 个文件在处理中，继续AI查询")

        # 刷新数据库会话
        db.expire_all()
        db.commit()

    try:
        # 2. 调用 invoke_agent 获取当前轮次的所有消息和最终答案
        agent_raw_response = await invoke_agent(
            db=db,
            user_id=current_user_id,
            query=query,
            llm_api_type=user_llm_api_type,
            llm_api_key=user_llm_api_key,
            llm_api_base_url=user_llm_api_base_url,
            llm_model_id=llm_model_id_final,
            kb_ids=actual_kb_ids,
            # note_ids 参数已移除，不再支持笔记RAG
            preferred_tools=actual_preferred_tools,
            past_messages=past_messages_for_llm,
            temp_file_ids=temp_file_ids_for_context,
            conversation_id_for_temp_files=db_conversation.id,
            enable_tool_use=use_tools
        )

        # 3. 持久化当前轮次的所有消息并立即刷新，以便获取 ID 和时间戳
        messages_for_db_commit = []
        for msg_data in agent_raw_response.get("turn_messages_to_log", []):
            db_message = AIConversationMessage(
                conversation_id=db_conversation.id,
                role=msg_data["role"],
                content=msg_data["content"],
                tool_calls_json=msg_data.get("tool_calls_json"),
                tool_output_json=msg_data.get("tool_output_json"),
                llm_type_used=msg_data.get("llm_type_used"),
                llm_model_used=msg_data.get("llm_model_used")
            )
            db.add(db_message)
            messages_for_db_commit.append(db_message)

        db.flush()

        final_turn_messages_for_response: List = []
        for db_msg in messages_for_db_commit:
            db.refresh(db_msg)
            final_turn_messages_for_response.append(
                schemas.AIConversationMessageResponse.model_validate(db_msg, from_attributes=True)
            )

        # --- IMPORTANT: AI Title Generation Logic for NEW conversations (在第一轮问答后生成标题) ---
        # 只有当对话是刚刚新建的 (is_new_and_first_message_exchange 为 True) 并且标题仍然是 None 时才尝试生成
        if is_new_and_first_message_exchange and db_conversation.title is None:
            first_exchange_messages_from_db = db.query(AIConversationMessage).filter(
                AIConversationMessage.conversation_id == db_conversation.id
            ).order_by(AIConversationMessage.sent_at).limit(2).all()

            if len(first_exchange_messages_from_db) >= 2:
                print(f"DEBUG_AI_TITLE_AUTO: 新对话 {db_conversation.id} 完成首次问答，尝试自动生成标题。")
                messages_for_title_generation = [msg.to_dict() for msg in first_exchange_messages_from_db]

                try:
                    ai_generated_title = await generate_conversation_title_from_llm(
                        messages=messages_for_title_generation,
                        user_llm_api_type=user_llm_api_type,
                        user_llm_api_key=user_llm_api_key,
                        user_llm_api_base_url=user_llm_api_base_url,
                        user_llm_model_id=user_llm_model_id_configured
                    )
                    if ai_generated_title and ai_generated_title != "新对话" and ai_generated_title != "无标题对话":
                        db_conversation.title = ai_generated_title
                        db.add(db_conversation)
                        print(f"DEBUG: AI对话 {db_conversation.id} 标题AI生成为 '{db_conversation.title}'。")
                    else:
                        db_conversation.title = "新对话"
                        db.add(db_conversation)
                        print(
                            f"DEBUG: LLM生成的标题不具意义 ('{ai_generated_title}')，对话 {db_conversation.id} 保持默认标题。")
                except Exception as e:
                    print(f"ERROR: AI自动生成标题失败: {e}. 对话 {db_conversation.id} 标题保持默认。")
                    db_conversation.title = "新对话"
                    db.add(db_conversation)
            else:
                db_conversation.title = "新对话"
                db.add(db_conversation)
                print(f"DEBUG_AI_TITLE_AUTO: 对话 {db_conversation.id} 消息内容不足，标题保持默认。")

        # 4. 更新对话的 last_updated 时间
        db_conversation.last_updated = func.now()
        db.add(db_conversation)

        db.commit()

        # 构造最终 AIQAResponse 对象
        response_to_client = schemas.AIQAResponse(
            answer=agent_raw_response["answer"],
            answer_mode=agent_raw_response["answer_mode"],
            llm_type_used=agent_raw_response.get("llm_type_used"),
            llm_model_used=agent_raw_response.get("llm_model_used"),
            conversation_id=db_conversation.id,
            turn_messages=final_turn_messages_for_response,
            source_articles=agent_raw_response.get("source_articles"),
            search_results=agent_raw_response.get("search_results")
        )

        print(f"DEBUG: 用户 {current_user_id} 在对话 {db_conversation.id} 中成功完成AI问答。")
        return response_to_client

    except Exception as e:
        db.rollback()
        print(f"ERROR: AI问答请求失败: {e}. 详细错误: {traceback.format_exc()}")

        if not conversation_id and db_conversation.id:  # 只有当是新创建的对话且已经有ID时才考虑

            pass

        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"AI问答失败: {e}")

# --- RAG诊断和AI对话管理接口 ---

@router.get("/rag_diagnosis", response_model=Dict[str, Any], summary="用户RAG功能诊断")
def diagnose_user_rag(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    诊断当前用户的RAG功能配置和数据状态
    """
    try:
        # from rag_utils import RAGDebugger
        # diagnosis = RAGDebugger.validate_rag_setup(db, current_user_id)
        # return diagnosis
        # 暂时注释掉rag_utils导入，直接提供基本诊断
        pass
    except ImportError:
        # 如果rag_utils不可用，提供基本诊断
        pass
    
    # 提供基本诊断
    user = db.query(Student).filter(Student.id == current_user_id).first()
    issues = []
    recommendations = []

    if not user.llm_api_type or user.llm_api_type != "siliconflow":
        issues.append("未配置SiliconFlow LLM API")
        recommendations.append("在个人设置中配置SiliconFlow API以启用完整RAG功能")

    if not user.llm_api_key_encrypted:
        issues.append("未配置LLM API密钥")
        recommendations.append("添加有效的LLM API密钥")

    # 检查用户内容 - 重点关注当前系统支持的内容类型
    kb_count = db.query(KnowledgeBase).filter(KnowledgeBase.owner_id == current_user_id).count()
    doc_count = db.query(KnowledgeDocument).filter(KnowledgeDocument.owner_id == current_user_id).count()  # 主要内容
    note_count = db.query(Note).filter(Note.owner_id == current_user_id).count()

    # 主要检查当前系统支持的内容类型
    if kb_count == 0 and doc_count == 0 and note_count == 0:
        issues.append("没有任何可搜索的内容")
        recommendations.append("创建知识库、上传文档或添加笔记")
    elif doc_count == 0 and note_count == 0:
        issues.append("知识库中没有文档内容")
        recommendations.append("上传文档到知识库或添加笔记")

    return {
        "issues": issues,
        "recommendations": recommendations,
        "status": "ok" if not issues else "has_issues",
        "content_summary": {
            "knowledge_bases": kb_count,
            "documents": doc_count,
            "notes": note_count
        }
    }

@router.get("/ai_conversations", response_model=List[schemas.AIConversationResponse],
         summary="获取当前用户的所有AI对话列表")
async def get_my_ai_conversations(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        limit: int = 10,
        offset: int = 0
):
    """
    获取当前用户的所有AI对话列表，按最新更新时间排序。
    """
    print(f"DEBUG: 获取用户 {current_user_id} 的AI对话列表。")
    conversations = db.query(AIConversation).filter(AIConversation.user_id == current_user_id) \
        .order_by(AIConversation.last_updated.desc()) \
        .offset(offset).limit(limit).all()

    response_list = []
    for conv in conversations:
        # 动态计算总消息数，填充 total_messages_count
        total_messages_count = db.query(AIConversationMessage).filter(
            AIConversationMessage.conversation_id == conv.id).count()
        conv_response = schemas.AIConversationResponse.model_validate(conv, from_attributes=True)
        conv_response.total_messages_count = total_messages_count
        response_list.append(conv_response)

    print(f"DEBUG: 用户 {current_user_id} 获取到 {len(response_list)} 个AI对话。")
    return response_list

@router.get("/ai_conversations/{conversation_id}", response_model=schemas.AIConversationResponse,
         summary="获取指定AI对话详情")
async def get_ai_conversation_detail(
        conversation_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取指定ID的AI对话详情。
    """
    print(f"DEBUG: 获取用户 {current_user_id} 的AI对话 {conversation_id} 详情。")
    db_conversation = db.query(AIConversation).filter(
        AIConversation.id == conversation_id,
        AIConversation.user_id == current_user_id
    ).first()
    if not db_conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话未找到或无权访问。")

    # 动态计算总消息数
    total_messages_count = db.query(AIConversationMessage).filter(
        AIConversationMessage.conversation_id == db_conversation.id).count()
    conv_response = schemas.AIConversationResponse.model_validate(db_conversation, from_attributes=True)
    conv_response.total_messages_count = total_messages_count

    return conv_response

@router.get("/ai_conversations/{conversation_id}/messages",
         response_model=List[schemas.AIConversationMessageResponse], summary="获取指定AI对话的所有消息历史")
async def get_ai_conversation_messages(
        conversation_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        limit: int = 50,
        offset: int = 0
):
    """
    获取指定AI对话的所有消息历史记录。
    """
    print(f"DEBUG: 获取用户 {current_user_id} 的AI对话 {conversation_id} 消息历史。")
    # 验证对话存在且属于当前用户
    db_conversation = db.query(AIConversation).filter(
        AIConversation.id == conversation_id,
        AIConversation.user_id == current_user_id
    ).first()
    if not db_conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话未找到或无权访问。")

    messages = db.query(AIConversationMessage).filter(AIConversationMessage.conversation_id == conversation_id) \
        .order_by(AIConversationMessage.sent_at).offset(offset).limit(limit).all()

    print(f"DEBUG: 对话 {conversation_id} 获取到 {len(messages)} 条消息。")
    # Pydantic的 from_attributes=True 会自动处理ORM对象到Schema的转换
    return messages

@router.get("/ai_conversations/{conversation_id}/retitle", response_model=schemas.AIConversationResponse,
         summary="触发AI重新生成指定AI对话的标题并返回")
async def get_ai_conversation_retitle(
        conversation_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    触发AI大模型根据对话内容重新生成并更新标题，然后返回该对话的详细信息（包含新标题）。
    此接口不接受用户手动提交的标题，其唯一作用是强制AI重新评估对话并生成新标题。
    """
    print(f"DEBUG: 用户 {current_user_id} 触发AI为对话 {conversation_id} 重新生成标题。")
    db_conversation = db.query(AIConversation).filter(
        AIConversation.id == conversation_id,
        AIConversation.user_id == current_user_id
    ).first()
    if not db_conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话未找到或无权访问。")

    # ----- 核心逻辑：强制走AI生成逻辑 -----
    print(f"DEBUG: AI将根据对话内容强制生成最新标题。")

    # 获取历史消息作为生成标题的上下文 (取所有消息，不再限制数量，让LLM更全面总结)
    raw_messages = db.query(AIConversationMessage).filter(
        AIConversationMessage.conversation_id == db_conversation.id
    ).order_by(AIConversationMessage.sent_at).all()  # 获取所有消息

    if not raw_messages:
        # 如果对话中没有任何消息，无法生成有意义的标题
        # 将标题设置为一个明确的空状态或默认
        db_conversation.title = "空对话"
        db.add(db_conversation)  # 标记为更新
        db.commit()  # 提交更改
        db.refresh(db_conversation)  # 刷新以获取最新状态
        print(f"WARNING: AI对话 {conversation_id} 中无消息，标题设置为 '空对话'。")

        # 动态计算总消息数 for response (此处为0)
        conv_response = schemas.AIConversationResponse.model_validate(db_conversation, from_attributes=True)
        conv_response.total_messages_count = 0
        return conv_response

    # 将消息反转，以便 ai_core 函数处理时是正序（从旧到新）
    past_messages_for_llm = [msg.to_dict() for msg in reversed(raw_messages)]  # to_dict() 确保兼容性

    # 获取用户的LLM配置
    current_user_obj = db.query(Student).filter(Student.id == current_user_id).first()
    user_llm_api_type: Optional[str] = None
    user_llm_api_base_url: Optional[str] = None
    user_llm_model_id_configured: Optional[str] = None
    user_llm_api_key: Optional[str] = None

    if not current_user_obj.llm_api_type or not current_user_obj.llm_api_key_encrypted:
        # 如果用户没有配置LLM，则无法生成标题，返回默认标题
        db_conversation.title = "新对话"
        db.add(db_conversation)
        db.commit()
        db.refresh(db_conversation)
        print(f"ERROR: 用户 {current_user_id} 未配置LLM API，无法生成标题，使用默认标题。")

        total_messages_count = db.query(AIConversationMessage).filter(
            AIConversationMessage.conversation_id == db_conversation.id).count()
        conv_response = schemas.AIConversationResponse.model_validate(db_conversation, from_attributes=True)
        conv_response.total_messages_count = total_messages_count
        return conv_response

    user_llm_api_type = current_user_obj.llm_api_type
    user_llm_api_base_url = current_user_obj.llm_api_base_url
    user_llm_model_id_configured = current_user_obj.llm_model_id

    try:
        user_llm_api_key = decrypt_key(current_user_obj.llm_api_key_encrypted)
        print(f"DEBUG_LLM_TITLE_REGEN: 密钥解密成功，使用用户配置的硅基流动 API 密钥为对话生成标题。")
    except Exception as e:
        # 如果密钥解密失败，也视为无法生成标题，返回默认标题
        db_conversation.title = "新对话"
        db.add(db_conversation)
        db.commit()
        db.refresh(db_conversation)
        print(f"ERROR_LLM_TITLE_REGEN: 解密用户LLM API密钥失败: {e}. 无法生成标题，使用默认标题。")
        total_messages_count = db.query(AIConversationMessage).filter(
            AIConversationMessage.conversation_id == db_conversation.id).count()
        conv_response = schemas.AIConversationResponse.model_validate(db_conversation, from_attributes=True)
        conv_response.total_messages_count = total_messages_count
        return conv_response

    if past_messages_for_llm:  # 确保有消息可以用来生成标题
        try:
            ai_generated_title = await generate_conversation_title_from_llm(
                messages=past_messages_for_llm,
                user_llm_api_type=user_llm_api_type,
                user_llm_api_key=user_llm_api_key,
                user_llm_api_base_url=user_llm_api_base_url,
                user_llm_model_id=user_llm_model_id_configured
            )
            # 只有当生成的标题有效且不是默认的"新对话"或"无标题对话"时才更新
            if ai_generated_title and ai_generated_title != "新对话" and ai_generated_title != "无标题对话":
                db_conversation.title = ai_generated_title
                print(f"DEBUG: AI对话 {conversation_id} 标题由AI强制生成为 '{db_conversation.title}'。")
            else:
                db_conversation.title = "新对话"  # LLM生成不具意义或空，使用默认
                print(f"DEBUG: LLM生成的标题不具意义 ('{ai_generated_title}')，对话 {conversation_id} 保持默认标题。")
        except Exception as e:
            print(f"ERROR: AI自动生成标题失败: {e}. 将使用默认标题。")
            db_conversation.title = "新对话"  # 自动生成失败时的默认标题
    else:
        db_conversation.title = "新对话"  # 没有消息时（虽然上面已处理），以防万一
        print(f"DEBUG: AI对话 {conversation_id} 没有历史消息用于生成标题，使用默认标题 '{db_conversation.title}'。")
    # ----- 核心修改结束 -----

    db.add(db_conversation)  # 标记为更新
    db.commit()  # 提交更新

    db.refresh(db_conversation)  # 刷新以获取最新状态

    # 动态计算总消息数 for response
    total_messages_count = db.query(AIConversationMessage).filter(
        AIConversationMessage.conversation_id == db_conversation.id).count()
    conv_response = schemas.AIConversationResponse.model_validate(db_conversation, from_attributes=True)
    conv_response.total_messages_count = total_messages_count

    return conv_response

@router.delete("/ai_conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="删除指定AI对话")
async def delete_ai_conversation(
        conversation_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    删除指定AI对话及其所有消息历史。
    """
    print(f"DEBUG: 用户 {current_user_id} 尝试删除AI对话 {conversation_id}。")
    db_conversation = db.query(AIConversation).filter(
        AIConversation.id == conversation_id,
        AIConversation.user_id == current_user_id
    ).first()
    if not db_conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话未找到或无权访问。")

    db.delete(db_conversation)  # 会级联删除所有消息 (cascade="all, delete-orphan")
    db.commit()
    print(f"DEBUG: AI对话 {conversation_id} 及其所有消息已删除。")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
