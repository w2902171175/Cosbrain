# project/temp_main.py (极简版，用于诊断)
from fastapi import FastAPI

app = FastAPI(title="Minimal API Test")

@app.get("/health", summary="健康检查")
def health_check():
    return {"status": "ok", "message": "Minimal API running!"}

# 暂时不导入任何 models, schemas, database, ai_core
