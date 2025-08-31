# ai_providers/agent_orchestrator.py
"""
智能代理编排模块
处理多步骤AI任务流程、工具选择和执行、代理链式调用等功能
"""
import json
import re
from typing import List, Dict, Any, Optional, Union

from sqlalchemy.orm import Session

# 导入模型和Schema
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from project.models import Student, KnowledgeBase, KnowledgeDocument, KnowledgeDocumentChunk, Note, CollectedContent, UserMcpConfig, UserSearchEngineConfig

# 导入AI提供者和工具
from .security_utils import decrypt_key
from .llm_provider import create_llm_provider
from .search_provider import create_search_provider
from .embedding_provider import create_embedding_provider
from .ai_config import DUMMY_API_KEY, get_user_model_for_provider

# --- 工具定义常量 ---
WEB_SEARCH_TOOL_SCHEMA = {
    "name": "web_search",
    "description": "搜索互联网获取最新信息，适用于时事、新闻、产品信息等查询",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索查询字符串"
            },
            "max_results": {
                "type": "integer",
                "description": "最大结果数量，默认为5",
                "default": 5
            }
        },
        "required": ["query"]
    }
}

RAG_TOOL_SCHEMA = {
    "name": "knowledge_search",
    "description": "从用户的多种内容源中搜索相关信息，包括知识库文档、课程笔记、收藏内容等",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索查询内容"
            },
            "max_results": {
                "type": "integer",
                "description": "最大结果数量，默认为3",
                "default": 3
            },
            "content_types": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["knowledge_document", "note", "collected_content"]
                },
                "description": "要搜索的内容类型，可选：knowledge_document(知识库文档), note(课程笔记), collected_content(收藏内容)。默认搜索所有类型",
                "default": ["knowledge_document", "note", "collected_content"]
            }
        },
        "required": ["query"]
    }
}

MCP_TOOL_SCHEMA = {
    "name": "mcp_tool_call",
    "description": "调用MCP（Model Context Protocol）工具执行特定任务",
    "input_schema": {
        "type": "object",
        "properties": {
            "tool_name": {
                "type": "string",
                "description": "要调用的MCP工具名称"
            },
            "arguments": {
                "type": "object",
                "description": "工具参数"
            }
        },
        "required": ["tool_name", "arguments"]
    }
}

PROJECT_MATCH_TOOL_SCHEMA = {
    "name": "find_matching_projects",
    "description": "为学生推荐匹配的项目",
    "input_schema": {
        "type": "object",
        "properties": {
            "student_id": {
                "type": "integer",
                "description": "学生ID"
            },
            "max_results": {
                "type": "integer",
                "description": "最大结果数量，默认为3",
                "default": 3
            }
        },
        "required": ["student_id"]
    }
}


async def execute_tool(
    tool_name: str,
    tool_arguments: Dict[str, Any],
    user_id: int,
    db: Session,
    kb_ids: Optional[List[int]] = None
) -> Dict[str, Any]:
    """
    执行指定的工具调用
    """
    try:
        if tool_name == "web_search":
            return await _execute_web_search_tool(tool_arguments, user_id, db)
        elif tool_name == "knowledge_search":
            return await _execute_rag_tool(tool_arguments, user_id, db, kb_ids)
        elif tool_name == "mcp_tool_call":
            return await _execute_mcp_tool(tool_arguments, user_id, db)
        elif tool_name == "find_matching_projects":
            return await _execute_project_match_tool(tool_arguments, user_id, db)
        else:
            return {
                "success": False,
                "error": f"未知的工具名称: {tool_name}",
                "data": None
            }
    except Exception as e:
        print(f"ERROR_TOOL_EXECUTION: 执行工具 {tool_name} 时发生错误: {e}")
        return {
            "success": False,
            "error": f"工具执行失败: {str(e)}",
            "data": None
        }


