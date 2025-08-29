# ai_providers/matching_engine.py
"""
匹配引擎模块
包含学生-项目-课程匹配逻辑、技能评估、时间匹配等功能
"""
import json
import ast
import re
from typing import List, Dict, Any, Optional, Literal, Union

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from fastapi import HTTPException
from sqlalchemy.orm import Session

# 导入模型和Schema
from project.models import Student, Project, Course
from project.schemas import MatchedProject, MatchedStudent, MatchedCourse

# 导入AI提供者和工具
from .security_utils import decrypt_key
from .llm_provider import create_llm_provider
from .embedding_provider import create_embedding_provider  
from .rerank_provider import create_rerank_provider
from .config import DUMMY_API_KEY

# --- 匹配相关的全局常量 ---
INITIAL_CANDIDATES_K = 50
FINAL_TOP_K = 3
MAX_SKILL_LEVEL_DIFF_PENALTY = 0.5
MIN_LEVEL_MATCH_SCORE = 1.0
SKILL_MATCH_OVERALL_WEIGHT = 5.0
OVERALL_TIME_MATCH_WEIGHT = 3.0


def _get_safe_embedding_np(raw_embedding: Any, entity_type: str, entity_id: Any) -> Optional[np.ndarray]:
    """
    尝试将各种原始嵌入格式转换为一个干净的np.ndarray (float32) 尺寸为 1024
    """
    np_embedding = None

    if isinstance(raw_embedding, np.ndarray):
        np_embedding = raw_embedding
    elif isinstance(raw_embedding, str):
        try:
            parsed_embedding = json.loads(raw_embedding)
            if isinstance(parsed_embedding, list) and all(isinstance(x, (float, int)) for x in parsed_embedding):
                np_embedding = np.array(parsed_embedding, dtype=np.float32)
            else:
                print(f"WARNING_AI_MATCHING: {entity_type} {entity_id} 嵌入字符串解析后不是浮点数列表。")
                return None
        except json.JSONDecodeError:
            print(f"WARNING_AI_MATCHING: {entity_type} {entity_id} 嵌入字符串JSON解码失败。")
            return None
    elif isinstance(raw_embedding, list):
        if all(isinstance(x, (float, int)) for x in raw_embedding):
            np_embedding = np.array(raw_embedding, dtype=np.float32)
        else:
            print(f"WARNING_AI_MATCHING: {entity_type} {entity_id} 嵌入列表包含非数值元素。")
            return None
    elif raw_embedding is None:
        print(f"WARNING_AI_MATCHING: {entity_type} {entity_id} 嵌入向量为None。")
        return None
    else:
        print(f"WARNING_AI_MATCHING: {entity_type} {entity_id} 嵌入向量类型未知: {type(raw_embedding)}。")
        return None

    if np_embedding is not None:
        if np_embedding.ndim != 1 or np_embedding.shape[0] != 1024:
            print(f"WARNING_AI_MATCHING: {entity_type} {entity_id} 嵌入向量维度或大小不正确: shape={np_embedding.shape} (期望 1024)。")
            return None

        if np.any(np.isnan(np_embedding)) or np.any(np.isinf(np_embedding)):
            print(f"WARNING_AI_MATCHING: {entity_type} {entity_id} 嵌入向量包含 NaN/Inf 值。")
            return None

    return np_embedding


def _get_skill_level_weight(level: str) -> float:
    """将技能熟练度等级转换为数值权重"""
    weights = {
        "初窥门径": 1.0,
        "登堂入室": 2.0,
        "融会贯通": 3.0,
        "炉火纯青": 4.0
    }
    return weights.get(level, 0.0)


