# project/import_data.py
import pandas as pd
import numpy as np
import os
import httpx
import json
import asyncio
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
import re
from datetime import datetime, timedelta  # 确保 datetime 和 timedelta 导入

# 导入数据库和模型定义
from database import SessionLocal, engine, init_db, Base
from models import Student, Project  # 导入 Student 和 Project 模型

# --- 1. 配置数据文件路径 ---
STUDENTS_CSV_PATH = 'export_tools/data/students.csv'  # 修正路径
PROJECTS_CSV_PATH = 'export_tools/data/projects.csv'  # 修正路径

# --- 2. 硅基流动API配置（固定端点和模型名称） ---
# 此脚本不再使用环境变量中的SILICONFLOW_API_KEY，而是明确依赖对get_embeddings_from_api_async的api_key参数传递。
# 这样，只有当API Key被显式传递（例如，如果将来需要一个特殊的导入密钥），才会进行实际API调用。
# 否则，它将依赖ai_core内部的占位符逻辑。
# **<<<<< MODIFICATION: 移除不必要的全局 API KEY 读取 >>>>>**
# SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY") # 移除此行
# if not SILICONFLOW_API_KEY or SILICONFLOW_API_KEY == "sk-YOUR_SILICONFLOW_API_KEY_HERE": # 移除此行
#     print("警告：SILICONFLOW_API_KEY 环境变量未设置或为默认值。AI Embedding/Rerank功能将受限。") # 移除此行
#     SILICONFLOW_API_KEY = "dummy_key_for_testing_without_api" # 移除此行

# 这些是API的固定端点和模型名称，需要保留
EMBEDDING_API_URL = "https://api.siliconflow.cn/v1/embeddings"
EMBEDDING_MODEL_NAME = "BAAI/bge-m3"


