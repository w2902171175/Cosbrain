# project/services/course_service.py
"""
课程业务逻辑服务层
"""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.sql import func
from fastapi import HTTPException, status, UploadFile
import json
import logging
import os
import uuid

from project.models import Course, UserCourse, User, CourseLike, CourseMaterial
from project.utils import _get_text_part, get_resource_or_404
from project.ai_providers.ai_config import GLOBAL_PLACEHOLDER_ZERO_VECTOR
from project.ai_providers.embedding_provider import get_embeddings_from_api
from project.ai_providers.security_utils import decrypt_key
import project.schemas as schemas
import project.oss_utils as oss_utils

logger = logging.getLogger(__name__)

class CourseUtils:
    """课程相关工具类"""
    
    @staticmethod
    def parse_required_skills(required_skills: Any) -> List[Dict]:
        """统一处理required_skills字段的JSON解析"""
        if isinstance(required_skills, str):
            try:
                return json.loads(required_skills)
            except json.JSONDecodeError:
                return []
        elif required_skills is None:
            return []
        elif isinstance(required_skills, list):
            return required_skills
        else:
            return []

    @staticmethod
    def build_combined_text_for_course(course_data: Any, required_skills: List[Dict] = None) -> str:
        """为课程构建combined_text"""
        skills_text = ""
        if required_skills:
            skills_text = ", ".join([
                s.get("name", "") for s in required_skills 
                if isinstance(s, dict) and s.get("name")
            ])
        
        return ". ".join(filter(None, [
            _get_text_part(getattr(course_data, 'title', None)),
            _get_text_part(getattr(course_data, 'description', None)),
            _get_text_part(getattr(course_data, 'instructor', None)),
            _get_text_part(getattr(course_data, 'category', None)),
            _get_text_part(skills_text),
            _get_text_part(getattr(course_data, 'total_lessons', None)),
            _get_text_part(getattr(course_data, 'avg_rating', None))
        ])).strip()

    @staticmethod
    def build_combined_text_for_material(material_data: Any) -> str:
        """为课程材料构建combined_text"""
        return ". ".join(filter(None, [
            _get_text_part(getattr(material_data, 'title', None)),
            _get_text_part(getattr(material_data, 'content', None)),
            _get_text_part(getattr(material_data, 'url', None)),
            _get_text_part(getattr(material_data, 'original_filename', None)),
            _get_text_part(getattr(material_data, 'file_type', None)),
            _get_text_part(getattr(material_data, 'file_path', None))
        ])).strip()

    @staticmethod
    async def generate_embedding_for_admin(
        text_content: str,
        admin_user: User,
        default_vector=None
    ) -> List[float]:
        """统一的嵌入向量生成逻辑"""
        if not text_content:
            return default_vector or GLOBAL_PLACEHOLDER_ZERO_VECTOR
        
        try:
            admin_api_key = None
            if admin_user.llm_api_key_encrypted:
                try:
                    admin_api_key = decrypt_key(admin_user.llm_api_key_encrypted)
                except Exception as e:
                    logger.error(f"解密管理员API密钥失败: {e}")
            
            if admin_api_key:
                new_embedding = await get_embeddings_from_api(
                    [text_content],
                    api_key=admin_api_key,
                    llm_type=admin_user.llm_api_type,
                    llm_base_url=admin_user.llm_api_base_url,
                    llm_model_id=admin_user.llm_model_id
                )
                if new_embedding:
                    return new_embedding[0]
            
            return default_vector or GLOBAL_PLACEHOLDER_ZERO_VECTOR
        except Exception as e:
            logger.error(f"生成嵌入向量失败: {e}")
            return default_vector or GLOBAL_PLACEHOLDER_ZERO_VECTOR