def _parse_single_skill_entry_to_dict(single_skill_raw_data: Any) -> Optional[Dict]:
    """将各种原始技能条目格式规范化为 {'name': '...', 'level': '...'}"""
    default_skill_level = "初窥门径"
    valid_skill_levels = ["初窥门径", "登堂入室", "融会贯通", "炉火纯青"]

    if isinstance(single_skill_raw_data, dict):
        name = single_skill_raw_data.get("name")
        level = single_skill_raw_data.get("level", default_skill_level)
        if name and isinstance(name, str) and name.strip():
            formatted_name = name.strip()
            formatted_level = level if level in valid_skill_levels else default_skill_level
            return {"name": formatted_name, "level": formatted_level}
        return None
    elif isinstance(single_skill_raw_data, str):
        processed_str = single_skill_raw_data.strip()
        if not processed_str:
            return None

        initial_str = processed_str
        for _ in range(2):
            if (initial_str.startswith(("'", '"')) and initial_str.endswith(("'", '"')) and len(initial_str) > 1):
                initial_str = initial_str[1:-1]
        initial_str = initial_str.replace('\\"', '"').replace("\\'", "'")

        parsing_attempts = [
            (json.loads, "json.loads"),
            (ast.literal_eval, "ast.literal_eval")
        ]

        for parser, parser_name in parsing_attempts:
            try:
                parsed_content = parser(initial_str)
                if isinstance(parsed_content, dict) and "name" in parsed_content:
                    name = parsed_content["name"]
                    level = parsed_content.get("level", default_skill_level)
                    if isinstance(name, str) and name.strip():
                        formatted_name = name.strip()
                        formatted_level = level if level in valid_skill_levels else default_skill_level
                        return {"name": formatted_name, "level": formatted_level}
                elif isinstance(parsed_content, list) and len(parsed_content) > 0:
                    for item in parsed_content:
                        recursively_parsed_item = _parse_single_skill_entry_to_dict(item)
                        if recursively_parsed_item:
                            return recursively_parsed_item
            except (json.JSONDecodeError, ValueError, SyntaxError):
                pass
        
        if processed_str.strip():
            return {"name": processed_str.strip(), "level": default_skill_level}
        return None
    elif isinstance(single_skill_raw_data, list):
        for item in single_skill_raw_data:
            recursive_parsed_item = _parse_single_skill_entry_to_dict(item)
            if recursive_parsed_item and "name" in recursive_parsed_item and recursive_parsed_item["name"].strip():
                return recursive_parsed_item
        return None
    else:
        return None


def _ensure_top_level_list(raw_input: Any) -> List[Any]:
    """确保原始传入的技能列表数据本身是可迭代的 Python 列表"""
    if isinstance(raw_input, list):
        return raw_input

    if isinstance(raw_input, str):
        processed_input = raw_input.strip()
        for _ in range(2):
            if (processed_input.startswith(("'", '"')) and processed_input.endswith(("'", '"')) and len(processed_input) > 1):
                processed_input = processed_input[1:-1]
        processed_input = processed_input.replace('\\"', '"').replace("\\'", "'")

        try:
            parsed = json.loads(processed_input)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

        try:
            parsed = ast.literal_eval(processed_input)
            if isinstance(parsed, list):
                return parsed
        except (ValueError, SyntaxError):
            pass
        return []

    if raw_input is None:
        return []

    return []


def _calculate_proficiency_match_score(
        entity1_skills_raw_data: Any,
        entity2_required_skills_raw_data: Any
) -> float:
    """计算基于技能名称和熟练度的匹配分数"""
    score = 0.0
    default_skill_level = "初窥门径"

    processed_entity1_skills_list_safe = _ensure_top_level_list(entity1_skills_raw_data)
    processed_entity2_required_skills_list_safe = _ensure_top_level_list(entity2_required_skills_raw_data)

    # 构建 entity1 技能映射
    entity1_skill_map = {}
    for s_raw_entry in processed_entity1_skills_list_safe:
        s_parsed_dict = _parse_single_skill_entry_to_dict(s_raw_entry)
        if s_parsed_dict and 'name' in s_parsed_dict:
            entity1_skill_map[s_parsed_dict['name']] = _get_skill_level_weight(s_parsed_dict['level'])

    # 遍历 entity2 所需技能，计算匹配分数
    for req_skill_raw_entry in processed_entity2_required_skills_list_safe:
        req_skill_parsed_dict = _parse_single_skill_entry_to_dict(req_skill_raw_entry)

        if not (isinstance(req_skill_parsed_dict, dict) and 'name' in req_skill_parsed_dict and req_skill_parsed_dict['name'].strip()):
            continue

        req_name = req_skill_parsed_dict.get('name')
        req_level_weight = _get_skill_level_weight(req_skill_parsed_dict.get('level', default_skill_level))

        if req_name in entity1_skill_map:
            student_level_weight = entity1_skill_map[req_name]
            level_difference = req_level_weight - student_level_weight

            if level_difference <= 0:
                score += req_level_weight
            else:
                base_score = student_level_weight
                penalty = level_difference * MAX_SKILL_LEVEL_DIFF_PENALTY
                current_skill_score = max(MIN_LEVEL_MATCH_SCORE, base_score - penalty)
                score += current_skill_score
        else:
            score -= (req_level_weight * 0.75)

    # 计算总可能得分
    total_possible_score = sum(
        _get_skill_level_weight(s.get('level', default_skill_level)) 
        for s in processed_entity2_required_skills_list_safe 
        if s and isinstance(s, dict) and s.get('name', '').strip()
    )

    if total_possible_score > 0:
        normalized_score = max(0.0, score / total_possible_score)
    else:
        normalized_score = 1.0

    return normalized_score * SKILL_MATCH_OVERALL_WEIGHT


