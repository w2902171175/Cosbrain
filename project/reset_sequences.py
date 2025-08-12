# project/reset_sequences.py
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from database import DATABASE_URL
load_dotenv()

if not DATABASE_URL:
    raise ValueError("DATABASE_URL 环境变量未设置。请确保 .env 文件存在且 DATABASE_URL 已配置。")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def reset_all_sequences_after_import():
    print("正在重置数据库序列以避免ID冲突...")

    tables_to_reset = [
        "students", "projects", "notes", "daily_records", "folders",
        "collected_contents", "chat_rooms", "chat_messages", "forum_topics",
        "forum_comments", "forum_likes", "user_follows", "user_mcp_configs",
        "user_search_engine_configs", "knowledge_bases", "knowledge_articles",
        "knowledge_documents", "knowledge_document_chunks", "courses"
    ]

    db_session = SessionLocal()
    try:
        for table_name in tables_to_reset:
            sequence_name = f"{table_name}_id_seq"

            command = text(
                f"SELECT setval('{sequence_name}', COALESCE((SELECT MAX(id) FROM {table_name}), 0) + 1, false);")

            try:
                db_session.execute(command)
                db_session.commit()
                print(f"成功重置并提升 '{sequence_name}' 序列。")
            except Exception as e:
                db_session.rollback()
                print(f"警告: 未能重置或提升 '{sequence_name}' 序列 (可能表或序列不存在，或无ID列): {e}")

    finally:
        db_session.close()
    print("所有数据库序列重置完成。")


if __name__ == "__main__":
    reset_all_sequences_after_import()