class MaterialUtils:
    """材料相关工具类"""
    
    @staticmethod
    def validate_material_data(material_data: schemas.CourseMaterialCreate, file: Optional[UploadFile]):
        """验证材料数据"""
        validation_rules = {
            "file": (file, "文件类型材料必须上传文件"),
            "link": (material_data.url, "链接类型材料必须提供URL"),
            "text": (material_data.content, "文本类型材料必须提供内容")
        }
        
        condition, error_msg = validation_rules.get(material_data.type, (True, ""))
        if not condition:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    @staticmethod
    async def handle_file_upload(file: UploadFile) -> Dict[str, Any]:
        """处理文件上传逻辑"""
        if not file:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件上传为必填")
        
        file_bytes = await file.read()
        file_extension = os.path.splitext(file.filename)[1]
        object_name = f"course_materials/{uuid.uuid4().hex}{file_extension}"
        
        try:
            file_path = await oss_utils.upload_file_to_oss(
                file_bytes=file_bytes,
                object_name=object_name,
                content_type=file.content_type
            )
            
            return {
                "file_path": file_path,
                "original_filename": file.filename,
                "file_type": file.content_type,
                "size_bytes": file.size,
                "object_name": object_name
            }
        except Exception as e:
            logger.error(f"文件上传失败: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="文件上传失败")

    @staticmethod
    async def handle_oss_file_cleanup(file_path: str):
        """统一的OSS文件清理逻辑"""
        if not file_path:
            return
        
        try:
            import os
            oss_base_url = os.getenv("S3_BASE_URL", "").rstrip('/') + '/'
            if file_path.startswith(oss_base_url):
                object_name = file_path.replace(oss_base_url, '', 1)
                if object_name:
                    import asyncio
                    asyncio.create_task(oss_utils.delete_file_from_oss(object_name))
                    logger.info(f"已安排删除OSS文件: {object_name}")
        except Exception as e:
            logger.error(f"OSS文件清理失败: {e}")

class CourseService:
    """课程业务逻辑服务类"""
    
    @staticmethod
    async def create_course_with_embedding(
        course_data: schemas.CourseBase,
        admin_user: User,
        db: Session
    ) -> Course:
        """创建带嵌入向量的课程"""
        # 处理required_skills
        required_skills_list = []
        if course_data.required_skills:
            required_skills_list = [skill.model_dump() for skill in course_data.required_skills]

        # 构建combined_text
        combined_text = CourseUtils.build_combined_text_for_course(course_data, required_skills_list)

        # 生成嵌入向量
        embedding = await CourseUtils.generate_embedding_for_admin(combined_text, admin_user)

        # 创建课程
        db_course = Course(
            title=course_data.title,
            description=course_data.description,
            instructor=course_data.instructor,
            category=course_data.category,
            total_lessons=course_data.total_lessons,
            avg_rating=course_data.avg_rating,
            cover_image_url=course_data.cover_image_url,
            required_skills=required_skills_list,
            combined_text=combined_text,
            embedding=embedding
        )

        return db_course

    @staticmethod
    def get_courses_optimized(
        db: Session,
        current_user_id: Optional[int] = None,
        page: int = 1,
        page_size: int = 20,
        category: Optional[str] = None
    ) -> List[Course]:
        """优化的课程查询 - 修复N+1查询问题"""
        # 使用预加载避免N+1查询
        query = db.query(Course).options(
            joinedload(Course.likes),
            joinedload(Course.materials).load_only(
                CourseMaterial.id, 
                CourseMaterial.title, 
                CourseMaterial.type
            )
        )
        
        if category:
            query = query.filter(Course.category == category)
        
        # 分页
        offset = (page - 1) * page_size
        courses = query.offset(offset).limit(page_size).all()
        
        # 批量处理点赞状态 - 避免逐个查询
        if current_user_id and courses:
            course_ids = [course.id for course in courses]
            user_likes = set(
                like.course_id for like in 
                db.query(CourseLike.course_id).filter(
                    CourseLike.owner_id == current_user_id,
                    CourseLike.course_id.in_(course_ids)
                ).all()
            )
            
            for course in courses:
                course.is_liked_by_current_user = course.id in user_likes
                course.required_skills = CourseUtils.parse_required_skills(course.required_skills)
        else:
            for course in courses:
                course.is_liked_by_current_user = False
                course.required_skills = CourseUtils.parse_required_skills(course.required_skills)
        
        return courses

    @staticmethod
    def get_course_by_id_optimized(
        db: Session,
        course_id: int,
        current_user_id: Optional[int] = None
    ) -> Course:
        """优化的单个课程查询"""
        # 使用joinedload预加载点赞数据
        course = db.query(Course).options(
            joinedload(Course.likes),
            joinedload(Course.materials)
        ).filter(Course.id == course_id).first()
        
        if not course:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程未找到")

        # 检查当前用户是否点赞
        course.is_liked_by_current_user = any(
            like.owner_id == current_user_id for like in course.likes
        ) if current_user_id else False

        # 处理required_skills
        course.required_skills = CourseUtils.parse_required_skills(course.required_skills)
        
        return course

    @staticmethod
    async def update_course_with_embedding(
        course_id: int,
        course_data: schemas.CourseUpdate,
        admin_user: User,
        db: Session
    ) -> Course:
        """更新课程并重新生成嵌入向量"""
        db_course = get_resource_or_404(db, Course, course_id, "课程未找到")
        
        update_data = course_data.dict(exclude_unset=True)

        # 处理required_skills
        if "required_skills" in update_data:
            db_course.required_skills = update_data.pop("required_skills")

        # 应用其他字段更新
        for key, value in update_data.items():
            if hasattr(db_course, key):
                setattr(db_course, key, value)

        # 重建combined_text和embedding
        combined_text = CourseUtils.build_combined_text_for_course(
            db_course, 
            CourseUtils.parse_required_skills(db_course.required_skills)
        )
        
        db_course.combined_text = combined_text
        db_course.embedding = await CourseUtils.generate_embedding_for_admin(combined_text, admin_user)

        return db_course

    @staticmethod
    def enroll_course_optimized(
        course_id: int,
        current_user_id: int,
        db: Session
    ) -> UserCourse:
        """优化的课程报名逻辑"""
        # 验证课程存在
        db_course = get_resource_or_404(db, Course, course_id, "课程未找到")

        # 检查是否已报名
        existing_enrollment = db.query(UserCourse).filter(
            UserCourse.student_id == current_user_id,
            UserCourse.course_id == course_id
        ).first()

        if existing_enrollment:
            if not existing_enrollment.course:
                existing_enrollment.course = db_course
            logger.info(f"用户 {current_user_id} 已报名课程 {course_id}")
            return existing_enrollment

        # 创建新报名
        new_enrollment = UserCourse(
            student_id=current_user_id,
            course_id=course_id,
            progress=0.0,
            status="registered",
            last_accessed=func.now()
        )

        new_enrollment.course = db_course
        return new_enrollment

    @staticmethod
    def toggle_course_like(
        course_id: int,
        current_user_id: int,
        db: Session,
        action: str  # "like" or "unlike"
    ) -> Dict[str, Any]:
        """统一的点赞/取消点赞逻辑"""
        # 验证课程存在
        db_course = get_resource_or_404(db, Course, course_id, "课程未找到")
        
        # 查找现有点赞记录
        existing_like = db.query(CourseLike).filter(
            CourseLike.owner_id == current_user_id,
            CourseLike.course_id == course_id
        ).first()

        if action == "like":
            if existing_like:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已点赞该课程")
            
            # 创建点赞记录并更新计数
            db_like = CourseLike(owner_id=current_user_id, course_id=course_id)
            db_course.likes_count += 1
            
            return {"like": db_like, "course": db_course, "action": "created"}
        
        elif action == "unlike":
            if not existing_like:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到点赞记录")
            
            # 更新课程点赞计数并删除记录
            if db_course.likes_count > 0:
                db_course.likes_count -= 1
            
            return {"like": existing_like, "course": db_course, "action": "deleted"}
        
        else:
            raise ValueError(f"不支持的操作: {action}")
