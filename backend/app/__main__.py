import os
from pathlib import Path

from dotenv import load_dotenv
import uvicorn


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env")
    uvicorn.run(
        "backend.app.main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        reload=True,
    )