def _parse_weekly_hours_from_availability(availability_str: Optional[str]) -> Optional[int]:
    """从学生 availability 字符串中提取每周小时数"""
    if not availability_str or not isinstance(availability_str, str):
        return None

    availability_str_lower = availability_str.lower().replace(' ', '')

    # 匹配 "15-20小时" 这种范围
    match = re.search(r'(\d+)-(\d+)(?:小时)?', availability_str_lower)
    if match: 
        return (int(match.group(1)) + int(match.group(2))) // 2

    # 匹配 ">30小时", "30+小时"
    match = re.search(r'>(\d+)(?:小时)?', availability_str_lower)
    if match: 
        return int(match.group(1)) + 5
    
    # 匹配 "30+小时"
    match = re.search(r'(\d+)\+(?:小时)?', availability_str_lower)
    if match: 
        return int(match.group(1)) + 5

    # 匹配 "20小时" 这种单个数字
    match = re.search(r'(\d+)(?:小时)?', availability_str_lower)
    if match: 
        return int(match.group(1))

    # 匹配 "全职"
    if "全职" in availability_str_lower or "full-time" in availability_str_lower:
        return 40

    return None


def _calculate_time_match_score(student: Student, item: Union[Project, Course]) -> float:
    """计算基于时间与投入度的匹配分数"""
    if isinstance(item, Project):
        score_hours = 0.0
        score_dates = 0.0

        # 1. 周小时数匹配 (权重 0.6)
        student_weekly_hours = _parse_weekly_hours_from_availability(student.availability)

        if item.estimated_weekly_hours is not None and item.estimated_weekly_hours > 0:
            if student_weekly_hours is not None:
                if student_weekly_hours >= item.estimated_weekly_hours:
                    score_hours = 1.0
                else:
                    score_hours = max(0.2, student_weekly_hours / item.estimated_weekly_hours)
            else:
                score_hours = 0.3
        else:
            if student_weekly_hours is not None:
                score_hours = 0.8
            else:
                score_hours = 0.5

        # 2. 日期/持续时间匹配 (权重 0.4)
        student_temporal_keywords = set()
        if student.availability:
            avail_lower = student.availability.lower()
            if "暑假" in avail_lower or "夏季" in avail_lower: 
                student_temporal_keywords.add("summer")
            if "寒假" in avail_lower or "冬季" in avail_lower: 
                student_temporal_keywords.add("winter")
            if "学期内" in avail_lower: 
                student_temporal_keywords.add("semester")
            if "长期" in avail_lower or "long-term" in avail_lower: 
                student_temporal_keywords.add("long_term")
            if "短期" in avail_lower or "short-term" in avail_lower: 
                student_temporal_keywords.add("short_term")

        project_has_dates = item.start_date and item.end_date and item.end_date > item.start_date
        project_duration_months = (item.end_date - item.start_date).days / 30 if project_has_dates else None

        if project_has_dates:
            matched_period = False
            project_start_month = item.start_date.month
            
            if "summer" in student_temporal_keywords and 6 <= project_start_month <= 8: 
                matched_period = True
            elif "winter" in student_temporal_keywords and (project_start_month == 1 or project_start_month == 12): 
                matched_period = True
            elif "semester" in student_temporal_keywords and not (6 <= project_start_month <= 8 or project_start_month == 1 or project_start_month == 12): 
                matched_period = True
            
            if "long_term" in student_temporal_keywords and project_duration_months is not None and project_duration_months >= 6: 
                matched_period = True
            elif "short_term" in student_temporal_keywords and project_duration_months is not None and project_duration_months < 3: 
                matched_period = True

            if matched_period: 
                score_dates = 1.0
            elif student_temporal_keywords: 
                score_dates = 0.5
            else: 
                score_dates = 0.2
        else:
            if student_temporal_keywords: 
                score_dates = 0.7
            else: 
                score_dates = 0.5

        combined_time_score = (score_hours * 0.6) + (score_dates * 0.4)
    elif isinstance(item, Course):
        combined_time_score = 0.9  # 课程给予较高的默认分数
    else:
        combined_time_score = 0.5

    return combined_time_score * OVERALL_TIME_MATCH_WEIGHT


