# project/routers/knowledge/distributed_processing.py
"""
分布式处理模块 - 支持水平扩展和负载均衡
实现多节点协同处理大型文件和批量任务
"""

import asyncio
import json
import uuid
import time
import hashlib
import os
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
from enum import Enum
import logging
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import redis
from sqlalchemy.orm import Session
import httpx
import psutil
import os

logger = logging.getLogger(__name__)

class NodeRole(str, Enum):
    """节点角色"""
    COORDINATOR = "coordinator"  # 协调者节点
    WORKER = "worker"           # 工作节点
    HYBRID = "hybrid"           # 混合节点

class TaskPriority(str, Enum):
    """任务优先级"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"

class DistributedTaskStatus(str, Enum):
    """分布式任务状态"""
    PENDING = "pending"
    ASSIGNED = "assigned"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class NodeInfo:
    """节点信息"""
    node_id: str
    host: str
    port: int
    role: NodeRole
    status: str  # online, offline, busy, maintenance
    cpu_usage: float
    memory_usage: float
    available_workers: int
    last_heartbeat: datetime
    capabilities: List[str]  # 支持的任务类型
    version: str
    region: str = "default"
    
class DistributedTask:
    """分布式任务"""
    
    def __init__(self, task_id: str = None, task_type: str = None, **kwargs):
        self.task_id = task_id or str(uuid.uuid4())
        self.task_type = task_type
        self.priority = kwargs.get('priority', TaskPriority.NORMAL)
        self.status = DistributedTaskStatus.PENDING
        self.created_at = datetime.now()
        self.assigned_node = None
        self.started_at = None
        self.completed_at = None
        self.retry_count = 0
        self.max_retries = kwargs.get('max_retries', 3)
        self.timeout = kwargs.get('timeout', 3600)  # 1小时超时
        self.data = kwargs.get('data', {})
        self.result = None
        self.error = None
        self.dependencies = kwargs.get('dependencies', [])  # 依赖的任务ID
        self.estimated_duration = kwargs.get('estimated_duration', 300)  # 估计执行时间（秒）
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'task_id': self.task_id,
            'task_type': self.task_type,
            'priority': self.priority,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'assigned_node': self.assigned_node,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'timeout': self.timeout,
            'data': self.data,
            'result': self.result,
            'error': self.error,
            'dependencies': self.dependencies,
            'estimated_duration': self.estimated_duration
        }

class LoadBalancer:
    """负载均衡器"""
    
    def __init__(self, redis_client):
        self.redis_client = redis_client
        
    async def select_optimal_node(self, task: DistributedTask, available_nodes: List[NodeInfo]) -> Optional[NodeInfo]:
        """选择最优节点执行任务"""
        if not available_nodes:
            return None
            
        # 过滤支持该任务类型的节点
        capable_nodes = [
            node for node in available_nodes 
            if task.task_type in node.capabilities and node.status == "online"
        ]
        
        if not capable_nodes:
            return None
            
        # 计算节点负载分数（越低越好）
        scored_nodes = []
        for node in capable_nodes:
            score = self._calculate_node_score(node, task)
            scored_nodes.append((node, score))
            
        # 按分数排序，选择最佳节点
        scored_nodes.sort(key=lambda x: x[1])
        return scored_nodes[0][0]
        
    def _calculate_node_score(self, node: NodeInfo, task: DistributedTask) -> float:
        """计算节点负载分数"""
        # 基础负载分数
        cpu_score = node.cpu_usage / 100.0
        memory_score = node.memory_usage / 100.0
        worker_score = max(0, 1 - (node.available_workers / 10.0))  # 假设最多10个worker
        
        # 优先级加权
        priority_weight = {
            TaskPriority.LOW: 0.5,
            TaskPriority.NORMAL: 1.0,
            TaskPriority.HIGH: 1.5,
            TaskPriority.URGENT: 2.0
        }.get(task.priority, 1.0)
        
        # 综合分数
        base_score = (cpu_score * 0.4 + memory_score * 0.4 + worker_score * 0.2)
        return base_score / priority_weight

class NodeManager:
    """节点管理器"""
    
    def __init__(self, redis_client, node_id: str = None):
        self.redis_client = redis_client
        self.node_id = node_id or f"node_{uuid.uuid4().hex[:8]}"
        self.node_info = None
        self.heartbeat_interval = 30  # 心跳间隔（秒）
        self._heartbeat_task = None
        
    async def register_node(self, host: str, port: int, role: NodeRole, 
                          capabilities: List[str], region: str = "default") -> NodeInfo:
        """注册节点"""
        self.node_info = NodeInfo(
            node_id=self.node_id,
            host=host,
            port=port,
            role=role,
            status="online",
            cpu_usage=0.0,
            memory_usage=0.0,
            available_workers=psutil.cpu_count(),
            last_heartbeat=datetime.now(),
            capabilities=capabilities,
            version="1.0.0",
            region=region
        )
        
        # 保存到Redis
        await self.redis_client.hset(
            f"nodes:{self.node_id}",
            mapping=asdict(self.node_info)
        )
        
        # 添加到活跃节点列表
        await self.redis_client.sadd("active_nodes", self.node_id)
        
        # 启动心跳
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        logger.info(f"节点 {self.node_id} 注册成功: {role} @ {host}:{port}")
        return self.node_info
        
    async def unregister_node(self):
        """注销节点"""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            
        await self.redis_client.srem("active_nodes", self.node_id)
        await self.redis_client.delete(f"nodes:{self.node_id}")
        
        logger.info(f"节点 {self.node_id} 已注销")
        
    async def get_active_nodes(self) -> List[NodeInfo]:
        """获取活跃节点列表"""
        node_ids = await self.redis_client.smembers("active_nodes")
        nodes = []
        
        for node_id in node_ids:
            node_data = await self.redis_client.hgetall(f"nodes:{node_id}")
            if node_data:
                # 检查心跳超时
                last_heartbeat = datetime.fromisoformat(node_data['last_heartbeat'])
                if datetime.now() - last_heartbeat > timedelta(minutes=2):
                    # 移除超时节点
                    await self.redis_client.srem("active_nodes", node_id)
                    await self.redis_client.delete(f"nodes:{node_id}")
                    continue
                    
                node_info = NodeInfo(**node_data)
                nodes.append(node_info)
                
        return nodes
        
    async def _heartbeat_loop(self):
        """心跳循环"""
        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                await self._send_heartbeat()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"心跳发送失败: {e}")
                
    async def _send_heartbeat(self):
        """发送心跳"""
        if not self.node_info:
            return
            
        # 更新系统状态
        self.node_info.cpu_usage = psutil.cpu_percent()
        self.node_info.memory_usage = psutil.virtual_memory().percent
        self.node_info.last_heartbeat = datetime.now()
        
        # 更新Redis
        await self.redis_client.hset(
            f"nodes:{self.node_id}",
            mapping=asdict(self.node_info)
        )

class DistributedTaskQueue:
    """分布式任务队列"""
    
    def __init__(self, redis_client, node_manager: NodeManager):
        self.redis_client = redis_client
        self.node_manager = node_manager
        self.load_balancer = LoadBalancer(redis_client)
        self.tasks = {}  # 本地任务缓存
        self.is_coordinator = False
        self._coordinator_task = None
        
    async def start_coordinator(self):
        """启动协调者模式"""
        self.is_coordinator = True
        self._coordinator_task = asyncio.create_task(self._coordinator_loop())
        logger.info("分布式协调者已启动")
        
    async def stop_coordinator(self):
        """停止协调者模式"""
        self.is_coordinator = False
        if self._coordinator_task:
            self._coordinator_task.cancel()
            
    async def submit_task(self, task: DistributedTask) -> str:
        """提交任务到分布式队列"""
        # 保存任务到Redis
        await self.redis_client.hset(
            f"task:{task.task_id}",
            mapping=task.to_dict()
        )
        
        # 添加到待处理队列
        priority_score = {
            TaskPriority.LOW: 1,
            TaskPriority.NORMAL: 2,
            TaskPriority.HIGH: 3,
            TaskPriority.URGENT: 4
        }.get(task.priority, 2)
        
        await self.redis_client.zadd("pending_tasks", {task.task_id: priority_score})
        
        logger.info(f"任务 {task.task_id} ({task.task_type}) 已提交到分布式队列")
        return task.task_id
        
    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        task_data = await self.redis_client.hgetall(f"task:{task_id}")
        return task_data if task_data else None
        
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        task_data = await self.redis_client.hgetall(f"task:{task_id}")
        if not task_data:
            return False
            
        # 更新状态
        await self.redis_client.hset(
            f"task:{task_id}",
            "status", DistributedTaskStatus.CANCELLED
        )
        
        # 从待处理队列移除
        await self.redis_client.zrem("pending_tasks", task_id)
        
        return True
        
    async def _coordinator_loop(self):
        """协调者主循环"""
        while self.is_coordinator:
            try:
                await self._process_pending_tasks()
                await self._check_timeout_tasks()
                await self._cleanup_completed_tasks()
                await asyncio.sleep(5)  # 每5秒检查一次
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"协调者循环错误: {e}")
                await asyncio.sleep(10)
                
    async def _process_pending_tasks(self):
        """处理待分配任务"""
        # 获取最高优先级的任务
        pending = await self.redis_client.zrevrange("pending_tasks", 0, 9, withscores=True)
        
        if not pending:
            return
            
        # 获取可用节点
        available_nodes = await self.node_manager.get_active_nodes()
        
        for task_id, score in pending:
            task_data = await self.redis_client.hgetall(f"task:{task_id}")
            if not task_data:
                await self.redis_client.zrem("pending_tasks", task_id)
                continue
                
            task = DistributedTask(**task_data)
            
            # 检查依赖是否完成
            if not await self._check_dependencies(task):
                continue
                
            # 选择最优节点
            optimal_node = await self.load_balancer.select_optimal_node(task, available_nodes)
            
            if optimal_node:
                # 分配任务
                task.status = DistributedTaskStatus.ASSIGNED
                task.assigned_node = optimal_node.node_id
                
                await self.redis_client.hset(
                    f"task:{task.task_id}",
                    mapping=task.to_dict()
                )
                
                # 从待处理队列移除
                await self.redis_client.zrem("pending_tasks", task_id)
                
                # 通知工作节点
                await self._notify_worker_node(optimal_node, task)
                
                logger.info(f"任务 {task.task_id} 已分配给节点 {optimal_node.node_id}")
                
    async def _check_dependencies(self, task: DistributedTask) -> bool:
        """检查任务依赖是否完成"""
        for dep_task_id in task.dependencies:
            dep_task_data = await self.redis_client.hgetall(f"task:{dep_task_id}")
            if not dep_task_data or dep_task_data['status'] != DistributedTaskStatus.COMPLETED:
                return False
        return True
        
    async def _notify_worker_node(self, node: NodeInfo, task: DistributedTask):
        """通知工作节点执行任务"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"http://{node.host}:{node.port}/api/worker/execute",
                    json=task.to_dict(),
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    logger.error(f"通知节点 {node.node_id} 失败: {response.status_code}")
                    # 重新放入队列
                    await self.redis_client.zadd("pending_tasks", {task.task_id: 2})
                    
        except Exception as e:
            logger.error(f"通知节点 {node.node_id} 异常: {e}")
            # 重新放入队列
            await self.redis_client.zadd("pending_tasks", {task.task_id: 2})
            
    async def _check_timeout_tasks(self):
        """检查超时任务"""
        current_time = datetime.now()
        
        # 获取所有进行中的任务
        active_tasks = await self.redis_client.keys("task:*")
        
        for task_key in active_tasks:
            task_data = await self.redis_client.hgetall(task_key)
            if not task_data or task_data['status'] not in [
                DistributedTaskStatus.ASSIGNED, 
                DistributedTaskStatus.PROCESSING
            ]:
                continue
                
            started_at = datetime.fromisoformat(task_data['started_at']) if task_data.get('started_at') else None
            timeout = int(task_data.get('timeout', 3600))
            
            if started_at and (current_time - started_at).total_seconds() > timeout:
                # 任务超时
                task_id = task_key.split(':')[1]
                await self._handle_timeout_task(task_id, task_data)
                
    async def _handle_timeout_task(self, task_id: str, task_data: Dict[str, Any]):
        """处理超时任务"""
        retry_count = int(task_data.get('retry_count', 0))
        max_retries = int(task_data.get('max_retries', 3))
        
        if retry_count < max_retries:
            # 重试
            await self.redis_client.hset(
                f"task:{task_id}",
                mapping={
                    'status': DistributedTaskStatus.PENDING,
                    'retry_count': retry_count + 1,
                    'assigned_node': '',
                    'started_at': '',
                    'error': f'Timeout after {task_data.get("timeout", 3600)} seconds'
                }
            )
            
            # 重新加入队列
            priority_score = 2  # 重试任务使用普通优先级
            await self.redis_client.zadd("pending_tasks", {task_id: priority_score})
            
            logger.warning(f"任务 {task_id} 超时，开始第 {retry_count + 1} 次重试")
        else:
            # 超过最大重试次数，标记为失败
            await self.redis_client.hset(
                f"task:{task_id}",
                mapping={
                    'status': DistributedTaskStatus.FAILED,
                    'error': f'Exceeded max retries ({max_retries}) after timeout'
                }
            )
            
            logger.error(f"任务 {task_id} 超过最大重试次数，标记为失败")
            
    async def _cleanup_completed_tasks(self):
        """清理已完成的任务"""
        cutoff_time = datetime.now() - timedelta(hours=24)  # 保留24小时
        
        completed_tasks = await self.redis_client.keys("task:*")
        
        for task_key in completed_tasks:
            task_data = await self.redis_client.hgetall(task_key)
            if not task_data:
                continue
                
            if task_data['status'] in [DistributedTaskStatus.COMPLETED, DistributedTaskStatus.FAILED]:
                completed_at = task_data.get('completed_at')
                if completed_at:
                    completed_time = datetime.fromisoformat(completed_at)
                    if completed_time < cutoff_time:
                        await self.redis_client.delete(task_key)

