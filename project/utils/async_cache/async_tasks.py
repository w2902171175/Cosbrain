# project/utils/async_tasks.py
"""
异步任务处理系统 - 支持后台任务、定时任务和队列处理
"""
import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
import threading
import time

logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4

@dataclass
class Task:
    """异步任务数据类"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    func: Callable = None
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Any = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    timeout: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'id': self.id,
            'name': self.name,
            'priority': self.priority.value,
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'error': self.error
        }

class AsyncTaskQueue:
    """异步任务队列管理器"""
    
    def __init__(self, max_workers: int = 5, max_queue_size: int = 1000):
        self.max_workers = max_workers
        self.max_queue_size = max_queue_size
        self.tasks: Dict[str, Task] = {}
        self.pending_queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=max_queue_size)
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.completed_tasks: List[str] = []
        self.failed_tasks: List[str] = []
        self.workers: List[asyncio.Task] = []
        self.is_running = False
        self.stats = {
            'total_tasks': 0,
            'completed_tasks': 0,
            'failed_tasks': 0,
            'cancelled_tasks': 0
        }
        self._lock = asyncio.Lock()
    
    async def start(self):
        """启动任务队列"""
        if self.is_running:
            return
        
        self.is_running = True
        logger.info(f"启动异步任务队列，工作线程数: {self.max_workers}")
        
        # 创建工作线程
        for i in range(self.max_workers):
            worker = asyncio.create_task(self._worker(f"worker-{i}"))
            self.workers.append(worker)
    
    async def stop(self):
        """停止任务队列"""
        if not self.is_running:
            return
        
        self.is_running = False
        logger.info("停止异步任务队列")
        
        # 取消所有工作线程
        for worker in self.workers:
            worker.cancel()
        
        # 等待工作线程结束
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers.clear()
        
        # 取消所有运行中的任务
        for task_id, task in self.running_tasks.items():
            task.cancel()
            if task_id in self.tasks:
                self.tasks[task_id].status = TaskStatus.CANCELLED
        
        self.running_tasks.clear()
    
    async def submit_task(
        self,
        func: Callable,
        *args,
        name: str = "",
        priority: TaskPriority = TaskPriority.NORMAL,
        max_retries: int = 3,
        timeout: Optional[int] = None,
        **kwargs
    ) -> str:
        """提交任务到队列"""
        if not self.is_running:
            await self.start()
        
        # 创建任务
        task = Task(
            name=name or f"{func.__name__}_{int(time.time())}",
            func=func,
            args=args,
            kwargs=kwargs,
            priority=priority,
            max_retries=max_retries,
            timeout=timeout
        )
        
        # 存储任务
        async with self._lock:
            self.tasks[task.id] = task
            self.stats['total_tasks'] += 1
        
        # 添加到队列 (优先级队列，数值越小优先级越高)
        priority_value = 5 - priority.value  # 反转优先级
        await self.pending_queue.put((priority_value, task.created_at, task.id))
        
        logger.info(f"任务已提交: {task.name} (ID: {task.id}, 优先级: {priority.name})")
        return task.id
    
    async def _worker(self, worker_name: str):
        """工作线程"""
        logger.info(f"工作线程 {worker_name} 启动")
        
        while self.is_running:
            try:
                # 从队列获取任务 (等待最多1秒)
                try:
                    priority, created_at, task_id = await asyncio.wait_for(
                        self.pending_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                # 获取任务对象
                async with self._lock:
                    if task_id not in self.tasks:
                        continue
                    task = self.tasks[task_id]
                
                # 执行任务
                await self._execute_task(worker_name, task)
                
            except asyncio.CancelledError:
                logger.info(f"工作线程 {worker_name} 被取消")
                break
            except Exception as e:
                logger.error(f"工作线程 {worker_name} 发生错误: {e}")
    
    async def _execute_task(self, worker_name: str, task: Task):
        """执行单个任务"""
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()
        
        logger.info(f"工作线程 {worker_name} 开始执行任务: {task.name} (ID: {task.id})")
        
        try:
            # 创建执行任务
            if asyncio.iscoroutinefunction(task.func):
                exec_task = asyncio.create_task(task.func(*task.args, **task.kwargs))
            else:
                # 在线程池中执行同步函数
                loop = asyncio.get_event_loop()
                exec_task = loop.run_in_executor(
                    None, lambda: task.func(*task.args, **task.kwargs)
                )
            
            # 记录运行中的任务
            async with self._lock:
                self.running_tasks[task.id] = exec_task
            
            # 执行任务（带超时）
            if task.timeout:
                task.result = await asyncio.wait_for(exec_task, timeout=task.timeout)
            else:
                task.result = await exec_task
            
            # 任务完成
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now()
            
            async with self._lock:
                self.completed_tasks.append(task.id)
                self.stats['completed_tasks'] += 1
                if task.id in self.running_tasks:
                    del self.running_tasks[task.id]
            
            execution_time = (task.completed_at - task.started_at).total_seconds()
            logger.info(f"任务完成: {task.name} (ID: {task.id}, 耗时: {execution_time:.2f}s)")
            
        except asyncio.CancelledError:
            task.status = TaskStatus.CANCELLED
            async with self._lock:
                self.stats['cancelled_tasks'] += 1
                if task.id in self.running_tasks:
                    del self.running_tasks[task.id]
            logger.info(f"任务被取消: {task.name} (ID: {task.id})")
            
        except Exception as e:
            task.error = str(e)
            logger.error(f"任务执行失败: {task.name} (ID: {task.id}), 错误: {e}")
            
            # 重试逻辑
            if task.retry_count < task.max_retries:
                task.retry_count += 1
                task.status = TaskStatus.PENDING
                
                # 重新添加到队列
                priority_value = 5 - task.priority.value
                await self.pending_queue.put((priority_value, datetime.now(), task.id))
                
                logger.info(f"任务重试: {task.name} (ID: {task.id}, 重试次数: {task.retry_count})")
            else:
                task.status = TaskStatus.FAILED
                task.completed_at = datetime.now()
                
                async with self._lock:
                    self.failed_tasks.append(task.id)
                    self.stats['failed_tasks'] += 1
            
            async with self._lock:
                if task.id in self.running_tasks:
                    del self.running_tasks[task.id]
    
    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        if task_id in self.tasks:
            return self.tasks[task_id].to_dict()
        return None
    
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        async with self._lock:
            if task_id in self.running_tasks:
                self.running_tasks[task_id].cancel()
                return True
            elif task_id in self.tasks and self.tasks[task_id].status == TaskStatus.PENDING:
                self.tasks[task_id].status = TaskStatus.CANCELLED
                return True
        return False
    
    async def get_queue_stats(self) -> Dict[str, Any]:
        """获取队列统计信息"""
        async with self._lock:
            return {
                'queue_size': self.pending_queue.qsize(),
                'running_tasks': len(self.running_tasks),
                'total_tasks': self.stats['total_tasks'],
                'completed_tasks': self.stats['completed_tasks'],
                'failed_tasks': self.stats['failed_tasks'],
                'cancelled_tasks': self.stats['cancelled_tasks'],
                'workers': len(self.workers),
                'is_running': self.is_running
            }

# 全局任务队列实例
task_queue = AsyncTaskQueue()

# 便捷的装饰器和函数
def background_task(
    priority: TaskPriority = TaskPriority.NORMAL,
    max_retries: int = 3,
    timeout: Optional[int] = None
):
    """后台任务装饰器"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            return await task_queue.submit_task(
                func,
                *args,
                name=func.__name__,
                priority=priority,
                max_retries=max_retries,
                timeout=timeout,
                **kwargs
            )
        return wrapper
    return decorator

async def submit_background_task(
    func: Callable,
    *args,
    name: str = "",
    priority: TaskPriority = TaskPriority.NORMAL,
    **kwargs
) -> str:
    """提交后台任务"""
    return await task_queue.submit_task(
        func,
        *args,
        name=name,
        priority=priority,
        **kwargs
    )

# 启动任务队列
async def initialize_task_system():
    """初始化任务系统"""
    await task_queue.start()
    logger.info("异步任务系统已启动")

async def shutdown_task_system():
    """关闭任务系统"""
    await task_queue.stop()
    logger.info("异步任务系统已关闭")