async def _execute_web_search_tool(
    arguments: Dict[str, Any],
    user_id: int,
    db: Session
) -> Dict[str, Any]:
    """执行网页搜索工具"""
    query = arguments.get("query", "")
    max_results = arguments.get("max_results", 5)
    
    if not query:
        return {
            "success": False,
            "error": "搜索查询不能为空",
            "data": None
        }

    # 获取用户配置
    user = db.query(Student).filter(Student.id == user_id).first()
    if not user:
        return {
            "success": False,
            "error": "用户未找到",
            "data": None
        }

    # 获取搜索引擎配置
    search_config = db.query(UserSearchEngineConfig).filter(
        UserSearchEngineConfig.student_id == user_id
    ).first()

    if not search_config:
        return {
            "success": False,
            "error": "未配置搜索引擎",
            "data": None
        }

    try:
        # 解密API密钥
        api_key = decrypt_key(search_config.api_key_encrypted) if search_config.api_key_encrypted else None
        
        # 创建搜索提供者
        search_provider = create_search_provider(search_config.provider_type, api_key)
        
        # 执行搜索
        search_results = await search_provider.search(query, max_results)
        
        return {
            "success": True,
            "error": None,
            "data": {
                "query": query,
                "results": search_results,
                "total_results": len(search_results)
            }
        }
        
    except Exception as e:
        print(f"ERROR_WEB_SEARCH: 网页搜索失败: {e}")
        return {
            "success": False,
            "error": f"网页搜索失败: {str(e)}",
            "data": None
        }


