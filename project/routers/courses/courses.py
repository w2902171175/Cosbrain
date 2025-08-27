# project/routers/courses/courses.py
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Response, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import func
from typing import List, Optional, Dict, Any, Literal
from pydantic import Field
import json, os, uuid, asyncio
from datetime import datetime

# 导入数据库和模型
from database import get_db
from models import Course, UserCourse, Student, CourseLike, CourseMaterial, PointTransaction, Achievement, UserAchievement, Project, ForumTopic, ForumComment, ForumLike, ChatMessage
from sqlalchemy import and_, or_
import schemas, oss_utils
from utils import (_get_text_part, populate_like_status, get_courses_with_details, get_resource_or_404, 
                  debug_operation, commit_or_rollback, _award_points, _check_and_award_achievements)
from ai_providers.config import GLOBAL_PLACEHOLDER_ZERO_VECTOR
from ai_providers.embedding_provider import get_embeddings_from_api
from ai_providers.security_utils import decrypt_key

# 创建路由器
router = APIRouter(
    prefix="/courses",
    tags=["课程管理"],
    responses={404: {"description": "Not found"}},
)

# --- 学生相关接口 ---
@router.get("/students/", response_model=List[schemas.StudentResponse], summary="获取所有学生列表")
def get_all_students(db: Session = Depends(get_db)):
    students = db.query(Student).all()
    debug_operation("获取所有学生列表", count=len(students))
    return students

@router.get("/students/{student_id}", response_model=schemas.StudentResponse, summary="获取指定学生详情")
def get_student_by_id(student_id: int, db: Session = Depends(get_db)):
    student = get_resource_or_404(db, Student, student_id, "Student not found.")
    debug_operation("获取学生详情", resource_id=student_id, resource_type="学生")
    return student

# 导入认证相关依赖
from dependencies import get_current_user_id, is_admin_user

