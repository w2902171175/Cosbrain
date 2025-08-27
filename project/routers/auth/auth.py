# project/routers/auth/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional, Dict, Any, Literal
import secrets
import json
from datetime import timedelta, date
from sqlalchemy.sql import func
from sqlalchemy import and_, or_

# 导入数据库和模型
from database import get_db
from models import Student, Project, UserCourse, ForumTopic, ForumComment, ForumLike, ChatMessage, PointTransaction, Achievement, UserAchievement
from dependencies import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, pwd_context, bearer_scheme, create_access_token, get_current_user_id
from utils import (_get_text_part, _award_points, _check_and_award_achievements, check_unique_field, 
                  process_skills_field, build_user_combined_text, update_embedding_safe, 
                  debug_operation, commit_or_rollback, get_user_by_id_or_404, update_fields_from_dict)
import schemas
from ai_providers.config import GLOBAL_PLACEHOLDER_ZERO_VECTOR, get_user_model_for_provider
from ai_providers.embedding_provider import get_embeddings_from_api
from ai_providers.security_utils import decrypt_key
from ai_providers.config import get_user_model_for_provider

router = APIRouter(
    tags=["认证管理"],
    responses={404: {"description": "Not found"}},
)

# --- 健康检查接口 ---
@router.get("/health", summary="健康检查", response_description="返回API服务状态")
def health_check():
    """检查API服务是否正常运行。"""
    return {"status": "ok", "message": "鸿庆书云创新协作平台后端API运行正常！"}

