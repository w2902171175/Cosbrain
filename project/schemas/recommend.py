# project/schemas/recommend.py
"""
推荐系统相关Schema模块
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from .common import SkillWithProficiency


# 这里引入其他模块中已定义的推荐相关模型
# 从 projects.py 导入
# from .projects import MatchedProject, MatchedStudent
# 从 courses.py 导入
# from .courses import MatchedCourse

# 或者在这里重新定义，避免循环导入
class MatchedProject(BaseModel):
    """推荐匹配项目模型"""
    project_id: int
    title: str
    description: str
    similarity_stage1: float
    relevance_score: float
    match_rationale: Optional[str] = Field(None, description="AI生成的用户与项目匹配理由及建议")


class MatchedCourse(BaseModel):
    """推荐匹配课程模型"""
    course_id: int
    title: str
    description: str
    instructor: Optional[str] = None
    category: Optional[str] = None
    cover_image_url: Optional[str] = None
    similarity_stage1: float
    relevance_score: float
    match_rationale: Optional[str] = Field(None, description="AI生成的用户与课程匹配理由及建议")


class MatchedStudent(BaseModel):
    """推荐匹配学生模型"""
    student_id: int
    name: str
    major: str
    skills: Optional[List[SkillWithProficiency]] = Field(None, description="学生的技能列表及熟练度详情")
    similarity_stage1: float
    relevance_score: float
    match_rationale: Optional[str] = Field(None, description="AI生成的用户与项目匹配理由及建议")