def _calculate_location_match_score(student_location: Optional[str], target_location: Optional[str]) -> float:
    """计算地理位置匹配分数"""
    score = 0.1
    
    student_loc_lower = (student_location or "").lower().strip()
    target_loc_lower = (target_location or "").lower().strip()

    if not student_loc_lower and not target_loc_lower:
        return 0.2

    if not student_loc_lower or not target_loc_lower:
        return 0.3

    # 完全相同
    if student_loc_lower == target_loc_lower:
        score = 1.0
        return score

    # 包含关系
    if student_loc_lower in target_loc_lower or target_loc_lower in student_loc_lower:
        score = 0.8
        return score

    # 城市级别匹配
    major_cities = ['广州', '深圳', '珠海', '佛山', '东莞', '惠州', '中山', '江门', '肇庆', '香港', '澳门']

    student_city_match = None
    target_city_match = None

    for city in major_cities:
        if city.lower() in student_loc_lower:
            student_city_match = city
        if city.lower() in target_loc_lower:
            target_city_match = city
        if student_city_match and target_city_match:
            break

    if student_city_match and target_city_match and student_city_match == target_city_match:
        score = 0.6
        return score

    return score


async def _generate_match_rationale_llm(
        student: Student,
        target_item: Union[Project, Course],
        sim_score: float,
        proficiency_score: float,
        time_score: float,
        location_score: float,
        match_type: Literal["student_to_project", "project_to_student", "student_to_course"],
        llm_api_key: Optional[str] = None
) -> str:
    """使用LLM生成匹配理由"""
    rationale_text = "AI匹配理由暂不可用。"

    if not llm_api_key or llm_api_key == DUMMY_API_KEY:
        print("WARNING_LLM_RATIONALE: 未配置LLM API KEY，无法生成动态匹配理由。")
        return rationale_text

    system_prompt = """
    你是一个智能匹配推荐系统的AI助手，需要为用户提供简洁、有说服力的匹配理由。
    请根据提供的学生和目标信息，以及各项匹配得分，总结为什么他们是匹配的。
    回复应简洁精炼，重点突出，不超过250字。
    """

    user_prompt = f"""
    学生信息:
    姓名: {student.name}, 专业: {student.major}
    技能: {json.dumps(student.skills, ensure_ascii=False)}
    兴趣: {student.interests or '无'}
    可用时间: {student.availability or '未指定'}
    地理位置: {student.location or '未指定'}

    目标信息:
    标题: {target_item.title}
    描述: {target_item.description}

    匹配得分:
    内容相关性: {sim_score:.2f}
    技能匹配: {proficiency_score:.2f}
    时间匹配: {time_score:.2f}
    地理位置匹配: {location_score:.2f}

    请为此匹配提供简洁的理由。
    """

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    try:
        llm_provider = create_llm_provider("siliconflow", llm_api_key)
        llm_response = await llm_provider.chat_completion(messages)
        
        if llm_response and 'choices' in llm_response and llm_response['choices'][0]['message'].get('content'):
            rationale_text = llm_response['choices'][0]['message']['content']
        else:
            rationale_text = "AI匹配理由生成失败或内容为空。"
    except Exception as e:
        print(f"ERROR_LLM_RATIONALE: 调用LLM生成匹配理由失败: {e}")
        rationale_text = f"基于AI分析，匹配得分 - 相关性：{sim_score:.2f}，技能：{proficiency_score:.2f}，时间：{time_score:.2f}，位置：{location_score:.2f}"

    return rationale_text


