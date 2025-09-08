# project/import_data.py
import pandas as pd
import numpy as np
import os, httpx, json, asyncio, re
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timedelta
from database import SessionLocal, engine, init_db, Base
from models import User, Project

# --- 1. 配置常量 ---
# 获取脚本所在目录，然后构建正确的数据文件路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STUDENTS_CSV_PATH = os.path.join(SCRIPT_DIR, 'data', 'students.csv')
PROJECTS_CSV_PATH = os.path.join(SCRIPT_DIR, 'data', 'projects.csv')

# 配置常量
DEFAULT_EMBEDDING_DIM = 1024
DEFAULT_SKILL_LEVEL = "初窥门径"
VALID_SKILL_LEVELS = ["初窥门径", "登堂入室", "融会贯通", "炉火纯青"]


# --- 3. 通用工具函数 ---
def get_string_value(val):
    """统一的字符串值处理函数"""
    if pd.isna(val) or val is None or (isinstance(val, str) and val.strip() == ""):
        return ''
    if isinstance(val, (datetime, pd.Timestamp)):
        return val.strftime("%Y-%m-%d")
    if isinstance(val, (int, float)):
        return f"{int(val)}小时" if val == int(val) else f"{val}小时"
    return str(val).strip()


def parse_json_field(raw_data, field_name="field", default_value=None):
    """统一的JSON字段解析函数"""
    if default_value is None:
        default_value = []
        
    if pd.isna(raw_data) or not str(raw_data).strip():
        return default_value
        
    try:
        return json.loads(str(raw_data))
    except json.JSONDecodeError:
        print(f"Warning: Failed to parse JSON for {field_name}, treating as string")
        return str(raw_data).strip()
    except Exception as e:
        print(f"Error processing {field_name}: {e}")
        return default_value


def process_skills_data(raw_data, record_id=None):
    """统一的技能数据处理函数"""
    processed_skills = []
    
    if pd.isna(raw_data) or not str(raw_data).strip():
        return processed_skills
        
    try:
        parsed_content = json.loads(str(raw_data))
        
        if isinstance(parsed_content, list):
            for item in parsed_content:
                if isinstance(item, dict) and "name" in item:
                    level = item.get("level", DEFAULT_SKILL_LEVEL)
                    processed_skills.append({
                        "name": item["name"],
                        "level": level if level in VALID_SKILL_LEVELS else DEFAULT_SKILL_LEVEL
                    })
                elif isinstance(item, str) and item.strip():
                    processed_skills.append({
                        "name": item.strip(), 
                        "level": DEFAULT_SKILL_LEVEL
                    })
        elif isinstance(parsed_content, dict) and "name" in parsed_content:
            level = parsed_content.get("level", DEFAULT_SKILL_LEVEL)
            processed_skills.append({
                "name": parsed_content["name"],
                "level": level if level in VALID_SKILL_LEVELS else DEFAULT_SKILL_LEVEL
            })
        else:
            # 如果解析的内容不是预期格式，按逗号分割处理
            skill_names = [s.strip() for s in str(raw_data).split(',') if s.strip()]
            processed_skills.extend([
                {"name": name, "level": DEFAULT_SKILL_LEVEL} for name in skill_names
            ])
    except json.JSONDecodeError:
        # JSON解析失败，按逗号分割处理
        skill_names = [s.strip() for s in str(raw_data).split(',') if s.strip()]
        processed_skills.extend([
            {"name": name, "level": DEFAULT_SKILL_LEVEL} for name in skill_names
        ])
    except Exception as e:
        print(f"Warning: Error processing skills for record {record_id}: {e}")
        processed_skills = []
        
    return processed_skills


