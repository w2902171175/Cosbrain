# ai_providers/agent_orchestrator.py
"""
智能代理编排模块
处理多步骤AI任务流程、工具选择和执行、代理链式调用等功能
"""
import json
import re
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session

# 导入模型和Schema
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import Student, KnowledgeBase, UserMcpConfig, UserSearchEngineConfig

# 导入AI提供者和工具
from .security_utils import decrypt_key
from .llm_provider import create_llm_provider
from .search_provider import create_search_provider
from .embedding_provider import create_embedding_provider
from .config import DUMMY_API_KEY

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
    "description": "从用户的知识库中搜索相关信息，适用于个人文档、笔记、项目资料等查询",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "知识库搜索查询"
            },
            "max_results": {
                "type": "integer",
                "description": "最大结果数量，默认为3",
                "default": 3
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
    db: Session
) -> Dict[str, Any]:
    """
    执行指定的工具调用
    """
    try:
        if tool_name == "web_search":
            return await _execute_web_search_tool(tool_arguments, user_id, db)
        elif tool_name == "knowledge_search":
            return await _execute_rag_tool(tool_arguments, user_id, db)
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
    db: Session
) -> Dict[str, Any]:
    """执行RAG知识库搜索工具"""
    query = arguments.get("query", "")
    max_results = arguments.get("max_results", 3)
    
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

    # 获取用户的知识库文档
    knowledge_docs = db.query(KnowledgeBase).filter(
        KnowledgeBase.creator_id == user_id
    ).all()

    if not knowledge_docs:
        return {
            "success": True,
            "error": None,
            "data": {
                "query": query,
                "results": [],
                "message": "知识库为空"
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
        
        scored_docs = []
        for doc in knowledge_docs:
            doc_embedding = None
            if doc.embedding:
                try:
                    if isinstance(doc.embedding, str):
                        doc_embedding = json.loads(doc.embedding)
                    elif isinstance(doc.embedding, list):
                        doc_embedding = doc.embedding
                except:
                    continue
                    
            if doc_embedding and len(doc_embedding) == len(query_embedding):
                similarity = cosine_similarity(
                    [query_embedding], 
                    [doc_embedding]
                )[0][0]
                scored_docs.append({
                    "document": doc,
                    "similarity": similarity
                })

        # 排序并取top结果
        scored_docs.sort(key=lambda x: x["similarity"], reverse=True)
        top_docs = scored_docs[:max_results]

        results = []
        for item in top_docs:
            doc = item["document"]
            results.append({
                "title": doc.title,
                "content": doc.content[:500] + "..." if len(doc.content) > 500 else doc.content,
                "similarity": item["similarity"],
                "created_at": doc.created_at.isoformat() if doc.created_at else None
            })

        return {
            "success": True,
            "error": None,
            "data": {
                "query": query,
                "results": results,
                "total_searched": len(knowledge_docs)
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
    messages: List[Dict[str, str]],
    user_id: int,
    db: Session,
    use_tools: bool = True
) -> Dict[str, Any]:
    """
    调用智能代理处理用户请求
    """
    try:
        # 获取用户信息
        user = db.query(Student).filter(Student.id == user_id).first()
        if not user:
            return {
                "success": False,
                "error": "用户未找到",
                "response": None
            }

        # 获取API密钥
        api_key = None
        if user.llm_api_type == "siliconflow" and user.llm_api_key_encrypted:
            api_key = decrypt_key(user.llm_api_key_encrypted)

        if not api_key or api_key == DUMMY_API_KEY:
            return {
                "success": False,
                "error": "未配置有效的API密钥",
                "response": None
            }

        # 创建LLM提供者
        llm_provider = create_llm_provider("siliconflow", api_key)
        
        # 获取可用工具
        available_tools = get_available_tools(user_id, db) if use_tools else []
        
        # 构建系统提示
        system_prompt = _build_system_prompt(available_tools)
        
        # 构建完整消息
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        
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
                    result = await execute_tool(
                        tool_call["name"],
                        tool_call["arguments"],
                        user_id,
                        db
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
        
        return {
            "success": True,
            "error": None,
            "response": assistant_message
        }
        
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
