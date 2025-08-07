# project/base.py
# 这是一个只定义 SQLAlchemy Base 的文件，用于避免循环导入
from sqlalchemy.orm import declarative_base

Base = declarative_base()
