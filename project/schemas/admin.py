# project/schemas/admin.py
"""
管理员相关Schema模块
"""

from pydantic import BaseModel, Field
from typing import Optional

# 管理员相关的Schema可以从auth模块导入
from .auth import UserAdminStatusUpdate

# 或者定义管理员特有的Schema
class AdminOperationRequest(BaseModel):
    """管理员操作请求模型"""
    operation_type: str = Field(..., description="操作类型")
    target_id: Optional[int] = Field(None, description="目标ID")
    reason: Optional[str] = Field(None, description="操作原因")


class AdminOperationResponse(BaseModel):
    """管理员操作响应模型"""
    success: bool = Field(..., description="操作是否成功")
    message: str = Field(..., description="操作结果消息")
    affected_count: Optional[int] = Field(None, description="受影响的记录数量")