def process_roles_data(raw_data, record_id=None):
    """统一的角色数据处理函数"""
    processed_roles = []
    
    if pd.isna(raw_data) or not str(raw_data).strip():
        return processed_roles
        
    try:
        parsed_content = json.loads(str(raw_data))
        if isinstance(parsed_content, list) and all(isinstance(r, str) for r in parsed_content):
            processed_roles.extend([r.strip() for r in parsed_content if r.strip()])
        elif isinstance(parsed_content, str) and parsed_content.strip():
            processed_roles.append(parsed_content.strip())
        else:
            role_names = [r.strip() for r in str(raw_data).split(',') if r.strip()]
            processed_roles.extend(role_names)
    except json.JSONDecodeError:
        role_names = [r.strip() for r in str(raw_data).split(',') if r.strip()]
        processed_roles.extend(role_names)
    except Exception as e:
        print(f"Warning: Error processing roles for record {record_id}: {e}")
        processed_roles = []
        
    return processed_roles
# --- 4. 数据预处理函数 ---
def preprocess_student_data(df: pd.DataFrame) -> pd.DataFrame:
    """为学生数据生成 combined_text，并处理 skills 字段和确保 username 唯一。"""
    
    # 确保所有必要的列存在
    required_cols = ['username', 'email', 'phone_number', 'school', 'password_hash',
                     'major', 'skills', 'interests', 'bio', 'awards_competitions',
                     'academic_achievements', 'soft_skills', 'portfolio_link',
                     'preferred_role', 'availability', 'location']
    
    for col_name in required_cols:
        if col_name not in df.columns:
            df[col_name] = np.nan

    # 批量处理数据，避免使用iterrows
    df_copy = df.copy()
    
    # 批量生成唯一标识符
    user_ids = df_copy['id'].astype(int)
    
    # 处理邮箱字段
    mask_email = df_copy['email'].isna() | (df_copy['email'].astype(str).str.strip() == '')
    df_copy.loc[mask_email, 'email'] = user_ids[mask_email].apply(lambda x: f"user{x:04d}@example.com")
    
    # 处理手机号字段
    mask_phone = df_copy['phone_number'].isna() | (df_copy['phone_number'].astype(str).str.strip() == '')
    df_copy.loc[mask_phone, 'phone_number'] = user_ids[mask_phone].apply(lambda x: f"139{x:08d}")
    
    # 处理学校字段
    mask_school = df_copy['school'].isna() | (df_copy['school'].astype(str).str.strip() == '')
    df_copy.loc[mask_school, 'school'] = user_ids[mask_school].apply(lambda x: f"示例大学_{x}")
    
    # 处理密码哈希字段
    mask_password = df_copy['password_hash'].isna() | (df_copy['password_hash'].astype(str).str.strip() == '')
    df_copy.loc[mask_password, 'password_hash'] = user_ids[mask_password].apply(lambda x: f"hash_{x}_placeholder")
    
    # 处理用户名字段，确保唯一性
    original_usernames = df_copy['username'].fillna("新用户").astype(str)
    df_copy['username'] = [f"{name.strip()}_{uid}" for name, uid in zip(original_usernames, user_ids)]
    
    # 处理技能字段和生成combined_text
    processed_data = []
    for index, row in df_copy.iterrows():
        user_id = int(row['id'])
        
        # 处理技能数据
        processed_skills = process_skills_data(row['skills'], user_id)
        df_copy.at[index, 'skills'] = json.dumps(processed_skills, ensure_ascii=False)
        
        # 生成combined_text
        skills_text = ", ".join([s.get("name", "") for s in processed_skills if isinstance(s, dict) and s.get("name")])
        
        combined_parts = [
            get_string_value(row.get('major')),
            skills_text,
            get_string_value(row.get('interests')),
            get_string_value(row.get('bio')),
            get_string_value(row.get('awards_competitions')),
            get_string_value(row.get('academic_achievements')),
            get_string_value(row.get('soft_skills')),
            get_string_value(row.get('portfolio_link')),
            get_string_value(row.get('preferred_role')),
            get_string_value(row.get('availability')),
            get_string_value(row.get('location'))
        ]
        
        df_copy.at[index, 'combined_text'] = ". ".join(filter(None, combined_parts)).strip()
        if not df_copy.at[index, 'combined_text']:
            df_copy.at[index, 'combined_text'] = ""

    return df_copy


