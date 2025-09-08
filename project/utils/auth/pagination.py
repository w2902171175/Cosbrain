# project/utils/dependencies/pagination.py
"""
分页相关依赖注入
"""


# --- 通用依赖项：分页参数 ---
def get_pagination_params(
    page: int = 1,
    page_size: int = 10,
    max_page_size: int = 100
):
    """
    通用分页参数依赖项
    
    Args:
        page: 页码（从1开始）
        page_size: 每页大小
        max_page_size: 最大每页大小
    
    Returns:
        dict: 包含分页参数的字典
    """
    page = max(1, page)  # 确保页码至少为1
    page_size = min(page_size, max_page_size)  # 限制每页大小
    offset = (page - 1) * page_size
    
    return {
        "page": page,
        "page_size": page_size,
        "offset": offset,
        "limit": page_size
    }
