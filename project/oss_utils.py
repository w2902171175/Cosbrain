# project/oss_utils.py
import os, io, asyncio
from typing import Optional
from fastapi import HTTPException # New: Import HTTPException
from oss2 import Auth, Bucket # Removed SizedFileAdaptor, put_object
from oss2.credentials import EnvironmentVariableCredentialsProvider # Although not directly used here, keep it if it's a common pattern in your project
from dotenv import load_dotenv
from functools import partial
load_dotenv()

# 从环境变量加载OSS配置
OSS_ACCESS_KEY_ID = os.getenv("OSS_ACCESS_KEY_ID")
OSS_ACCESS_KEY_SECRET = os.getenv("OSS_ACCESS_KEY_SECRET")
OSS_ENDPOINT = os.getenv("OSS_ENDPOINT")
OSS_BUCKET_NAME = os.getenv("OSS_BUCKET_NAME")
OSS_BASE_URL = os.getenv("OSS_BASE_URL") # 公开访问的URL前缀

if not all([OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET, OSS_ENDPOINT, OSS_BUCKET_NAME, OSS_BASE_URL]):
    raise ValueError("Missing one or more OSS environment variables (OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET, OSS_ENDPOINT, OSS_BUCKET_NAME, OSS_BASE_URL).")

_oss_bucket = None

def get_oss_bucket() -> Bucket:
    """
    获取OSS Bucket实例。单例模式，避免重复初始化。
    """
    global _oss_bucket
    if _oss_bucket is None:
        try:
            # 使用环境变量认证（推荐）
            auth = Auth(OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET)
            _oss_bucket = Bucket(auth, OSS_ENDPOINT, OSS_BUCKET_NAME)
            # 可以在这里尝试进行一次简单的操作来验证连接，例如列举桶中对象（如果权限允许且不影响性能）
            # bucket.get_bucket_info() # 这是一个同步调用，如果在这里执行，也会阻塞，所以通常不在这种公共函数里做。
            print(f"DEBUG_OSS: OSS Bucket '{OSS_BUCKET_NAME}' 初始化成功。")
        except Exception as e:
            print(f"ERROR_OSS: OSS Bucket 初始化失败: {e}")
            raise
    return _oss_bucket


async def upload_file_to_oss(
        file_bytes: bytes,
        object_name: str,
        content_type: str
) -> str:
    """
    将文件字节流上传到OSS。(兼容 Python < 3.9)
    :param file_bytes: 文件内容的字节流
    :param object_name: OSS对象存储的完整路径和文件名，例如 'uploads/my_file.pdf'
    :param content_type: 文件的MIME类型，例如 'application/pdf'
    :return: 文件在OSS上的完整URL
    """
    bucket = get_oss_bucket()
    try:
        file_like_object = io.BytesIO(file_bytes)
        # 获取当前正在运行的事件循环
        loop = asyncio.get_running_loop()
        # 因为 run_in_executor 不能很好地直接处理关键字参数，
        # 我们使用 functools.partial 来创建一个已经“内嵌”了所有参数的新函数。
        blocking_call = partial(
            bucket.put_object,
            object_name,
            file_like_object,
            headers={'Content-Type': content_type}
        )

        # 在默认的线程池执行器中运行这个同步（阻塞）的函数。
        result = await loop.run_in_executor(
            None,  # 'None' 表示使用默认的执行器
            blocking_call
        )

        if result.status == 200:
            print(f"DEBUG_OSS: 文件 '{object_name}' 上传到OSS成功。")
            # 假设你有 OSS_BASE_URL 这个配置
            return f"{OSS_BASE_URL.rstrip('/')}/{object_name}"
        else:
            print(
                f"ERROR_OSS: 文件 '{object_name}' 上传到OSS失败，状态码: {result.status}, 响应: {result.resp.response}")
            raise Exception(f"OSS上传失败，状态码: {result.status}")
    except Exception as e:
        print(f"ERROR_OSS: 上传文件 '{object_name}' 到OSS时发生错误: {e}")
        # 重新抛出 HTTPException，让 FastAPI 框架来处理
        raise HTTPException(status_code=500, detail=f"文件上传到云存储失败: {e}")

async def delete_file_from_oss(object_name: str):
    """
    从OSS删除文件。
    :param object_name: OSS对象存储的完整路径和文件名，例如 'uploads/my_file.pdf'
    """
    bucket = get_oss_bucket()
    try:
        # Wrap the synchronous oss2.delete_object call in asyncio.to_thread
        result = await asyncio.to_thread(bucket.delete_object, object_name)
        if result.status == 204: # 204 No Content for successful deletion
            print(f"DEBUG_OSS: 文件 '{object_name}' 从OSS删除成功。")
        else:
            print(f"WARNING_OSS: 文件 '{object_name}' 删除失败，状态码: {result.status}, 响应: {result.resp.response}")
        return {"status": "success", "message": f"Object {object_name} deleted or not found."}
    except Exception as e:
        print(f"ERROR_OSS: 从OSS删除文件 '{object_name}' 时发生错误: {e}")
        # Here, we don't necessarily want to raise an HTTPException as deletion might be idempotent
        return {"status": "failure", "message": f"Failed to delete object {object_name}: {e}"}


async def download_file_from_oss(object_name: str) -> bytes:
    """
    从OSS下载文件内容。(兼容 Python < 3.9)
    :param object_name: OSS对象存储的完整路径和文件名，例如 'uploads/my_file.pdf'
    :return: 文件内容的字节流
    """
    bucket = get_oss_bucket()
    try:

        # 获取当前正在运行的事件循环
        loop = asyncio.get_running_loop()

        # 1. 异步执行 bucket.get_object (这是一个阻塞操作)
        blocking_get_call = partial(bucket.get_object, object_name)
        oss_obj_result = await loop.run_in_executor(
            None,
            blocking_get_call
        )

        # 2. 异步执行 oss_obj_result.read() (这同样是阻塞操作)
        blocking_read_call = partial(oss_obj_result.read)
        file_content_bytes = await loop.run_in_executor(
            None,
            blocking_read_call
        )

        print(f"DEBUG_OSS: 文件 '{object_name}' 从OSS下载成功。")
        return file_content_bytes
    except Exception as e:
        print(f"ERROR_OSS: 从OSS下载文件 '{object_name}' 时发生错误: {e}")
        raise HTTPException(status_code=500, detail=f"从云存储下载文件失败: {e}")


def is_oss_url(url: Optional[str]) -> bool:
    """检查给定的URL是否是OSS URL。"""
    if not url:
        return False
    # 确保 OSS_BASE_URL 是从环境变量中加载的
    loaded_oss_base_url = os.getenv("OSS_BASE_URL", "").rstrip('/')
    if not loaded_oss_base_url:
        print("WARNING: OSS_BASE_URL is not set in environment or is empty. Cannot determine if URL is an OSS URL.")
        return False # 或者根据您的错误处理策略，可以选择抛出一个异常
    return url.startswith(loaded_oss_base_url)