async def _execute_rag_tool(
    arguments: Dict[str, Any],
    user_id: int,
    db: Session,
    kb_ids: Optional[List[int]] = None
) -> Dict[str, Any]:
    """执行RAG多内容搜索工具 - 支持知识库文档、课程笔记、收藏内容检索"""
    query = arguments.get("query", "")
    max_results = arguments.get("max_results", 3)
    content_types = arguments.get("content_types", ["knowledge_document", "note", "collected_content"])
    
    if not query:
        return {
            "success": False,
            "error": "搜索查询不能为空",
            "data": None
        }

    # 获取用户配置
    user = db.query(Student).filter(Student.id == user_id).first()
    if not user:
        return {
            "success": False,
            "error": "用户未找到",
            "data": None
        }

    # 收集所有可搜索的内容
    searchable_items = []
    
    # 知识库文档块 (上传文档的内容) - 这是知识库的主要内容
    if "knowledge_document" in content_types:
        # 查找用户有权限访问的知识库
        kb_query = db.query(KnowledgeBase).filter(
            (KnowledgeBase.owner_id == user_id) | (KnowledgeBase.access_type == "public")
        )
        
        # 如果指定了kb_ids，进一步过滤
        if kb_ids:
            kb_query = kb_query.filter(KnowledgeBase.id.in_(kb_ids))
        
        accessible_kbs = kb_query.all()
        
        for kb in accessible_kbs:
            document_chunks = db.query(KnowledgeDocumentChunk).filter(
                KnowledgeDocumentChunk.kb_id == kb.id,
                KnowledgeDocumentChunk.embedding.isnot(None)
            ).all()
            for chunk in document_chunks:
                searchable_items.append({"obj": chunk, "type": "knowledge_document"})
    
    # 课程笔记
    if "note" in content_types:
        notes = db.query(Note).filter(
            Note.owner_id == user_id,
            Note.embedding.isnot(None)
        ).all()
        for note in notes:
            searchable_items.append({"obj": note, "type": "note"})
    
    # 收藏内容
    if "collected_content" in content_types:
        collected_items = db.query(CollectedContent).filter(
            CollectedContent.owner_id == user_id,
            CollectedContent.embedding.isnot(None)
        ).all()
        for item in collected_items:
            searchable_items.append({"obj": item, "type": "collected_content"})

    if not searchable_items:
        return {
            "success": True,
            "error": None,
            "data": {
                "query": query,
                "results": [],
                "message": "没有找到可搜索的内容"
            }
        }

    try:
        # 获取API密钥
        api_key = None
        if user.llm_api_type == "siliconflow" and user.llm_api_key_encrypted:
            api_key = decrypt_key(user.llm_api_key_encrypted)

        if not api_key or api_key == DUMMY_API_KEY:
            return {
                "success": False,
                "error": "未配置有效的API密钥",
                "data": None
            }

        # 创建嵌入提供者
        embedding_provider = create_embedding_provider("siliconflow", api_key)
        
        # 获取查询嵌入向量
        query_embeddings = await embedding_provider.get_embeddings([query])
        if not query_embeddings:
            return {
                "success": False,
                "error": "无法生成查询嵌入向量",
                "data": None
            }

        query_embedding = query_embeddings[0]

        # 计算相似度并排序
        import numpy as np
        from sklearn.metrics.pairwise import cosine_similarity
        
        scored_items = []
        for item in searchable_items:
            obj = item["obj"]
            item_type = item["type"]
            
            item_embedding = None
            if obj.embedding:
                try:
                    if isinstance(obj.embedding, str):
                        item_embedding = json.loads(obj.embedding)
                    elif isinstance(obj.embedding, list):
                        item_embedding = obj.embedding
                except:
                    continue
                    
            if item_embedding and len(item_embedding) == len(query_embedding):
                similarity = cosine_similarity(
                    [query_embedding], 
                    [item_embedding]
                )[0][0]
                scored_items.append({
                    "object": obj,
                    "type": item_type,
                    "similarity": similarity
                })

        # 排序并取top结果
        scored_items.sort(key=lambda x: x["similarity"], reverse=True)
        top_items = scored_items[:max_results]

        results = []
        for item in top_items:
            obj = item["object"]
            item_type = item["type"]
            
            # 根据类型提取不同的字段
            if item_type == "knowledge_document":
                # 对于文档块，我们需要获取其父文档信息
                document = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == obj.document_id).first()
                document_name = document.file_name if document else f"文档块 {obj.id}"
                result = {
                    "type": "知识库文档",
                    "title": f"{document_name} (第{obj.chunk_index}块)",
                    "content": obj.content[:500] + "..." if obj.content and len(obj.content) > 500 else obj.content,
                    "similarity": item["similarity"],
                    "created_at": obj.created_at.isoformat() if obj.created_at else None
                }
            elif item_type == "note":
                result = {
                    "type": "课程笔记",
                    "title": obj.title if hasattr(obj, 'title') else f"笔记 {obj.id}",
                    "content": obj.content[:500] + "..." if obj.content and len(obj.content) > 500 else obj.content,
                    "similarity": item["similarity"],
                    "created_at": obj.created_at.isoformat() if obj.created_at else None
                }
            elif item_type == "collected_content":
                result = {
                    "type": "收藏内容",
                    "title": obj.title if hasattr(obj, 'title') else f"收藏 {obj.id}",
                    "content": obj.content[:500] + "..." if obj.content and len(obj.content) > 500 else obj.content,
                    "similarity": item["similarity"],
                    "created_at": obj.created_at.isoformat() if obj.created_at else None
                }
            else:
                continue
                
            results.append(result)

        return {
            "success": True,
            "error": None,
            "data": {
                "query": query,
                "results": results,
                "content_types_searched": content_types,
                "total_searched": len(searchable_items)
            }
        }
        
    except Exception as e:
        print(f"ERROR_RAG_SEARCH: RAG搜索失败: {e}")
        return {
            "success": False,
            "error": f"知识库搜索失败: {str(e)}",
            "data": None
        }