# --- 3. API 调用函数 ---
# **<<<<< MODIFICATION: get_embeddings_from_api_async 接受 api_key 参数 >>>>>**
async def get_embeddings_from_api_async(texts: List[str], api_key: Optional[str] = None) -> List[List[float]]:
    """
    通过硅基流动API异步获取文本嵌入。
    此版本明确接受api_key参数。如果api_key为None或虚拟key，则返回零向量。
    """
    non_empty_texts = [t for t in texts if t and t.strip()]
    if not non_empty_texts:
        print("警告：没有有效的文本可以发送给Embedding API。")
        return [np.zeros(1024).tolist()] * len(texts)

    # **<<<<< MODIFICATION: 使用传入的 api_key 进行检查 >>>>>**
    if not api_key or api_key == "dummy_key_for_testing_without_api":
        print("API密钥未配置或为虚拟密钥，无法获取嵌入。将返回零向量作为占位符。")
        return [np.zeros(1024).tolist()] * len(texts)

    headers = {
        "Authorization": f"Bearer {api_key}", # <-- 使用传入的 api_key
        "Content-Type": "application/json",
    }
    payload = {
        "model": EMBEDDING_MODEL_NAME,
        "input": non_empty_texts
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(EMBEDDING_API_URL, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            embeddings_result = [item['embedding'] for item in response.json()['data']]

            full_embeddings = []
            result_idx = 0
            for text_orig in texts:
                if text_orig and text_orig.strip():
                    if result_idx < len(embeddings_result):
                        full_embeddings.append(embeddings_result[result_idx])
                        result_idx += 1
                    else:
                        full_embeddings.append(np.zeros(1024).tolist())
                else:
                    full_embeddings.append(np.zeros(1024).tolist())
            return full_embeddings

    except httpx.RequestError as e:
        print(f"API请求错误 (Embedding): {e}")
        print(f"响应内容: {getattr(e, 'response', None).text if hasattr(e, 'response') and e.response else '无'}")
        return [np.zeros(1024).tolist()] * len(texts)
    except KeyError as e:
        print(f"API响应格式错误 (Embedding): {e}. 响应: {response.json() if 'response' in locals() and hasattr(response, 'json') else '无法获取响应数据'}")
        return [np.zeros(1024).tolist()] * len(texts) # 确保返回列表以匹配预期
    except json.JSONDecodeError as e:
        print(f"API响应JSON解码错误 (Embedding): {e}. 响应: {response.text if 'response' in locals() and hasattr(response, 'text') else '无响应内容可获取'}")
        return [np.zeros(1024).tolist()] * len(texts)


# --- 4. 数据预处理函数 ---
def preprocess_student_data(df: pd.DataFrame) -> pd.DataFrame:
    """为学生数据生成 combined_text，并处理 skills 字段和确保 username 唯一。"""

    for col_name in ['username', 'email', 'phone_number', 'school', 'password_hash',
                     'major', 'skills', 'interests', 'bio', 'awards_competitions',
                     'academic_achievements', 'soft_skills', 'portfolio_link',
                     'preferred_role', 'availability', 'location']:
        if col_name not in df.columns:
            df[col_name] = np.nan

    default_skill_level = "初窥门径"
    valid_skill_levels = ["初窥门径", "登堂入室", "融会贯通", "炉火纯青"]

    for index, row in df.iterrows():
        user_id = int(row['id'])

        # **<<<<< MODIFICATION: 为确保唯一性，这些字段即使在 CSV 里为空，也会生成唯一值 >>>>>**
        # 以前在 main.py 的 register 中处理过 username 生成，这里也需要保证唯一。
        # 对于 email, phone_number, school, password_hash 这些唯一或非空的字段，
        # 如果 CSV 中为空，我们也生成一个唯一的占位符，避免导入时报错
        if pd.isna(row.get('email')) or not str(row.get('email')).strip():
            df.at[index, 'email'] = f"user{user_id:04d}@example.com" # 确保邮箱唯一且有格式

        if pd.isna(row.get('phone_number')) or not str(row.get('phone_number')).strip():
            df.at[index, 'phone_number'] = f"139{user_id:08d}" # 生成一个唯一的11位手机号

        if pd.isna(row.get('school')) or not str(row.get('school')).strip():
            df.at[index, 'school'] = f"示例大学_{user_id}"

        if pd.isna(row.get('password_hash')) or not str(row.get('password_hash')).strip():
            # 这里简单用 hash_id_placeholder，实际中应使用加密过的默认密码
            df.at[index, 'password_hash'] = f"hash_{user_id}_placeholder"

        skills_raw_data = row['skills']
        processed_skills_for_cell = []

        if pd.notna(skills_raw_data) and str(skills_raw_data).strip():
            try:
                parsed_content = json.loads(str(skills_raw_data))

                if isinstance(parsed_content, list):
                    for item in parsed_content:
                        if isinstance(item, dict) and "name" in item:
                            level = item.get("level", default_skill_level)
                            processed_skills_for_cell.append({"name": item["name"],
                                                              "level": level if level in valid_skill_levels else default_skill_level})
                        elif isinstance(item, str) and item.strip():
                            processed_skills_for_cell.append({"name": item.strip(), "level": default_skill_level})
                elif isinstance(parsed_content, dict) and "name" in parsed_content:
                    level = parsed_content.get("level", default_skill_level)
                    processed_skills_for_cell.append({"name": parsed_content["name"],
                                                      "level": level if level in valid_skill_levels else default_skill_level})
                else:
                    skill_names = [s.strip() for s in str(skills_raw_data).split(',') if s.strip()]
                    processed_skills_for_cell.extend(
                        [{"name": name, "level": default_skill_level} for name in skill_names])
            except json.JSONDecodeError:
                skill_names = [s.strip() for s in str(skills_raw_data).split(',') if s.strip()]
                processed_skills_for_cell.extend([{"name": name, "level": default_skill_level} for name in skill_names])
            except Exception as e:
                print(f"WARNING_PREPROCESS: Error processing skills for student {row.get('id', index)}: {e}")
                processed_skills_for_cell = []

        df.at[index, 'skills'] = json.dumps(processed_skills_for_cell, ensure_ascii=False)

        # 确保 username 在导入时绝对唯一
        original_username = row['username'] if pd.notna(row['username']) and str(row['username']).strip() else "新用户"
        df.at[index, 'username'] = f"{original_username}_{int(row['id'])}"

        def _get_string_value(val):
            if pd.isna(val) or val is None or (isinstance(val, str) and val.strip() == ""):
                return ''
            return str(val).strip()

        skills_text_for_combined = ", ".join(
            [s.get("name", "") for s in processed_skills_for_cell if isinstance(s, dict) and s.get("name")])

        df.at[index, 'combined_text'] = ". ".join(filter(None, [
            _get_string_value(row.get('major')),
            skills_text_for_combined,
            _get_string_value(row.get('interests')),
            _get_string_value(row.get('bio')),
            _get_string_value(row.get('awards_competitions')),
            _get_string_value(row.get('academic_achievements')),
            _get_string_value(row.get('soft_skills')),
            _get_string_value(row.get('portfolio_link')),
            _get_string_value(row.get('preferred_role')),
            _get_string_value(row.get('availability')),
            _get_string_value(row.get('location'))
        ])).strip()

        if not df.at[index, 'combined_text']:
            df.at[index, 'combined_text'] = ""

    return df


def preprocess_project_data(df: pd.DataFrame) -> pd.DataFrame:
    """为项目数据生成 combined_text，并处理 required_skills/roles 字段。"""

    for col_name in ['creator_id', 'description', 'keywords', 'project_type',
                     'expected_deliverables', 'contact_person_info', 'learning_outcomes',
                     'team_size_preference', 'project_status', 'required_skills',
                     'required_roles', 'start_date', 'end_date', 'estimated_weekly_hours', 'location']:
        if col_name not in df.columns:
            df[col_name] = np.nan

    default_skill_level = "初窥门径"
    valid_skill_levels = ["初窥门径", "登堂入室", "融会贯通", "炉火纯青"]

    for index, row in df.iterrows():
        required_skills_raw_data = row['required_skills']
        processed_required_skills_for_cell = []

        if pd.notna(required_skills_raw_data) and str(required_skills_raw_data).strip():
            try:
                parsed_content = json.loads(str(required_skills_raw_data))

                if isinstance(parsed_content, list):
                    for item in parsed_content:
                        if isinstance(item, dict) and "name" in item:
                            level = item.get("level", default_skill_level)
                            processed_required_skills_for_cell.append({"name": item["name"],
                                                                       "level": level if level in valid_skill_levels else default_skill_level})
                        elif isinstance(item, str) and item.strip():
                            processed_required_skills_for_cell.append(
                                {"name": item.strip(), "level": default_skill_level})
                elif isinstance(parsed_content, dict) and "name" in parsed_content:
                    level = parsed_content.get("level", default_skill_level)
                    processed_required_skills_for_cell.append({"name": parsed_content["name"],
                                                               "level": level if level in valid_skill_levels else default_skill_level})
                else:
                    skill_names = [s.strip() for s in str(required_skills_raw_data).split(',') if s.strip()]
                    processed_required_skills_for_cell.extend(
                        [{"name": name, "level": default_skill_level} for name in skill_names])
            except json.JSONDecodeError:
                skill_names = [s.strip() for s in str(required_skills_raw_data).split(',') if s.strip()]
                processed_required_skills_for_cell.extend(
                    [{"name": name, "level": default_skill_level} for name in skill_names])
            except Exception as e:
                print(f"WARNING_PREPROCESS: Error processing required_skills for project {row.get('id', index)}: {e}")
                processed_required_skills_for_cell = []

        df.at[index, 'required_skills'] = json.dumps(processed_required_skills_for_cell, ensure_ascii=False)

        required_roles_raw_data = row['required_roles']
        processed_required_roles_for_cell = []
        if pd.notna(required_roles_raw_data) and str(required_roles_raw_data).strip():
            try:
                parsed_content = json.loads(str(required_roles_raw_data))
                if isinstance(parsed_content, list) and all(isinstance(r, str) for r in parsed_content):
                    processed_required_roles_for_cell.extend([r.strip() for r in parsed_content if r.strip()])
                elif isinstance(parsed_content, str) and parsed_content.strip():
                    processed_required_roles_for_cell.append(parsed_content.strip())
                else:  # Fallback
                    role_names = [r.strip() for r in str(required_roles_raw_data).split(',') if r.strip()]
                    processed_required_roles_for_cell.extend(role_names)
            except json.JSONDecodeError:  # 如果不是有效的JSON字符串，按逗号分隔
                role_names = [r.strip() for r in str(required_roles_raw_data).split(',') if r.strip()]
                processed_required_roles_for_cell.extend(role_names)
            except Exception as e:
                print(f"WARNING_PREPROCESS: Error processing required_roles for project {row.get('id', index)}: {e}")
                processed_required_roles_for_cell = []

        df.at[index, 'required_roles'] = json.dumps(processed_required_roles_for_cell, ensure_ascii=False)


        def _get_string_value(val):
            if pd.isna(val) or val is None or (isinstance(val, str) and val.strip() == ""):
                return ''
            if isinstance(val, (datetime, pd.Timestamp)):
                return val.strftime("%Y-%m-%d")
            if 'estimated_weekly_hours' in row and val == row['estimated_weekly_hours'] and isinstance(val,
                                                                                                       (int, float)):
                return f"{int(val)}小时" if val == int(val) else f"{val}小时"
            return str(val).strip()

        skills_text_for_combined = ", ".join(
            [s.get("name", "") for s in processed_required_skills_for_cell if isinstance(s, dict) and s.get("name")])

        roles_text_for_combined = ", ".join(
            [r for r in processed_required_roles_for_cell if isinstance(r, str) and r.strip()])

        df.at[index, 'combined_text'] = ". ".join(filter(None, [
            _get_string_value(row.get('title')),
            _get_string_value(row.get('description')),
            skills_text_for_combined,
            roles_text_for_combined,
            _get_string_value(row.get('keywords')),
            _get_string_value(row.get('project_type')),
            _get_string_value(row.get('expected_deliverables')),
            _get_string_value(row.get('contact_person_info')),
            _get_string_value(row.get('learning_outcomes')),
            _get_string_value(row.get('team_size_preference')),
            _get_string_value(row.get('project_status')),
            _get_string_value(row.get('start_date')),
            _get_string_value(row.get('end_date')),
            _get_string_value(row.get('estimated_weekly_hours')),
            _get_string_value(row.get('location'))
        ])).strip()

        if not df.at[index, 'combined_text']:
            df.at[index, 'combined_text'] = ""

    return df


# --- 5. 数据导入函数 ---
def import_students_to_db(db: Session, students_df: pd.DataFrame):
    """将学生数据（仅数据，不生成嵌入）导入数据库。"""
    print("\n开始导入学生数据到数据库...")
    # **<<<<< MODIFICATION: 在导入脚本中，不再尝试调用外部API生成嵌入 >>>>>**
    # 嵌入将由用户在配置API密钥后，通过更新个人资料或在推荐时按需生成
    # texts = students_df['combined_text'].tolist() # 移除此行
    # embeddings = asyncio.run(get_embeddings_from_api_async(texts)) # 移除此行

    for i, row in students_df.iterrows():
        skills_data = row['skills']
        if isinstance(skills_data, str):
            try:
                skills_data = json.loads(skills_data)
            except json.JSONDecodeError:
                skills_data = []
        elif pd.isna(skills_data):
            skills_data = []

        student = Student(
            id=int(row['id']),
            name=row['name'],
            major=row['major'],
            username=row['username'],
            skills=skills_data,
            interests=row['interests'],
            bio=row['bio'],
            awards_competitions=row['awards_competitions'],
            academic_achievements=row['academic_achievements'],
            soft_skills=row['soft_skills'],
            portfolio_link=row['portfolio_link'],
            preferred_role=row['preferred_role'],
            availability=row['availability'],
            location=row['location'],
            email=row['email'],
            phone_number=row['phone_number'],
            school=row['school'],
            password_hash=row['password_hash'],

            combined_text=row['combined_text'],
            embedding=np.zeros(1024).tolist(), # **<<<<< 新增: 默认生成零向量 >>>>>**
            llm_api_type=None, # 导入时 LLM API 类型默认为 None
            llm_api_key_encrypted=None, # 导入时 API Key 默认为 None
            llm_api_base_url=None,
            llm_model_id=None
        )
        if pd.isna(getattr(student, 'location')):
            setattr(student, 'location', None)

        db.add(student)
        print(f"添加学生: {student.name} (用户名: {student.username})")
    db.commit()
    print("学生数据导入完成。")


def import_projects_to_db(db: Session, projects_df: pd.DataFrame):
    """将项目数据（仅数据，不生成嵌入）导入数据库。"""
    print("\n开始导入项目数据到数据库...")
    # **<<<<< MODIFICATION: 在导入脚本中，不再尝试调用外部API生成嵌入 >>>>>**
    # texts = projects_df['combined_text'].tolist() # 移除此行
    # embeddings = asyncio.run(get_embeddings_from_api_async(texts)) # 移除此行

    for i, row in projects_df.iterrows():
        creator_id_for_db = None
        if pd.notna(row['creator_id']):
            creator_id_for_db = int(row['creator_id'])
        else:
            existing_student_ids = db.query(Student.id).all()
            if existing_student_ids:
                random_creator_id = np.random.choice([s.id for s in existing_student_ids])
                creator_id_for_db = int(random_creator_id)
            else:
                print("警告：没有可用的学生ID来分配项目创建者，请确保学生数据已经导入。")
                raise ValueError("无法为项目分配创建者，因为数据库中没有学生记录。请先导入学生数据或手动指定 creator_id。")

        start_date_val = row['start_date'] if pd.notna(row['start_date']) else None
        end_date_val = row['end_date'] if pd.notna(row['end_date']) else None
        estimated_weekly_hours_val = row['estimated_weekly_hours'] if pd.notna(row['estimated_weekly_hours']) else None

        required_skills_data = row['required_skills']
        if isinstance(required_skills_data, str):
            try:
                required_skills_data = json.loads(required_skills_data)
            except json.JSONDecodeError:
                required_skills_data = []
        elif pd.isna(required_skills_data):
            required_skills_data = []

        required_roles_data = row['required_roles']
        if isinstance(required_roles_data, str):
            try:
                required_roles_data = json.loads(required_roles_data)
            except json.JSONDecodeError:
                required_roles_data = []
        elif pd.isna(required_roles_data):
            required_roles_data = []

        project = Project(
            id=int(row['id']),
            title=row['title'],
            description=row['description'],
            required_skills=required_skills_data,
            required_roles=required_roles_data,
            keywords=row['keywords'],
            project_type=row['project_type'],
            expected_deliverables=row['expected_deliverables'],
            contact_person_info=row['contact_person_info'],
            learning_outcomes=row['learning_outcomes'],
            team_size_preference=row['team_size_preference'],
            project_status=row['project_status'],
            start_date=start_date_val,
            end_date=end_date_val,
            estimated_weekly_hours=estimated_weekly_hours_val,
            location=row['location'],
            creator_id=creator_id_for_db,
            combined_text=row['combined_text'],
            embedding=np.zeros(1024).tolist() # **<<<<< 新增: 默认生成零向量 >>>>>**
        )
        if pd.isna(getattr(project, 'location')):
            setattr(project, 'location', None)

        db.add(project)
        print(f"添加项目: {project.title} (创建者ID: {project.creator_id})")
    db.commit()
    print("项目数据导入完成。")


# --- 主执行流程 ---
if __name__ == "__main__":
    print("--- 开始数据导入流程 ---")

    # 1. 初始化数据库表（如果尚未创建）
    init_db()

    # 2. 从CSV加载数据
    try:
        students_df = pd.read_csv(STUDENTS_CSV_PATH)
        projects_df = pd.read_csv(PROJECTS_CSV_PATH)
        print("\nCSV数据加载成功！")
    except FileNotFoundError:
        print(f"错误：请确保 '{STUDENTS_CSV_PATH}' 和 '{PROJECTS_CSV_PATH}' 文件存在于当前目录下。")
        exit()
    except Exception as e:
        print(f"错误：加载CSV文件或处理CSV列时发生问题: {e}. 请检查您的CSV文件内容和列名。")
        exit()

    # 确保ID列是整数类型
    students_df['id'] = students_df['id'].astype(int)
    projects_df['id'] = projects_df['id'].astype(int)

    # 将日期时间列转换为 datetime 对象
    for col in ['start_date', 'end_date']:
        if col in projects_df.columns:
            projects_df[col] = pd.to_datetime(projects_df[col], errors='coerce')

    # 将新的 'location' 列转换为字符串类型，缺失值转换为None (以便后续存入数据库)
    if 'location' in students_df.columns:
        students_df['location'] = students_df['location'].astype(str).replace('nan', None)
    if 'location' in projects_df.columns:
        projects_df['location'] = projects_df['location'].astype(str).replace('nan', None)

    # 3. 预处理数据
    students_df = preprocess_student_data(students_df)
    projects_df = preprocess_project_data(projects_df)

    # 4. 获取数据库会话并导入数据
    db_session = SessionLocal()
    try:
        import_students_to_db(db_session, students_df)
        import_projects_to_db(db_session, projects_df)
    except Exception as e:
        db_session.rollback()
        print(f"\n数据导入过程中发生错误，事务已回滚: {e}")
        import traceback

        traceback.print_exc()
    finally:
        db_session.close()

    print("\n--- 数据导入流程结束 ---")