async def find_matching_projects_for_student(
    db: Session, 
    student_id: int,
    initial_k: int = INITIAL_CANDIDATES_K,
    final_k: int = FINAL_TOP_K
) -> List[MatchedProject]:
    """为指定学生推荐项目"""
    print(f"INFO_AI_MATCHING: 为学生 {student_id} 推荐项目。")
    
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生未找到。")

    # 获取学生的API密钥
    student_api_key = None
    if student.llm_api_type == "siliconflow" and student.llm_api_key_encrypted:
        try:
            student_api_key = decrypt_key(student.llm_api_key_encrypted)
        except Exception as e:
            print(f"ERROR_EMBEDDING_KEY: 解密学生API密钥失败: {e}")

    # 获取学生嵌入向量
    student_embedding_np = _get_safe_embedding_np(student.embedding, "学生", student.id)
    if student_embedding_np is None or (student_embedding_np == np.zeros(1024, dtype=np.float32)).all():
        # 尝试重新生成嵌入向量
        if student_api_key:
            try:
                embedding_provider = create_embedding_provider("siliconflow", student_api_key)
                re_generated_embedding = await embedding_provider.get_embeddings([student.combined_text])
                if re_generated_embedding and len(re_generated_embedding) > 0:
                    student_embedding_np = np.array(re_generated_embedding[0], dtype=np.float32)
            except Exception as e:
                print(f"ERROR_AI_MATCHING: 重新生成学生嵌入向量失败: {e}")
        
        if student_embedding_np is None or (student_embedding_np == np.zeros(1024, dtype=np.float32)).all():
            return []

    student_embedding = student_embedding_np.reshape(1, -1)

    # 获取所有项目
    all_projects = db.query(Project).all()
    if not all_projects:
        return []

    project_embeddings = []
    valid_projects = []

    for p in all_projects:
        p_embedding_np = _get_safe_embedding_np(p.embedding, "项目", p.id)
        if p_embedding_np is None or (p_embedding_np == np.zeros(1024, dtype=np.float32)).all():
            # 尝试重新生成项目嵌入向量
            if student_api_key:
                try:
                    embedding_provider = create_embedding_provider("siliconflow", student_api_key)
                    re_generated_embedding = await embedding_provider.get_embeddings([p.combined_text])
                    if re_generated_embedding and len(re_generated_embedding) > 0:
                        p_embedding_np = np.array(re_generated_embedding[0], dtype=np.float32)
                except Exception as e:
                    print(f"ERROR_AI_MATCHING: 重新生成项目嵌入向量失败: {e}")

        if p_embedding_np is None or (p_embedding_np == np.zeros(1024, dtype=np.float32)).all():
            continue

        project_embeddings.append(p_embedding_np)
        valid_projects.append(p)

    if not valid_projects:
        return []

    project_embeddings_array = np.array(project_embeddings, dtype=np.float32)

    # 计算余弦相似度
    try:
        cosine_sims = cosine_similarity(student_embedding, project_embeddings_array)[0]
    except Exception as e:
        print(f"ERROR_AI_MATCHING: 计算余弦相似度失败: {e}")
        return []

    # 初步筛选
    initial_candidates_indices = cosine_sims.argsort()[-initial_k:][::-1]
    initial_candidates = [(valid_projects[i], cosine_sims[i]) for i in initial_candidates_indices]

    # 细化匹配分数
    refined_candidates = []
    for project, sim_score in initial_candidates:
        proficiency_score = _calculate_proficiency_match_score(student.skills, project.required_skills)
        time_score = _calculate_time_match_score(student, project)
        location_score = _calculate_location_match_score(student.location, project.location)
        
        combined_score = (sim_score * 0.5) + (proficiency_score * 0.3) + (time_score * 0.1) + (location_score * 0.1)

        refined_candidates.append({
            "project": project,
            "combined_score": combined_score,
            "sim_score": sim_score,
            "proficiency_score": proficiency_score,
            "time_score": time_score,
            "location_score": location_score
        })

    refined_candidates.sort(key=lambda x: x["combined_score"], reverse=True)

    # Reranking
    final_recommendations = []
    reranker_documents = [candidate["project"].combined_text or "" for candidate in refined_candidates[:final_k * 2]]
    reranker_query = student.combined_text or ""

    if reranker_documents and reranker_query and student_api_key:
        try:
            rerank_provider = create_rerank_provider("siliconflow", student_api_key)
            rerank_results = await rerank_provider.rerank(reranker_query, reranker_documents)
            
            # 处理重排结果
            for result in rerank_results[:final_k]:
                original_index = result.get("index", 0)
                if original_index < len(refined_candidates):
                    rec = refined_candidates[original_index]
                    rationale = await _generate_match_rationale_llm(
                        student=student,
                        target_item=rec["project"],
                        sim_score=rec["sim_score"],
                        proficiency_score=rec["proficiency_score"],
                        time_score=rec["time_score"],
                        location_score=rec["location_score"],
                        match_type="student_to_project",
                        llm_api_key=student_api_key
                    )
                    final_recommendations.append(
                        MatchedProject(
                            project_id=rec["project"].id,
                            title=rec["project"].title,
                            description=rec["project"].description,
                            similarity_stage1=rec["combined_score"],
                            relevance_score=result.get("relevance_score", rec["combined_score"]),
                            match_rationale=rationale
                        )
                    )
        except Exception as e:
            print(f"ERROR_AI_MATCHING: Rerank失败: {e}")
    
    # 如果rerank失败，使用原始排序
    if not final_recommendations:
        for rec in refined_candidates[:final_k]:
            rationale = await _generate_match_rationale_llm(
                student=student,
                target_item=rec["project"],
                sim_score=rec["sim_score"],
                proficiency_score=rec["proficiency_score"],
                time_score=rec["time_score"],
                location_score=rec["location_score"],
                match_type="student_to_project",
                llm_api_key=student_api_key
            )
            final_recommendations.append(
                MatchedProject(
                    project_id=rec["project"].id,
                    title=rec["project"].title,
                    description=rec["project"].description,
                    similarity_stage1=rec["combined_score"],
                    relevance_score=rec["combined_score"],
                    match_rationale=rationale
                )
            )

    return final_recommendations


