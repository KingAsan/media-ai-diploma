import os
import uvicorn
import httpx
import json
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from sqlalchemy import desc

from passlib.context import CryptContext
from jose import JWTError, jwt

from youtube_search import YoutubeSearch

from database import engine, SessionLocal, Base
from models import HistoryEntry, User

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

api_key = os.getenv("GOOGLE_API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY", "diploma-super-secret-key-asanali")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

MODEL_NAME = "gemini-2.5-flash"
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{MODEL_NAME}:generateContent?key={api_key}"
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Media Universe - Diploma Project")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def asset_path(*parts: str) -> Path:
    return BASE_DIR.joinpath(*parts)


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Сессия истекла, войдите снова",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError as exc:
        raise credentials_exception from exc

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user


def resolve_download_file() -> Path | None:
    candidates = [
        asset_path("dist", "MediaAI", "MediaAI.exe"),
        asset_path("dist", "MediaAI.exe"),
        asset_path("downloads", "MediaAI.exe"),
        asset_path("downloads", "MediaAI.zip"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


class UserCreate(BaseModel):
    username: str
    password: str


class UserRequest(BaseModel):
    query: str
    session_id: str
    temporary: bool = False


@app.post("/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Пользователь уже существует")

    
    is_admin = db.query(User).count() == 0

    hashed_pwd = get_password_hash(user.password)
    new_user = User(username=user.username, hashed_password=hashed_pwd, is_admin=is_admin)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    token = create_access_token(data={"sub": new_user.username})
    return {
        "access_token": token,
        "token_type": "bearer",
        "is_admin": is_admin,
        "username": new_user.username,
    }


@app.post("/token")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    token = create_access_token(data={"sub": user.username})
    return {
        "access_token": token,
        "token_type": "bearer",
        "is_admin": user.is_admin,
        "username": user.username,
    }


@app.get("/")
async def serve_index():
    return FileResponse(asset_path("templates", "index.html"))


@app.get("/manifest.json")
async def serve_manifest():
    return FileResponse(asset_path("manifest.json"), media_type="application/manifest+json")


@app.get("/icon.png")
async def serve_icon():
    return FileResponse(asset_path("icon.png"))


@app.get("/service-worker.js")
async def serve_sw():
    return FileResponse(asset_path("service-worker.js"), media_type="application/javascript")


@app.get("/sakura.gif")
async def serve_gif():
    gif_path = asset_path("sakura.gif")
    if not gif_path.exists():
        raise HTTPException(status_code=404, detail="GIF файл не найден")
    return FileResponse(gif_path)


@app.get("/health")
async def healthcheck():
    download_file = resolve_download_file()
    return {
        "status": "ok",
        "gemini_configured": bool(api_key),
        "desktop_download_available": bool(download_file),
        "download_file": download_file.name if download_file else None,
    }


from fastapi.responses import RedirectResponse

@app.get("/download")
async def download_app():
    return RedirectResponse(
        url="https://github.com/KingAsan/media-ai-diploma/releases/download/MediaAI/MediaAI.exe",
        status_code=302
    )


def find_trailer(title, category):
    try:
        search_query = f"{title} трейлер"
        if category and ("Музыка" in category or "Music" in category):
            search_query = f"{title} official video"

        results = YoutubeSearch(search_query, max_results=1).to_dict()
        return results[0]["id"] if results else None
    except Exception as e:
        print(f"YouTube Search Error: {e}")
        return None


@app.post("/recommend")
async def get_recommendation(
    request: UserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    system_instruction = (
        "Ты — элитный персональный ассистент по развлечениям. "
        "Твоя база знаний охватывает всё: 🎬 Фильмы, 🍿 Сериалы, 🎮 Игры (ПК/Консоли), 🎵 Музыку и ⛩️ Аниме. "
        f"Входящий запрос пользователя: '{request.query}'. "
        "Твоя задача: "
        "1. Глубоко проанализировать запрос, понять настроение, жанр или скрытые предпочтения. "
        "2. Предложить 3 идеальных, максимально подходящих варианта. "
        "3. В поле 'description' используй возможности Markdown: "
        "   - Выделяй **жирным** ключевые особенности или имена. "
        "   - Используй маркированные списки (•) для перечисления плюсов или атмосферы. "
        "   - Пиши живым, вовлекающим языком. "
        "ВАЖНО: Твой ответ должен быть СТРОГО в формате JSON списка. "
        "Структура JSON: "
        "[{'title': 'Название', 'year_genre': 'Год | Жанр', 'description': 'Описание с Markdown', 'category': 'Категория' }]"
    )

    payload = {
        "contents": [{"parts": [{"text": system_instruction}]}],
        "generationConfig": {"response_mime_type": "application/json"},
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(GEMINI_URL, json=payload, timeout=60.0)
            if response.status_code != 200:
                raise HTTPException(status_code=500, detail="Ошибка API Gemini")

            data = response.json()
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            recommendations = json.loads(raw_text)

            history_text = ""
            for item in recommendations:
                item["video_id"] = find_trailer(item.get("title", ""), item.get("category", ""))
                history_text += f"**{item.get('title')}**\n{item.get('description')}\n\n"

            if not request.temporary:
                new_entry = HistoryEntry(
                    session_id=request.session_id,
                    user_query=request.query,
                    ai_response=history_text,
                    ai_response_json=json.dumps(recommendations, ensure_ascii=False),
                    user_id=current_user.id,
                )
                db.add(new_entry)
                db.commit()

            return {"recommendations": recommendations, "is_json": True}

        except Exception as e:
            print(f"Error: {e}")
            return {"recommendations": f"Произошла ошибка: {str(e)}", "is_json": False}


@app.get("/api/sessions")
def get_sessions(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    history = (
        db.query(HistoryEntry)
        .filter(HistoryEntry.user_id == current_user.id)
        .order_by(desc(HistoryEntry.timestamp))
        .all()
    )
    sessions = []
    seen_ids = set()
    for item in history:
        if item.session_id not in seen_ids:
            sessions.append({"session_id": item.session_id, "title": item.user_query})
            seen_ids.add(item.session_id)
    return sessions


@app.get("/api/chat/{session_id}")
def get_chat_history(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(HistoryEntry)
        .filter(
            HistoryEntry.session_id == session_id,
            HistoryEntry.user_id == current_user.id,
        )
        .order_by(HistoryEntry.id)
        .all()
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)




