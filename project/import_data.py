# project/import_data.py
import pandas as pd
import numpy as np
import os, httpx, json, asyncio, re
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timedelta
from database import SessionLocal, engine, init_db, Base
from models import Student, Project, Achievement

# --- 1. 配置数据文件路径 ---
# 获取脚本所在目录，然后构建正确的数据文件路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STUDENTS_CSV_PATH = os.path.join(SCRIPT_DIR, 'data', 'export', 'students.csv')
PROJECTS_CSV_PATH = os.path.join(SCRIPT_DIR, 'data', 'export', 'projects.csv')

DEFAULT_ACHIEVEMENTS = [
    {
        "name": "初次见面",
        "description": "首次登录平台，踏上创新协作之旅！",
        "criteria_type": "LOGIN_COUNT",
        "criteria_value": 1.0,
        "badge_url": "/static/badges/welcome.png",
        "reward_points": 10,
        "is_active": True
    },
    {
        "name": "每日坚持",
        "description": "连续登录 7 天，养成每日学习与协作的习惯！",
        "criteria_type": "DAILY_LOGIN_STREAK", # 假定有机制统计 streak
        "criteria_value": 7.0,
        "badge_url": "/static/badges/daily_streak.png",
        "reward_points": 50,
        "is_active": True
    },
    {
        "name": "项目新手",
        "description": "你的第一个项目已成功完成，在实践中探索AI应用！",
        "criteria_type": "PROJECT_COMPLETED_COUNT",
        "criteria_value": 1.0,
        "badge_url": "/static/badges/project_novice.png",
        "reward_points": 100,
        "is_active": True
    },
    {
        "name": "项目骨干",
        "description": "累计完成 3 个项目，你已是项目协作的得力助手！",
        "criteria_type": "PROJECT_COMPLETED_COUNT",
        "criteria_value": 3.0,
        "badge_url": "/static/badges/project_backbone.png",
        "reward_points": 200,
        "is_active": True
    },
    {
        "name": "学习起步",
        "description": "成功完成 1 门课程，点亮个人知识树！",
        "criteria_type": "COURSE_COMPLETED_COUNT",
        "criteria_value": 1.0,
        "badge_url": "/static/badges/course_starter.png",
        "reward_points": 20,
        "is_active": True
    },
    {
        "name": "课程达人",
        "description": "累计完成 3 门课程，你是名副其实的知识探索者！",
        "criteria_type": "COURSE_COMPLETED_COUNT",
        "criteria_value": 3.0,
        "badge_url": "/static/badges/course_expert.png",
        "reward_points": 80,
        "is_active": True
    },
    {
        "name": "初试啼声",
        "description": "首次在论坛发布话题或评论，与社区积极互动！",
        "criteria_type": "FORUM_POSTS_COUNT",
        "criteria_value": 1.0,
        "badge_url": "/static/badges/forum_post_novice.png",
        "reward_points": 5,
        "is_active": True
    },
    {
        "name": "社区参与者",
        "description": "在论坛发布累计 10 个话题或评论，积极分享你的见解！",
        "criteria_type": "FORUM_POSTS_COUNT",
        "criteria_value": 10.0,
        "badge_url": "/static/badges/forum_participant.png",
        "reward_points": 30,
        "is_active": True
    },
    {
        "name": "小有名气",
        "description": "你的话题或评论获得了 5 次点赞，内容已被认可！",
        "criteria_type": "FORUM_LIKES_RECEIVED",
        "criteria_value": 5.0,
        "badge_url": "/static/badges/likes_5.png",
        "reward_points": 25,
        "is_active": True
    },
    {
        "name": "人气之星",
        "description": "你的话题或评论获得了 20 次点赞，在社区中声名鹊起！",
        "criteria_type": "FORUM_LIKES_RECEIVED",
        "criteria_value": 20.0,
        "badge_url": "/static/badges/likes_stars.png",
        "reward_points": 100,
        "is_active": True
    },
     {
        "name": "沟通达人",
        "description": "累计发送 50 条聊天消息，你活跃在团队协作的前线！",
        "criteria_type": "CHAT_MESSAGES_SENT_COUNT",
        "criteria_value": 50.0,
        "badge_url": "/static/badges/chat_master.png",
        "reward_points": 20,
        "is_active": True
    }
]


