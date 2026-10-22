"""启动 AI 智行助手服务。运行: python run.py  然后访问 http://127.0.0.1:8000"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=False)