async def _execute_mcp_tool(
    arguments: Dict[str, Any],
    user_id: int,
    db: Session
) -> Dict[str, Any]:
    """执行MCP工具调用"""
    tool_name = arguments.get("tool_name", "")
    tool_arguments = arguments.get("arguments", {})
    
    if not tool_name:
        return {
            "success": False,
            "error": "工具名称不能为空",
            "data": None
        }

    # 获取用户的MCP配置
    mcp_config = db.query(UserMcpConfig).filter(
        UserMcpConfig.student_id == user_id
    ).first()

    if not mcp_config:
        return {
            "success": False,
            "error": "未配置MCP服务",
            "data": None
        }

    try:
        # 这里应该实现实际的MCP协议调用
        # 暂时返回模拟结果
        return {
            "success": True,
            "error": None,
            "data": {
                "tool_name": tool_name,
                "arguments": tool_arguments,
                "result": f"MCP工具 {tool_name} 执行完成（模拟结果）"
            }
        }
        
    except Exception as e:
        print(f"ERROR_MCP_TOOL: MCP工具调用失败: {e}")
        return {
            "success": False,
            "error": f"MCP工具调用失败: {str(e)}",
            "data": None
        }


async def _execute_project_match_tool(
    arguments: Dict[str, Any],
    user_id: int,
    db: Session
) -> Dict[str, Any]:
    """执行项目匹配工具"""
    student_id = arguments.get("student_id")
    max_results = arguments.get("max_results", 3)
    
    if not student_id:
        return {
            "success": False,
            "error": "学生ID不能为空",
            "data": None
        }

    try:
        # 导入匹配引擎
        from .matching_engine import find_matching_projects_for_student
        
        # 执行匹配
        matched_projects = await find_matching_projects_for_student(
            db=db,
            student_id=student_id,
            final_k=max_results
        )
        
        # 转换为字典格式
        results = []
        for project in matched_projects:
            results.append({
                "project_id": project.project_id,
                "title": project.title,
                "description": project.description,
                "relevance_score": project.relevance_score,
                "match_rationale": project.match_rationale
            })
        
        return {
            "success": True,
            "error": None,
            "data": {
                "student_id": student_id,
                "matched_projects": results,
                "total_matches": len(results)
            }
        }
        
    except Exception as e:
        print(f"ERROR_PROJECT_MATCH: 项目匹配失败: {e}")
        return {
            "success": False,
            "error": f"项目匹配失败: {str(e)}",
            "data": None
        }


def get_available_tools(user_id: int, db: Session) -> List[Dict[str, Any]]:
    """
    获取用户可用的工具列表
    """
    tools = []
    
    # 检查搜索引擎配置
    search_config = db.query(UserSearchEngineConfig).filter(
        UserSearchEngineConfig.student_id == user_id
    ).first()
    if search_config:
        tools.append(WEB_SEARCH_TOOL_SCHEMA)
    
    # 检查知识库
    knowledge_count = db.query(KnowledgeBase).filter(
        KnowledgeBase.creator_id == user_id
    ).count()
    if knowledge_count > 0:
        tools.append(RAG_TOOL_SCHEMA)
    
    # 检查MCP配置
    mcp_config = db.query(UserMcpConfig).filter(
        UserMcpConfig.student_id == user_id
    ).first()
    if mcp_config:
        tools.append(MCP_TOOL_SCHEMA)
    
    # 项目匹配工具总是可用
    tools.append(PROJECT_MATCH_TOOL_SCHEMA)
    
    return tools