@router.post("/register", response_model=schemas.StudentResponse, summary="用户注册")
async def register_user(
        user_data: schemas.StudentCreate,
        db: Session = Depends(get_db)
):
    debug_operation("尝试注册用户", email=user_data.email, phone=user_data.phone_number)

    # 1. 检查邮箱和手机号的唯一性
    if user_data.email:
        check_unique_field(db, Student, "email", user_data.email, error_message="邮箱已被注册。")

    if user_data.phone_number:
        check_unique_field(db, Student, "phone_number", user_data.phone_number, error_message="手机号已被注册。")

    # 2. 处理用户名: 如果用户未提供，则自动生成一个唯一用户名
    final_username = user_data.username
    if not final_username:
        unique_username_found = False
        attempts = 0
        max_attempts = 10
        while not unique_username_found and attempts < max_attempts:
            random_suffix = secrets.token_hex(4)
            proposed_username = f"新用户_{random_suffix}"
            if not db.query(Student).filter(Student.username == proposed_username).first():
                final_username = proposed_username
                unique_username_found = True
            attempts += 1

        if not unique_username_found:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="无法生成唯一用户名，请稍后再试或提供一个自定义用户名。")
        print(f"DEBUG: 用户未提供用户名，自动生成唯一用户名: {final_username}")
    else:
        existing_user_username = db.query(Student).filter(Student.username == final_username).first()
        if existing_user_username:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已被使用。")

    # 哈希密码
    hashed_password = pwd_context.hash(user_data.password)

    # 处理 skills 字段
    skills_list_for_db = []
    if user_data.skills:
        skills_list_for_db = [skill.model_dump() for skill in user_data.skills]

    user_skills_text = ""
    if skills_list_for_db:
        user_skills_text = ", ".join(
            [s.get("name", "") for s in skills_list_for_db if isinstance(s, dict) and s.get("name")])

    combined_text_content = ". ".join(filter(None, [
        _get_text_part(user_data.name),
        _get_text_part(user_data.major),
        _get_text_part(user_skills_text),
        _get_text_part(user_data.interests),
        _get_text_part(user_data.bio),
        _get_text_part(user_data.awards_competitions),
        _get_text_part(user_data.academic_achievements),
        _get_text_part(user_data.soft_skills),
        _get_text_part(user_data.portfolio_link),
        _get_text_part(user_data.preferred_role),
        _get_text_part(user_data.availability),
        _get_text_part(user_data.location)
    ])).strip()

    if not combined_text_content:
        combined_text_content = f"{user_data.name if user_data.name else final_username} 的简介。"

    print(f"DEBUG_REGISTER: 为用户 '{final_username}' 生成 combined_text: '{combined_text_content[:100]}...'")

    embedding = None
    if combined_text_content:
        try:
            # 对于新注册用户，LLM配置最初是空的。get_embeddings_from_api会返回零向量。
            new_embedding = await get_embeddings_from_api(
                [combined_text_content],
                api_key=None,  # 新注册用户未配置密钥
                llm_type=None,  # 新注册用户未配置LLM类型
                llm_base_url=None,
                llm_model_id=None
            )
            if new_embedding:  # ai_core现在会在没有有效key时返回零向量的List
                embedding = new_embedding[0]
            print(f"DEBUG_REGISTER: 用户嵌入向量已生成。")  # 此时应是零向量
        except Exception as e:
            print(f"ERROR_REGISTER: 生成用户嵌入向量失败: {e}")
    else:
        print(f"WARNING_REGISTER: 用户的 combined_text 为空，无法生成嵌入向量。")

    db_user = Student(
        email=user_data.email,
        phone_number=user_data.phone_number,
        password_hash=hashed_password,
        username=final_username,
        school=user_data.school,

        name=user_data.name if user_data.name else final_username,
        major=user_data.major if user_data.major else "未填写",
        skills=skills_list_for_db,
        interests=user_data.interests if user_data.interests else "未填写",
        bio=user_data.bio if user_data.bio else "欢迎使用本平台！",

        awards_competitions=user_data.awards_competitions,
        academic_achievements=user_data.academic_achievements,
        soft_skills=user_data.soft_skills,
        portfolio_link=user_data.portfolio_link,
        preferred_role=user_data.preferred_role,
        availability=user_data.availability,
        location=user_data.location,

        combined_text=combined_text_content,
        embedding=embedding,

        llm_api_type=None,
        llm_api_key_encrypted=None,
        llm_api_base_url=None,
        llm_model_id=None,
        is_admin=False
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    if isinstance(db_user.skills, str):
        try:
            db_user.skills = json.loads(db_user.skills)
            print(f"DEBUG_REGISTER: 强制转换 db_user.skills 为列表。")
        except json.JSONDecodeError as e:
            print(f"ERROR_REGISTER: 转换为列表失败，JSON解码错误: {e}")
            db_user.skills = []
    elif db_user.skills is None:
        db_user.skills = []

    print(f"DEBUG_REGISTER: db_user.skills type: {type(db_user.skills)}, content: {db_user.skills}")
    print(
        f"DEBUG: 用户 {db_user.email if db_user.email else db_user.phone_number} (ID: {db_user.id}) 注册成功。用户名: {db_user.username}")
    return db_user

@router.post("/token", response_model=schemas.Token, summary="用户登录并获取JWT令牌")
async def login_for_access_token(
        form_data: OAuth2PasswordRequestForm = Depends(),  # 使用 OAuth2PasswordRequestForm 适应标准登录表单
        db: Session = Depends(get_db)
):
    """
    通过邮箱或手机号或手机号和密码获取 JWT 访问令牌。
    - username (实际上可以是邮箱或手机号): 用户邮箱或手机号
    - password: 用户密码
    """
    credential = form_data.username  # 获取用户输入的凭证 (邮箱或手机号)
    password = form_data.password

    print(f"DEBUG_AUTH: 尝试用户登录: {credential}")

    user = None
    # 尝试通过邮箱或手机号查找用户
    if "@" in credential:
        user = db.query(Student).filter(Student.email == credential).first()
        print(f"DEBUG_AUTH: 尝试通过邮箱 '{credential}' 查找用户。")
    elif credential.isdigit() and len(credential) >= 7 and len(credential) <= 15:  # 假设手机号是纯数字且合理长度
        user = db.query(Student).filter(Student.phone_number == credential).first()
        print(f"DEBUG_AUTH: 尝试通过手机号 '{credential}' 查找用户。")
    else:
        print(f"DEBUG_AUTH: 凭证 '{credential}' 格式不正确，登录失败。")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="不正确的邮箱/手机号或密码",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 密码验证
    if not user or not pwd_context.verify(password, user.password_hash):
        print(f"DEBUG_AUTH: 用户 '{credential}' 登录失败：不正确的邮箱/手机号或密码。")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="不正确的邮箱/手机号或密码",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 每日登录打卡和积分奖励逻辑
    # 获取用户最初的积分和登录次数，用于对比和调试
    initial_total_points = user.total_points
    initial_login_count = user.login_count

    # 检查是否需要每日打卡奖励
    today = date.today()
    if user.last_login_at is None or user.last_login_at.date() < today:
        daily_points = 10  # 每日登录奖励积分
        # _award_points 现在只往 session 里 add，不 commit
        await _award_points(
            db=db,
            user=user,  # 传递会话中的 user 对象
            amount=daily_points,
            reason="每日登录打卡",
            transaction_type="EARN",
            related_entity_type="login_daily"
        )
        user.last_login_at = func.now()  # 更新上次登录时间
        user.login_count += 1  # 增加登录计数
        # db.add(user) # user对象已经在session中被跟踪和修改，无需再次add了

        print(
            f"DEBUG_LOGIN_PENDING: 用户 {user.id} 成功完成每日打卡，获得 {daily_points} 积分。总登录天数: {user.login_count} (待提交)")

        # 触发成就检查 (例如，总登录次数类的成就)
        # _check_and_award_achievements 也会将对象 add 到 session
        await _check_and_award_achievements(db, user.id)
    else:
        print(f"DEBUG_LOGIN: 用户 {user.id} 今日已打卡。")

    # 登录成功，创建访问令牌
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=access_token_expires
    )

    # 显式提交事务，并确保总积分在提交后更新
    try:
        db.commit()  # 提交所有待处理的数据库更改（包括 User, PointTransaction, UserAchievement）
        # db.refresh(user) 不再在这里 refresh，避免状态覆盖

        # 在所有更改提交后，重新从数据库载入 user 对象，确保准确显示最终的 total_points
        # 这确保我们看到的是所有奖励（包括成就奖励）都生效后的总积分。
        final_user_state = db.query(Student).filter(Student.id == user.id).first()
        if final_user_state:
            print(
                f"DEBUG_AUTH_FINAL: 用户 {final_user_state.email if final_user_state.email else final_user_state.phone_number} (ID: {final_user_state.id}) 登录成功，颁发JWT令牌。**最终积分: {final_user_state.total_points}, 登录次数: {final_user_state.login_count}**")
            # 可以在这里验证一下是否有新成就
            earned_achievements_count = db.query(UserAchievement).filter(
                UserAchievement.user_id == final_user_state.id).count()
            print(f"DEBUG_AUTH_FINAL: 用户 {final_user_state.id} 现有成就数量: {earned_achievements_count}")
        else:
            print(f"WARNING_AUTH_FINAL: 无法在提交后重新加载用户 {user.id} 的最终状态。")

        return schemas.Token(
            access_token=access_token,
            token_type="bearer",
            expires_in_minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )
    except Exception as e:
        db.rollback()  # 如果提交过程中发生任何错误，回滚事务
        print(f"ERROR_LOGIN_COMMIT: 用户 {user.id} 登录事务提交失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="登录成功但数据保存失败，请重试或联系管理员。",
            headers={"WWW-Authenticate": "Bearer"},
        )

