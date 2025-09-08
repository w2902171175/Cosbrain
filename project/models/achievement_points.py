# project/models/achievement_points.py
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from project.base import Base


# 默认成就数据配置
DEFAULT_ACHIEVEMENTS = [
    {
        "name": "初次见面",
        "description": "首次登录平台，踏上创新协作之旅！",
        "criteria_type": "LOGIN_COUNT",
        "criteria_value": 1.0,
        "badge_url": "/static/badges/welcome.png",
        "reward_points": 10,
        "is_active": True
    },
    {
        "name": "每日坚持",
        "description": "连续登录 7 天，养成每日学习与协作的习惯！",
        "criteria_type": "DAILY_LOGIN_STREAK",
        "criteria_value": 7.0,
        "badge_url": "/static/badges/daily_streak.png",
        "reward_points": 50,
        "is_active": True
    },
    {
        "name": "项目新手",
        "description": "你的第一个项目已成功完成，在实践中探索AI应用！",
        "criteria_type": "PROJECT_COMPLETED_COUNT",
        "criteria_value": 1.0,
        "badge_url": "/static/badges/project_novice.png",
        "reward_points": 100,
        "is_active": True
    },
    {
        "name": "项目骨干",
        "description": "累计完成 3 个项目，你已是项目协作的得力助手！",
        "criteria_type": "PROJECT_COMPLETED_COUNT",
        "criteria_value": 3.0,
        "badge_url": "/static/badges/project_backbone.png",
        "reward_points": 200,
        "is_active": True
    },
    {
        "name": "学习起步",
        "description": "成功完成 1 门课程，点亮个人知识树！",
        "criteria_type": "COURSE_COMPLETED_COUNT",
        "criteria_value": 1.0,
        "badge_url": "/static/badges/course_starter.png",
        "reward_points": 20,
        "is_active": True
    },
    {
        "name": "课程达人",
        "description": "累计完成 3 门课程，你是名副其实的知识探索者！",
        "criteria_type": "COURSE_COMPLETED_COUNT",
        "criteria_value": 3.0,
        "badge_url": "/static/badges/course_expert.png",
        "reward_points": 80,
        "is_active": True
    },
    {
        "name": "初试啼声",
        "description": "首次在论坛发布话题或评论，与社区积极互动！",
        "criteria_type": "FORUM_POSTS_COUNT",
        "criteria_value": 1.0,
        "badge_url": "/static/badges/forum_post_novice.png",
        "reward_points": 5,
        "is_active": True
    },
    {
        "name": "社区参与者",
        "description": "在论坛发布累计 10 个话题或评论，积极分享你的见解！",
        "criteria_type": "FORUM_POSTS_COUNT",
        "criteria_value": 10.0,
        "badge_url": "/static/badges/forum_participant.png",
        "reward_points": 30,
        "is_active": True
    },
    {
        "name": "小有名气",
        "description": "你的话题或评论获得了 5 次点赞，内容已被认可！",
        "criteria_type": "FORUM_LIKES_RECEIVED",
        "criteria_value": 5.0,
        "badge_url": "/static/badges/likes_5.png",
        "reward_points": 25,
        "is_active": True
    },
    {
        "name": "人气之星",
        "description": "你的话题或评论获得了 20 次点赞，在社区中声名鹊起！",
        "criteria_type": "FORUM_LIKES_RECEIVED",
        "criteria_value": 20.0,
        "badge_url": "/static/badges/likes_stars.png",
        "reward_points": 100,
        "is_active": True
    },
    {
        "name": "沟通达人",
        "description": "累计发送 50 条聊天消息，你活跃在团队协作的前线！",
        "criteria_type": "CHAT_MESSAGES_SENT_COUNT",
        "criteria_value": 50.0,
        "badge_url": "/static/badges/chat_master.png",
        "reward_points": 20,
        "is_active": True
    }
]


class Achievement(Base):
    __tablename__ = "achievements"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, comment="成就名称")
    description = Column(Text, nullable=False, comment="成就描述")
    # 成就达成条件类型，例如：PROJECT_COMPLETED_COUNT, COURSE_COMPLETED_COUNT, FORUM_LIKES_RECEIVED, DAILY_LOGIN_STREAK
    criteria_type = Column(String, nullable=False, comment="达成成就的条件类型")
    criteria_value = Column(Float, nullable=False, comment="达成成就所需的数值门槛") # 使用Float以支持小数，如平均分
    badge_url = Column(String, nullable=True, comment="勋章图片或图标URL")
    reward_points = Column(Integer, default=0, nullable=False, comment="达成此成就额外奖励的积分")
    is_active = Column(Boolean, default=True, nullable=False, comment="该成是否启用")

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    earned_by_users = relationship("UserAchievement", back_populates="achievement", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Achievement(id={self.id}, name='{self.name}', criteria_type='{self.criteria_type}')>"


class UserAchievement(Base):
    __tablename__ = "user_achievements"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    achievement_id = Column(Integer, ForeignKey("achievements.id"), nullable=False)
    earned_at = Column(DateTime, server_default=func.now(), nullable=False)
    is_notified = Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="achievements")
    achievement = relationship("Achievement", back_populates="earned_by_users")

    __table_args__ = (
        UniqueConstraint('user_id', 'achievement_id', name='_user_achievement_uc'), # 确保一个用户不会重复获得同一个成就
    )

    def __repr__(self):
        return f"<UserAchievement(user_id={self.user_id}, achievement_id={self.achievement_id})>"


class PointTransaction(Base):
    __tablename__ = "point_transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Integer, nullable=False, comment="积分变动金额（正数获得，负数消耗）")
    reason = Column(String, nullable=True, comment="积分变动理由描述")
    # 交易类型：EARN, CONSUME, ADMIN_ADJUST 等
    transaction_type = Column(String, nullable=False, comment="积分交易类型")
    related_entity_type = Column(String, nullable=True, comment="关联的实体类型")
    related_entity_id = Column(Integer, nullable=True, comment="关联实体的ID")

    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="point_transactions")

    def __repr__(self):
        return f"<PointTransaction(user_id={self.user_id}, amount={self.amount}, type='{self.transaction_type}')>"