async def invoke_agent(
    query: Optional[str] = None,
    db: Session = None,
    user_id: int = None,
    conversation_context: Optional[List[Dict[str, Any]]] = None,
    kb_ids: Optional[List[int]] = None,
    use_tools: bool = True,
    preferred_tools: Optional[List[str]] = None,
    temp_file_ids: Optional[List[int]] = None,
    llm_api_key: Optional[str] = None,
    llm_type: Optional[str] = None,
    llm_base_url: Optional[str] = None,
    llm_model_id: Optional[str] = None,
    rag_sources: Optional[List[str]] = None,
    # 为了向后兼容，保留原始参数
    messages: Optional[List[Dict[str, str]]] = None,
    # ai_original.py 使用的参数
    llm_api_type: Optional[str] = None,
    past_messages: Optional[List[Dict[str, Any]]] = None,
    conversation_id_for_temp_files: Optional[int] = None,
    enable_tool_use: Optional[bool] = None
) -> Dict[str, Any]:
    """
    调用智能代理处理用户请求
    支持多种参数格式以保持向后兼容性
    """
    try:
        # 参数兼容性处理
        if llm_api_type is not None:
            llm_type = llm_api_type
        if enable_tool_use is not None:
            use_tools = enable_tool_use
        if past_messages is not None:
            conversation_context = past_messages
        
        # 如果传入了简单的messages参数（旧版本兼容），构建查询
        if messages and not query:
            query = messages[-1].get("content", "") if messages else ""
            conversation_context = messages[:-1] if len(messages) > 1 else []
        
        # 验证必需参数
        if not query:
            return {
                "success": False,
                "error": "缺少查询内容",
                "response": None
            }
        
        if not db or not user_id:
            return {
                "success": False,
                "error": "缺少数据库连接或用户ID",
                "response": None
            }

        # 获取用户信息
        user = db.query(Student).filter(Student.id == user_id).first()
        if not user:
            return {
                "success": False,
                "error": "用户未找到",
                "response": None
            }

        # 确定API配置 - 优先使用传入的参数，否则使用用户配置
        effective_llm_type = llm_type or user.llm_api_type
        effective_llm_base_url = llm_base_url or user.llm_api_base_url
        effective_llm_model_id = llm_model_id or get_user_model_for_provider(
            user.llm_model_ids, user.llm_api_type, user.llm_model_id
        )
        
        # API密钥处理
        api_key = llm_api_key
        if not api_key and user.llm_api_key_encrypted:
            try:
                api_key = decrypt_key(user.llm_api_key_encrypted)
            except Exception:
                pass
        
        if not api_key or api_key == DUMMY_API_KEY:
            return {
                "success": False,
                "error": "未配置有效的API密钥",
                "response": None
            }

        # 创建LLM提供者
        llm_provider = create_llm_provider(
            effective_llm_type, 
            api_key, 
            effective_llm_base_url, 
            effective_llm_model_id
        )
        
        # 获取可用工具并应用偏好过滤
        available_tools = []
        if use_tools:
            all_tools = await get_all_available_tools_for_llm(db, user_id)
            if preferred_tools:
                available_tools = _filter_tools_by_preference(all_tools, preferred_tools, rag_sources)
            else:
                available_tools = all_tools
        
        # 构建系统提示
        system_prompt = _build_system_prompt(available_tools)
        
        # 构建消息历史
        full_messages = [{"role": "system", "content": system_prompt}]
        
        # 添加对话历史
        if conversation_context:
            for msg in conversation_context:
                if isinstance(msg, dict) and "role" in msg and "content" in msg:
                    full_messages.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })
        
        # 添加当前查询
        full_messages.append({"role": "user", "content": query})
        
        # 第一轮LLM调用
        response = await llm_provider.chat_completion(full_messages)
        
        if not response or 'choices' not in response:
            return {
                "success": False,
                "error": "LLM响应异常",
                "response": None
            }

        assistant_message = response['choices'][0]['message']['content']
        
        # 检查是否需要工具调用
        if use_tools and available_tools:
            tool_calls = _extract_tool_calls(assistant_message)
            
            if tool_calls:
                # 执行工具调用
                tool_results = []
                for tool_call in tool_calls:
                    # 为RAG工具传递rag_sources参数
                    if tool_call["name"] == "knowledge_search" and rag_sources:
                        tool_call["arguments"]["content_types"] = rag_sources
                    
                    result = await execute_tool(
                        tool_call["name"],
                        tool_call["arguments"],
                        user_id,
                        db,
                        kb_ids=kb_ids
                    )
                    tool_results.append({
                        "tool_name": tool_call["name"],
                        "result": result
                    })
                
                # 将工具结果添加到对话中
                full_messages.append({"role": "assistant", "content": assistant_message})
                tool_results_text = _format_tool_results(tool_results)
                full_messages.append({"role": "user", "content": f"工具执行结果：\n{tool_results_text}\n\n请基于这些结果提供最终回答。"})
                
                # 第二轮LLM调用
                final_response = await llm_provider.chat_completion(full_messages)
                
                if final_response and 'choices' in final_response:
                    assistant_message = final_response['choices'][0]['message']['content']
        
        # 构建返回结果
        result = {
            "success": True,
            "error": None,
            "response": assistant_message,
            "content": assistant_message  # 兼容性字段
        }
        
        # 为ai_original.py兼容性，添加turn_messages_to_log字段
        result["turn_messages_to_log"] = [
            {
                "role": "user",
                "content": query,
                "llm_type_used": effective_llm_type,
                "llm_model_used": effective_llm_model_id
            },
            {
                "role": "assistant", 
                "content": assistant_message,
                "llm_type_used": effective_llm_type,
                "llm_model_used": effective_llm_model_id
            }
        ]
        
        return result
        
    except Exception as e:
        print(f"ERROR_AGENT_INVOKE: 代理调用失败: {e}")
        return {
            "success": False,
            "error": f"代理调用失败: {str(e)}",
            "response": None
        }


