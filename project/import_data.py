# project/import_data.py
import pandas as pd
import numpy as np
import os
import requests
import json
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import text

# 导入数据库和模型定义
from database import SessionLocal, engine, init_db, Base
from models import Student, Project

# --- 1. 配置数据文件路径 ---
STUDENTS_CSV_PATH = 'students.csv'
PROJECTS_CSV_PATH = 'projects' # 注意：这里是文件夹名，不是文件名。 projects.csv，如果它还是文件，请确保路径正确

PROJECTS_CSV_PATH = 'projects.csv'


# --- 2. 硅基流动API配置 (确保 .env 文件已正确配置) ---
# 从环境变量加载API密钥
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY")

if not SILICONFLOW_API_KEY or SILICONFLOW_API_KEY == "sk-YOUR_SILICONFLOW_API_KEY_HERE":
    raise ValueError("SILICONFLOW_API_KEY 环境变量未设置或为默认值。请在 .env 文件中提供你的API密钥。")

EMBEDDING_API_URL = "https://api.siliconflow.cn/v1/embeddings"
EMBEDDING_MODEL_NAME = "BAAI/bge-m3"

# --- 3. API 调用函数 ---
def get_embeddings_from_api(texts: List[str]) -> List[List[float]]:
    """
    通过硅基流动API获取文本嵌入。
    """
    headers = {
        "Authorization": f"Bearer {SILICONFLOW_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": EMBEDDING_MODEL_NAME,
        "input": texts
    }
    try:
        response = requests.post(EMBEDDING_API_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        embeddings = [item['embedding'] for item in data['data']]
        return embeddings
    except requests.exceptions.RequestException as e:
        print(f"API请求错误 (Embedding): {e}")
        print(f"响应内容: {response.text if 'response' in locals() else '无'}")
        raise # 重新抛出异常，停止执行
    except KeyError as e:
        print(f"API响应格式错误 (Embedding): {e}. 响应: {data}")
        raise # 重新抛出异常，停止执行

# --- 4. 数据预处理函数（与 ai_core.py 相同） ---
def preprocess_student_data(df: pd.DataFrame) -> pd.DataFrame:
    """为学生数据生成 combined_text。"""
    df['combined_text'] = df['major'].fillna('') + ". " + \
                          df['skills'].fillna('') + ". " + \
                          df['interests'].fillna('') + ". " + \
                          df['bio'].fillna('') + ". " + \
                          df['awards_competitions'].fillna('') + ". " + \
                          df['academic_achievements'].fillna('') + ". " + \
                          df['soft_skills'].fillna('') + ". " + \
                          df['preferred_role'].fillna('') + ". " + \
                          df['availability'].fillna('') + ". " + \
                          df['portfolio_link'].fillna('')
    return df

def preprocess_project_data(df: pd.DataFrame) -> pd.DataFrame:
    """为项目数据生成 combined_text。"""
    df['combined_text'] = df['title'].fillna('') + ". " + \
                          df['description'].fillna('') + ". " + \
                          df['required_skills'].fillna('') + ". " + \
                          df['keywords'].fillna('') + ". " + \
                          df['project_type'].fillna('') + ". " + \
                          df['expected_deliverables'].fillna('') + ". " + \
                          df['contact_person_info'].fillna('') + ". " + \
                          df['learning_outcomes'].fillna('') + ". " + \
                          df['team_size_preference'].fillna('') + ". " + \
                          df['project_status'].fillna('')
    return df

# --- 5. 数据导入函数 ---
def import_students_to_db(db: Session, students_df: pd.DataFrame):
    """将学生数据（含嵌入）导入数据库。"""
    print("\n开始导入学生数据到数据库...")
    texts = students_df['combined_text'].tolist()
    embeddings = get_embeddings_from_api(texts) # 获取所有嵌入

    for i, row in students_df.iterrows():
        # 检查是否已存在，如果存在则跳过或更新 (这里选择跳过，保证幂等性)
        if db.query(Student).filter(Student.id == int(row['id'])).first():
            print(f"学生ID {int(row['id'])} 已存在，跳过导入。")
            continue

        student = Student(
            id=int(row['id']),
            name=row['name'],
            major=row['major'],
            skills=row['skills'],
            interests=row['interests'],
            bio=row['bio'],
            awards_competitions=row.get('awards_competitions', ''), # 使用get防止列不存在报错
            academic_achievements=row.get('academic_achievements', ''),
            soft_skills=row.get('soft_skills', ''),
            portfolio_link=row.get('portfolio_link', ''),
            preferred_role=row.get('preferred_role', ''),
            availability=row.get('availability', ''),
            combined_text=row['combined_text'],
            embedding=embeddings[i] # 对应行获取嵌入
        )
        db.add(student)
        print(f"添加学生: {student.name}")
    db.commit()
    print("学生数据导入完成。")

def import_projects_to_db(db: Session, projects_df: pd.DataFrame):
    """将项目数据（含嵌入）导入数据库。"""
    print("\n开始导入项目数据到数据库...")
    texts = projects_df['combined_text'].tolist()
    embeddings = get_embeddings_from_api(texts) # 获取所有嵌入

    for i, row in projects_df.iterrows():
        # 检查是否已存在
        if db.query(Project).filter(Project.id == int(row['id'])).first():
            print(f"项目ID {int(row['id'])} 已存在，跳过导入。")
            continue

        project = Project(
            id=int(row['id']),
            title=row['title'],
            description=row['description'],
            required_skills=row['required_skills'],
            keywords=row['keywords'],
            project_type=row.get('project_type', ''),
            expected_deliverables=row.get('expected_deliverables', ''),
            contact_person_info=row.get('contact_person_info', ''),
            learning_outcomes=row.get('learning_outcomes', ''),
            team_size_preference=row.get('team_size_preference', ''),
            project_status=row.get('project_status', ''),
            combined_text=row['combined_text'],
            embedding=embeddings[i] # 对应行获取嵌入
        )
        db.add(project)
        print(f"添加项目: {project.title}")
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

    # 确保ID列是整数类型
    students_df['id'] = students_df['id'].astype(int)
    projects_df['id'] = projects_df['id'].astype(int)

    # 3. 预处理数据
    students_df = preprocess_student_data(students_df)
    projects_df = preprocess_project_data(projects_df)

    # 4. 获取数据库会话并导入数据
    db_session = SessionLocal()
    try:
        import_students_to_db(db_session, students_df)
        import_projects_to_db(db_session, projects_df)
    except Exception as e:
        db_session.rollback() # 发生错误时回滚事务
        print(f"数据导入过程中发生错误，事务已回滚: {e}")
    finally:
        db_session.close() # 确保关闭会话

    print("\n--- 数据导入流程结束 ---")

