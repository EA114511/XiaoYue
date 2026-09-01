"""
数据库模块（Async SQLAlchemy + SQLite）

提供异步数据库引擎、会话工厂和 CRUD 操作。
支持对话历史、消息记录的持久化存储。
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Column, DateTime, Float, ForeignKey, Integer, String, Text, select,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship, selectinload

from app.core.config import settings

logger = logging.getLogger("voice-assistant")


# ============================================================
# ORM 基类
# ============================================================
class Base(DeclarativeBase):
    pass


# ============================================================
# 数据表模型
# ============================================================
class ConversationRecord(Base):
    """对话记录表"""
    __tablename__ = "conversations"

    id = Column(String(64), primary_key=True)
    title = Column(String(256), default="新对话")
    status = Column(String(32), default="active", index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship(
        "MessageRecord", back_populates="conversation",
        cascade="all, delete-orphan", order_by="MessageRecord.timestamp",
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "message_count": len(self.messages) if self.messages else 0,
        }


class MessageRecord(Base):
    """消息记录表"""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(
        String(64), ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    role = Column(String(16), nullable=False)  # user / assistant / system
    content = Column(Text, nullable=False)
    intent = Column(String(64), nullable=True)
    confidence = Column(Float, nullable=True)
    entities = Column(Text, nullable=True)  # JSON 存储
    timestamp = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("ConversationRecord", back_populates="messages")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "role": self.role,
            "content": self.content,
            "intent": self.intent,
            "confidence": self.confidence,
            "entities": json.loads(self.entities) if self.entities else None,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


# ============================================================
# 数据库服务
# ============================================================
class DatabaseService:
    """异步数据库操作封装"""

    def __init__(self, db_url: Optional[str] = None):
        self._db_url = db_url or settings.DATABASE_URL
        # 将 sqlite:/// 转换为 aiosqlite 可识别的异步 URL
        if self._db_url.startswith("sqlite:///"):
            self._async_url = self._db_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
        else:
            self._async_url = self._db_url
        self._engine = None
        self._session_factory = None

    async def initialize(self):
        """初始化数据库连接和表结构"""
        logger.info(f"[Database] 正在连接数据库: {self._db_url}")

        self._engine = create_async_engine(
            self._async_url,
            echo=False,
            connect_args={"check_same_thread": False},
        )

        # 创建所有表
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False,
        )

        logger.info("[Database] 数据库初始化完成")

    async def cleanup(self):
        """关闭数据库连接"""
        if self._engine:
            await self._engine.dispose()
            logger.info("[Database] 数据库连接已关闭")

    # ─── 会话操作 ──────────────────────────────────────────

    async def save_conversation(self, conv_id: str, title: str = "新对话") -> bool:
        """保存新会话到数据库"""
        async with self._session_factory() as session:
            existing = await session.get(ConversationRecord, conv_id)
            if existing:
                return False  # 已存在
            record = ConversationRecord(id=conv_id, title=title)
            session.add(record)
            await session.commit()
            return True

    async def get_conversation(self, conv_id: str) -> Optional[Dict[str, Any]]:
        """获取会话详情（含消息）"""
        async with self._session_factory() as session:
            stmt = (
                select(ConversationRecord)
                .where(ConversationRecord.id == conv_id)
                .options(selectinload(ConversationRecord.messages))
            )
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()
            return record.to_dict() if record else None

    async def list_conversations(
        self, limit: int = 50, offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """列出最近会话"""
        async with self._session_factory() as session:
            stmt = (
                select(ConversationRecord)
                .order_by(ConversationRecord.updated_at.desc())
                .offset(offset)
                .limit(limit)
            )
            result = await session.execute(stmt)
            records = result.scalars().all()
            return [r.to_dict() for r in records]

    async def delete_conversation(self, conv_id: str) -> bool:
        """删除会话及其所有消息"""
        async with self._session_factory() as session:
            record = await session.get(ConversationRecord, conv_id)
            if not record:
                return False
            await session.delete(record)
            await session.commit()
            return True

    # ─── 消息操作 ──────────────────────────────────────────

    async def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        intent: Optional[str] = None,
        confidence: Optional[float] = None,
        entities: Optional[Dict[str, Any]] = None,
    ) -> int:
        """保存消息并更新会话时间戳"""
        async with self._session_factory() as session:
            # 确保会话存在
            conv = await session.get(ConversationRecord, conversation_id)
            if not conv:
                conv = ConversationRecord(id=conversation_id)
                session.add(conv)

            msg = MessageRecord(
                conversation_id=conversation_id,
                role=role,
                content=content,
                intent=intent,
                confidence=confidence,
                entities=json.dumps(entities, ensure_ascii=False) if entities else None,
            )
            session.add(msg)

            # 更新会话时间戳
            conv.updated_at = datetime.utcnow()

            await session.commit()
            return msg.id  # type: ignore

    async def get_conversation_messages(
        self, conversation_id: str, limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """获取会话消息列表"""
        async with self._session_factory() as session:
            stmt = (
                select(MessageRecord)
                .where(MessageRecord.conversation_id == conversation_id)
                .order_by(MessageRecord.timestamp.asc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            records = result.scalars().all()
            return [r.to_dict() for r in records]


# 全局单例
database_service = DatabaseService()