async def find_matching_courses_for_student(
    db: Session, 
    student_id: int,
    initial_k: int = INITIAL_CANDIDATES_K,
    final_k: int = FINAL_TOP_K
) -> List[MatchedCourse]:
    """为指定学生推荐课程"""
    print(f"INFO_AI_MATCHING: 为学生 {student_id} 推荐课程。")
    
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生未找到。")

    # 获取学生的API密钥
    student_api_key = None
    if student.llm_api_type == "siliconflow" and student.llm_api_key_encrypted:
        try:
            student_api_key = decrypt_key(student.llm_api_key_encrypted)
        except Exception as e:
            print(f"ERROR_EMBEDDING_KEY: 解密学生API密钥失败: {e}")

    # 获取学生嵌入向量
    student_embedding_np = _get_safe_embedding_np(student.embedding, "学生", student.id)
    if student_embedding_np is None or (student_embedding_np == np.zeros(1024, dtype=np.float32)).all():
        if student_api_key:
            try:
                embedding_provider = create_embedding_provider("siliconflow", student_api_key)
                re_generated_embedding = await embedding_provider.get_embeddings([student.combined_text])
                if re_generated_embedding and len(re_generated_embedding) > 0:
                    student_embedding_np = np.array(re_generated_embedding[0], dtype=np.float32)
            except Exception as e:
                print(f"ERROR_AI_MATCHING: 重新生成学生嵌入向量失败: {e}")
        
        if student_embedding_np is None or (student_embedding_np == np.zeros(1024, dtype=np.float32)).all():
            return []

    student_embedding = student_embedding_np.reshape(1, -1)

    # 获取所有课程
    all_courses = db.query(Course).all()
    if not all_courses:
        return []

    course_embeddings = []
    valid_courses = []

    for c in all_courses:
        c_embedding_np = _get_safe_embedding_np(c.embedding, "课程", c.id)
        if c_embedding_np is None or (c_embedding_np == np.zeros(1024, dtype=np.float32)).all():
            if student_api_key:
                try:
                    embedding_provider = create_embedding_provider("siliconflow", student_api_key)
                    re_generated_embedding = await embedding_provider.get_embeddings([c.combined_text])
                    if re_generated_embedding and len(re_generated_embedding) > 0:
                        c_embedding_np = np.array(re_generated_embedding[0], dtype=np.float32)
                except Exception as e:
                    print(f"ERROR_AI_MATCHING: 重新生成课程嵌入向量失败: {e}")

        if c_embedding_np is None or (c_embedding_np == np.zeros(1024, dtype=np.float32)).all():
            continue

        course_embeddings.append(c_embedding_np)
        valid_courses.append(c)

    if not valid_courses:
        return []

    course_embeddings_array = np.array(course_embeddings, dtype=np.float32)

    # 计算余弦相似度
    try:
        cosine_sims = cosine_similarity(student_embedding, course_embeddings_array)[0]
    except Exception as e:
        print(f"ERROR_AI_MATCHING: 计算余弦相似度失败: {e}")
        return []

    # 初步筛选
    initial_candidates_indices = cosine_sims.argsort()[-initial_k:][::-1]
    initial_candidates = [(valid_courses[i], cosine_sims[i]) for i in initial_candidates_indices]

    # 细化匹配分数
    refined_candidates = []
    for course, sim_score in initial_candidates:
        proficiency_score = _calculate_proficiency_match_score(student.skills, course.required_skills)
        time_score = _calculate_time_match_score(student, course)
        location_score = _calculate_location_match_score(student.location, course.category)
        
        combined_score = (sim_score * 0.5) + (proficiency_score * 0.3) + (time_score * 0.1) + (location_score * 0.1)

        refined_candidates.append({
            "course": course,
            "combined_score": combined_score,
            "sim_score": sim_score,
            "proficiency_score": proficiency_score,
            "time_score": time_score,
            "location_score": location_score
        })

    refined_candidates.sort(key=lambda x: x["combined_score"], reverse=True)

    # 生成最终推荐
    final_recommendations = []
    for rec in refined_candidates[:final_k]:
        rationale = await _generate_match_rationale_llm(
            student=student,
            target_item=rec["course"],
            sim_score=rec["sim_score"],
            proficiency_score=rec["proficiency_score"],
            time_score=rec["time_score"],
            location_score=rec["location_score"],
            match_type="student_to_course",
            llm_api_key=student_api_key
        )
        final_recommendations.append(
            MatchedCourse(
                course_id=rec["course"].id,
                title=rec["course"].title,
                description=rec["course"].description,
                instructor=rec["course"].instructor,
                category=rec["course"].category,
                cover_image_url=rec["course"].cover_image_url,
                similarity_stage1=rec["combined_score"],
                relevance_score=rec["combined_score"],
                match_rationale=rationale
            )
        )

    return final_recommendations