def preprocess_project_data(df: pd.DataFrame) -> pd.DataFrame:
    """为项目数据生成 combined_text，并处理 required_skills/roles 字段。"""
    
    # 确保所有必要的列存在
    required_cols = ['creator_id', 'description', 'keywords', 'project_type',
                     'expected_deliverables', 'contact_person_info', 'learning_outcomes',
                     'team_size_preference', 'project_status', 'required_skills',
                     'required_roles', 'start_date', 'end_date', 'estimated_weekly_hours', 'location']
    
    for col_name in required_cols:
        if col_name not in df.columns:
            df[col_name] = np.nan

    # 创建副本避免修改原数据
    df_copy = df.copy()
    
    # 批量处理每一行
    for index, row in df_copy.iterrows():
        project_id = int(row['id'])
        
        # 处理必需技能数据
        processed_skills = process_skills_data(row['required_skills'], project_id)
        df_copy.at[index, 'required_skills'] = json.dumps(processed_skills, ensure_ascii=False)
        
        # 处理必需角色数据
        processed_roles = process_roles_data(row['required_roles'], project_id)
        df_copy.at[index, 'required_roles'] = json.dumps(processed_roles, ensure_ascii=False)
        
        # 生成combined_text
        skills_text = ", ".join([s.get("name", "") for s in processed_skills if isinstance(s, dict) and s.get("name")])
        roles_text = ", ".join([r for r in processed_roles if isinstance(r, str) and r.strip()])
        
        combined_parts = [
            get_string_value(row.get('title')),
            get_string_value(row.get('description')),
            skills_text,
            roles_text,
            get_string_value(row.get('keywords')),
            get_string_value(row.get('project_type')),
            get_string_value(row.get('expected_deliverables')),
            get_string_value(row.get('contact_person_info')),
            get_string_value(row.get('learning_outcomes')),
            get_string_value(row.get('team_size_preference')),
            get_string_value(row.get('project_status')),
            get_string_value(row.get('start_date')),
            get_string_value(row.get('end_date')),
            get_string_value(row.get('estimated_weekly_hours')),
            get_string_value(row.get('location'))
        ]
        
        df_copy.at[index, 'combined_text'] = ". ".join(filter(None, combined_parts)).strip()
        if not df_copy.at[index, 'combined_text']:
            df_copy.at[index, 'combined_text'] = ""

    return df_copy


# --- 5. 数据导入函数 ---
def import_students_to_db(db: Session, students_df: pd.DataFrame):
    """将学生数据（仅数据，不生成嵌入）导入数据库。"""
    print("\n开始导入学生数据到数据库...")
    
    try:
        for i, row in students_df.iterrows():
            skills_data = row['skills']
            if isinstance(skills_data, str):
                try:
                    skills_data = json.loads(skills_data)
                except json.JSONDecodeError:
                    skills_data = []
            elif pd.isna(skills_data):
                skills_data = []

            student = User(
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
                location=row['location'] if pd.notna(row['location']) else None,
                email=row['email'],
                phone_number=row['phone_number'],
                school=row['school'],
                password_hash=row['password_hash'],
                combined_text=row['combined_text'],
                embedding=np.zeros(DEFAULT_EMBEDDING_DIM).tolist(),  # 使用常量
                llm_api_type=None,
                llm_api_key_encrypted=None,
                llm_api_base_url=None,
                llm_model_id=None
            )

            db.add(student)
            print(f"添加学生: {student.name} (用户名: {student.username})")
        
        db.commit()
        print("学生数据导入完成。")
        
    except Exception as e:
        db.rollback()
        print(f"导入学生数据时发生错误: {e}")
        raise


