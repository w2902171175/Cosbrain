# project/routers/courses/courses.py
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Response, Query
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from typing import List, Optional, Dict, Any, Literal
import os, uuid, asyncio
import logging

# 导入数据库和模型
from project.database import get_db
from project.models import Course, UserCourse, User, CourseLike, CourseMaterial
import project.schemas as schemas, project.oss_utils as oss_utils
from project.utils import (get_resource_or_404, debug_operation, _award_points, _check_and_award_achievements)

# 导入新的服务层和错误处理
from project.services.course_service import CourseService, CourseUtils, MaterialUtils
from project.utils.core.error_decorators import handle_database_errors, database_transaction, safe_db_operation

# 创建路由器
router = APIRouter(
    prefix="/courses",
    tags=["课程管理"],
    responses={404: {"description": "Not found"}},
)

# --- 学生相关接口 ---
@router.get("/students/", response_model=List[schemas.StudentResponse], summary="获取所有学生列表")
def get_all_students(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小")
):
    """获取学生列表，支持分页"""
    offset = (page - 1) * page_size
    students = db.query(User).offset(offset).limit(page_size).all()
    debug_operation("获取学生列表", count=len(students), page=page)
    return students

@router.get("/students/{student_id}", response_model=schemas.StudentResponse, summary="获取指定学生详情")
def get_student_by_id(student_id: int, db: Session = Depends(get_db)):
    """获取学生详情"""
    student = get_resource_or_404(db, User, student_id, "学生未找到")
    debug_operation("获取学生详情", resource_id=student_id)
    return student

# 导入认证相关依赖
from project.utils import get_current_user_id, is_admin_user

# 配置日志
logger = logging.getLogger(__name__)

# ============================================================================
# 路由接口
# ============================================================================

# --- 课程路由 ---
@router.post("/", response_model=schemas.CourseResponse, summary="创建新课程")
@handle_database_errors("创建课程")
async def create_course(
        course_data: schemas.CourseBase,
        current_admin_user: User = Depends(is_admin_user),
        db: Session = Depends(get_db)
):
    """创建新课程 - 优化版本"""
    logger.info(f"管理员 {current_admin_user.id} 创建课程: {course_data.title}")

    # 使用服务层创建课程
    db_course = await CourseService.create_course_with_embedding(
        course_data, current_admin_user, db
    )
    
    # 使用事务安全操作
    with database_transaction(db):
        db.add(db_course)
        db.flush()
        db.refresh(db_course)

    # 确保返回格式正确
    db_course.required_skills = CourseUtils.parse_required_skills(db_course.required_skills)
    
    logger.info(f"课程 '{db_course.title}' 创建成功")
    return db_course

@router.get("/", response_model=List[schemas.CourseResponse], summary="获取所有课程列表")
async def get_all_courses(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, le=1000, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小"),
    category: Optional[str] = Query(None, max_length=50, description="分类过滤")
):
    """获取课程列表 - 优化查询性能，修复N+1查询问题"""
    # 使用优化的服务层方法
    courses = CourseService.get_courses_optimized(
        db=db,
        current_user_id=current_user_id,
        page=page,
        page_size=page_size,
        category=category
    )

    debug_operation("获取课程列表", user_id=current_user_id, count=len(courses), page=page)
    return courses