def _build_system_prompt(available_tools: List[Dict[str, Any]]) -> str:
    """构建系统提示"""
    base_prompt = """你是一个智能助手，可以帮助用户处理各种任务。"""
    
    if available_tools:
        tool_descriptions = []
        for tool in available_tools:
            tool_descriptions.append(f"- {tool['name']}: {tool['description']}")
        
        tools_text = "\n".join(tool_descriptions)
        
        base_prompt += f"""

你可以使用以下工具：
{tools_text}

如果需要使用工具，请按照以下格式调用：
<tool_call>
{{"name": "工具名称", "arguments": {{"参数": "值"}}}}
</tool_call>

每次只能调用一个工具。在使用工具之前，请先分析用户的需求，判断是否真的需要使用工具。"""
    
    return base_prompt


def _extract_tool_calls(content: str) -> List[Dict[str, Any]]:
    """从助手回复中提取工具调用"""
    tool_calls = []
    
    # 匹配工具调用格式
    pattern = r'<tool_call>\s*(\{.*?\})\s*</tool_call>'
    matches = re.findall(pattern, content, re.DOTALL)
    
    for match in matches:
        try:
            tool_call = json.loads(match)
            if "name" in tool_call and "arguments" in tool_call:
                tool_calls.append(tool_call)
        except json.JSONDecodeError:
            continue
    
    return tool_calls


def _format_tool_results(tool_results: List[Dict[str, Any]]) -> str:
    """格式化工具执行结果"""
    formatted_results = []
    
    for result in tool_results:
        tool_name = result["tool_name"]
        tool_result = result["result"]
        
        if tool_result["success"]:
            formatted_results.append(f"{tool_name}执行成功：\n{json.dumps(tool_result['data'], ensure_ascii=False, indent=2)}")
        else:
            formatted_results.append(f"{tool_name}执行失败：{tool_result['error']}")
    
    return "\n\n".join(formatted_results)


