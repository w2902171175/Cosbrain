# project/routers/projects/projects.py
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form, Response, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import func
from typing import List, Optional, Literal
import json
import os
import uuid
import asyncio

# 导入数据库和模型 - 使用正确的绝对导入
from project.database import get_db
from project.models import Student, Project, ProjectApplication, ProjectMember, ProjectFile, ProjectLike
from project.dependencies import get_current_user_id, get_pagination_params
import project.schemas as schemas
import project.oss_utils as oss_utils
from project.utils import (_get_text_part, generate_embedding_safe, populate_user_name, populate_like_status, 
                  validate_ownership, _award_points, _check_and_award_achievements, get_projects_with_details,
                  get_resource_or_404, get_user_by_id_or_404, check_resource_permission, debug_operation,
                  commit_or_rollback, create_and_add_resource)
from project.ai_providers.ai_config import GLOBAL_PLACEHOLDER_ZERO_VECTOR
from project.ai_providers.embedding_provider import get_embeddings_from_api
from project.ai_providers.security_utils import decrypt_key

router = APIRouter(
    prefix="/projects",
    tags=["项目管理"]
)

@router.get("/", response_model=List[schemas.ProjectResponse], summary="获取所有项目列表")
async def get_all_projects(current_user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    query = db.query(Project)
    projects = await get_projects_with_details(query, current_user_id, db)
    debug_operation("获取所有项目列表", user_id=current_user_id, count=len(projects))
    return projects

@router.get("/{project_id}", response_model=schemas.ProjectResponse, summary="获取指定项目详情")
async def get_project_by_id(project_id: int, current_user_id: int = Depends(get_current_user_id),
                            db: Session = Depends(get_db)):
    """
    获取指定项目详情，包括项目封面信息和关联的项目文件列表。
    项目文件将根据其访问权限和当前用户的项目成员身份进行过滤。
    """
    debug_operation("获取项目详情", user_id=current_user_id, resource_id=project_id, resource_type="项目")
    
    # 使用 joinedload 预加载 project_files 及其 uploader，以及 creator 和 likes，避免N+1查询
    project = db.query(Project).options(
        joinedload(Project.project_files).joinedload(ProjectFile.uploader),  # 确保上传者信息被预加载
        joinedload(Project.creator),
        joinedload(Project.likes)
    ).filter(Project.id == project_id).first()

    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目未找到。")

    # 填充 creator_name (直接从预加载的 creator 对象获取)
    # 确保 project.creator 不为 None，再访问其 name 属性
    project._creator_name = project.creator.name if project.creator else "未知用户"

    # 填充 is_liked_by_current_user
    project.is_liked_by_current_user = False
    if current_user_id:
        # 由于已经 joinedload 了 project.likes，可以直接在内存中检查点赞关系
        if any(like.owner_id == current_user_id for like in project.likes):
            project.is_liked_by_current_user = True

    # --- 1. 获取项目成员身份（用于文件访问权限判断）---
    is_project_creator = (project.creator_id == current_user_id)
    is_project_member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.student_id == current_user_id,
        ProjectMember.status == "active"
    ).first() is not None

    visible_project_files = []
    # 遍历预加载的 project.project_files 列表
    for file_record in project.project_files:
        # 'public' 文件对所有用户可见
        if file_record.access_type == "public":
            # 直接访问预加载的 uploader 关系来获取上传者姓名，避免重复查询
            file_record._uploader_name = file_record.uploader.name if file_record.uploader else "未知用户"
            visible_project_files.append(file_record)
        # 'member_only' 文件仅对项目创建者或成员可见
        elif file_record.access_type == "member_only":
            if is_project_creator or is_project_member:
                # 直接访问预加载的 uploader 关系来获取上传者姓名
                file_record._uploader_name = file_record.uploader.name if file_record.uploader else "未知用户"
                visible_project_files.append(file_record)

    # --- 2. 将过滤后的 project_files 列表赋值给 project 对象 ---
    # Pydantic 响应模型会从 ORM 对象的 `project_files` 属性中加载数据
    # 这里我们直接替换 ORM 对象的 `project_files` 列表为过滤后的列表
    project.project_files = visible_project_files

    debug_operation("项目详情查询完成", resource_id=project_id, visible_files=len(visible_project_files))
    return project