def import_projects_to_db(db: Session, projects_df: pd.DataFrame):
    """将项目数据（仅数据，不生成嵌入）导入数据库。"""
    print("\n开始导入项目数据到数据库...")
    
    # 预先获取所有学生ID，避免重复查询
    existing_student_ids = [s.id for s in db.query(User.id).all()]
    
    if not existing_student_ids:
        raise ValueError("无法为项目分配创建者，因为数据库中没有学生记录。请先导入学生数据。")
    
    try:
        for i, row in projects_df.iterrows():
            # 处理创建者ID
            if pd.notna(row['creator_id']):
                creator_id_for_db = int(row['creator_id'])
            else:
                # 随机选择一个已存在的学生ID
                creator_id_for_db = np.random.choice(existing_student_ids)
                print(f"项目 {row['id']} 未指定创建者，随机分配创建者ID: {creator_id_for_db}")

            # 处理日期字段
            start_date_val = row['start_date'] if pd.notna(row['start_date']) else None
            end_date_val = row['end_date'] if pd.notna(row['end_date']) else None
            estimated_weekly_hours_val = row['estimated_weekly_hours'] if pd.notna(row['estimated_weekly_hours']) else None

            # 处理技能和角色数据
            required_skills_data = parse_json_field(row['required_skills'], "required_skills", [])
            required_roles_data = parse_json_field(row['required_roles'], "required_roles", [])

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
                location=row['location'] if pd.notna(row['location']) else None,
                creator_id=creator_id_for_db,
                combined_text=row['combined_text'],
                embedding=np.zeros(DEFAULT_EMBEDDING_DIM).tolist()  # 使用常量
            )

            db.add(project)
            print(f"添加项目: {project.title} (创建者ID: {project.creator_id})")
        
        db.commit()
        print("项目数据导入完成。")
        
    except Exception as e:
        db.rollback()
        print(f"导入项目数据时发生错误: {e}")
        raise

# 插入默认成就的函数（已废弃，成就初始化已集成到database.py中）
def insert_default_achievements(db: Session):
    """
    插入预设的成就到数据库中，如果同名成就已存在则跳过。
    注意：此函数已废弃，成就初始化现在由database.py的init_db()自动处理
    """
    print("\n⚠️  此函数已废弃：成就初始化现在由database.py自动处理")
    print("成就会在数据库表创建后自动初始化，无需手动调用此函数。")


# --- 主执行流程 ---
def main():
    """主执行函数"""
    print("--- 开始数据导入流程 ---")

    try:
        # 1. 初始化数据库表（如果尚未创建）
        init_db()

        # 2. 从CSV加载数据
        print(f"正在加载数据文件...")
        print(f"学生数据: {STUDENTS_CSV_PATH}")
        print(f"项目数据: {PROJECTS_CSV_PATH}")
        
        students_df = pd.read_csv(STUDENTS_CSV_PATH)
        projects_df = pd.read_csv(PROJECTS_CSV_PATH)
        print("\nCSV数据加载成功！")

        # 确保ID列是整数类型
        students_df['id'] = students_df['id'].astype(int)
        projects_df['id'] = projects_df['id'].astype(int)

        # 将日期时间列转换为 datetime 对象
        for col in ['start_date', 'end_date']:
            if col in projects_df.columns:
                projects_df[col] = pd.to_datetime(projects_df[col], errors='coerce')

        # 将 'location' 列转换为字符串类型，缺失值转换为None
        for df, name in [(students_df, '学生'), (projects_df, '项目')]:
            if 'location' in df.columns:
                df['location'] = df['location'].astype(str).replace('nan', None)

        # 3. 预处理数据
        print("\n开始预处理数据...")
        students_df = preprocess_student_data(students_df)
        projects_df = preprocess_project_data(projects_df)
        print("数据预处理完成。")

        # 4. 获取数据库会话并导入数据
        db_session = SessionLocal()
        try:
            import_students_to_db(db_session, students_df)
            import_projects_to_db(db_session, projects_df)
            
            print("\n✅ 所有数据导入成功！")
            print("💡 注意：默认成就已在数据库初始化时自动创建")
        except Exception as e:
            db_session.rollback()
            print(f"\n❌ 数据导入过程中发生错误，事务已回滚: {e}")
            import traceback
            traceback.print_exc()
            raise
        finally:
            db_session.close()

    except FileNotFoundError as e:
        print(f"❌ 错误：CSV文件未找到 - {e}")
        print(f"请确保以下文件存在：")
        print(f"  - {STUDENTS_CSV_PATH}")
        print(f"  - {PROJECTS_CSV_PATH}")
    except Exception as e:
        print(f"❌ 错误：{e}")
        import traceback
        traceback.print_exc()
    
    print("\n--- 数据导入流程结束 ---")


if __name__ == "__main__":
    main()
