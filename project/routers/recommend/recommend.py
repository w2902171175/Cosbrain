# project/routers/recommend/recommend.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

# 导入数据库和模型
from project.database import get_db
import project.schemas as schemas
from project.ai_providers.config import INITIAL_CANDIDATES_K, FINAL_TOP_K
from project.ai_providers.matching_engine import (
    find_matching_courses_for_student,
    find_matching_projects_for_student, 
    find_matching_students_for_project
)

# 创建路由器
router = APIRouter(
    prefix="/recommend",
    tags=["推荐系统"],
    responses={404: {"description": "Not found"}},
)

# --- 推荐系统接口 ---

@router.get("/courses/{student_id}", response_model=List[schemas.MatchedCourse], summary="为指定学生推荐课程")
async def recommend_courses_for_student(
        student_id: int,
        db: Session = Depends(get_db),
        initial_k: int = INITIAL_CANDIDATES_K,
        final_k: int = FINAL_TOP_K
):
    """
    为指定学生推荐相关课程。
    """
    print(f"DEBUG_AI: 为学生 {student_id} 推荐课程。")
    try:
        recommendations = await find_matching_courses_for_student(db, student_id, initial_k, final_k)
        if not recommendations:
            print(f"DEBUG_AI: 未为学生 {student_id} 找到课程推荐。")
        return recommendations
    except Exception as e:
        print(f"ERROR_AI: 推荐课程失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"课程推荐失败: {e}")

@router.get("/projects/{student_id}", response_model=List[schemas.MatchedProject], summary="为指定学生推荐项目")
async def recommend_projects_for_student(
        student_id: int,
        db: Session = Depends(get_db),
        initial_k: int = INITIAL_CANDIDATES_K,
        final_k: int = FINAL_TOP_K
):
    print(f"DEBUG_AI: 为学生 {student_id} 推荐项目。")
    try:
        recommendations = await find_matching_projects_for_student(db, student_id, initial_k, final_k)
        if not recommendations:
            print(f"DEBUG_AI: 未为学生 {student_id} 找到项目推荐。")
        return recommendations
    except Exception as e:
        print(f"ERROR_AI: 推荐项目失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"项目推荐失败: {e}")

@router.get("/projects/{project_id}/match-students", response_model=List[schemas.MatchedStudent],
         summary="为指定项目推荐学生")
async def match_students_for_project(
        project_id: int,
        db: Session = Depends(get_db),
        initial_k: int = INITIAL_CANDIDATES_K,
        final_k: int = FINAL_TOP_K
):
    print(f"DEBUG_AI: 为项目 {project_id} 推荐学生。")
    try:
        recommendations = await find_matching_students_for_project(db, project_id, initial_k, final_k)
        if not recommendations:
            print(f"DEBUG_AI: 未为项目 {project_id} 找到学生推荐。")
        return recommendations
    except Exception as e:
        print(f"ERROR_AI: 推荐学生失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"学生推荐失败: {e}")