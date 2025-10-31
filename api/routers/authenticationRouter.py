from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import pymysql, bcrypt, jwt
from datetime import datetime, timedelta

from database_functions import get_mysql_connection,add_multiple_elements,DbPathEnum,fetch_one_element
from schemas import LoginRequest, TokenResponse, UserInfo,UserCreateRequest
from config_loader import JWT_SECRET_KEY,JWT_TOKEN_EXPIRE_MINUTES,JWT_ALGORITHM


bearer_scheme = HTTPBearer()

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.now() + (expires_delta or timedelta(minutes=JWT_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

def normalize_hash_for_check(stored_hash: str) -> str:
    """Convert Laravel $2y$ prefix to $2b$ for Python bcrypt verification."""
    if stored_hash.startswith("$2y$"):
        return "$2b$" + stored_hash[4:]
    return stored_hash

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")









def getAuthenticationRouter():
    auth_router = APIRouter(tags=["Authentication"], prefix="/auth")

    @auth_router.post("/login", response_model=TokenResponse)
    def login(data: LoginRequest, use_sqlite: bool = True):
        user = None
        if use_sqlite:
            query = "SELECT id, password FROM User WHERE email = ?"
            user = fetch_one_element(DbPathEnum.CONFIGURATION, query, (data.email,))
        else:
            conn = get_mysql_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT id, password FROM users WHERE email = %s", (data.email,))
                    user = cursor.fetchone()
            finally:
                conn.close()

        if not user:
            raise HTTPException(status_code=401, detail="Invalid email")

        stored_pw = normalize_hash_for_check(user["password"])
        if not bcrypt.checkpw(data.password.encode(), stored_pw.encode()):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        token = create_access_token({"user_id": user["id"], "email": data.email})
        return {"access_token": token, "token_type": "bearer"}

    @auth_router.post("/register")
    def register(user_data: UserCreateRequest):
        # Hash password and convert to Laravel $2y$ format
        hashed_pw = bcrypt.hashpw(user_data.password.encode(), bcrypt.gensalt(rounds=12)).decode()
        laravel_hash = "$2y$" + hashed_pw[4:]

        # Default values
        now_iso = datetime.utcnow().isoformat()
        email_verified_at = None
        remember_token = None
        preference = "Health;Security;Entertainment;Study"
        url_photo = None
        privacy_1 = 0
        privacy_2 = 0

        # SQLite path
        if user_data.use_sqlite:
            query = (
                "INSERT INTO User (username, email, email_verified_at, password, remember_token, "
                "created_at, updated_at, preference, url_photo, privacy_1, privacy_2) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            )
            values = (
                user_data.username,
                user_data.email,
                email_verified_at,
                laravel_hash,
                remember_token,
                now_iso,
                now_iso,
                preference,
                url_photo,
                privacy_1,
                privacy_2,
            )
            success = add_multiple_elements(DbPathEnum.CONFIGURATION, query, [values])
            if not success:
                raise HTTPException(status_code=500, detail="Failed to insert user into SQLite")
            return {"status": "success", "message": f"User '{user_data.username}' added to SQLite"}

        # MySQL path
        else:
            conn = get_mysql_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO users (username, email, email_verified_at, password, remember_token, created_at, updated_at, preference, url_photo, privacy_1, privacy_2) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            user_data.username,
                            user_data.email,
                            email_verified_at,
                            laravel_hash,
                            remember_token,
                            now_iso,
                            now_iso,
                            preference,
                            url_photo,
                            privacy_1,
                            privacy_2,
                        ),
                    )
                    conn.commit()
                    return {"status": "success", "message": f"User '{user_data.username}' added to MySQL"}
            except pymysql.IntegrityError:
                raise HTTPException(status_code=400, detail="User with this email already exists")
            except pymysql.Error as e:
                raise HTTPException(status_code=500, detail=f"MySQL Error: {e}")
            finally:
                conn.close()


    @auth_router.get("/me", response_model=UserInfo)
    def me(current_user: dict = Depends(get_current_user)):
        return {"user_id": current_user["user_id"], "email": current_user["email"]}

    @auth_router.post("/refresh", response_model=TokenResponse)
    def refresh(current_user: dict = Depends(get_current_user)):
        token = create_access_token({"user_id": current_user["user_id"], "email": current_user["email"]})
        return {"access_token": token, "token_type": "bearer"}

    return auth_router