@router.get("/{course_id}", response_model=schemas.CourseResponse, summary="获取指定课程详情")
def get_course_by_id(
    course_id: int, 
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取课程详情 - 优化查询，修复N+1查询问题"""
    # 使用优化的服务层方法
    course = CourseService.get_course_by_id_optimized(
        db=db,
        course_id=course_id,
        current_user_id=current_user_id
    )
    
    return course

@router.put("/{course_id}", response_model=schemas.CourseResponse, summary="更新指定课程")
@handle_database_errors("更新课程")
async def update_course(
    course_id: int,
    course_data: schemas.CourseUpdate,
    current_admin_user: User = Depends(is_admin_user),
    db: Session = Depends(get_db)
):
    """更新课程 - 优化版本"""
    logger.info(f"管理员 {current_admin_user.id} 更新课程 {course_id}")

    # 使用服务层更新课程
    db_course = await CourseService.update_course_with_embedding(
        course_id, course_data, current_admin_user, db
    )
    
    # 使用事务安全操作
    with database_transaction(db):
        db.add(db_course)
        db.flush()
        db.refresh(db_course)

    # 确保返回格式正确
    db_course.required_skills = CourseUtils.parse_required_skills(db_course.required_skills)
    
    logger.info(f"课程 {course_id} 更新成功")
    return db_course

@router.post("/{course_id}/enroll", response_model=schemas.UserCourseResponse, summary="用户报名课程")
@handle_database_errors("课程报名")
def enroll_course(
    course_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """课程报名 - 优化版本"""
    logger.info(f"用户 {current_user_id} 报名课程 {course_id}")

    # 使用服务层处理报名逻辑
    enrollment = CourseService.enroll_course_optimized(
        course_id, current_user_id, db
    )
    
    # 如果是新报名，需要保存到数据库
    if not enrollment.id:
        with database_transaction(db):
            db.add(enrollment)
            db.flush()
            db.refresh(enrollment)

    logger.info(f"用户 {current_user_id} 成功报名课程 {course_id}")
    return enrollment

@router.post("/{course_id}/materials/", response_model=schemas.CourseMaterialResponse,
             summary="为指定课程上传新材料")
@handle_database_errors("创建课程材料")
async def create_course_material(
    course_id: int,
    file: Optional[UploadFile] = File(None),
    material_data: schemas.CourseMaterialCreate = Depends(),
    current_admin_user: User = Depends(is_admin_user),
    db: Session = Depends(get_db)
):
    """创建课程材料 - 重构版本"""
    logger.info(f"管理员 {current_admin_user.id} 为课程 {course_id} 创建材料: {material_data.title}")

    # 验证课程存在
    get_resource_or_404(db, Course, course_id, "课程未找到")
    
    # 验证材料数据
    MaterialUtils.validate_material_data(material_data, file)

    rollback_object_name = None
    
    # 准备材料参数
    material_params = {
        "course_id": course_id,
        "title": material_data.title,
        "type": material_data.type,
        "content": material_data.content,
        "url": None,
        "file_path": None,
        "original_filename": None,
        "file_type": None,
        "size_bytes": None
    }

    # 根据类型处理数据
    if material_data.type == "file":
        file_info = await MaterialUtils.handle_file_upload(file)
        material_params.update(file_info)
        rollback_object_name = file_info["object_name"]
    elif material_data.type == "link":
        material_params["url"] = material_data.url

    # 生成combined_text和embedding
    combined_text = CourseUtils.build_combined_text_for_material(type('obj', (), material_params))
    embedding = await CourseUtils.generate_embedding_for_admin(combined_text, current_admin_user)

    material_params.update({
        "combined_text": combined_text,
        "embedding": embedding
    })

    # 创建数据库记录
    db_material = CourseMaterial(**material_params)
    
    try:
        with database_transaction(db):
            db.add(db_material)
            db.flush()
            db.refresh(db_material)

        logger.info(f"课程材料 '{db_material.title}' 创建成功")
        return db_material

    except Exception as e:
        if rollback_object_name:
            await MaterialUtils.handle_oss_file_cleanup(f"{os.getenv('S3_BASE_URL', '').rstrip('/')}/{rollback_object_name}")
        raise

@router.get("/{course_id}/materials/", response_model=List[schemas.CourseMaterialResponse],
            summary="获取指定课程的所有材料列表")
def get_course_materials(
    course_id: int,
    db: Session = Depends(get_db),
    type_filter: Optional[Literal["file", "link", "text"]] = None,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小")
):
    """获取课程材料列表 - 优化查询"""
    print(f"DEBUG: 获取课程 {course_id} 的材料列表")
    
    # 验证课程存在
    get_resource_or_404(db, Course, course_id, "课程未找到")

    query = db.query(CourseMaterial).filter(CourseMaterial.course_id == course_id)
    
    if type_filter:
        query = query.filter(CourseMaterial.type == type_filter)

    # 分页
    offset = (page - 1) * page_size
    materials = query.order_by(CourseMaterial.created_at.desc()).offset(offset).limit(page_size).all()
    
    print(f"DEBUG: 课程 {course_id} 获取到 {len(materials)} 个材料")
    return materials

@router.get("/{course_id}/materials/{material_id}", response_model=schemas.CourseMaterialResponse,
            summary="获取指定课程材料详情")
def get_course_material_detail(
    course_id: int,
    material_id: int,
    db: Session = Depends(get_db)
):
    """获取课程材料详情 - 优化版本"""
    print(f"DEBUG: 获取课程 {course_id} 材料 {material_id} 详情")
    
    db_material = db.query(CourseMaterial).filter(
        CourseMaterial.id == material_id,
        CourseMaterial.course_id == course_id
    ).first()
    
    if not db_material:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程材料未找到或不属于该课程")
    
    return db_material

@router.put("/{course_id}/materials/{material_id}", response_model=schemas.CourseMaterialResponse,
            summary="更新指定课程材料")
@handle_database_errors("更新课程材料")
async def update_course_material(
    course_id: int,
    material_id: int,
    file: Optional[UploadFile] = File(None, description="可选：上传新文件替换旧文件"),
    material_data: schemas.CourseMaterialUpdate = Depends(),
    current_admin_user: User = Depends(is_admin_user),
    db: Session = Depends(get_db)
):
    """更新课程材料 - 重构版本"""
    logger.info(f"管理员 {current_admin_user.id} 更新课程 {course_id} 材料 {material_id}")

    # 验证材料存在
    db_material = db.query(CourseMaterial).filter(
        CourseMaterial.id == material_id,
        CourseMaterial.course_id == course_id
    ).first()
    if not db_material:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程材料未找到或不属于该课程")

    # 验证课程存在
    get_resource_or_404(db, Course, course_id, "课程未找到")

    rollback_object_name = None
    old_file_path = db_material.file_path

    update_data = material_data.dict(exclude_unset=True)

    # 处理类型变更
    type_changed = "type" in update_data and update_data["type"] != db_material.type
    if type_changed:
        # 如果从文件类型改为其他类型，清理OSS文件
        if db_material.type == "file" and old_file_path:
            await MaterialUtils.handle_oss_file_cleanup(old_file_path)
        
        # 清理字段
        if update_data["type"] in ["link", "text"]:
            db_material.file_path = None
            db_material.original_filename = None
            db_material.file_type = None
            db_material.size_bytes = None

    # 处理文件上传
    if file:
        if db_material.type == "file" and old_file_path:
            await MaterialUtils.handle_oss_file_cleanup(old_file_path)
        
        file_info = await MaterialUtils.handle_file_upload(file)
        update_data.update(file_info)
        rollback_object_name = file_info["object_name"]
        update_data["type"] = "file"

    # 验证更新后的数据
    if update_data.get("type") == "file" and not update_data.get("file_path") and not db_material.file_path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件类型材料必须有文件")
    elif update_data.get("type") == "link" and not update_data.get("url") and not db_material.url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="链接类型材料必须有URL")
    elif update_data.get("type") == "text" and not update_data.get("content") and not db_material.content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文本类型材料必须有内容")

    # 应用更新
    for key, value in update_data.items():
        if hasattr(db_material, key):
            setattr(db_material, key, value)

    # 重新生成combined_text和embedding
    combined_text = CourseUtils.build_combined_text_for_material(db_material)
    embedding = await CourseUtils.generate_embedding_for_admin(combined_text, current_admin_user)

    db_material.combined_text = combined_text
    db_material.embedding = embedding

    try:
        with database_transaction(db):
            db.add(db_material)
            db.flush()
            db.refresh(db_material)

        logger.info(f"课程材料 {material_id} 更新成功")
        return db_material

    except Exception as e:
        if rollback_object_name:
            await MaterialUtils.handle_oss_file_cleanup(f"{os.getenv('S3_BASE_URL', '').rstrip('/')}/{rollback_object_name}")
        raise

@router.delete("/{course_id}/materials/{material_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="删除指定课程材料")
async def delete_course_material(
    course_id: int,
    material_id: int,
    current_admin_user: User = Depends(is_admin_user),
    db: Session = Depends(get_db)
):
    """删除课程材料 - 优化版本"""
    logger.info(f"管理员 {current_admin_user.id} 删除课程 {course_id} 材料 {material_id}")

    db_material = db.query(CourseMaterial).filter(
        CourseMaterial.id == material_id,
        CourseMaterial.course_id == course_id
    ).first()
    
    if not db_material:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程材料未找到或不属于该课程")

    # 如果是文件类型，删除OSS文件
    if db_material.type == "file" and db_material.file_path:
        await MaterialUtils.handle_oss_file_cleanup(db_material.file_path)

    with database_transaction(db):
        db.delete(db_material)
    
    logger.info(f"课程材料 {material_id} 已删除")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post("/{course_id}/like", response_model=schemas.CourseLikeResponse, summary="点赞指定课程")
@handle_database_errors("课程点赞")
def like_course_item(
    course_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """点赞课程 - 优化版本"""
    logger.info(f"用户 {current_user_id} 点赞课程 {course_id}")
    
    # 使用服务层统一处理点赞逻辑
    result = CourseService.toggle_course_like(
        course_id, current_user_id, db, "like"
    )
    
    # 保存到数据库
    with database_transaction(db):
        db.add(result["like"])
        db.add(result["course"])
        db.flush()
        db.refresh(result["like"])

    logger.info(f"用户 {current_user_id} 点赞课程 {course_id} 成功")
    return result["like"]

@router.delete("/{course_id}/unlike", status_code=status.HTTP_204_NO_CONTENT, summary="取消点赞课程")
@handle_database_errors("取消点赞")
def unlike_course_item(
    course_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """取消点赞课程 - 优化版本"""
    logger.info(f"用户 {current_user_id} 取消点赞课程 {course_id}")
    
    # 使用服务层统一处理取消点赞逻辑
    result = CourseService.toggle_course_like(
        course_id, current_user_id, db, "unlike"
    )
    
    # 保存到数据库
    with database_transaction(db):
        db.delete(result["like"])
        db.add(result["course"])

    logger.info(f"用户 {current_user_id} 取消点赞课程 {course_id} 成功")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.put("/{course_id}/progress", response_model=schemas.UserCourseResponse,
            summary="更新当前用户课程学习进度和状态")
async def update_user_course_progress(
    course_id: int,
    update_data: Dict[str, Any],
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """更新课程进度 - 优化版本"""
    print(f"DEBUG: 用户 {current_user_id} 更新课程 {course_id} 进度")

    try:
        user_course = db.query(UserCourse).filter(
            UserCourse.student_id == current_user_id,
            UserCourse.course_id == course_id
        ).first()

        if not user_course:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户未注册该课程")

        old_status = user_course.status
        new_status = update_data.get("status")

        # 更新进度和状态
        if "progress" in update_data and isinstance(update_data["progress"], (int, float)):
            user_course.progress = update_data["progress"]
        if "status" in update_data and isinstance(update_data["status"], str):
            user_course.status = update_data["status"]

        user_course.last_accessed = func.now()
        db.add(user_course)

        # 处理课程完成奖励
        if new_status == "completed" and old_status != "completed":
            db.flush()  # 确保状态已更新
            
            user = db.query(User).filter(User.id == current_user_id).first()
            if user:
                await _award_points(
                    db=db,
                    user=user,
                    amount=30,
                    reason=f"完成课程：'{user_course.course.title if user_course.course else course_id}'",
                    transaction_type="EARN",
                    related_entity_type="course",
                    related_entity_id=course_id
                )
                await _check_and_award_achievements(db, current_user_id)
                print(f"DEBUG: 用户完成课程，获得30积分并检查成就")

        db.commit()

        # 填充课程信息
        if not user_course.course:
            user_course.course = db.query(Course).filter(Course.id == course_id).first()

        print(f"DEBUG: 用户 {current_user_id} 课程 {course_id} 进度更新成功")
        return user_course

    except Exception as e:
        db.rollback()
        if isinstance(e, HTTPException):
            raise e
        print(f"ERROR: 课程进度更新失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="课程进度更新失败")

# 模块加载日志
logger = logging.getLogger(__name__)
logger.info("📚 Courses Module - 课程管理模块已加载")