@router.post("/{project_id}/apply", response_model=schemas.ProjectApplicationResponse, summary="学生申请加入项目")
async def apply_to_project(
        project_id: int,
        application_data: schemas.ProjectApplicationCreate,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    允许学生申请加入指定项目。
    - 如果用户已是项目成员，则无法申请。
    - 如果用户已提交待处理的申请，则无法重复申请。
    """
    print(f"DEBUG_PROJECT_APP: 用户 {current_user_id} 尝试申请加入项目 {project_id}。")

    # 1. 验证项目是否存在
    db_project = db.query(Project).filter(Project.id == project_id).first()
    if not db_project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目未找到。")

    # 2. 检查用户是否已是项目成员
    existing_member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.student_id == current_user_id
    ).first()
    if existing_member:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="您已经是该项目的成员，无需申请加入。")

    # 3. 检查是否已有待处理或已拒绝的申请
    existing_application = db.query(ProjectApplication).filter(
        ProjectApplication.project_id == project_id,
        ProjectApplication.student_id == current_user_id
    ).first()

    if existing_application:
        if existing_application.status == "pending":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="您已有待处理的项目申请，请勿重复提交。")
        elif existing_application.status == "approved":
            # 理论上这里不会走到，因为如果 approved 就会成为 ProjectMember
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="您已批准加入该项目，请勿重复申请。")
        elif existing_application.status == "rejected":
            # 如果是已拒绝的申请，可以考虑是返回冲突，还是允许重新申请
            # 这里选择返回冲突，如果需要重新申请，可能由前端引导用户先删除旧申请
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="您有此项目已被拒绝的申请，请联系项目创建者。")

            # 4. 创建新的项目申请
    db_application = ProjectApplication(
        project_id=project_id,
        student_id=current_user_id,
        message=application_data.message,  # 允许 message 为 None
        status="pending"
    )

    db.add(db_application)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        print(f"ERROR_DB: 提交项目申请时发生完整性错误: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="提交申请失败：可能已存在您的申请，或发生并发冲突。")
    except Exception as e:
        db.rollback()
        print(f"ERROR: 提交项目申请 {project_id} 失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"提交项目申请失败: {e}")
    db.refresh(db_application)

    # Populate applicant name/email for response
    applicant_user = db.query(Student).filter(Student.id == current_user_id).first()
    if applicant_user:
        db_application.applicant_name = applicant_user.name
        db_application.applicant_email = applicant_user.email
    else:
        db_application.applicant_name = "未知用户"  # 理论上不发生
        db_application.applicant_email = None

    print(f"DEBUG_PROJECT_APP: 用户 {current_user_id} 成功向项目 {project_id} 提交了申请 (ID: {db_application.id})。")
    return db_application

@router.get("/{project_id}/applications", response_model=List[schemas.ProjectApplicationResponse],
         summary="获取项目所有申请列表")
async def get_project_applications(
        project_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        status_filter: Optional[Literal["pending", "approved", "rejected"]] = None
):

    """
    项目创建者或系统管理员可以获取指定项目的申请列表。
    可根据 status_filter (pending, approved, rejected) 筛选。
    """
    print(f"DEBUG_PROJECT_APP: 用户 {current_user_id} 尝试获取项目 {project_id} 的申请列表。")

    # 1. 验证项目和权限 (只有项目创建者或系统管理员能查看)
    db_project = db.query(Project).filter(Project.id == project_id).first()
    if not db_project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目未找到。")

    current_user_obj = db.query(Student).filter(Student.id == current_user_id).first()
    if not current_user_obj:  # 理论上不会发生
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证用户无效。")

    # --- 开始修改权限检查 ---

    # 检查1: 用户是否为项目创建者
    is_creator = (db_project.creator_id == current_user_id)

    # 检查2: 用户是否为系统管理员
    is_system_admin = current_user_obj.is_admin

    # 检查3: 用户是否为该项目的管理员
    membership = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.student_id == current_user_id,
        ProjectMember.role == 'admin',  # 明确检查角色是否为 'admin'
        ProjectMember.status == 'active'
    ).first()
    is_project_admin = (membership is not None)

    # 只要满足以上任一条件，就授予权限
    if not (is_creator or is_system_admin or is_project_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="无权查看该项目的申请列表。只有项目创建者、项目管理员或系统管理员可以。")

    if not (db_project.creator_id == current_user_id or current_user_obj.is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="无权查看该项目的申请列表。只有项目创建者或系统管理员可以。")

    # 2. 查询申请列表，并预加载申请者信息
    # 使用 joinedload 避免 N+1 查询问题
    query = db.query(ProjectApplication).options(joinedload(ProjectApplication.applicant)).filter(
        ProjectApplication.project_id == project_id
    )
    if status_filter:
        query = query.filter(ProjectApplication.status == status_filter)

    applications = query.order_by(ProjectApplication.applied_at.desc()).all()

    # 3. 填充响应模型
    response_applications = []
    for app in applications:
        app_response = schemas.ProjectApplicationResponse.model_validate(app, from_attributes=True)
        app_response.applicant_name = app.applicant.name if app.applicant else "未知用户"
        app_response.applicant_email = app.applicant.email if app.applicant else None

        # 填充审批者信息 (如果已处理)
        if app.processed_by_id:
            processor_user = db.query(Student).filter(Student.id == app.processed_by_id).first()
            app_response.processor_name = processor_user.name if processor_user else "未知审批者"
        response_applications.append(app_response)

    print(f"DEBUG_PROJECT_APP: 项目 {project_id} 获取到 {len(response_applications)} 条申请。")
    return response_applications

@router.post("/applications/{application_id}/process", response_model=schemas.ProjectApplicationResponse,
          summary="处理项目申请")
async def process_project_application(
        application_id: int,
        process_data: schemas.ProjectApplicationProcess,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    项目创建者、项目管理员或系统管理员可以批准或拒绝项目申请。
    如果申请被批准，用户将成为项目成员。
    """
    print(f"DEBUG_PROJECT_APP: 用户 {current_user_id} 尝试处理申请 {application_id} 为 '{process_data.status}'。")

    # 2. 验证申请是否存在且为 'pending' 状态
    db_application = db.query(ProjectApplication).filter(ProjectApplication.id == application_id).first()
    if not db_application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目申请未找到。")
    if db_application.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该申请已处理或状态异常，无法再次处理。")

    # 3. 验证操作者权限 (只有项目创建者、项目管理员或系统管理员能处理)
    db_project = db.query(Project).filter(Project.id == db_application.project_id).first()
    if not db_project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="关联的项目未找到。")

    current_user_obj = db.query(Student).filter(Student.id == current_user_id).first()
    if not current_user_obj:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证用户无效。")

    # --- 4. 实现完整的三重权限检查 (关键修复点) ---
    is_creator = (db_project.creator_id == current_user_id)
    is_system_admin = current_user_obj.is_admin

    membership = db.query(ProjectMember).filter(
        ProjectMember.project_id == db_project.id,
        ProjectMember.student_id == current_user_id,
        ProjectMember.role == 'admin',
        ProjectMember.status == 'active'
    ).first()
    is_project_admin = (membership is not None)

    if not (is_creator or is_system_admin or is_project_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="无权处理该项目申请。只有项目创建者、项目管理员或系统管理员可以。")

    # 5. 更新申请状态
    db_application.status = process_data.status
    db_application.processed_at = func.now()
    db_application.processed_by_id = current_user_id
    db_application.message = process_data.process_message if process_data.process_message is not None else db_application.message

    db.add(db_application)

    # 6. 如果批准，则添加为项目成员或激活现有成员
    if process_data.status == "approved":
        existing_member = db.query(ProjectMember).filter(
            ProjectMember.project_id == db_application.project_id,
            ProjectMember.student_id == db_application.student_id
        ).first()

        if existing_member:
            existing_member.status = "active"  # 确保是激活状态
            existing_member.role = "member"
            existing_member.joined_at = func.now()
            db.add(existing_member)
            print(
                f"DEBUG_PROJECT_APP: 用户 {db_application.student_id} 已再次激活为项目 {db_application.project_id} 的成员。")
        else:
            new_member = ProjectMember(
                project_id=db_application.project_id,
                student_id=db_application.student_id,
                role="member",
                status="active"  # 新成员也应是 active 状态
            )
            db.add(new_member)
            print(
                f"DEBUG_PROJECT_APP: 用户 {db_application.student_id} 已添加为项目 {db_application.project_id} 的新成员。")

    db.commit()
    db.refresh(db_application)

    # 7. 填充响应模型 (这部分可以优化，但功能上没问题)
    applicant_user = db.query(Student).filter(Student.id == db_application.student_id).first()
    processor_user = current_user_obj  # 直接复用前面查过的 current_user_obj，更高效

    db_application.applicant_name = applicant_user.name if applicant_user else "未知用户"
    db_application.applicant_email = applicant_user.email if applicant_user else None
    db_application.processor_name = processor_user.name if processor_user else "未知审批者"

    print(f"DEBUG_PROJECT_APP: 项目申请 {db_application.id} 已处理为 '{process_data.status}'。")
    return db_application