async def find_matching_students_for_project(
    db: Session, 
    project_id: int,
    initial_k: int = INITIAL_CANDIDATES_K,
    final_k: int = FINAL_TOP_K
) -> List[MatchedStudent]:
    """为指定项目推荐学生"""
    print(f"INFO_AI_MATCHING: 为项目 {project_id} 推荐学生。")
    
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目未找到。")

    # 获取项目创建者的API密钥
    project_api_key = None
    if project.creator_id:
        project_creator = db.query(Student).filter(Student.id == project.creator_id).first()
        if project_creator and project_creator.llm_api_type == "siliconflow" and project_creator.llm_api_key_encrypted:
            try:
                project_api_key = decrypt_key(project_creator.llm_api_key_encrypted)
            except Exception as e:
                print(f"ERROR_EMBEDDING_KEY: 解密项目创建者API密钥失败: {e}")

    # 获取项目嵌入向量
    project_embedding_np = _get_safe_embedding_np(project.embedding, "项目", project.id)
    if project_embedding_np is None or (project_embedding_np == np.zeros(1024, dtype=np.float32)).all():
        if project_api_key:
            try:
                embedding_provider = create_embedding_provider("siliconflow", project_api_key)
                re_generated_embedding = await embedding_provider.get_embeddings([project.combined_text])
                if re_generated_embedding and len(re_generated_embedding) > 0:
                    project_embedding_np = np.array(re_generated_embedding[0], dtype=np.float32)
            except Exception as e:
                print(f"ERROR_AI_MATCHING: 重新生成项目嵌入向量失败: {e}")
        
        if project_embedding_np is None or (project_embedding_np == np.zeros(1024, dtype=np.float32)).all():
            return []

    project_embedding = project_embedding_np.reshape(1, -1)

    # 获取所有学生
    all_students = db.query(Student).all()
    if not all_students:
        return []

    student_embeddings = []
    valid_students = []

    for s in all_students:
        s_embedding_np = _get_safe_embedding_np(s.embedding, "学生", s.id)
        if s_embedding_np is None or (s_embedding_np == np.zeros(1024, dtype=np.float32)).all():
            # 尝试用学生自己的密钥或项目创建者的密钥重新生成
            student_api_key = None
            if s.llm_api_type == "siliconflow" and s.llm_api_key_encrypted:
                try:
                    student_api_key = decrypt_key(s.llm_api_key_encrypted)
                except Exception:
                    pass

            key_to_use = student_api_key or project_api_key
            if key_to_use:
                try:
                    embedding_provider = create_embedding_provider("siliconflow", key_to_use)
                    re_generated_embedding = await embedding_provider.get_embeddings([s.combined_text])
                    if re_generated_embedding and len(re_generated_embedding) > 0:
                        s_embedding_np = np.array(re_generated_embedding[0], dtype=np.float32)
                except Exception as e:
                    print(f"ERROR_AI_MATCHING: 重新生成学生嵌入向量失败: {e}")

        if s_embedding_np is None or (s_embedding_np == np.zeros(1024, dtype=np.float32)).all():
            continue

        student_embeddings.append(s_embedding_np)
        valid_students.append(s)

    if not valid_students:
        return []

    student_embeddings_array = np.array(student_embeddings, dtype=np.float32)

    # 计算余弦相似度
    try:
        cosine_sims = cosine_similarity(project_embedding, student_embeddings_array)[0]
    except Exception as e:
        print(f"ERROR_AI_MATCHING: 计算余弦相似度失败: {e}")
        return []

    # 初步筛选
    initial_candidates_indices = cosine_sims.argsort()[-initial_k:][::-1]
    initial_candidates = [(valid_students[i], cosine_sims[i]) for i in initial_candidates_indices]

    # 细化匹配分数
    refined_candidates = []
    for student, sim_score in initial_candidates:
        proficiency_score = _calculate_proficiency_match_score(student.skills, project.required_skills)
        time_score = _calculate_time_match_score(student, project)
        location_score = _calculate_location_match_score(student.location, project.location)
        
        combined_score = (sim_score * 0.5) + (proficiency_score * 0.3) + (time_score * 0.1) + (location_score * 0.1)

        refined_candidates.append({
            "student": student,
            "combined_score": combined_score,
            "sim_score": sim_score,
            "proficiency_score": proficiency_score,
            "time_score": time_score,
            "location_score": location_score
        })

    refined_candidates.sort(key=lambda x: x["combined_score"], reverse=True)

    # 生成最终推荐
    final_recommendations = []
    for rec in refined_candidates[:final_k]:
        rationale = await _generate_match_rationale_llm(
            student=rec["student"],
            target_item=project,
            sim_score=rec["sim_score"],
            proficiency_score=rec["proficiency_score"],
            time_score=rec["time_score"],
            location_score=rec["location_score"],
            match_type="project_to_student",
            llm_api_key=project_api_key
        )
        final_recommendations.append(
            MatchedStudent(
                student_id=rec["student"].id,
                name=rec["student"].name,
                major=rec["student"].major,
                skills=rec["student"].skills,
                similarity_stage1=rec["combined_score"],
                relevance_score=rec["combined_score"],
                match_rationale=rationale
            )
        )

    return final_recommendations