# --- 3. 数据预处理函数 ---
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

        # 为确保唯一性，这些字段即使在 CSV 里为空，也会生成唯一值
        # 对于 email, phone_number, school, password_hash 这些唯一或非空的字段，
        # 如果 CSV 中为空，也生成一个唯一的占位符，避免导入时报错
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
                processed_skills_for_cell = []  # 异常发生时也确保是列表
        else:
            processed_skills_for_cell = []  # 明确为空列表，为了安全和IDE提示

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
        else:
            processed_required_skills_for_cell = [] # 明确为空列表，为了安全和IDE提示

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
                else:
                    role_names = [r.strip() for r in str(required_roles_raw_data).split(',') if r.strip()]
                    processed_required_roles_for_cell.extend(role_names)
            except json.JSONDecodeError:  # 如果不是有效的JSON字符串，按逗号分隔
                role_names = [r.strip() for r in str(required_roles_raw_data).split(',') if r.strip()]
                processed_required_roles_for_cell.extend(role_names)
            except Exception as e:
                print(f"WARNING_PREPROCESS: Error processing required_roles for project {row.get('id', index)}: {e}")
                processed_required_roles_for_cell = []
        else:
           processed_required_roles_for_cell = [] # 明确为空列表，为了安全和IDE提示
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


# --- 4. 数据导入函数 ---
def import_students_to_db(db: Session, students_df: pd.DataFrame):
    """将学生数据（仅数据，不生成嵌入）导入数据库。"""
    print("\n开始导入学生数据到数据库...")
    #  在导入脚本中，不再尝试调用外部API生成嵌入
    # 嵌入将由用户在配置API密钥后，通过更新个人资料或在推荐时按需生成

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
            embedding=np.zeros(1024).tolist(), #  默认生成零向量
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
            embedding=np.zeros(1024).tolist() # 默认生成零向量
        )
        if pd.isna(getattr(project, 'location')):
            setattr(project, 'location', None)

        db.add(project)
        print(f"添加项目: {project.title} (创建者ID: {project.creator_id})")
    db.commit()
    print("项目数据导入完成。")

# 插入默认成就的函数
def insert_default_achievements(db: Session):
    """
    插入预设的成就到数据库中，如果同名成就已存在则跳过。
    """
    print("\n开始检查并插入默认成就...")
    for achievement_data in DEFAULT_ACHIEVEMENTS:
        existing_achievement = db.query(Achievement).filter(Achievement.name == achievement_data["name"]).first()
        if existing_achievement:
            print(f"DEBUG_ACHIEVEMENT_IMPORT: 成就 '{achievement_data['name']}' 已存在，跳过。")
            continue

        new_achievement = Achievement(
            name=achievement_data["name"],
            description=achievement_data["description"],
            criteria_type=achievement_data["criteria_type"],
            criteria_value=achievement_data["criteria_value"],
            badge_url=achievement_data["badge_url"],
            reward_points=achievement_data["reward_points"],
            is_active=achievement_data["is_active"]
        )
        db.add(new_achievement)
        print(f"DEBUG_ACHIEVEMENT_IMPORT: 插入成就: {new_achievement.name}")
    try:
        db.commit()
        print("默认成就插入完成。")
    except Exception as e:
        db.rollback()
        print(f"ERROR_ACHIEVEMENT_IMPORT: 插入默认成就失败: {e}")


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
        insert_default_achievements(db_session)
    except Exception as e:
        db_session.rollback()
        print(f"\n数据导入过程中发生错误，事务已回滚: {e}")
        import traceback

        traceback.print_exc()
    finally:
        db_session.close()

    print("\n--- 数据导入流程结束 ---")