@router.get("/users/me", response_model=schemas.StudentResponse, summary="获取当前登录用户详情")
async def read_users_me(current_user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    """
    获取当前登录用户的详细信息，包括其完成的项目和课程数量。
    """
    print(f"DEBUG: 获取当前用户 ID: {current_user_id} 的详情。")
    user = db.query(Student).filter(Student.id == current_user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # 计算用户完成的项目和课程数量
    completed_projects_count = db.query(Project).filter(
        Project.creator_id == current_user_id,
        Project.project_status == "已完成"
    ).count()

    completed_courses_count = db.query(UserCourse).filter(
        UserCourse.student_id == current_user_id,
        UserCourse.status == "completed"
    ).count()

    # 从 ORM 对象创建 StudentResponse 的基本实例，这将负责映射所有已存在的字段
    response_data = schemas.StudentResponse.model_validate(user, from_attributes=True)

    # 手动填充计算出的字段
    response_data.completed_projects_count = completed_projects_count
    response_data.completed_courses_count = completed_courses_count

    print(
        f"DEBUG: 用户 {current_user_id} 详情查询完成。完成项目: {completed_projects_count}, 完成课程: {completed_courses_count}。")
    return response_data

@router.put("/users/me", response_model=schemas.StudentResponse, summary="更新当前登录用户详情")
async def update_users_me(
        student_update_data: schemas.StudentUpdate,
        current_user_id: str = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    current_user_id_int = int(current_user_id)

    print(f"DEBUG: 更新用户 ID: {current_user_id_int} 的信息。")
    db_student = db.query(Student).filter(Student.id == current_user_id_int).first()
    if not db_student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    update_data = student_update_data.dict(exclude_unset=True)

    # --- 1. 特殊处理 username 的唯一性检查和更新 ---
    if "username" in update_data and update_data["username"] is not None:
        new_username = update_data["username"]
        if new_username != db_student.username:
            # 添加调试日志以便排查问题
            print(f"DEBUG: 检查用户名冲突 - new_username: {new_username}, current_user_id: {current_user_id_int}")
            
            existing_user_with_username = db.query(Student).filter(
                Student.username == new_username,
                Student.id != current_user_id_int
            ).first()
            
            print(f"DEBUG: 查询结果 - existing_user: {existing_user_with_username}")
            
            if existing_user_with_username:
                print(f"DEBUG: 发现用户名冲突 - 现有用户ID: {existing_user_with_username.id}")
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已被其他用户使用。")
        
        db_student.username = new_username
        print(f"DEBUG: 用户 {current_user_id_int} 用户名更新为: {new_username}")
        del update_data["username"]

    # --- 2. 特殊处理 phone_number 的唯一性检查和更新 ---
    if "phone_number" in update_data:
        new_phone_number = update_data["phone_number"]
        if new_phone_number is not None and new_phone_number != db_student.phone_number:
            # 添加调试日志以便排查问题
            print(f"DEBUG: 检查手机号冲突 - new_phone: {new_phone_number}, current_user_id: {current_user_id_int}")
            
            existing_user_with_phone = db.query(Student).filter(
                Student.phone_number == new_phone_number,
                Student.id != current_user_id_int
            ).first()
            
            print(f"DEBUG: 查询结果 - existing_user: {existing_user_with_phone}")
            
            if existing_user_with_phone:
                print(f"DEBUG: 发现手机号冲突 - 现有用户ID: {existing_user_with_phone.id}")
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="手机号已被其他用户使用。")
        
        db_student.phone_number = new_phone_number
        print(f"DEBUG: 用户 {current_user_id_int} 手机号更新为: {new_phone_number}")
        del update_data["phone_number"]

    # --- 3. 特殊处理 skills 字段的更新 ---
    if "skills" in update_data:
        new_skills_data_for_db = update_data["skills"]
        db_student.skills = new_skills_data_for_db
        print(f"DEBUG: 用户 {current_user_id_int} 技能更新为: {db_student.skills}")
        del update_data["skills"]

    # --- 4. 通用循环处理其余字段 (例如 school, name, major, location 等) ---
    for key, value in update_data.items():
        if hasattr(db_student, key) and value is not None:
            setattr(db_student, key, value)
            print(f"DEBUG: 更新字段 {key}: {value}")
        elif hasattr(db_student, key) and value is None:
            if key in ["major", "school", "interests", "bio", "awards_competitions",
                       "academic_achievements", "soft_skills", "portfolio_link",
                       "preferred_role", "availability", "name", "location"]:
                setattr(db_student, key, value)
                print(f"DEBUG: 清空字段 {key}")

    # 重建 combined_text
    current_skills_for_text = db_student.skills
    parsed_skills_for_text = []

    if isinstance(current_skills_for_text, str):
        try:
            parsed_skills_for_text = json.loads(current_skills_for_text)
        except json.JSONDecodeError:
            parsed_skills_for_text = []
    elif isinstance(current_skills_for_text, list):
        parsed_skills_for_text = current_skills_for_text
    elif current_skills_for_text is None:
        parsed_skills_for_text = []

    skills_text = ""
    if isinstance(parsed_skills_for_text, list):
        skills_text = ", ".join(
            [s.get("name", "") for s in parsed_skills_for_text if isinstance(s, dict) and s.get("name")])

    db_student.combined_text = ". ".join(filter(None, [
        _get_text_part(db_student.major),
        _get_text_part(skills_text),
        _get_text_part(db_student.interests),
        _get_text_part(db_student.bio),
        _get_text_part(db_student.awards_competitions),
        _get_text_part(db_student.academic_achievements),
        _get_text_part(db_student.soft_skills),
        _get_text_part(db_student.portfolio_link),
        _get_text_part(db_student.preferred_role),
        _get_text_part(db_student.availability),
        _get_text_part(db_student.location)
    ])).strip()

    # 获取用户配置的硅基流动 API 密钥用于生成嵌入向量
    siliconflow_api_key_for_embedding = None
    if db_student.llm_api_type == "siliconflow" and db_student.llm_api_key_encrypted:
        try:
            siliconflow_api_key_for_embedding = decrypt_key(db_student.llm_api_key_encrypted)
            print(f"DEBUG_EMBEDDING_KEY: 使用用户配置的硅基流动 API 密钥进行嵌入生成。")
        except Exception as e:
            print(f"ERROR_EMBEDDING_KEY: 解密用户硅基流动 API 密钥失败: {e}。将跳过嵌入生成。")
            siliconflow_api_key_for_embedding = None  # 解密失败，不要使用
    else:
        print(f"DEBUG_EMBEDDING_KEY: 用户未配置硅基流动 API 类型或密钥，使用默认占位符。")

    # 更新 embedding
    # 确定用于嵌入的API密钥和LLM配置
    user_llm_api_type_for_embedding = db_student.llm_api_type
    user_llm_api_base_url_for_embedding = db_student.llm_api_base_url
    # 优先使用新的多模型配置，fallback到原模型ID
    user_llm_model_id_for_embedding = get_user_model_for_provider(
        db_student.llm_model_ids,
        db_student.llm_api_type,
        db_student.llm_model_id
    )
    user_api_key_for_embedding = None

    if db_student.llm_api_key_encrypted:
        try:
            user_api_key_for_embedding = decrypt_key(db_student.llm_api_key_encrypted)
            print(f"DEBUG_EMBEDDING_KEY: 使用当前用户配置的LLM API 密钥进行嵌入生成。")
        except Exception as e:
            print(f"ERROR_EMBEDDING_KEY: 解密用户LLM API 密钥失败: {e}。将使用零向量。")
            user_api_key_for_embedding = None

    if db_student.combined_text:
        try:
            new_embedding = await get_embeddings_from_api(
                [db_student.combined_text],
                api_key=user_api_key_for_embedding,
                llm_type=user_llm_api_type_for_embedding,
                llm_base_url=user_llm_api_base_url_for_embedding,
                llm_model_id=user_llm_model_id_for_embedding  # 尽管 embedding API 不直接用，但传过去更好
            )
            if new_embedding:
                db_student.embedding = new_embedding[0]
                print(f"DEBUG: 用户 {db_student.id} 嵌入向量已更新。")
            else:
                db_student.embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 确保为零向量
        except Exception as e:
            print(f"ERROR: 更新用户 {db_student.id} 嵌入向量失败: {e}. 嵌入向量设为零。")
            db_student.embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR
    else:
        print(f"WARNING_EMBEDDING_RECALC: 用户 {current_user_id} 的 combined_text 为空，无法重新计算嵌入向量。")
        if db_student.embedding is None:
            db_student.embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR

    db.add(db_student)
    db.commit()
    db.refresh(db_student)

    if isinstance(db_student.skills, str):
        try:
            db_student.skills = json.loads(db_student.skills)
            print(f"DEBUG_UPDATE: 强制转换 db_student.skills 为列表。")
        except json.JSONDecodeError as e:
            print(f"ERROR_UPDATE: 转换为列表失败，JSON解码错误: {e}")
            db_student.skills = []
    elif db_student.skills is None:
        db_student.skills = []

    print(f"DEBUG: 用户 {current_user_id_int} 信息更新成功。")
    return db_student