async def multi_step_agent_workflow(
    initial_query: str,
    user_id: int,
    db: Session,
    max_steps: int = 3
) -> Dict[str, Any]:
    """
    多步骤代理工作流
    """
    workflow_history = []
    current_query = initial_query
    
    for step in range(max_steps):
        print(f"INFO_AGENT_WORKFLOW: 执行第 {step + 1} 步")
        
        # 构建当前步骤的消息
        messages = [{"role": "user", "content": current_query}]
        
        # 调用代理
        result = await invoke_agent(messages, user_id, db, use_tools=True)
        
        workflow_history.append({
            "step": step + 1,
            "query": current_query,
            "result": result
        })
        
        if not result["success"]:
            return {
                "success": False,
                "error": f"第 {step + 1} 步执行失败: {result['error']}",
                "workflow_history": workflow_history
            }
        
        # 检查是否需要继续
        response = result["response"]
        if not _needs_continuation(response):
            break
            
        # 准备下一步查询
        current_query = _extract_next_query(response)
        if not current_query:
            break
    
    return {
        "success": True,
        "error": None,
        "workflow_history": workflow_history,
        "final_response": workflow_history[-1]["result"]["response"] if workflow_history else None
    }


def _needs_continuation(response: str) -> bool:
    """判断是否需要继续多步骤工作流"""
    continuation_keywords = ["接下来", "然后", "下一步", "继续", "还需要"]
    return any(keyword in response for keyword in continuation_keywords)


def _extract_next_query(response: str) -> Optional[str]:
    """从响应中提取下一步查询"""
    # 简单实现：查找包含问号的句子
    sentences = response.split('。')
    for sentence in sentences:
        if '？' in sentence or '?' in sentence:
            return sentence.strip()
    return None


async def get_all_available_tools_for_llm(db, user_id: int) -> List[Dict[str, Any]]:
    """
    获取用户可用的所有LLM工具
    这是原ai_core.get_all_available_tools_for_llm的简化版本
    """
    from sqlalchemy.orm import Session
    try:
        from models import UserMcpConfig
    except ImportError:
        # 如果模型导入失败，只返回基础工具
        return [WEB_SEARCH_TOOL_SCHEMA, RAG_TOOL_SCHEMA]
    
    tools = []

    # 1. 添加通用的内置工具
    tools.append(WEB_SEARCH_TOOL_SCHEMA)
    tools.append(RAG_TOOL_SCHEMA)

    # 2. 添加用户定义和活动的 MCP 工具
    try:
        active_mcp_configs = db.query(UserMcpConfig).filter(
            UserMcpConfig.owner_id == user_id,
            UserMcpConfig.is_active == True
        ).all()

        for config in active_mcp_configs:
            # 为每个活跃的MCP配置生成通用工具
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
    except Exception as e:
        print(f"WARNING: 获取MCP工具失败: {e}")

    print(f"DEBUG_TOOL: Assembled {len(tools)} available tools for user {user_id}.")
    return tools


def _filter_tools_by_preference(
    available_tools: List[Dict[str, Any]], 
    preferred_tools: Union[List[str], str, None],
    rag_sources: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """根据偏好过滤工具"""
    if preferred_tools is None:
        return []
    
    if preferred_tools == "all":
        filtered_tools = available_tools
    elif isinstance(preferred_tools, list):
        if not preferred_tools:  # 空数组
            return []
            
        filtered_tools = []
        for tool in available_tools:
            tool_name = tool.get("name", "")
            # 根据工具名称匹配类型
            if ("web_search" in preferred_tools and "web_search" in tool_name) or \
               ("rag" in preferred_tools and ("knowledge_search" in tool_name or "rag" in tool_name)) or \
               ("mcp_tool" in preferred_tools and "mcp" in tool_name):
                filtered_tools.append(tool)
    else:
        return []
    
    # 为RAG工具添加来源配置
    if rag_sources:
        for tool in filtered_tools:
            if tool.get("name") == "knowledge_search":
                # 修改工具的参数定义，添加content_types默认值
                if "input_schema" in tool and "properties" in tool["input_schema"]:
                    tool["input_schema"]["properties"]["content_types"] = {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["knowledge_document", "note", "collected_content"]
                        },
                        "description": "要搜索的内容类型",
                        "default": rag_sources
                    }
                # 为工具实例添加来源配置
                tool["_rag_sources"] = rag_sources
    
    return filtered_tools