class WorkerNode:
    """工作节点"""
    
    def __init__(self, redis_client, node_manager: NodeManager):
        self.redis_client = redis_client
        self.node_manager = node_manager
        self.executor = ThreadPoolExecutor(max_workers=psutil.cpu_count())
        self.active_tasks = {}
        
    async def execute_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行任务"""
        task = DistributedTask(**task_data)
        
        # 更新任务状态
        task.status = DistributedTaskStatus.PROCESSING
        task.started_at = datetime.now()
        
        await self.redis_client.hset(
            f"task:{task.task_id}",
            mapping=task.to_dict()
        )
        
        self.active_tasks[task.task_id] = task
        
        try:
            # 执行任务
            result = await self._execute_task_by_type(task)
            
            # 更新完成状态
            task.status = DistributedTaskStatus.COMPLETED
            task.completed_at = datetime.now()
            task.result = result
            
            await self.redis_client.hset(
                f"task:{task.task_id}",
                mapping=task.to_dict()
            )
            
            logger.info(f"任务 {task.task_id} 执行完成")
            return {"status": "success", "result": result}
            
        except Exception as e:
            # 更新失败状态
            task.status = DistributedTaskStatus.FAILED
            task.error = str(e)
            task.completed_at = datetime.now()
            
            await self.redis_client.hset(
                f"task:{task.task_id}",
                mapping=task.to_dict()
            )
            
            logger.error(f"任务 {task.task_id} 执行失败: {e}")
            return {"status": "error", "error": str(e)}
            
        finally:
            self.active_tasks.pop(task.task_id, None)
            
    async def _execute_task_by_type(self, task: DistributedTask) -> Any:
        """根据任务类型执行任务"""
        if task.task_type == "document_processing":
            return await self._process_document_task(task)
        elif task.task_type == "batch_vectorization":
            return await self._process_batch_vectorization(task)
        elif task.task_type == "thumbnail_generation":
            return await self._process_thumbnail_task(task)
        elif task.task_type == "format_conversion":
            return await self._process_conversion_task(task)
        else:
            raise ValueError(f"不支持的任务类型: {task.task_type}")
            
    async def _process_document_task(self, task: DistributedTask) -> Dict[str, Any]:
        """处理文档任务"""
        # 这里调用现有的文档处理逻辑
        return {"processed": True, "document_id": task.data.get('document_id')}
        
    async def _process_batch_vectorization(self, task: DistributedTask) -> Dict[str, Any]:
        """处理批量向量化任务"""
        # 这里调用现有的向量化逻辑
        return {"vectorized": True, "vectors_count": task.data.get('chunks_count', 0)}
        
    async def _process_thumbnail_task(self, task: DistributedTask) -> Dict[str, Any]:
        """处理缩略图生成任务"""
        # 这里调用现有的缩略图生成逻辑
        return {"thumbnail_generated": True, "thumbnail_path": task.data.get('output_path')}
        
    async def _process_conversion_task(self, task: DistributedTask) -> Dict[str, Any]:
        """处理格式转换任务"""
        # 这里调用现有的格式转换逻辑
        return {"converted": True, "output_format": task.data.get('target_format')}

# 全局实例
distributed_queue = None
node_manager = None

async def init_distributed_system(redis_url: str, node_role: NodeRole = NodeRole.HYBRID,
                                 host: str = "localhost", port: int = 8000,
                                 capabilities: List[str] = None) -> DistributedTaskQueue:
    """初始化分布式系统"""
    global distributed_queue, node_manager
    
    if capabilities is None:
        capabilities = [
            "document_processing",
            "batch_vectorization", 
            "thumbnail_generation",
            "format_conversion"
        ]
    
    # 创建Redis连接
    redis_client = redis.from_url(redis_url, decode_responses=True)
    
    # 创建节点管理器
    node_manager = NodeManager(redis_client)
    await node_manager.register_node(host, port, node_role, capabilities)
    
    # 创建分布式队列
    distributed_queue = DistributedTaskQueue(redis_client, node_manager)
    
    # 如果是协调者角色，启动协调者
    if node_role in [NodeRole.COORDINATOR, NodeRole.HYBRID]:
        await distributed_queue.start_coordinator()
        
    logger.info(f"分布式系统初始化完成 - 角色: {node_role}")
    return distributed_queue

async def shutdown_distributed_system():
    """关闭分布式系统"""
    global distributed_queue, node_manager
    
    if distributed_queue:
        await distributed_queue.stop_coordinator()
        
    if node_manager:
        await node_manager.unregister_node()
        
    logger.info("分布式系统已关闭")


class DistributedTaskProcessor:
    """分布式任务处理器 - 增强模块的主入口类"""
    
    def __init__(self, redis_url: str = None):
        """初始化分布式任务处理器"""
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self.distributed_queue = None
        self.node_manager = None
        self.is_initialized = False
        logger.info("DistributedTaskProcessor 初始化")
    
    async def initialize(self, node_role: NodeRole = NodeRole.HYBRID,
                        host: str = "localhost", port: int = 8001,
                        capabilities: List[str] = None):
        """初始化分布式处理系统"""
        try:
            self.distributed_queue = await init_distributed_system(
                self.redis_url, node_role, host, port, capabilities
            )
            self.is_initialized = True
            logger.info("分布式任务处理器初始化成功")
        except Exception as e:
            logger.warning(f"分布式任务处理器初始化失败: {e}")
            self.is_initialized = False
    
    async def submit_task(self, task_type: str, task_data: Dict[str, Any],
                         priority: TaskPriority = TaskPriority.NORMAL) -> Optional[str]:
        """提交分布式任务"""
        if not self.is_initialized or not self.distributed_queue:
            logger.warning("分布式任务处理器未初始化，无法提交任务")
            return None
        
        try:
            task_id = await self.distributed_queue.submit_task(task_type, task_data, priority)
            logger.info(f"分布式任务已提交: {task_id}")
            return task_id
        except Exception as e:
            logger.error(f"提交分布式任务失败: {e}")
            return None
    
    async def get_task_status(self, task_id: str) -> Optional[DistributedTaskStatus]:
        """获取任务状态"""
        if not self.is_initialized or not self.distributed_queue:
            return None
        
        try:
            return await self.distributed_queue.get_task_status(task_id)
        except Exception as e:
            logger.error(f"获取任务状态失败: {e}")
            return None
    
    async def get_node_status(self) -> Dict[str, Any]:
        """获取节点状态信息"""
        if not self.is_initialized:
            return {"status": "not_initialized"}
        
        try:
            nodes = await self.node_manager.get_all_nodes() if self.node_manager else []
            queue_stats = await self.distributed_queue.get_queue_stats() if self.distributed_queue else {}
            
            return {
                "status": "initialized",
                "nodes_count": len(nodes),
                "active_nodes": len([n for n in nodes if n.status == "active"]),
                "queue_stats": queue_stats
            }
        except Exception as e:
            logger.error(f"获取节点状态失败: {e}")
            return {"status": "error", "error": str(e)}
    
    async def shutdown(self):
        """关闭分布式处理器"""
        if self.is_initialized:
            await shutdown_distributed_system()
            self.is_initialized = False
            logger.info("分布式任务处理器已关闭")