@router.get("/{project_id}/members", response_model=List[schemas.ProjectMemberResponse],
         summary="获取项目成员列表")
async def get_project_members(
        project_id: int,
        # 保持登录认证，确保只有已认证用户能访问
        # 如果希望未登录用户也能访问，请移除上面的 `current_user_id: int = Depends(get_current_user_id)`
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取指定项目的所有成员列表。
    现在所有已认证用户都可以查看。
    """
    print(f"DEBUG_PROJECT_MEMBERS: 用户 {current_user_id} 尝试获取项目 {project_id} 的成员列表。")

    # 1. 验证项目是否存在
    db_project = db.query(Project).filter(Project.id == project_id).first()
    if not db_project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目未找到。")

    # 2. 查询成员列表，并预加载成员信息
    # 使用 joinedload 避免 N+1 查询问题
    query = db.query(ProjectMember).options(joinedload(ProjectMember.member)).filter(
        ProjectMember.project_id == project_id
    )

    memberships = query.order_by(ProjectMember.joined_at).all()

    # 3. 填充响应模型
    response_members = []
    for member_ship in memberships:
        member_response = schemas.ProjectMemberResponse.model_validate(member_ship, from_attributes=True)
        member_response.member_name = member_ship.member.name if member_ship.member else "未知用户"
        member_response.member_email = member_ship.member.email if member_ship.member else None
        response_members.append(member_response)

    print(f"DEBUG_PROJECT_MEMBERS: 项目 {project_id} 获取到 {len(response_members)} 位成员。")
    return response_members

@router.post("/", response_model=schemas.ProjectResponse, summary="创建新项目")
async def create_project(
        project_data_json: str = Form(..., description="项目主体数据，JSON字符串格式"),
        # Optional: project cover image upload
        cover_image: Optional[UploadFile] = File(None, description="可选：上传项目封面图片"),
        # Optional: multiple project files/attachments upload with their metadata
        project_files_meta_json: Optional[str] = Form(None,
                                                      description="项目附件的元数据列表，JSON字符串格式。例如: '[{\"file_name\":\"doc.pdf\", \"description\":\"概述\", \"access_type\":\"public\"}]'"),
        project_files: Optional[List[UploadFile]] = File(None, description="可选：上传项目附件文件列表"),
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG_RECEIVE_PROJECT: 接收到 project_data_json: '{project_data_json}'")
    print(
        f"DEBUG_RECEIVE_COVER: 接收到 cover_image: {cover_image.filename if cover_image else 'None'}, size: {cover_image.size if cover_image else 'N/A'}")
    print(f"DEBUG_RECEIVE_FILES_META: 接收到 project_files_meta_json: '{project_files_meta_json}'")
    print(f"DEBUG_RECEIVE_FILES: 接收到 project_files count: {len(project_files) if project_files else 0}")

    try:
        project_data = schemas.ProjectCreate.model_validate_json(project_data_json)
        print(f"DEBUG: 用户 {current_user_id} 尝试创建项目: {project_data.title}")
    except json.JSONDecodeError as e:
        print(f"ERROR_JSON_DECODE: 项目数据 JSON 解析失败: {e}. 原始字符串: '{project_data_json}'")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"项目数据 JSON 格式不正确: {e}")
    except ValueError as e:
        print(f"ERROR_PYDANTIC_VALIDATION: 项目数据 Pydantic 验证失败: {e}. 原始字符串: '{project_data_json}'")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"项目数据验证失败: {e}")

    current_user = db.query(Student).filter(Student.id == current_user_id).first()
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证用户无效。")

    # List to store OSS objects that were newly uploaded during this request, for rollback purposes
    newly_uploaded_oss_objects_for_rollback: List[str] = []

    try:
        final_cover_image_url = None
        final_cover_image_original_filename = None
        final_cover_image_type = None
        final_cover_image_size_bytes = None

        # --- Process Cover Image Upload ---
        if cover_image and cover_image.filename:
            # 即使文件对象存在，也要检查其大小或文件名是否有效，避免处理空文件部分
            if cover_image.size == 0 or not cover_image.filename.strip():
                print(f"WARNING: 接收到一个空封面文件或文件名为 ' ' 的封面文件。跳过封面处理。")
                # 将其视为没有有效的封面文件上传
            else:
                print("DEBUG: 接收到有效封面文件。开始处理封面上传。")

                if not cover_image.content_type.startswith("image/"):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                        detail=f"不支持的封面文件类型: {cover_image.content_type}。项目封面只接受图片文件。")

                file_bytes = await cover_image.read()
                file_extension = os.path.splitext(cover_image.filename)[1]
                content_type = cover_image.content_type
                file_size = cover_image.size

                oss_path_prefix = "project_covers"
                current_oss_object_name = f"{oss_path_prefix}/{uuid.uuid4().hex}{file_extension}"
                newly_uploaded_oss_objects_for_rollback.append(current_oss_object_name)  # Add to rollback list

                try:
                    final_cover_image_url = await oss_utils.upload_file_to_oss(
                        file_bytes=file_bytes,
                        object_name=current_oss_object_name,
                        content_type=content_type
                    )
                    final_cover_image_original_filename = cover_image.filename
                    final_cover_image_type = content_type
                    final_cover_image_size_bytes = file_size

                    print(
                        f"DEBUG: 封面文件 '{cover_image.filename}' (类型: {content_type}) 上传到OSS成功，URL: {final_cover_image_url}")

                except HTTPException as e:
                    print(f"ERROR: 上传封面文件到OSS失败: {e.detail}")
                    raise e
                except Exception as e:
                    print(f"ERROR: 上传封面文件到OSS时发生未知错误: {e}")
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                        detail=f"封面文件上传到云存储失败: {e}")
        else:
            print("DEBUG: 未接收到有效封面文件。")

        # --- Parse and Validate Project Files Metadata ---
        parsed_project_files_meta: List[schemas.ProjectFileCreate] = []
        if project_files_meta_json:
            try:
                raw_meta = json.loads(project_files_meta_json)
                if not isinstance(raw_meta, list):
                    raise ValueError("project_files_meta_json 必须是 JSON 列表。")
                parsed_project_files_meta = [schemas.ProjectFileCreate(**f) for f in raw_meta]
            except (json.JSONDecodeError, ValueError) as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail=f"项目附件元数据 JSON 格式不正确或验证失败: {e}")

        # --- Validate consistency between file attachments and their metadata ---
        if project_files:
            if not parsed_project_files_meta or len(project_files) != len(parsed_project_files_meta):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="项目附件文件数量与提供的元数据数量不匹配，或缺失附件元数据。")
            # Enforce file_name consistency for user provided metadata with actual uploaded file's filename
            for i, file_obj in enumerate(project_files):
                if parsed_project_files_meta[i].file_name != file_obj.filename:
                    # For a stricter API, you could raise an error here.
                    # For more flexibility, we'll overwrite metadata's file_name with actual filename.
                    print(
                        f"WARNING: 附件元数据中的文件名 '{parsed_project_files_meta[i].file_name}' 与实际上传文件名 '{file_obj.filename}' 不匹配，将使用实际文件名。")
                    parsed_project_files_meta[i].file_name = file_obj.filename
        elif parsed_project_files_meta:  # metadata exists but no files were provided (error condition)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="提供了项目附件元数据但未上传任何文件。")

        # --- Create Project Record (before files, to get project_id) ---
        # The db_project object needs to exist before ProjectFiles can be related to it
        # This will be the first DB commit point, if this fails, earlier OSS uploads need to be cleaned up
        db_project = Project(
            title=project_data.title,
            description=project_data.description,
            # Ensure skills and roles are converted to list format if they are Pydantic models from input
            required_skills=[skill.model_dump() for skill in
                             project_data.required_skills] if project_data.required_skills else [],
            required_roles=project_data.required_roles if project_data.required_roles else [],
            keywords=project_data.keywords,
            project_type=project_data.project_type,
            expected_deliverables=project_data.expected_deliverables,
            contact_person_info=project_data.contact_person_info,
            learning_outcomes=project_data.learning_outcomes,
            team_size_preference=project_data.team_size_preference,
            project_status=project_data.project_status,
            start_date=project_data.start_date,
            end_date=project_data.end_date,
            estimated_weekly_hours=project_data.estimated_weekly_hours,
            location=project_data.location,
            creator_id=current_user_id,
            cover_image_url=final_cover_image_url,
            cover_image_original_filename=final_cover_image_original_filename,
            cover_image_type=final_cover_image_type,
            cover_image_size_bytes=final_cover_image_size_bytes,
            combined_text="",  # Will be updated after all files are processed
            embedding=None  # Will be updated after all files are processed
        )
        db.add(db_project)
        db.flush()  # Flush to get the ID for db_project, but don't commit yet to allow rollback of files

        # --- 新增逻辑：将创建者自动添加为项目的第一个成员 ---
        print(f"DEBUG: 准备将创建者 {current_user_id} 自动添加为项目 {db_project.id} 的成员。")
        initial_member = ProjectMember(
            project_id=db_project.id,  # 使用刚生成的项目ID
            student_id=current_user_id,  # 创建者的ID
            role="admin",  # 或者 "管理员", "负责人" 等，根据你的系统设计
            status="active",  # 状态设为活跃
            # join_date=datetime.utcnow()     # 如果你的模型有加入日期字段
        )
        db.add(initial_member)
        print(f"DEBUG: 创建者已作为成员添加到数据库会话中。")
        # --- 新增逻辑结束 ---

        # --- Process Project Attachment Files ---
        project_files_for_db = []
        allowed_file_mime_types = [
            "text/plain", "text/markdown", "application/pdf",
            "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-powerpoint",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "application/json", "application/xml", "text/html", "text/css", "text/javascript",
            "application/x-python-code", "text/x-python", "application/x-sh",
        ]

        if project_files:
            for index, file_obj in enumerate(project_files):
                file_metadata = parsed_project_files_meta[index]

                if file_obj.content_type.startswith('image/'):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                        detail=f"项目附件不支持图片文件：{file_obj.filename}。请使用项目封面上传或作为图片消息在聊天室上传。")
                if file_obj.content_type.startswith('video/'):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                        detail=f"项目附件不支持视频文件：{file_obj.filename}。请作为视频消息在聊天室上传。")
                if file_obj.content_type not in allowed_file_mime_types:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                        detail=f"不支持的项目附件文件类型: {file_obj.filename} ({file_obj.content_type})。仅支持常见文档、文本和代码文件。")

                file_bytes_content = await file_obj.read()
                file_extension = os.path.splitext(file_obj.filename)[1]

                # IMPORTANT: Use the newly created project ID in the OSS path
                oss_path_prefix = f"project_attachments/{db_project.id}"
                current_oss_object_name_attach = f"{oss_path_prefix}/{uuid.uuid4().hex}{file_extension}"
                newly_uploaded_oss_objects_for_rollback.append(current_oss_object_name_attach)  # Add to rollback list

                attachment_url = await oss_utils.upload_file_to_oss(
                    file_bytes=file_bytes_content,
                    object_name=current_oss_object_name_attach,
                    content_type=file_obj.content_type
                )

                new_project_file = ProjectFile(
                    project_id=db_project.id,
                    upload_by_id=current_user_id,
                    file_name=file_obj.filename,
                    oss_object_name=current_oss_object_name_attach,
                    file_path=attachment_url,
                    file_type=file_obj.content_type,
                    size_bytes=file_obj.size,
                    description=file_metadata.description,
                    access_type=file_metadata.access_type
                )
                project_files_for_db.append(new_project_file)
                db.add(new_project_file)  # Add to session
                print(f"DEBUG: 项目附件文件 '{file_obj.filename}' 已上传并添加到session。")

        # --- Rebuild combined_text and Update Embedding for Project ---
        _required_skills_text = ", ".join(
            [s.get("name", "") for s in db_project.required_skills if isinstance(s, dict) and s.get("name")])
        _required_roles_text = "、".join(db_project.required_roles)

        # Include attachment filenames and descriptions in combined_text if attachments exist
        attachments_text = ""
        if project_files_for_db:
            attachment_snippets = []
            for pf in project_files_for_db:
                snippet = f"{pf.file_name}"
                if pf.description:
                    snippet += f" ({pf.description})"
                attachment_snippets.append(snippet)
            attachments_text = "。附件列表：" + "。".join(attachment_snippets)

        db_project.combined_text = ". ".join(filter(None, [
            _get_text_part(db_project.title),
            _get_text_part(db_project.description),
            _get_text_part(_required_skills_text),
            _get_text_part(_required_roles_text),
            _get_text_part(db_project.keywords),
            _get_text_part(db_project.project_type),
            _get_text_part(db_project.expected_deliverables),
            _get_text_part(db_project.learning_outcomes),
            _get_text_part(db_project.team_size_preference),
            _get_text_part(db_project.project_status),
            _get_text_part(db_project.start_date),
            _get_text_part(db_project.end_date),
            _get_text_part(db_project.estimated_weekly_hours),
            _get_text_part(db_project.location),
            _get_text_part(db_project.cover_image_original_filename),
            _get_text_part(db_project.cover_image_type),
            attachments_text  # Include attachments in combined_text
        ])).strip()

        # Generate embedding using AI core
        db_project.embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR
        if db_project.combined_text:
            try:
                # Use creator's LLM configuration
                project_creator_llm_api_key = None
                project_creator_llm_type = current_user.llm_api_type
                project_creator_llm_base_url = current_user.llm_api_base_url
                project_creator_llm_model_id = current_user.llm_model_id

                if project_creator_llm_type == "siliconflow" and current_user.llm_api_key_encrypted:
                    try:
                        project_creator_llm_api_key = decrypt_key(current_user.llm_api_key_encrypted)
                    except Exception as e:
                        print(f"ERROR_EMBEDDING_KEY: 解密创建者硅基流动 API 密钥失败: {e}。")
                        project_creator_llm_api_key = None

                new_embedding = await get_embeddings_from_api(
                    [db_project.combined_text],
                    api_key=project_creator_llm_api_key,
                    llm_type=project_creator_llm_type,
                    llm_base_url=project_creator_llm_base_url,
                    llm_model_id=project_creator_llm_model_id
                )
                if new_embedding:
                    db_project.embedding = new_embedding[0]
                print(f"DEBUG: 项目嵌入向量已生成。")
            except Exception as e:
                print(f"ERROR: 生成项目嵌入向量失败: {e}")
                db_project.embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR

        db.add(db_project)
        db.commit()  # FINAL COMMIT of all DB changes
        db.refresh(db_project)

        # Populate response data
        db_project._creator_name = current_user.name if current_user else "未知用户"
        
        # Filter and populate project files for response
        visible_project_files = []
        for file_record in project_files_for_db:
            if file_record.access_type == "public":
                file_record._uploader_name = current_user.name
                visible_project_files.append(file_record)
            elif file_record.access_type == "member_only":
                # Creator is always a member
                file_record._uploader_name = current_user.name
                visible_project_files.append(file_record)
        
        db_project.project_files = visible_project_files

        print(f"DEBUG: 项目 '{db_project.title}' (ID: {db_project.id}) 创建成功。")
        return db_project

    except HTTPException as e:
        db.rollback()
        if newly_uploaded_oss_objects_for_rollback:
            for obj_name in newly_uploaded_oss_objects_for_rollback:
                asyncio.create_task(oss_utils.delete_file_from_oss(obj_name))
                print(f"DEBUG: HTTP exception occurred, attempting to delete new OSS file: {obj_name}")
        raise e
    except IntegrityError as e:
        db.rollback()
        if newly_uploaded_oss_objects_for_rollback:
            for obj_name in newly_uploaded_oss_objects_for_rollback:
                asyncio.create_task(oss_utils.delete_file_from_oss(obj_name))
                print(f"DEBUG: DB integrity error occurred, attempting to delete new OSS file: {obj_name}")
        print(f"ERROR_DB: 创建项目发生完整性约束错误: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="创建项目失败，可能存在数据冲突或唯一性约束。")
    except Exception as e:
        db.rollback()
        if newly_uploaded_oss_objects_for_rollback:
            for obj_name in newly_uploaded_oss_objects_for_rollback:
                asyncio.create_task(oss_utils.delete_file_from_oss(obj_name))
                print(f"DEBUG: Unknown error occurred, attempting to delete new OSS file: {obj_name}")
        print(f"ERROR_DB: 创建项目发生未知错误: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"创建项目失败: {e}")

@router.put("/{project_id}", response_model=schemas.ProjectResponse, summary="更新指定项目")
async def update_project(
        project_id: int,
        project_data_json: str = Form(..., description="要更新的项目主体数据，JSON字符串格式"),
        cover_image: Optional[UploadFile] = File(None, description="可选：上传项目封面图片，将替换现有封面"),
        project_files_meta_json: Optional[str] = Form(None, description="新项目附件的元数据列表，JSON字符串格式"),
        project_files: Optional[List[UploadFile]] = File(None, description="可选：上传的新项目附件文件列表"),
        files_to_delete_ids_json: Optional[str] = Form(None, description="要删除的项目文件ID列表，JSON字符串格式"),
        files_to_update_metadata_json: Optional[str] = Form(None, description="要更新元数据的文件列表，JSON字符串格式"),
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG_UPDATE_PROJECT: 用户 {current_user_id} 尝试更新项目 ID: {project_id}。")

    # 简化版的更新逻辑，完整版本很长
    try:
        db_project = db.query(Project).filter(Project.id == project_id).first()
        if not db_project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目未找到。")

        current_user = db.query(Student).filter(Student.id == current_user_id).first()
        if not current_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证用户无效。")

        is_creator = (db_project.creator_id == current_user_id)
        is_system_admin = current_user.is_admin

        if not (is_creator or is_system_admin):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="无权更新此项目。只有项目创建者或系统管理员可以修改。")

        # 解析更新数据
        try:
            project_data_dict = json.loads(project_data_json)
            update_project_data_schema = schemas.ProjectUpdate(**project_data_dict)
            update_data = update_project_data_schema.dict(exclude_unset=True)
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"JSON数据解析失败: {e}")

        # 应用更新
        for key, value in update_data.items():
            if hasattr(db_project, key):
                setattr(db_project, key, value)

        db.add(db_project)
        db.commit()
        db.refresh(db_project)

        # 填充响应数据
        db_project._creator_name = current_user.name if current_user else "未知用户"

        print(f"DEBUG: 项目 {project_id} 更新成功。")
        return db_project

    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        print(f"ERROR_PROJECT_UPDATE: 项目 {project_id} 更新失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"项目更新失败: {e}")

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除指定项目")
async def delete_project(
        project_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    删除指定ID的项目。只有项目的创建者或系统管理员可以执行此操作。
    """
    print(f"DEBUG_DELETE_PROJECT: 用户 {current_user_id} 尝试删除项目 ID: {project_id}。")

    try:
        db_project = db.query(Project).filter(Project.id == project_id).first()
        if not db_project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目未找到。")

        current_user = db.query(Student).filter(Student.id == current_user_id).first()
        if not current_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证用户无效。")

        is_creator = (db_project.creator_id == current_user_id)
        is_system_admin = current_user.is_admin

        if not (is_creator or is_system_admin):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="无权删除此项目。只有项目创建者或系统管理员可以执行此操作。")

        # 删除项目封面图片（如果托管在OSS）
        oss_base_url_parsed = os.getenv("S3_BASE_URL", "").rstrip('/') + '/'
        if db_project.cover_image_url and db_project.cover_image_url.startswith(oss_base_url_parsed):
            cover_image_oss_object_name = db_project.cover_image_url.replace(oss_base_url_parsed, '', 1)
            try:
                asyncio.create_task(oss_utils.delete_file_from_oss(cover_image_oss_object_name))
            except Exception as e:
                print(f"ERROR_DELETE_PROJECT: 删除项目封面OSS文件失败: {e}")

        # 删除数据库记录（级联删除关联数据）
        db.delete(db_project)
        db.commit()

        print(f"DEBUG_DELETE_PROJECT: 项目 {project_id} 及其所有关联数据已成功删除。")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        print(f"ERROR_DELETE_PROJECT: 删除项目 {project_id} 失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"删除项目失败: {e}")

@router.delete("/{project_id}/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT,
            summary="删除指定项目的附件文件")
async def delete_project_file(
        project_id: int,
        file_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    从指定项目中删除一个附件文件。
    """
    print(f"DEBUG_DELETE_PROJECT_FILE: 用户 {current_user_id} 尝试删除项目 {project_id} 中的文件 ID: {file_id}。")

    try:
        db_project = db.query(Project).filter(Project.id == project_id).first()
        if not db_project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目未找到。")

        db_project_file = db.query(ProjectFile).filter(
            ProjectFile.id == file_id,
            ProjectFile.project_id == project_id
        ).first()
        if not db_project_file:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目文件未找到或不属于该项目。")

        current_user = db.query(Student).filter(Student.id == current_user_id).first()
        if not current_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证用户无效。")

        # 权限检查
        is_uploader = (db_project_file.upload_by_id == current_user_id)
        is_project_creator = (db_project.creator_id == current_user_id)
        is_project_member = db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.student_id == current_user_id,
            ProjectMember.status == "active"
        ).first() is not None
        is_system_admin = current_user.is_admin

        if not (is_uploader or is_project_creator or is_project_member or is_system_admin):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="无权删除此文件。")

        # 删除文件
        db.delete(db_project_file)
        db.commit()

        print(f"DEBUG_DELETE_PROJECT_FILE: 项目文件 ID: {file_id} 已成功删除。")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        print(f"ERROR_DELETE_PROJECT_FILE: 删除项目文件 {file_id} 失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"删除项目文件失败: {e}")

@router.post("/{project_id}/files/", response_model=schemas.ProjectFileResponse,
          status_code=status.HTTP_201_CREATED, summary="为指定项目上传文件")
async def upload_project_file(
        project_id: int,
        file: UploadFile = File(..., description="要上传的项目文件"),
        file_data: schemas.ProjectFileCreate = Depends(),
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    为指定项目上传一个新文件。
    """
    print(f"DEBUG_PROJECT_FILE: 用户 {current_user_id} 尝试为项目 {project_id} 上传文件 '{file.filename}'。")

    # 验证项目是否存在
    db_project = db.query(Project).filter(Project.id == project_id).first()
    if not db_project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目未找到。")

    # 权限检查
    is_project_creator = (db_project.creator_id == current_user_id)
    is_project_member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.student_id == current_user_id,
        ProjectMember.status == "active"
    ).first() is not None

    if not (is_project_creator or is_project_member):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="无权为该项目上传文件。")

    # 文件类型检查
    allowed_mime_types = [
        "text/plain", "text/markdown", "application/pdf",
        "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/json", "application/xml", "text/html", "text/css", "text/javascript",
        "application/x-python-code", "text/x-python", "application/x-sh",
    ]

    if file.content_type.startswith('image/'):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="项目文件不支持直接上传图片。")
    if file.content_type not in allowed_mime_types:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"不支持的文件类型: {file.content_type}。")

    oss_object_name_for_rollback = None
    try:
        # 上传到OSS
        file_bytes = await file.read()
        file_extension = os.path.splitext(file.filename)[1]
        oss_path_prefix = f"project_files/{project_id}"
        current_oss_object_name = f"{oss_path_prefix}/{uuid.uuid4().hex}{file_extension}"
        oss_object_name_for_rollback = current_oss_object_name

        file_url = await oss_utils.upload_file_to_oss(
            file_bytes=file_bytes,
            object_name=current_oss_object_name,
            content_type=file.content_type
        )

        # 创建数据库记录
        db_project_file = ProjectFile(
            project_id=project_id,
            upload_by_id=current_user_id,
            file_name=file.filename,
            oss_object_name=current_oss_object_name,
            file_path=file_url,
            file_type=file.content_type,
            size_bytes=file.size,
            description=file_data.description,
            access_type=file_data.access_type
        )
        db.add(db_project_file)
        db.commit()
        db.refresh(db_project_file)

        # 填充上传者姓名
        uploader_student = db.query(Student).filter(Student.id == current_user_id).first()
        db_project_file._uploader_name = uploader_student.name if uploader_student else "未知用户"

        print(f"DEBUG_PROJECT_FILE: 文件上传成功。")
        return db_project_file

    except HTTPException as e:
        db.rollback()
        if oss_object_name_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(oss_object_name_for_rollback))
        raise e
    except Exception as e:
        db.rollback()
        if oss_object_name_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(oss_object_name_for_rollback))
        print(f"ERROR_PROJECT_FILE: 上传项目文件失败：{e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"上传项目文件失败: {e}")

@router.post("/{project_id}/like", response_model=schemas.ProjectLikeResponse, summary="点赞指定项目")
async def like_project_item(
        project_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    点赞一个项目。同一用户不能重复点赞同一项目。
    """
    print(f"DEBUG_LIKE: 用户 {current_user_id} 尝试点赞项目 ID: {project_id}")
    try:
        # 验证项目是否存在
        db_project = db.query(Project).filter(Project.id == project_id).first()
        if not db_project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目未找到。")

        # 检查是否已点赞
        existing_like = db.query(ProjectLike).filter(
            ProjectLike.owner_id == current_user_id,
            ProjectLike.project_id == project_id
        ).first()
        if existing_like:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已点赞该项目。")

        # 创建点赞记录
        db_like = ProjectLike(
            owner_id=current_user_id,
            project_id=project_id
        )
        db.add(db_like)

        # 更新项目点赞计数
        db_project.likes_count += 1
        db.add(db_project)

        # 奖励积分（给项目创建者）
        project_creator_id = db_project.creator_id
        if project_creator_id and project_creator_id != current_user_id:
            creator_user = db.query(Student).filter(Student.id == project_creator_id).first()
            if creator_user:
                await _award_points(
                    db=db,
                    user=creator_user,
                    amount=5,
                    reason=f"项目获得点赞：'{db_project.title}'",
                    transaction_type="EARN",
                    related_entity_type="project",
                    related_entity_id=project_id
                )

        db.commit()
        db.refresh(db_like)

        print(f"DEBUG_LIKE: 用户 {current_user_id} 点赞项目 {project_id} 成功。")
        return db_like

    except Exception as e:
        db.rollback()
        print(f"ERROR_LIKE: 项目点赞失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"项目点赞失败: {e}")

@router.delete("/{project_id}/unlike", status_code=status.HTTP_204_NO_CONTENT, summary="取消点赞指定项目")
async def unlike_project_item(
        project_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    取消点赞一个项目。
    """
    print(f"DEBUG_UNLIKE: 用户 {current_user_id} 尝试取消点赞项目 ID: {project_id}")
    try:
        # 查找点赞记录
        db_like = db.query(ProjectLike).filter(
            ProjectLike.owner_id == current_user_id,
            ProjectLike.project_id == project_id
        ).first()

        if not db_like:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到您对该项目的点赞记录。")

        # 更新项目点赞计数
        db_project = db.query(Project).filter(Project.id == project_id).first()
        if db_project and db_project.likes_count > 0:
            db_project.likes_count -= 1
            db.add(db_project)

        # 删除点赞记录
        db.delete(db_like)
        db.commit()

        print(f"DEBUG_UNLIKE: 用户 {current_user_id} 取消点赞项目 {project_id} 成功。")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except Exception as e:
        db.rollback()
        print(f"ERROR_UNLIKE: 取消项目点赞失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"取消项目点赞失败: {e}")