# --- 课程路由 ---
@router.post("/", response_model=schemas.CourseResponse, summary="创建新课程")
async def create_course(
        course_data: schemas.CourseBase,
        # 接收 CourseBase 数据 (包含 cover_image_url 和 required_skills)
        # current_user_id: str = Depends(get_current_user_id), # 暂时不需要普通用户ID
        current_admin_user: Student = Depends(is_admin_user),  # 只有管理员能创建课程
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 管理员 {current_admin_user.id} 尝试创建课程: {course_data.title}")

    # 将 required_skills 转换为数据库存储格式（列表或JSONB）
    required_skills_list_for_db = []
    if course_data.required_skills:
        required_skills_list_for_db = [skill.model_dump() for skill in course_data.required_skills]

    # 重建 combined_text
    skills_text = ""
    if required_skills_list_for_db:
        skills_text = ", ".join(
            [s.get("name", "") for s in required_skills_list_for_db if isinstance(s, dict) and s.get("name")])

    combined_text_content = ". ".join(filter(None, [
        _get_text_part(course_data.title),
        _get_text_part(course_data.description),
        _get_text_part(course_data.instructor),
        _get_text_part(course_data.category),
        _get_text_part(skills_text),  # 新增
        _get_text_part(course_data.total_lessons),
        _get_text_part(course_data.avg_rating)
    ])).strip()

    embedding = None
    if combined_text_content:
        try:
            admin_api_key_for_embedding = None
            admin_llm_type = current_admin_user.llm_api_type
            admin_llm_base_url = current_admin_user.llm_api_base_url
            admin_llm_model_id = current_admin_user.llm_model_id

            if admin_llm_type == "siliconflow" and current_admin_user.llm_api_key_encrypted:
                try:
                    admin_api_key_for_embedding = decrypt_key(current_admin_user.llm_api_key_encrypted)
                    print(f"DEBUG_EMBEDDING_KEY: 使用管理员配置的硅基流动 API 密钥为课程生成嵌入。")
                except Exception as e:
                    print(f"ERROR_EMBEDDING_KEY: 解密管理员硅基流动 API 密钥失败: {e}。课程嵌入将使用零向量或默认行为。")
                    admin_api_key_for_embedding = None
            else:
                print(f"DEBUG_EMBEDDING_KEY: 管理员未配置硅基流动 API 类型或密钥，课程嵌入将使用零向量或默认行为。")

            new_embedding = await get_embeddings_from_api(
                [combined_text_content],
                api_key=admin_api_key_for_embedding,
                llm_type=admin_llm_type,
                llm_base_url=admin_llm_base_url,
                llm_model_id=admin_llm_model_id  # 传入管理员的模型ID
            )
            if new_embedding:
                embedding = new_embedding[0]
            print(f"DEBUG: 课程嵌入向量已生成。")
        except Exception as e:
            print(f"ERROR: 生成课程嵌入向量失败: {e}")

    try:
        db_course = Course(
            title=course_data.title,
            description=course_data.description,
            instructor=course_data.instructor,
            category=course_data.category,
            total_lessons=course_data.total_lessons,
            avg_rating=course_data.avg_rating,
            cover_image_url=course_data.cover_image_url,
            required_skills=required_skills_list_for_db,
            combined_text=combined_text_content,
            embedding=embedding
        )

        db.add(db_course)
        db.commit()
        db.refresh(db_course)

        # 确保返回时 required_skills 是解析后的列表形式
        if isinstance(db_course.required_skills, str):
            try:
                db_course.required_skills = json.loads(db_course.required_skills)
            except json.JSONDecodeError:
                db_course.required_skills = []
        elif db_course.required_skills is None:
            db_course.required_skills = []

        print(f"DEBUG: 课程 '{db_course.title}' (ID: {db_course.id}) 创建成功。")
        return db_course
    except IntegrityError as e:
        db.rollback()
        print(f"ERROR_DB: 创建课程发生完整性约束错误: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="创建课程失败，可能存在数据冲突。")
    except Exception as e:
        db.rollback()
        print(f"ERROR_DB: 创建课程发生未知错误: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="创建课程失败: 系统错误")

@router.get("/", response_model=List[schemas.CourseResponse], summary="获取所有课程列表")
async def get_all_courses(current_user_id: int = Depends(get_current_user_id),
                          db: Session = Depends(get_db),  # 添加 current_user_id 依赖
                          page: int = Query(1, ge=1, le=1000, description="页码"),  # 添加分页支持
                          page_size: int = Query(20, ge=1, le=100, description="每页大小"),  # 每页大小
                          category: Optional[str] = Query(None, max_length=50, description="分类过滤")  # 添加分类过滤
):
    """
    获取平台上所有课程的概要列表。
    """
    query = db.query(Course)
    
    # 添加分类过滤
    if category:
        query = query.filter(Course.category == category)
    
    # 调用新的辅助函数来填充 is_liked_by_current_user
    courses = await get_courses_with_details(query, current_user_id, db)  # 修改这里

    # 添加分页
    offset = (page - 1) * page_size
    total_courses = len(courses)
    paginated_courses = courses[offset:offset + page_size] if courses else []

    debug_operation("获取所有课程列表", user_id=current_user_id, count=len(paginated_courses), 
                   total=total_courses, page=page, page_size=page_size)

    for course in paginated_courses:
        if isinstance(course.required_skills, str):
            try:
                course.required_skills = json.loads(course.required_skills)
            except json.JSONDecodeError:
                course.required_skills = []
        elif course.required_skills is None:
            course.required_skills = []

    return paginated_courses

@router.get("/{course_id}", response_model=schemas.CourseResponse, summary="获取指定课程详情")
def get_course_by_id(course_id: int, current_user_id: int = Depends(get_current_user_id),
                           db: Session = Depends(get_db)):  # 移除 async，因为没有 await 操作
    """
    获取指定ID的课程详情。
    """
    print(f"DEBUG: 获取课程 ID: {course_id} 的详情。")
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程未找到。")

    # 填充 is_liked_by_current_user
    course.is_liked_by_current_user = False
    if current_user_id:
        like = db.query(CourseLike).filter(
            CourseLike.owner_id == current_user_id,
            CourseLike.course_id == course.id
        ).first()
        if like:
            course.is_liked_by_current_user = True

    # 确保返回时 required_skills 是解析后的列表形式
    if isinstance(course.required_skills, str):
        try:
            course.required_skills = json.loads(course.required_skills)
        except json.JSONDecodeError:
            course.required_skills = []
    elif course.required_skills is None:
        course.required_skills = []

    return course

@router.put("/{course_id}", response_model=schemas.CourseResponse, summary="更新指定课程")
async def update_course(
        course_id: int,
        course_data: schemas.CourseUpdate,  # 接收 CourseUpdate
        current_admin_user: Student = Depends(is_admin_user),  # 只有管理员能更新课程
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 管理员 {current_admin_user.id} 尝试更新课程 ID: {course_id}。")

    try:
        db_course = db.query(Course).filter(Course.id == course_id).first()
        if not db_course:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程未找到。")

        update_data = course_data.dict(exclude_unset=True)

        # 特殊处理 required_skills
        if "required_skills" in update_data:
            db_course.required_skills = update_data["required_skills"]  # 直接赋值列表或 None
            del update_data["required_skills"]  # 避免通用循环再次处理

        # 应用其他字段更新
        for key, value in update_data.items():
            if hasattr(db_course, key):
                setattr(db_course, key, value)

        db.add(db_course)

        # 重建 combined_text
        skills_text = ""
        current_skills_for_text = db_course.required_skills
        if isinstance(current_skills_for_text, str):
            try:
                current_skills_for_text = json.loads(current_skills_for_text)
            except json.JSONDecodeError:
                current_skills_for_text = []

        if isinstance(current_skills_for_text, list):
            skills_text = ", ".join(
                [s.get("name", "") for s in current_skills_for_text if isinstance(s, dict) and s.get("name")])

        db_course.combined_text = ". ".join(filter(None, [
            _get_text_part(db_course.title),
            _get_text_part(db_course.description),
            _get_text_part(db_course.instructor),
            _get_text_part(db_course.category),
            _get_text_part(skills_text),
            _get_text_part(db_course.total_lessons),
            _get_text_part(db_course.avg_rating),
            _get_text_part(db_course.cover_image_url)
        ])).strip()

        # 重新生成 embedding
        embedding = None  # 每次更新都重新生成
        if db_course.combined_text:
            try:
                admin_api_key_for_embedding = None
                admin_llm_type = current_admin_user.llm_api_type
                admin_llm_base_url = current_admin_user.llm_api_base_url
                admin_llm_model_id = current_admin_user.llm_model_id  # 传入管理员的模型ID

                if admin_llm_type == "siliconflow" and current_admin_user.llm_api_key_encrypted:
                    try:
                        admin_api_key_for_embedding = decrypt_key(current_admin_user.llm_api_key_encrypted)
                    except Exception:
                        pass

                new_embedding = await get_embeddings_from_api(
                    [db_course.combined_text],
                    api_key=admin_api_key_for_embedding,
                    llm_type=admin_llm_type,
                    llm_base_url=admin_llm_base_url,
                    llm_model_id=admin_llm_model_id
                )
                if new_embedding:
                    db_course.embedding = new_embedding[0]
                else:  # 如果没有返回嵌入，设为零向量
                    db_course.embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR
                print(f"DEBUG: 课程 {course_id} 嵌入向量已更新。")
            except Exception as e:
                print(f"ERROR: 更新课程 {course_id} 嵌入向量失败: {e}")
                db_course.embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 确保失败时是零向量
        else:  # 如果combined_text为空，也确保embedding是零向量
            db_course.embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR

        db.add(db_course)

        db.commit()
        db.refresh(db_course)

        # 确保返回时 required_skills 是解析后的列表形式
        if isinstance(db_course.required_skills, str):
            try:
                db_course.required_skills = json.loads(db_course.required_skills)
            except json.JSONDecodeError:
                db_course.required_skills = []
        elif db_course.required_skills is None:
            db_course.required_skills = []

        print(f"DEBUG: 课程 {course_id} 信息更新成功。")
        return db_course

    except IntegrityError as e:
        db.rollback()
        print(f"ERROR_DB: 更新课程发生完整性约束错误: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="更新课程失败，可能存在数据冲突。")
    except Exception as e:
        db.rollback()
        print(f"ERROR_DB: 更新课程发生未知错误: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="更新课程失败: 系统错误")

@router.post("/{course_id}/enroll", response_model=schemas.UserCourseResponse, summary="用户报名课程")
def enroll_course(
        course_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):  # 移除 async，因为没有 await 操作
    """
    允许用户报名（注册）一门课程。
    如果用户已报名，则返回已有的报名信息，不会重复创建。
    """
    print(f"DEBUG_COURSE_ENROLL: 用户 {current_user_id} 尝试报名课程 {course_id}。")

    # 1. 验证课程是否存在
    db_course = db.query(Course).filter(Course.id == course_id).first()
    if not db_course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程未找到。")

    # 2. 检查用户是否已报名该课程
    existing_enrollment = db.query(UserCourse).filter(
        UserCourse.student_id == current_user_id,
        UserCourse.course_id == course_id
    ).first()

    if existing_enrollment:
        print(f"DEBUG_COURSE_ENROLL: 用户 {current_user_id} 已报名课程 {course_id}，返回现有报名信息。")
        # 确保返回的UserCourseResponse包含课程标题
        if existing_enrollment.course is None:  # 如果course关系没有被加载
            existing_enrollment.course = db_course  # 暂时赋值以填充响应模型
        return existing_enrollment

    # 3. 创建新的报名记录
    new_enrollment = UserCourse(
        student_id=current_user_id,
        course_id=course_id,
        progress=0.0,
        status="registered",  # 初始状态为"已注册"
        last_accessed=func.now()
    )

    db.add(new_enrollment)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        # 捕获可能的并发冲突，如果同时有多个请求尝试创建
        print(f"ERROR_DB: 报名课程时发生完整性错误: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="报名失败：课程已被您注册，或发生并发冲突。")
    except Exception as e:
        db.rollback()
        print(f"ERROR: 报名课程 {course_id} 失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="报名课程失败: 系统错误")
    db.refresh(new_enrollment)

    # 确保返回的UserCourseResponse包含课程标题
    if new_enrollment.course is None:  # 如果course关系没有被加载
        new_enrollment.course = db_course  # 暂时赋值以填充响应模型

    print(f"DEBUG_COURSE_ENROLL: 用户 {current_user_id} 成功报名课程 {course_id}。")
    return new_enrollment

# --- 课程材料管理接口 ---
@router.post("/{course_id}/materials/", response_model=schemas.CourseMaterialResponse,
          summary="为指定课程上传新材料（文件或链接）")
async def create_course_material(
        course_id: int,
        file: Optional[UploadFile] = File(None, description="上传课程文件，如PDF、视频等"),
        material_data: schemas.CourseMaterialCreate = Depends(),
        current_admin_user: Student = Depends(is_admin_user),  # 管理员创建材料
        db: Session = Depends(get_db)
):
    print(
        f"DEBUG_COURSE_MATERIAL: 管理员 {current_admin_user.id} 尝试为课程 {course_id} 创建材料: {material_data.title} (类型: {material_data.type})")

    # 1. 验证课程是否存在
    db_course = db.query(Course).filter(Course.id == course_id).first()
    if not db_course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程未找到。")

    # 用于在OSS上传失败或DB事务回滚时删除OSS中已上传文件的变量
    oss_object_name_for_rollback = None

    try:
        # 2. 根据材料类型处理数据
        material_params = {
            "course_id": course_id,
            "title": material_data.title,
            "type": material_data.type,
            "content": material_data.content  # 可选，无论哪种类型都可作为补充描述
        }

        if material_data.type == "file":
            if not file:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="类型为 'file' 时，必须上传文件。")

            # 读取文件所有字节
            file_bytes = await file.read()
            file_extension = os.path.splitext(file.filename)[1]
            # OSS上的文件路径和名称，例如 course_materials/UUID.pdf
            current_oss_object_name = f"course_materials/{uuid.uuid4().hex}{file_extension}"
            oss_object_name_for_rollback = current_oss_object_name  # 记录用于回滚

            try:
                material_params["file_path"] = await oss_utils.upload_file_to_oss(  # 存储OSS URL
                    file_bytes=file_bytes,
                    object_name=current_oss_object_name,
                    content_type=file.content_type
                )
                material_params["original_filename"] = file.filename
                material_params["file_type"] = file.content_type
                material_params["size_bytes"] = file.size
                print(
                    f"DEBUG_COURSE_MATERIAL: 文件 '{file.filename}' 上传到OSS成功，URL: {material_params['file_path']}")
            except HTTPException as e:  # oss_utils.upload_file_to_oss will re-raise HTTPException
                print(f"ERROR_COURSE_MATERIAL: 上传文件到OSS失败: {e.detail}")
                raise e  # 直接重新抛出
            except Exception as e:
                print(f"ERROR_COURSE_MATERIAL: 上传文件到OSS时发生未知错误: {e}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                    detail="文件上传到云存储失败: 系统错误")

        elif material_data.type == "link":
            if not material_data.url:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="类型为 'link' 时，'url' 字段为必填。")
            material_params["url"] = material_data.url
            material_params["original_filename"] = None;
            material_params["file_type"] = None;
            material_params["size_bytes"] = None
            material_params["file_path"] = None  # 确保明确为None
        elif material_data.type == "text":
            if not material_data.content:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="类型为 'text' 时，'content' 字段为必填。")
            material_params["url"] = None;
            material_params["original_filename"] = None;
            material_params["file_type"] = None;
            material_params["size_bytes"] = None
            material_params["file_path"] = None  # 确保明确为None
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的材料类型。")

        # 3. 生成 combined_text 用于嵌入，并计算嵌入向量
        combined_text_content = ". ".join(filter(None, [
            _get_text_part(material_data.title),
            _get_text_part(material_data.content),
            _get_text_part(material_data.url),
            _get_text_part(material_data.original_filename),
            _get_text_part(material_data.file_type),
            _get_text_part(material_params.get("file_path"))  # 添加file_path (OSS URL)到combined_text
        ])).strip()
        if not combined_text_content:  # 如果组合文本为空，可能需要给个默认值
            combined_text_content = ""  # 确保是空字符串而不是None

        embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 默认零向量

        # 获取管理员的LLM配置用于嵌入生成
        admin_llm_api_key = None
        admin_llm_type = current_admin_user.llm_api_type
        admin_llm_base_url = current_admin_user.llm_api_base_url
        admin_llm_model_id = current_admin_user.llm_model_id

        if current_admin_user.llm_api_key_encrypted:
            try:
                admin_llm_api_key = decrypt_key(current_admin_user.llm_api_key_encrypted)
                admin_llm_type = current_admin_user.llm_api_type
                admin_llm_base_url = current_admin_user.llm_api_base_url
                admin_llm_model_id = current_admin_user.llm_model_id
                print(f"DEBUG_EMBEDDING_KEY: 使用管理员配置的硅基流动 API 密钥为课程材料生成嵌入。")
            except Exception as e:
                print(f"ERROR_EMBEDDING_KEY: 解密管理员硅基流动 API 密钥失败: {e}。课程材料嵌入将使用零向量。")
                admin_llm_api_key = None
        else:
            print(f"DEBUG_EMBEDDING_KEY: 管理员未配置硅基流动 API 类型或密钥，课程材料嵌入将使用零向量或默认行为。")

        if combined_text_content:
            try:
                new_embedding = await get_embeddings_from_api(
                    [combined_text_content],
                    api_key=admin_llm_api_key,
                    llm_type=admin_llm_type,
                    llm_base_url=admin_llm_base_url,
                    llm_model_id=admin_llm_model_id
                )
                if new_embedding:
                    embedding = new_embedding[0]
                else:
                    embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 确保为零向量
                print(f"DEBUG_COURSE_MATERIAL: 材料嵌入向量已生成。")
            except Exception as e:
                print(f"ERROR_COURSE_MATERIAL: 生成材料嵌入向量失败: {e}. 嵌入向量设为零。")
                embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR
        else:
            print(f"WARNING_EMBEDDING: 课程材料 combined_text 为空，嵌入向量设为零。")

        material_params["combined_text"] = combined_text_content
        material_params["embedding"] = embedding

        # 4. 创建数据库记录
        db_material = CourseMaterial(**material_params)
        db.add(db_material)

        db.commit()  # 提交DB写入
        db.refresh(db_material)
        print(f"DEBUG_COURSE_MATERIAL: 课程材料 '{db_material.title}' (ID: {db_material.id}) 创建成功。")
        return db_material

    except IntegrityError as e:
        db.rollback()
        # 如果数据库提交失败，并且之前有文件上传到OSS，则尝试删除OSS文件
        if oss_object_name_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(oss_object_name_for_rollback))
            print(
                f"DEBUG_COURSE_MATERIAL: DB commit failed, attempting to delete OSS file: {oss_object_name_for_rollback}")

        print(f"ERROR_DB: 创建课程材料发生完整性约束错误: {e}")
        if "_course_material_title_uc" in str(e): raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                                                      detail="同一课程下已存在同名材料。")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="创建课程材料失败，可能存在数据冲突。")
    except HTTPException as e:  # Catch FastAPI's HTTPException and re-raise it
        db.rollback()
        if oss_object_name_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(oss_object_name_for_rollback))
            print(
                f"DEBUG_COURSE_MATERIAL: HTTP exception, attempting to delete OSS file: {oss_object_name_for_rollback}")
        raise e
    except Exception as e:
        db.rollback()
        # 如果发生其他错误，并且之前有文件上传到OSS，则尝试删除OSS文件
        if oss_object_name_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(oss_object_name_for_rollback))
            print(
                f"DEBUG_COURSE_MATERIAL: Unknown error, attempting to delete OSS file: {oss_object_name_for_rollback}")
        print(f"ERROR_DB: 创建课程材料发生未知错误: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="创建课程材料失败: 系统错误")

@router.get("/{course_id}/materials/", response_model=List[schemas.CourseMaterialResponse],
         summary="获取指定课程的所有材料列表")
def get_course_materials(
        course_id: int,
        # 课程材料通常是公开的，或者在学习课程后才能访问，这里简化为只要课程存在即可查看
        # current_user_id: int = Depends(get_current_user_id)，如果需要认证，可 uncomment
        db: Session = Depends(get_db),
        type_filter: Optional[Literal["file", "link", "text"]] = None,
        page: int = Query(1, ge=1, le=1000, description="页码"),  # 添加分页支持
        page_size: int = Query(20, ge=1, le=100, description="每页大小")  # 每页大小
):  # 移除 async，因为没有 await 操作
    print(f"DEBUG_COURSE_MATERIAL: 获取课程 {course_id} 的材料列表。")
    db_course = db.query(Course).filter(Course.id == course_id).first()
    if not db_course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程未找到。")

    query = db.query(CourseMaterial).filter(CourseMaterial.course_id == course_id)
    if type_filter:
        query = query.filter(CourseMaterial.type == type_filter)

    # 添加分页
    offset = (page - 1) * page_size
    materials = query.order_by(CourseMaterial.title).offset(offset).limit(page_size).all()
    print(f"DEBUG_COURSE_MATERIAL: 课程 {course_id} 获取到 {len(materials)} 个材料。")
    return materials

@router.get("/{course_id}/materials/{material_id}", response_model=schemas.CourseMaterialResponse,
         summary="获取指定课程材料详情")
def get_course_material_detail(
        course_id: int,
        material_id: int,
        # current_user_id: int = Depends(get_current_user_id), 如果需要认证，可 uncomment
        db: Session = Depends(get_db)
):  # 移除 async，因为没有 await 操作
    print(f"DEBUG_COURSE_MATERIAL: 获取课程 {course_id} 材料 ID: {material_id} 的详情。")
    db_material = db.query(CourseMaterial).filter(
        CourseMaterial.id == material_id,
        CourseMaterial.course_id == course_id
    ).first()
    if not db_material:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程材料未找到或不属于该课程。")
    return db_material

@router.put("/{course_id}/materials/{material_id}", response_model=schemas.CourseMaterialResponse,
         summary="更新指定课程材料")
async def update_course_material(
        course_id: int,
        material_id: int,
        file: Optional[UploadFile] = File(None, description="可选：上传新文件替换旧文件"),
        material_data: schemas.CourseMaterialUpdate = Depends(),
        current_admin_user: Student = Depends(is_admin_user),  # 管理员更新
        db: Session = Depends(get_db)
):
    print(f"DEBUG_COURSE_MATERIAL: 管理员 {current_admin_user.id} 尝试更新课程 {course_id} 材料 ID: {material_id}。")

    db_material = db.query(CourseMaterial).filter(
        CourseMaterial.id == material_id,
        CourseMaterial.course_id == course_id
    ).first()
    if not db_material:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程材料未找到或不属于该课程。")

    # 验证课程是否存在 (保持不变)
    db_course = db.query(Course).filter(Course.id == course_id).first()
    if not db_course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程未找到。")

    update_dict = material_data.dict(exclude_unset=True)  # 获取所有明确传入的字段及其值

    # 获取旧的OSS对象名称，用于替换时删除
    old_oss_object_name = None
    oss_base_url_parsed = os.getenv("S3_BASE_URL").rstrip('/') + '/'
    if db_material.file_path and db_material.file_path.startswith(oss_base_url_parsed):
        old_oss_object_name = db_material.file_path.replace(oss_base_url_parsed, '', 1)

    new_oss_object_name = None  # 用于新的文件上传成功后，在 commit 失败时回滚删除

    # 类型转换的复杂逻辑
    # 检查是否尝试改变材料类型
    type_changed = "type" in update_dict and update_dict["type"] != db_material.type
    new_type_from_data = update_dict.get("type", db_material.type)  # 获取新的类型，如果没变就用旧的

    if type_changed:
        # 如果从 "file" 类型改为其他类型，需要删除旧的OSS文件
        if db_material.type == "file" and old_oss_object_name:
            try:
                # 异步删除旧的OSS文件，不阻塞主线程
                asyncio.create_task(oss_utils.delete_file_from_oss(old_oss_object_name))
                print(f"DEBUG_COURSE_MATERIAL: Deleted old OSS file {old_oss_object_name} due to type change.")
            except Exception as e:
                print(
                    f"ERROR_COURSE_MATERIAL: Failed to schedule deletion of old OSS file {old_oss_object_name} during type change: {e}")

        # 清除旧文件相关的数据库字段（file_path, original_filename, file_type, size_bytes）
        # 也清除 url 或 content，根据新类型而定
        if new_type_from_data in ["link", "text"]:
            db_material.file_path = None
            db_material.original_filename = None
            db_material.file_type = None
            db_material.size_bytes = None
            if new_type_from_data == "link":
                db_material.content = None  # 如果改为link，清除content
                if not update_dict.get("url") and not db_material.url:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                        detail="类型为 'link' 时，'url' 字段为必填。")
            elif new_type_from_data == "text":
                db_material.url = None  # 如果改为text，清除url
                if not update_dict.get("content") and not db_material.content:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                        detail="类型为 'text' 时，'content' 字段为必填。")

        db_material.type = new_type_from_data  # 更新类型

    # 如果上传了新文件 (无论类型是否改变，只要有文件上传就处理)
    if file:
        # 如果当前材料类型不是 "file" （且不是从 "file" 类型更新），则不允许文件上传
        if db_material.type != "file" and new_type_from_data != "file":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="只有类型为 'file' 的材料才能上传文件。如需更改材料类型，请在material_data中同时指定 type='file'。")

        # 如果旧文件存在且是文件类型，先从OSS删除旧文件
        if db_material.type == "file" and old_oss_object_name:
            try:
                # 异步删除旧的OSS文件
                asyncio.create_task(oss_utils.delete_file_from_oss(old_oss_object_name))
                print(f"DEBUG_COURSE_MATERIAL: Deleted old OSS file: {old_oss_object_name} for replacement.")
            except Exception as e:
                print(
                    f"ERROR_COURSE_MATERIAL: Failed to schedule deletion of old OSS file {old_oss_object_name} during replacement: {e}")

        # 读取新文件内容并上传到OSS
        file_bytes = await file.read()
        new_file_extension = os.path.splitext(file.filename)[1]
        new_oss_object_name = f"course_materials/{uuid.uuid4().hex}{new_file_extension}"  # OSS上的路径和文件名

        try:
            db_material.file_path = await oss_utils.upload_file_to_oss(  # 存储OSS URL
                file_bytes=file_bytes,
                object_name=new_oss_object_name,
                content_type=file.content_type
            )
            db_material.original_filename = file.filename
            db_material.file_type = file.content_type
            db_material.size_bytes = file.size

            if db_material.type != "file":  # 如果之前不是file类型，且上传了文件，则强制改为file类型
                db_material.type = "file"
                print(f"DEBUG_COURSE_MATERIAL: Material type automatically changed to 'file' due to file upload.")

            # 清除其他类型特有的字段
            db_material.url = None
            db_material.content = None

            print(f"DEBUG_COURSE_MATERIAL: New file '{file.filename}' saved to OSS: {db_material.file_path}")
        except HTTPException as e:  # oss_utils.upload_file_to_oss will re-raise HTTPException
            print(f"ERROR_COURSE_MATERIAL: 上传新文件到OSS失败: {e.detail}")
            raise e  # 直接重新抛出
        except Exception as e:
            print(f"ERROR_COURSE_MATERIAL: 上传新文件到OSS时发生未知错误: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="文件上传到云存储失败: 系统错误")

    # 应用 material_data 中的其他更新 (覆盖已处理的file/type字段)
    # 确保 material_data.dict(exclude_unset=True) 不会将 file, url, content, type等重新覆盖为None如果是没传的话
    # 所以要跳过已手工处理的字段
    fields_to_skip_manual_update = ["type", "url", "content", "original_filename", "file_type", "size_bytes", "file"]
    for key, value in update_dict.items():
        if key in fields_to_skip_manual_update:
            continue
        if hasattr(db_material, key):
            if key == "title":
                if value is None or (isinstance(value, str) and not value.strip()):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="材料标题不能为空。")
                setattr(db_material, key, value)
            else:
                setattr(db_material, key, value)

    # 重新生成 combined_text 和 embedding
    combined_text_content = ". ".join(filter(None, [
        _get_text_part(db_material.title),  # 使用 db_material 的最新属性
        _get_text_part(db_material.content),
        _get_text_part(db_material.url),
        _get_text_part(db_material.original_filename),
        _get_text_part(db_material.file_type),
        _get_text_part(db_material.file_path)  # 添加file_path (OSS URL)到combined_text
    ])).strip()

    # 获取管理员LLM配置和API密钥用于嵌入生成 (管理员对象已从依赖注入提供)
    admin_llm_api_key = None
    admin_llm_type = current_admin_user.llm_api_type
    admin_llm_base_url = current_admin_user.llm_api_base_url
    admin_llm_model_id = current_admin_user.llm_model_id

    if current_admin_user.llm_api_key_encrypted:
        try:
            admin_llm_api_key = decrypt_key(current_admin_user.llm_api_key_encrypted)
        except Exception as e:
            print(
                f"WARNING_COURSE_MATERIAL_EMBEDDING: 解密管理员 {current_admin_user.id} LLM API密钥失败: {e}. 课程材料嵌入将使用零向量或默认行为。")

    embedding_recalculated = GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 默认零向量
    if combined_text_content:
        try:
            new_embedding = await get_embeddings_from_api(
                [combined_text_content],
                api_key=admin_llm_api_key,
                llm_type=admin_llm_type,
                llm_base_url=admin_llm_base_url,
                llm_model_id=admin_llm_model_id
            )
            if new_embedding:
                embedding_recalculated = new_embedding[0]
            print(f"DEBUG_COURSE_MATERIAL: 材料嵌入向量已更新。")
        except Exception as e:
            print(f"ERROR_COURSE_MATERIAL: 更新材料嵌入向量失败: {e}. 嵌入向量设为零。")
            embedding_recalculated = GLOBAL_PLACEHOLDER_ZERO_VECTOR
    else:  # 如果 combined_text_content 为空
        print(f"WARNING: 课程材料内容为空，无法更新有效嵌入向量。")
        embedding_recalculated = GLOBAL_PLACEHOLDER_ZERO_VECTOR

    db_material.combined_text = combined_text_content
    db_material.embedding = embedding_recalculated  # 赋值给DB对象

    db.add(db_material)
    try:
        db.commit()
        db.refresh(db_material)
    except IntegrityError as e:
        db.rollback()
        # 如果数据库提交失败，尝试删除新上传的OSS文件
        if new_oss_object_name:
            asyncio.create_task(oss_utils.delete_file_from_oss(new_oss_object_name))
            print(
                f"DEBUG_COURSE_MATERIAL: Update DB commit failed, attempting to delete new OSS file: {new_oss_object_name}")
        print(f"ERROR_DB: Update course material integrity constraint error: {e}")
        if "_course_material_title_uc" in str(e):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="同一课程下已存在同名材料。")
        elif 'null value in column "type"' in str(e):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="材料类型不能为空。")
        else:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="更新课程材料失败，可能存在数据冲突。")
    except Exception as e:
        db.rollback()
        # 如果发生其他错误，尝试删除新上传的OSS文件
        if new_oss_object_name:
            asyncio.create_task(oss_utils.delete_file_from_oss(new_oss_object_name))
            print(
                f"DEBUG_COURSE_MATERIAL: Unknown error during update, attempting to delete new OSS file: {new_oss_object_name}")
        print(f"ERROR_DB: Unknown error during course material update: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="更新课程材料失败: 系统错误")

    print(f"DEBUG_COURSE_MATERIAL: Course material ID: {material_id} updated successfully.")
    return db_material

@router.delete("/{course_id}/materials/{material_id}", status_code=status.HTTP_204_NO_CONTENT,
            summary="删除指定课程材料")
async def delete_course_material(
        course_id: int,
        material_id: int,
        current_admin_user: Student = Depends(is_admin_user),  # 只有管理员能删除课程材料
        db: Session = Depends(get_db)
):
    print(f"DEBUG_COURSE_MATERIAL: 管理员 {current_admin_user.id} 尝试删除课程 {course_id} 材料 ID: {material_id}。")

    db_material = db.query(CourseMaterial).filter(
        CourseMaterial.id == material_id,
        CourseMaterial.course_id == course_id  # 确保材料属于该课程
    ).first()
    if not db_material:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程材料未找到或不属于该课程。")

    # 如果材料是 'file' 类型，从OSS删除文件
    if db_material.type == "file" and db_material.file_path:
        oss_base_url_parsed = os.getenv("S3_BASE_URL").rstrip('/') + '/'
        # 从OSS URL中解析出 object_name
        object_name = db_material.file_path.replace(oss_base_url_parsed, '', 1) if db_material.file_path.startswith(
            oss_base_url_parsed) else db_material.file_path

        if object_name:
            try:
                await oss_utils.delete_file_from_oss(object_name)
                print(f"DEBUG_COURSE_MATERIAL: 删除了OSS文件: {object_name}")
            except Exception as e:
                print(f"ERROR_COURSE_MATERIAL: 删除OSS文件 {object_name} 失败: {e}")
                # 这里不抛出异常，即使OSS文件删除失败，也应该允许数据库记录被删除
        else:
            print(
                f"WARNING_COURSE_MATERIAL: 材料 {material_id} 的 file_path 无效或非OSS URL: {db_material.file_path}，跳过OSS文件删除。")

    db.delete(db_material)
    db.commit()
    print(f"DEBUG_COURSE_MATERIAL: 课程材料 ID: {material_id} 及其关联数据已删除。")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# --- 课程点赞接口 ---
@router.post("/{course_id}/like", response_model=schemas.CourseLikeResponse, summary="点赞指定课程")
def like_course_item(
        course_id: int,
        current_user_id: int = Depends(get_current_user_id),  # 点赞者
        db: Session = Depends(get_db)
):  # 移除 async，因为没有 await 操作
    """
    点赞一个课程。同一用户不能重复点赞同一课程。\n
    点赞成功后，为被点赞课程的讲师奖励积分。
    """
    print(f"DEBUG_LIKE: 用户 {current_user_id} 尝试点赞课程 ID: {course_id}")
    try:
        # 1. 验证课程是否存在
        db_course = db.query(Course).filter(Course.id == course_id).first()
        if not db_course:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程未找到。")

        # 2. 检查是否已点赞
        existing_like = db.query(CourseLike).filter(
            CourseLike.owner_id == current_user_id,
            CourseLike.course_id == course_id
        ).first()
        if existing_like:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已点赞该课程。")

        # 3. 创建点赞记录
        db_like = CourseLike(
            owner_id=current_user_id,
            course_id=course_id
        )
        db.add(db_like)

        # 4. 更新课程点赞计数
        db_course.likes_count += 1
        db.add(db_course)

        # 5. 奖励积分和检查成就 (为课程的讲师奖励积分)
        # 暂时没有讲师的 Student ID，如果讲师不是平台用户，则无法奖励积分。
        # 如果 Instructor 是平台用户，需要额外逻辑来查找其 ID。
        # 这里假设 Instructor 只是一个名字，不直接关联到 Student 表。
        # 如果需要奖励，需要将 Instructor 也关联到 Student 表。
        # 为了简化，这里先不给课程讲师或创建者加积分，或者仅在讲师是平台注册用户时进行。
        print(f"DEBUG_POINTS_ACHIEVEMENT: 课程点赞不直接奖励积分给讲师，除非讲师是平台注册用户且有相应逻辑支持。")

        db.commit()  # 统一提交所有操作
        db.refresh(db_like)

        print(f"DEBUG_LIKE: 用户 {current_user_id} 点赞课程 {course_id} 成功。")
        return db_like

    except Exception as e:
        db.rollback()
        print(f"ERROR_LIKE: 课程点赞失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="课程点赞失败: 系统错误")

@router.delete("/{course_id}/unlike", status_code=status.HTTP_204_NO_CONTENT, summary="取消点赞指定课程")
def unlike_course_item(
        course_id: int,
        current_user_id: int = Depends(get_current_user_id),  # 取消点赞者
        db: Session = Depends(get_db)
):  # 移除 async，因为没有 await 操作
    """
    取消点赞一个课程。
    """
    print(f"DEBUG_UNLIKE: 用户 {current_user_id} 尝试取消点赞课程 ID: {course_id}")
    try:
        # 1. 查找点赞记录
        db_like = db.query(CourseLike).filter(
            CourseLike.owner_id == current_user_id,
            CourseLike.course_id == course_id
        ).first()

        if not db_like:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到您对该课程的点赞记录。")

        # 2. 更新课程点赞计数
        db_course = db.query(Course).filter(Course.id == course_id).first()
        if db_course and db_course.likes_count > 0:
            db_course.likes_count -= 1
            db.add(db_course)

        # 3. 删除点赞记录
        db.delete(db_like)
        db.commit()

        print(f"DEBUG_UNLIKE: 用户 {current_user_id} 取消点赞课程 {course_id} 成功。")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except Exception as e:
        db.rollback()
        print(f"ERROR_UNLIKE: 取消课程点赞失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="取消课程点赞失败: 系统错误")

# --- 用户课程学习进度管理接口 ---
@router.put("/{course_id}/progress", response_model=schemas.UserCourseResponse,
         summary="更新当前用户课程学习进度和状态")
async def update_user_course_progress(
        course_id: int,
        update_data: Dict[str, Any],
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 用户 {current_user_id} 尝试更新课程 {course_id} 的进度。")

    try:
        user_course = db.query(UserCourse).filter(
            UserCourse.student_id == current_user_id,
            UserCourse.course_id == course_id
        ).first()

        if not user_course:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户未注册该课程或课程未找到。")

        old_status = user_course.status
        new_status = update_data.get("status")

        # 更新进度和状态 (先更新到ORM对象，等待最终提交)
        if "progress" in update_data and isinstance(update_data["progress"], (int, float)):
            user_course.progress = update_data["progress"]
        if "status" in update_data and isinstance(update_data["status"], str):
            user_course.status = update_data["status"]

        user_course.last_accessed = func.now()  # 更新上次访问时间

        db.add(user_course)  # 将修改后的user_course对象添加到会话中

        # 在检查成就前，强制刷新会话，使 UserCourse 的最新状态对查询可见！
        if new_status == "completed" and old_status != "completed":
            db.flush()  # 确保 user_course 的 completed 状态已刷新到数据库会话，供 _check_and_award_achievements 查询
            print(f"DEBUG_FLUSH: 用户 {current_user_id} 课程 {course_id} 状态更新已刷新到会话。")

        # 检查课程状态是否变为"已完成"，并奖励积分
        if new_status == "completed" and old_status != "completed":
            user = db.query(Student).filter(Student.id == current_user_id).first()
            if user:
                course_completion_points = 30
                await _award_points(
                    db=db,
                    user=user,
                    amount=course_completion_points,
                    reason=f"完成课程：'{user_course.course.title if user_course.course else course_id}'",
                    transaction_type="EARN",
                    related_entity_type="course",
                    related_entity_id=course_id
                )
                await _check_and_award_achievements(db, current_user_id)
                print(
                    f"DEBUG_POINTS_ACHIEVEMENT: 用户 {current_user_id} 完成课程 {course_id}，获得 {course_completion_points} 积分并检查成就 (待提交)。")

        db.commit()  # 现在，这里是唯一也是最终的提交！

        # 填充 UserCourseResponse 中的 Course 标题，如果需要的话
        if user_course.course is None:
            user_course.course = db.query(Course).filter(Course.id == user_course.course_id).first()

        print(f"DEBUG: 用户 {current_user_id} 课程 {course_id} 进度更新成功，所有事务已提交。")
        return user_course  # 返回 user_course 才能映射到 UserCourseResponse

    except Exception as e:  # 捕获所有异常并回滚
        db.rollback()
        print(
            f"ERROR_USER_COURSE_UPDATE_GLOBAL: 用户 {current_user_id} 课程 {course_id} 更新过程中发生错误，事务已回滚: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="课程更新失败: 系统错误",
        )