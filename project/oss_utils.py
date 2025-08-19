# project/oss_utils.py
import os, io, asyncio
from typing import Optional
from fastapi import HTTPException
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv
from functools import partial
load_dotenv()

# 从环境变量加载S3兼容存储配置
S3_ACCESS_KEY_ID = os.getenv("S3_ACCESS_KEY_ID") or os.getenv("OSS_ACCESS_KEY_ID")
S3_SECRET_ACCESS_KEY = os.getenv("S3_SECRET_ACCESS_KEY") or os.getenv("OSS_ACCESS_KEY_SECRET")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL") or os.getenv("OSS_ENDPOINT")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME") or os.getenv("OSS_BUCKET_NAME")
S3_REGION = os.getenv("S3_REGION", "oss-cn-hangzhou")
S3_BASE_URL = os.getenv("S3_BASE_URL") or os.getenv("OSS_BASE_URL")

if not all([S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY, S3_ENDPOINT_URL, S3_BUCKET_NAME, S3_BASE_URL]):
    raise ValueError("Missing one or more S3/OSS environment variables.")

_s3_client = None

def get_s3_client():
    """
    获取S3客户端实例。单例模式，避免重复初始化。
    """
    global _s3_client
    if _s3_client is None:
        try:
            _s3_client = boto3.client(
                's3',
                aws_access_key_id=S3_ACCESS_KEY_ID,
                aws_secret_access_key=S3_SECRET_ACCESS_KEY,
                endpoint_url=S3_ENDPOINT_URL,
                region_name=S3_REGION,
                config=boto3.session.Config(
                    signature_version='s3v4',
                    s3={'addressing_style': 'virtual'}
                )
            )
            print(f"DEBUG_S3: S3客户端初始化成功，连接到 {S3_ENDPOINT_URL}")
        except Exception as e:
            print(f"ERROR_S3: S3客户端初始化失败: {e}")
            raise
    return _s3_client

# 向后兼容的别名函数
def get_oss_bucket():
    """为了向后兼容，返回S3客户端"""
    return get_s3_client()


async def upload_file_to_oss(
        file_bytes: bytes,
        object_name: str,
        content_type: str
) -> str:
    """
    将文件字节流上传到S3兼容存储。
    :param file_bytes: 文件内容的字节流
    :param object_name: 对象存储的完整路径和文件名，例如 'uploads/my_file.pdf'
    :param content_type: 文件的MIME类型，例如 'application/pdf'
    :return: 文件在云存储上的完整URL
    """
    s3_client = get_s3_client()
    try:
        file_like_object = io.BytesIO(file_bytes)
        loop = asyncio.get_running_loop()
        
        blocking_call = partial(
            s3_client.put_object,
            Bucket=S3_BUCKET_NAME,
            Key=object_name,
            Body=file_like_object,
            ContentType=content_type
        )

        result = await loop.run_in_executor(None, blocking_call)
        
        print(f"DEBUG_S3: 文件 '{object_name}' 上传到云存储成功。ETag: {result.get('ETag', 'N/A')}")
        return f"{S3_BASE_URL.rstrip('/')}/{object_name}"
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        print(f"ERROR_S3: 上传文件 '{object_name}' 到云存储时发生ClientError: {error_code} - {e}")
        raise HTTPException(status_code=500, detail=f"文件上传到云存储失败: {error_code}")
    except Exception as e:
        print(f"ERROR_S3: 上传文件 '{object_name}' 到云存储时发生错误: {e}")
        raise HTTPException(status_code=500, detail=f"文件上传到云存储失败: {e}")

async def delete_file_from_oss(object_name: str):
    """
    从S3兼容存储删除文件。
    :param object_name: 对象存储的完整路径和文件名，例如 'uploads/my_file.pdf'
    """
    s3_client = get_s3_client()
    try:
        blocking_call = partial(
            s3_client.delete_object,
            Bucket=S3_BUCKET_NAME,
            Key=object_name
        )
        
        result = await asyncio.get_running_loop().run_in_executor(None, blocking_call)
        print(f"DEBUG_S3: 文件 '{object_name}' 从S3删除成功。")
        return {"status": "success", "message": f"Object {object_name} deleted successfully."}
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'NoSuchKey':
            print(f"WARNING_S3: 文件 '{object_name}' 不存在。")
            return {"status": "success", "message": f"Object {object_name} not found (already deleted)."}
        else:
            print(f"ERROR_S3: 从S3删除文件 '{object_name}' 时发生ClientError: {error_code} - {e}")
            return {"status": "failure", "message": f"Failed to delete object {object_name}: {error_code}"}
    except Exception as e:
        print(f"ERROR_S3: 从S3删除文件 '{object_name}' 时发生错误: {e}")
        return {"status": "failure", "message": f"Failed to delete object {object_name}: {e}"}


async def download_file_from_oss(object_name: str) -> bytes:
    """
    从S3兼容存储下载文件内容。
    :param object_name: S3对象存储的完整路径和文件名，例如 'uploads/my_file.pdf'
    :return: 文件内容的字节流
    """
    s3_client = get_s3_client()
    try:
        loop = asyncio.get_running_loop()
        
        blocking_call = partial(
            s3_client.get_object,
            Bucket=S3_BUCKET_NAME,
            Key=object_name
        )
        
        response = await loop.run_in_executor(None, blocking_call)
        
        # 读取文件内容
        blocking_read_call = partial(response['Body'].read)
        file_content_bytes = await loop.run_in_executor(None, blocking_read_call)
        
        print(f"DEBUG_S3: 文件 '{object_name}' 从S3下载成功。")
        return file_content_bytes
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'NoSuchKey':
            print(f"ERROR_S3: 文件 '{object_name}' 不存在。")
            raise HTTPException(status_code=404, detail=f"文件不存在: {object_name}")
        else:
            print(f"ERROR_S3: 从S3下载文件 '{object_name}' 时发生ClientError: {error_code} - {e}")
            raise HTTPException(status_code=500, detail=f"从云存储下载文件失败: {error_code}")
    except Exception as e:
        print(f"ERROR_S3: 从S3下载文件 '{object_name}' 时发生错误: {e}")
        raise HTTPException(status_code=500, detail=f"从云存储下载文件失败: {e}")


def is_oss_url(url: Optional[str]) -> bool:
    """检查给定的URL是否是OSS URL。"""
    if not url:
        return False
    # 确保 S3_BASE_URL 是从环境变量中加载的
    loaded_s3_base_url = (S3_BASE_URL or "").rstrip('/')
    if not loaded_s3_base_url:
        print("WARNING: S3_BASE_URL is not set in environment or is empty. Cannot determine if URL is an S3 URL.")
        return False # 或者根据您的错误处理策略，可以选择抛出一个异常
    return url.startswith(loaded_s3_base_url)

