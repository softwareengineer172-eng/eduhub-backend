"""EduHub API — safer, semester-aware academic portal.

Configuration is provided through environment variables; no credentials belong in source code.
"""
from __future__ import annotations

import hmac
import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Generator, Optional
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Query, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, func, inspect, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, declarative_base, sessionmaker

APP_TITLE = "EduHub API"
APP_VERSION = "3.6.0"
DEFAULT_DB_URL = "sqlite:///./eduhub_v2.db"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DB_URL).strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql+psycopg2://" + DATABASE_URL[len("postgres://"):]
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg2://" + DATABASE_URL[len("postgresql://"):]

engine_options = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False, "timeout": 15}
engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
Base = declarative_base()

# ---------- Data models ----------
class Semester(Base):
    __tablename__ = "semesters"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(80), nullable=False, unique=True, index=True)
    academic_year = Column(String(30), nullable=False, default="")
    is_archived = Column(Boolean, nullable=False, default=False)

class Course(Base):
    __tablename__ = "courses"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, index=True)
    professor = Column(String(120), nullable=False, default="")
    semester_id = Column(Integer, ForeignKey("semesters.id", ondelete="RESTRICT"), nullable=False, index=True)
    has_practical = Column(Boolean, nullable=False, default=False)
    is_archived = Column(Boolean, nullable=False, default=False)

class Announcement(Base):
    __tablename__ = "announcements"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    content = Column(Text, nullable=False)
    is_archived = Column(Boolean, nullable=False, default=False)
    created_at = Column(String(40), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())

class AcademicFile(Base):
    __tablename__ = "academic_files"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    course_name = Column(String(100), nullable=False)
    type_section = Column(String(50), nullable=False)
    file_category = Column(String(50), nullable=False)
    title = Column(String(150), nullable=False)
    file_url = Column(Text, nullable=False)
    semester_name = Column(String(80), nullable=False, default="الترم الأول", index=True)
    is_archived = Column(Boolean, nullable=False, default=False)
    created_at = Column(String(40), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())

class StudentGrade(Base):
    __tablename__ = "student_grades"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    student_name = Column(String(150), nullable=False, index=True)
    course_name = Column(String(100), nullable=False)
    theory_grade = Column(Float, default=0.0)
    practical_grade = Column(Float, default=0.0)

class DailyAgenda(Base):
    __tablename__ = "daily_agenda"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    lecture_1 = Column(String(100), nullable=False, default="")
    time_1 = Column(String(50), nullable=False, default="")
    lecture_2 = Column(String(100), nullable=False, default="")
    time_2 = Column(String(50), nullable=False, default="")
    status_msg = Column(String(200), nullable=False, default="")
    updated_at = Column(String(40), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())

class UpcomingExam(Base):
    __tablename__ = "upcoming_exams"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    course_name = Column(String(100), nullable=False)
    exam_date_text = Column(String(100), nullable=False)
    exam_time = Column(String(50), nullable=False)
    timestamp = Column(String(100), nullable=False)
    updated_at = Column(String(40), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())

class ScheduleSettings(Base):
    __tablename__ = "schedule_settings"
    id = Column(Integer, primary_key=True, default=1)
    semester_start = Column(String(10), nullable=False)
    semester_end = Column(String(10), nullable=False)
    updated_at = Column(String(40), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())

class WeeklyLecture(Base):
    __tablename__ = "weekly_lectures"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    weekday = Column(Integer, nullable=False, index=True)  # Monday=0 ... Sunday=6
    title = Column(String(150), nullable=False)
    start_time = Column(String(10), nullable=False, default="")
    end_time = Column(String(10), nullable=False, default="")
    location = Column(String(120), nullable=False, default="")
    notes = Column(String(250), nullable=False, default="")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(String(40), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())

class AgendaOverride(Base):
    __tablename__ = "agenda_overrides"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    agenda_date = Column(String(10), nullable=False, unique=True, index=True)
    note = Column(String(500), nullable=False, default="")
    lectures_json = Column(Text, nullable=False, default="[]")
    updated_at = Column(String(40), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())

class AnalyticsUser(Base):
    """Pseudonymous browser/device identifier; no IP address or device fingerprint is stored."""
    __tablename__ = "analytics_users"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    device_id = Column(String(36), nullable=False, unique=True, index=True)
    first_seen_at = Column(String(40), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())
    last_seen_at = Column(String(40), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())

class AnalyticsSession(Base):
    """One row per browser tab/session; refreshes reuse sessionStorage and do not add visits."""
    __tablename__ = "analytics_sessions"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    session_id = Column(String(36), nullable=False, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("analytics_users.id", ondelete="CASCADE"), nullable=False, index=True)
    started_at = Column(String(40), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())
    last_seen_at = Column(String(40), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())

class AnalyticsDailyActivity(Base):
    __tablename__ = "analytics_daily_activity"
    __table_args__ = (UniqueConstraint("user_id", "activity_date", name="uq_analytics_user_day"),)
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("analytics_users.id", ondelete="CASCADE"), nullable=False, index=True)
    activity_date = Column(String(10), nullable=False, index=True)
    last_seen_at = Column(String(40), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())

# ---------- Request schemas ----------
class SemesterCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    academic_year: str = Field(default="", max_length=30)

class CourseCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    professor: str = Field(default="", max_length=120)
    semester_name: str = Field(default="الترم الأول", min_length=2, max_length=80)
    has_practical: bool = False

class AnnouncementCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)

class FileCreate(BaseModel):
    course_name: str = Field(min_length=1, max_length=100)
    type_section: str = Field(min_length=1, max_length=50)
    file_category: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=150)
    file_url: str = Field(min_length=8, max_length=2000)
    semester_name: str = Field(default="الترم الأول", min_length=2, max_length=80)

    @field_validator("file_url")
    @classmethod
    def safe_http_url(cls, value: str) -> str:
        value = value.strip()
        parsed = urlsplit(value)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            raise ValueError("رابط الملف يجب أن يبدأ بـ https:// أو http://")
        if any(ord(ch) < 32 for ch in value):
            raise ValueError("الرابط يحتوي على محارف غير صالحة")
        return value

class GradeCreate(BaseModel):
    student_name: str = Field(min_length=1, max_length=150)
    course_name: str = Field(min_length=1, max_length=100)
    theory_grade: float = Field(ge=0, le=100)
    practical_grade: float = Field(default=0, ge=0, le=100)

class AgendaCreate(BaseModel):
    lecture_1: str = Field(default="", max_length=100)
    time_1: str = Field(default="", max_length=50)
    lecture_2: str = Field(default="", max_length=100)
    time_2: str = Field(default="", max_length=50)
    status_msg: str = Field(default="", max_length=200)

class WeeklyLectureCreate(BaseModel):
    weekday: int = Field(ge=0, le=6)
    title: str = Field(min_length=1, max_length=150)
    start_time: str = Field(default="", max_length=5)
    end_time: str = Field(default="", max_length=5)
    location: str = Field(default="", max_length=120)
    notes: str = Field(default="", max_length=250)

    @field_validator("start_time", "end_time")
    @classmethod
    def valid_optional_time(cls, value: str) -> str:
        value = value.strip()
        if value == "":
            return value
        try:
            datetime.strptime(value, "%H:%M")
        except ValueError:
            raise ValueError("يجب إدخال الوقت بصيغة HH:MM مثل 08:30")
        return value

    @field_validator("end_time")
    @classmethod
    def end_after_start(cls, value: str, info):
        start = info.data.get("start_time", "")
        if start and value and value <= start:
            raise ValueError("وقت نهاية المحاضرة يجب أن يأتي بعد وقت بدايتها")
        return value

class ScheduleSettingsUpdate(BaseModel):
    semester_start: str = Field(min_length=10, max_length=10)
    semester_end: str = Field(min_length=10, max_length=10)

    @field_validator("semester_start", "semester_end")
    @classmethod
    def valid_iso_date(cls, value: str) -> str:
        try:
            date.fromisoformat(value)
        except ValueError:
            raise ValueError("يجب إدخال التاريخ بصيغة YYYY-MM-DD")
        return value

class LectureOverrideUpdate(BaseModel):
    weekly_lecture_id: int = Field(ge=1)
    title: Optional[str] = Field(default=None, max_length=150)
    start_time: Optional[str] = Field(default=None, max_length=10)
    end_time: Optional[str] = Field(default=None, max_length=10)
    location: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = Field(default=None, max_length=250)

class ScheduleOverrideCreate(BaseModel):
    agenda_date: str = Field(min_length=10, max_length=10)
    note: str = Field(default="", max_length=500)
    lecture_updates: list[LectureOverrideUpdate] = Field(default_factory=list, max_length=20)

    @field_validator("agenda_date")
    @classmethod
    def valid_agenda_date(cls, value: str) -> str:
        try:
            date.fromisoformat(value)
        except ValueError:
            raise ValueError("يجب إدخال التاريخ بصيغة YYYY-MM-DD")
        return value

class ExamCreate(BaseModel):
    course_name: str = Field(min_length=1, max_length=100)
    exam_date_text: str = Field(min_length=1, max_length=100)
    exam_time: str = Field(min_length=1, max_length=50)
    timestamp: str = Field(min_length=1, max_length=100)

class PresenceCreate(BaseModel):
    session_id: str = Field(min_length=8, max_length=80)

class AnalyticsTrack(BaseModel):
    device_id: str = Field(min_length=36, max_length=36)
    session_id: str = Field(min_length=36, max_length=36)
    local_date: str = Field(min_length=10, max_length=10)

    @field_validator("device_id", "session_id")
    @classmethod
    def valid_uuid(cls, value: str) -> str:
        try:
            return str(uuid.UUID(value))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("المعرّف غير صالح") from exc

    @field_validator("local_date")
    @classmethod
    def valid_local_date(cls, value: str) -> str:
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("التاريخ المحلي غير صالح") from exc
        utc_today = datetime.now(timezone.utc).date()
        if abs((parsed - utc_today).days) > 1:
            raise ValueError("التاريخ المحلي خارج النطاق المقبول")
        return parsed.isoformat()

# ---------- App/config ----------
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
_IS_PRODUCTION = APP_ENV == "production"
app = FastAPI(
    title=APP_TITLE,
    version=APP_VERSION,
    docs_url=None if _IS_PRODUCTION else "/docs",
    redoc_url=None,
    openapi_url=None if _IS_PRODUCTION else "/openapi.json",
)
origins = [x.strip() for x in os.getenv(
    "CORS_ORIGINS",
    "https://software-engineers-hub.netlify.app"
).split(",") if x.strip()]
if _IS_PRODUCTION:
    if DATABASE_URL.startswith("sqlite"):
        raise RuntimeError("Production requires a durable PostgreSQL DATABASE_URL; SQLite is for local development only.")
    production_token = os.getenv("ADMIN_TOKEN", "").strip()
    if len(production_token) < 32:
        raise RuntimeError("Production requires a newly generated ADMIN_TOKEN of at least 32 characters.")
    if (not origins or "*" in origins or any(
        urlsplit(origin).scheme != "https" or not urlsplit(origin).netloc
        or urlsplit(origin).path not in ("", "/") or urlsplit(origin).query or urlsplit(origin).fragment
        or "localhost" in origin or "127.0.0.1" in origin for origin in origins
    )):
        raise RuntimeError("Production CORS_ORIGINS must contain only exact public HTTPS origins.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.url.path == "/analytics/stats" or request.url.path == "/grades" or request.url.path.startswith("/admin/"):
        response.headers["Cache-Control"] = "no-store"
    return response

security = HTTPBearer(auto_error=False)


def require_admin(credentials: Optional[HTTPAuthorizationCredentials] = Security(security)) -> bool:
    configured_token = os.getenv("ADMIN_TOKEN", "").strip()
    if not configured_token:
        raise HTTPException(status_code=503, detail="لم يتم إعداد ADMIN_TOKEN على الخادم")
    supplied = credentials.credentials if credentials else ""
    if not supplied or not hmac.compare_digest(supplied, configured_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="غير مصرح. تحقق من رمز الإدارة.")
    return True


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def commit_or_rollback(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="يتعارض هذا السجل مع بيانات موجودة مسبقًا.")
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="تعذر حفظ البيانات. لم يتم اعتماد التغيير.")

# ---------- Safe additive migration ----------
def migrate_schema() -> None:
    """Create new tables and add columns without deleting existing records."""
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    additions = {
        "announcements": {
            "is_archived": "BOOLEAN NOT NULL DEFAULT FALSE",
            "created_at": "VARCHAR(40) NOT NULL DEFAULT ''",
        },
        "academic_files": {
            "semester_name": "VARCHAR(80) NOT NULL DEFAULT 'الترم الأول'",
            "is_archived": "BOOLEAN NOT NULL DEFAULT FALSE",
            "created_at": "VARCHAR(40) NOT NULL DEFAULT ''",
        },
        "daily_agenda": {"updated_at": "VARCHAR(40) NOT NULL DEFAULT ''"},
        "upcoming_exams": {"updated_at": "VARCHAR(40) NOT NULL DEFAULT ''"},
    }
    with engine.begin() as connection:
        for table_name, columns in additions.items():
            if table_name not in inspector.get_table_names():
                continue
            present = {col["name"] for col in inspect(connection).get_columns(table_name)}
            for column_name, ddl in columns.items():
                if column_name not in present:
                    connection.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {ddl}'))
        # Preserve existing records; only fill blank timestamps on old rows.
        for table_name in ("announcements", "academic_files", "daily_agenda", "upcoming_exams"):
            if table_name in inspect(connection).get_table_names():
                cols = {col["name"] for col in inspect(connection).get_columns(table_name)}
                if "created_at" in cols:
                    connection.execute(text(f'UPDATE "{table_name}" SET created_at = :ts WHERE created_at = :blank'), {"ts": now_iso(), "blank": ""})
                if "updated_at" in cols:
                    connection.execute(text(f'UPDATE "{table_name}" SET updated_at = :ts WHERE updated_at = :blank'), {"ts": now_iso(), "blank": ""})
    # Seed the semester labels only when absent. Existing course/file rows are untouched.
    with SessionLocal() as db:
        for name in ("الترم الأول", "الترم الثاني"):
            if not db.query(Semester).filter(Semester.name == name).first():
                db.add(Semester(name=name, academic_year="2026-2027"))
        db.commit()
        # Keep the legacy course cards available in the first semester.
        first = db.query(Semester).filter(Semester.name == "الترم الأول").first()
        if first and db.query(Course).count() == 0:
            legacy_courses = [
                ("قواعد البيانات", "الدكتور أحمد فؤاد", True),
                ("مبدأ تراسل بيانات وشبكات", "الدكتور بلال الفهيدي", True),
                ("الصراع العربي الاسرائلي", "الدكتور علي شرف الدين", False),
                ("جبر خطي", "الدكتور عبده العامري", False),
                ("احصاء واحتمالات", "الدكتور عابد الشميري", False),
                ("البرمجة الموجهه بالكائنات", "الدكتور فاروق الفهيدي", True),
                ("هندسة برمجيات", "الدكتور وديع القباطي", True),
                ("تطوير تطبيقات الويب", "الدكتورة وفاء النبهاني", True),
            ]
            db.add_all([Course(name=n, professor=p, has_practical=pr, semester_id=first.id) for n, p, pr in legacy_courses])
            db.commit()
        settings = db.get(ScheduleSettings, 1)
        if settings is None:
            start = date.today()
            end = start + timedelta(days=120)
            db.add(ScheduleSettings(id=1, semester_start=start.isoformat(), semester_end=end.isoformat(), updated_at=now_iso()))
            db.commit()


try:
    migrate_schema()
except Exception as exc:
    # Let deployment diagnostics show a clear failure rather than silently running against a partial schema.
    raise RuntimeError("EduHub database initialization failed. Verify DATABASE_URL and database permissions.") from exc

# ---------- General ----------
@app.get("/")
def root():
    return {"name": APP_TITLE, "version": APP_VERSION, "status": "ok", "docs": None if _IS_PRODUCTION else "/docs"}

@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="قاعدة البيانات غير متاحة")

# ---------- Semesters / courses ----------
@app.get("/semesters")
def get_semesters(db: Session = Depends(get_db)):
    return db.query(Semester).filter(Semester.is_archived.is_(False)).order_by(Semester.id.asc()).all()

@app.post("/semesters", dependencies=[Depends(require_admin)])
def add_semester(payload: SemesterCreate, db: Session = Depends(get_db)):
    name = payload.name.strip()
    if db.query(Semester).filter(Semester.name == name).first():
        raise HTTPException(status_code=409, detail="هذا الفصل الدراسي موجود بالفعل")
    item = Semester(name=name, academic_year=payload.academic_year.strip())
    db.add(item); commit_or_rollback(db); db.refresh(item)
    return item

@app.patch("/semesters/{semester_id}", dependencies=[Depends(require_admin)])
def update_semester(semester_id: int, payload: SemesterCreate, db: Session = Depends(get_db)):
    item = db.get(Semester, semester_id)
    if not item: raise HTTPException(status_code=404, detail="الفصل غير موجود")
    new_name = payload.name.strip()
    duplicate = db.query(Semester).filter(Semester.name == new_name, Semester.id != semester_id).first()
    if duplicate: raise HTTPException(status_code=409, detail="اسم الفصل مستخدم بالفعل")
    old_name = item.name
    # AcademicFile uses a legacy semester-name column; keep those associations valid on rename.
    if old_name != new_name:
        db.query(AcademicFile).filter(AcademicFile.semester_name == old_name).update(
            {AcademicFile.semester_name: new_name}, synchronize_session=False
        )
    item.name, item.academic_year = new_name, payload.academic_year.strip()
    commit_or_rollback(db); db.refresh(item); return item

@app.post("/semesters/{semester_id}/archive", dependencies=[Depends(require_admin)])
def archive_semester(semester_id: int, db: Session = Depends(get_db)):
    item = db.get(Semester, semester_id)
    if not item: raise HTTPException(status_code=404, detail="الفصل غير موجود")
    item.is_archived = True
    commit_or_rollback(db); return {"status": "archived"}

@app.post("/semesters/{semester_id}/restore", dependencies=[Depends(require_admin)])
def restore_semester(semester_id: int, db: Session = Depends(get_db)):
    item = db.get(Semester, semester_id)
    if not item: raise HTTPException(status_code=404, detail="الفصل غير موجود")
    item.is_archived = False
    commit_or_rollback(db); return {"status": "restored"}

@app.get("/courses")
def get_courses(semester_name: str = Query(default="الترم الثاني", max_length=80), db: Session = Depends(get_db)):
    semester = db.query(Semester).filter(Semester.name == semester_name, Semester.is_archived.is_(False)).first()
    if not semester: return []
    return db.query(Course).filter(Course.semester_id == semester.id, Course.is_archived.is_(False)).order_by(Course.name.asc()).all()

@app.post("/courses", dependencies=[Depends(require_admin)])
def add_course(payload: CourseCreate, db: Session = Depends(get_db)):
    semester = db.query(Semester).filter(Semester.name == payload.semester_name.strip(), Semester.is_archived.is_(False)).first()
    if not semester: raise HTTPException(status_code=404, detail="الفصل الدراسي غير موجود")
    duplicate = db.query(Course).filter(Course.name == payload.name.strip(), Course.semester_id == semester.id, Course.is_archived.is_(False)).first()
    if duplicate: raise HTTPException(status_code=409, detail="المقرر موجود في هذا الفصل بالفعل")
    item = Course(name=payload.name.strip(), professor=payload.professor.strip(), semester_id=semester.id, has_practical=payload.has_practical)
    db.add(item); commit_or_rollback(db); db.refresh(item)
    return {"id": item.id, "name": item.name, "professor": item.professor, "semester_name": semester.name, "has_practical": item.has_practical, "is_archived": item.is_archived}

@app.patch("/courses/{course_id}", dependencies=[Depends(require_admin)])
def update_course(course_id: int, payload: CourseCreate, db: Session = Depends(get_db)):
    item = db.get(Course, course_id)
    if not item: raise HTTPException(status_code=404, detail="المقرر غير موجود")
    semester = db.query(Semester).filter(Semester.name == payload.semester_name.strip(), Semester.is_archived.is_(False)).first()
    if not semester: raise HTTPException(status_code=404, detail="الفصل الدراسي غير موجود")
    new_name = payload.name.strip()
    duplicate = db.query(Course).filter(Course.name == new_name, Course.semester_id == semester.id, Course.is_archived.is_(False), Course.id != course_id).first()
    if duplicate: raise HTTPException(status_code=409, detail="يوجد مقرر آخر بهذا الاسم في الفصل المحدد")
    old_name = item.name
    old_semester = db.get(Semester, item.semester_id)
    old_semester_name = old_semester.name if old_semester else "الترم الأول"
    # Keep legacy file associations intact if the course is renamed or moved to another semester.
    related_files = db.query(AcademicFile).filter(AcademicFile.course_name == old_name, AcademicFile.semester_name == old_semester_name).all()
    for academic_file in related_files:
        academic_file.course_name = new_name
        academic_file.semester_name = semester.name
    item.name, item.professor, item.semester_id, item.has_practical = new_name, payload.professor.strip(), semester.id, payload.has_practical
    commit_or_rollback(db); db.refresh(item)
    return {"id": item.id, "name": item.name, "professor": item.professor, "semester_name": semester.name, "has_practical": item.has_practical, "is_archived": item.is_archived}

@app.post("/courses/{course_id}/archive", dependencies=[Depends(require_admin)])
def archive_course(course_id: int, db: Session = Depends(get_db)):
    item = db.get(Course, course_id)
    if not item: raise HTTPException(status_code=404, detail="المقرر غير موجود")
    item.is_archived = True
    commit_or_rollback(db); return {"status": "archived"}

@app.post("/courses/{course_id}/restore", dependencies=[Depends(require_admin)])
def restore_course(course_id: int, db: Session = Depends(get_db)):
    item = db.get(Course, course_id)
    if not item: raise HTTPException(status_code=404, detail="المقرر غير موجود")
    item.is_archived = False
    commit_or_rollback(db); return {"status": "restored"}

# ---------- Announcements ----------
@app.get("/announcements")
def get_announcements(db: Session = Depends(get_db)):
    return db.query(Announcement).filter(Announcement.is_archived.is_(False)).order_by(Announcement.id.desc()).limit(100).all()

@app.post("/announcements", dependencies=[Depends(require_admin)])
def add_announcement(payload: AnnouncementCreate, db: Session = Depends(get_db)):
    item = Announcement(content=payload.content.strip(), created_at=now_iso())
    db.add(item); commit_or_rollback(db); db.refresh(item); return item

@app.patch("/announcements/{announcement_id}", dependencies=[Depends(require_admin)])
def update_announcement(announcement_id: int, payload: AnnouncementCreate, db: Session = Depends(get_db)):
    item = db.get(Announcement, announcement_id)
    if not item: raise HTTPException(status_code=404, detail="الإعلان غير موجود")
    item.content = payload.content.strip(); commit_or_rollback(db); db.refresh(item); return item

@app.post("/announcements/{announcement_id}/archive", dependencies=[Depends(require_admin)])
def archive_announcement(announcement_id: int, db: Session = Depends(get_db)):
    item = db.get(Announcement, announcement_id)
    if not item: raise HTTPException(status_code=404, detail="الإعلان غير موجود")
    item.is_archived = True; commit_or_rollback(db); return {"status": "archived"}

@app.post("/announcements/{announcement_id}/restore", dependencies=[Depends(require_admin)])
def restore_announcement(announcement_id: int, db: Session = Depends(get_db)):
    item = db.get(Announcement, announcement_id)
    if not item: raise HTTPException(status_code=404, detail="الإعلان غير موجود")
    item.is_archived = False; commit_or_rollback(db); return {"status": "restored"}

# ---------- Academic files ----------
@app.get("/files")
def get_files(semester_name: str = Query(default="الترم الثاني", max_length=80), course_name: Optional[str] = Query(default=None, max_length=100), category: Optional[str] = Query(default=None, max_length=50), db: Session = Depends(get_db)):
    query = db.query(AcademicFile).filter(AcademicFile.is_archived.is_(False), AcademicFile.semester_name == semester_name)
    if course_name: query = query.filter(AcademicFile.course_name == course_name)
    if category: query = query.filter(AcademicFile.file_category == category)
    return query.order_by(AcademicFile.id.desc()).limit(500).all()

@app.post("/files", dependencies=[Depends(require_admin)])
def add_file(payload: FileCreate, db: Session = Depends(get_db)):
    semester = db.query(Semester).filter(Semester.name == payload.semester_name.strip(), Semester.is_archived.is_(False)).first()
    if not semester: raise HTTPException(status_code=404, detail="الفصل الدراسي غير موجود")
    item = AcademicFile(course_name=payload.course_name.strip(), type_section=payload.type_section.strip(), file_category=payload.file_category.strip(), title=payload.title.strip(), file_url=payload.file_url, semester_name=semester.name, is_archived=False, created_at=now_iso())
    db.add(item); commit_or_rollback(db); db.refresh(item); return item

@app.patch("/files/{file_id}", dependencies=[Depends(require_admin)])
def update_file(file_id: int, payload: FileCreate, db: Session = Depends(get_db)):
    item = db.get(AcademicFile, file_id)
    if not item: raise HTTPException(status_code=404, detail="الملف غير موجود")
    semester = db.query(Semester).filter(Semester.name == payload.semester_name.strip(), Semester.is_archived.is_(False)).first()
    if not semester: raise HTTPException(status_code=404, detail="الفصل الدراسي غير موجود")
    item.course_name, item.type_section, item.file_category = payload.course_name.strip(), payload.type_section.strip(), payload.file_category.strip()
    item.title, item.file_url, item.semester_name = payload.title.strip(), payload.file_url, semester.name
    commit_or_rollback(db); db.refresh(item); return item

@app.post("/files/{file_id}/archive", dependencies=[Depends(require_admin)])
def archive_file(file_id: int, db: Session = Depends(get_db)):
    item = db.get(AcademicFile, file_id)
    if not item: raise HTTPException(status_code=404, detail="الملف غير موجود")
    item.is_archived = True; commit_or_rollback(db); return {"status": "archived"}

@app.post("/files/{file_id}/restore", dependencies=[Depends(require_admin)])
def restore_file(file_id: int, db: Session = Depends(get_db)):
    item = db.get(AcademicFile, file_id)
    if not item: raise HTTPException(status_code=404, detail="الملف غير موجود")
    item.is_archived = False; commit_or_rollback(db); return {"status": "restored"}

@app.get("/admin/archive", dependencies=[Depends(require_admin)])
def get_archive(db: Session = Depends(get_db)):
    """Return archived academic content to authorized administrators only."""
    archived_semesters = db.query(Semester).filter(Semester.is_archived.is_(True)).order_by(Semester.id.desc()).all()
    archived_courses = db.query(Course).filter(Course.is_archived.is_(True)).order_by(Course.id.desc()).all()
    archived_files = db.query(AcademicFile).filter(AcademicFile.is_archived.is_(True)).order_by(AcademicFile.id.desc()).all()
    archived_announcements = db.query(Announcement).filter(Announcement.is_archived.is_(True)).order_by(Announcement.id.desc()).all()
    return {
        "semesters": [{"id": x.id, "name": x.name} for x in archived_semesters],
        "courses": [{"id": x.id, "name": x.name} for x in archived_courses],
        "files": [{"id": x.id, "title": x.title, "course_name": x.course_name, "semester_name": x.semester_name} for x in archived_files],
        "announcements": [{"id": x.id, "content": x.content} for x in archived_announcements],
    }

@app.post("/admin/archive/{kind}/{item_id}/restore", dependencies=[Depends(require_admin)])
def restore_archived_item(kind: str, item_id: int, db: Session = Depends(get_db)):
    models = {"semester": Semester, "course": Course, "file": AcademicFile, "announcement": Announcement}
    model = models.get(kind)
    if model is None:
        raise HTTPException(status_code=404, detail="نوع الأرشيف غير معروف")
    item = db.get(model, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="العنصر غير موجود")
    item.is_archived = False
    commit_or_rollback(db)
    return {"status": "restored"}

# ---------- Private grades ----------
@app.get("/grades", dependencies=[Depends(require_admin)])
def get_grades(db: Session = Depends(get_db)):
    return db.query(StudentGrade).order_by(StudentGrade.student_name.asc(), StudentGrade.course_name.asc()).limit(2000).all()

@app.post("/grades", dependencies=[Depends(require_admin)])
def add_grade(payload: GradeCreate, db: Session = Depends(get_db)):
    item = StudentGrade(student_name=payload.student_name.strip(), course_name=payload.course_name.strip(), theory_grade=payload.theory_grade, practical_grade=payload.practical_grade)
    db.add(item); commit_or_rollback(db); db.refresh(item); return item

@app.patch("/grades/{grade_id}", dependencies=[Depends(require_admin)])
def update_grade(grade_id: int, payload: GradeCreate, db: Session = Depends(get_db)):
    item = db.get(StudentGrade, grade_id)
    if not item: raise HTTPException(status_code=404, detail="السجل غير موجود")
    item.student_name, item.course_name = payload.student_name.strip(), payload.course_name.strip()
    item.theory_grade, item.practical_grade = payload.theory_grade, payload.practical_grade
    commit_or_rollback(db); db.refresh(item); return item

@app.delete("/admin/students/{student_id}", dependencies=[Depends(require_admin)])
def remove_student(student_id: int, db: Session = Depends(get_db)):
    item = db.get(StudentGrade, student_id)
    if not item: raise HTTPException(status_code=404, detail="السجل غير موجود")
    db.delete(item); commit_or_rollback(db); return {"status": "deleted"}

# ---------- Recurring weekly schedule and date-specific overrides ----------
WEEKDAY_NAMES_AR = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

def _lecture_dict(item: WeeklyLecture) -> dict:
    return {"id": item.id, "weekly_lecture_id": item.id, "weekday": item.weekday,
            "weekday_name": WEEKDAY_NAMES_AR[item.weekday], "title": item.title,
            "start_time": item.start_time, "end_time": item.end_time,
            "location": item.location, "notes": item.notes}

def _schedule_settings(db: Session) -> ScheduleSettings:
    settings = db.get(ScheduleSettings, 1)
    if settings is None:
        start = date.today()
        settings = ScheduleSettings(id=1, semester_start=start.isoformat(),
                                    semester_end=(start + timedelta(days=120)).isoformat(), updated_at=now_iso())
        db.add(settings); db.commit(); db.refresh(settings)
    return settings

@app.get("/schedule/settings")
def get_schedule_settings(db: Session = Depends(get_db)):
    item = _schedule_settings(db)
    return {"semester_start": item.semester_start, "semester_end": item.semester_end, "updated_at": item.updated_at}

@app.put("/schedule/settings", dependencies=[Depends(require_admin)])
def update_schedule_settings(payload: ScheduleSettingsUpdate, db: Session = Depends(get_db)):
    if payload.semester_end < payload.semester_start:
        raise HTTPException(status_code=422, detail="تاريخ نهاية الفصل يجب أن يأتي بعد تاريخ بدايته")
    item = _schedule_settings(db)
    item.semester_start = payload.semester_start
    item.semester_end = payload.semester_end
    item.updated_at = now_iso()
    commit_or_rollback(db)
    return {"semester_start": item.semester_start, "semester_end": item.semester_end, "updated_at": item.updated_at}

@app.get("/schedule/weekly")
def get_weekly_schedule(db: Session = Depends(get_db)):
    return [_lecture_dict(x) for x in db.query(WeeklyLecture).filter(WeeklyLecture.is_active.is_(True)).order_by(WeeklyLecture.weekday, WeeklyLecture.start_time, WeeklyLecture.id).all()]

@app.post("/schedule/weekly", dependencies=[Depends(require_admin)])
def add_weekly_lecture(payload: WeeklyLectureCreate, db: Session = Depends(get_db)):
    item = WeeklyLecture(**payload.model_dump())
    db.add(item); commit_or_rollback(db); db.refresh(item)
    return _lecture_dict(item)

@app.patch("/schedule/weekly/{lecture_id}", dependencies=[Depends(require_admin)])
def update_weekly_lecture(lecture_id: int, payload: WeeklyLectureCreate, db: Session = Depends(get_db)):
    item = db.get(WeeklyLecture, lecture_id)
    if item is None: raise HTTPException(status_code=404, detail="المحاضرة غير موجودة")
    for key, value in payload.model_dump().items(): setattr(item, key, value)
    item.is_active = True
    commit_or_rollback(db); db.refresh(item)
    return _lecture_dict(item)

@app.delete("/schedule/weekly/{lecture_id}", dependencies=[Depends(require_admin)])
def delete_weekly_lecture(lecture_id: int, db: Session = Depends(get_db)):
    item = db.get(WeeklyLecture, lecture_id)
    if item is None: raise HTTPException(status_code=404, detail="المحاضرة غير موجودة")
    item.is_active = False
    commit_or_rollback(db)
    return {"ok": True, "archived": True}

@app.get("/schedule/daily")
def get_daily_schedule(agenda_date: date = Query(default_factory=date.today), db: Session = Depends(get_db)):
    settings = _schedule_settings(db)
    date_text = agenda_date.isoformat()
    override = db.query(AgendaOverride).filter(AgendaOverride.agenda_date == date_text).first()
    in_semester = settings.semester_start <= date_text <= settings.semester_end
    if override:
        try: lectures = json.loads(override.lectures_json)
        except (ValueError, TypeError): lectures = []
        return {"date": date_text, "weekday": agenda_date.weekday(), "weekday_name": WEEKDAY_NAMES_AR[agenda_date.weekday()],
                "lectures": lectures, "note": override.note, "is_override": True, "in_semester": in_semester,
                "semester_start": settings.semester_start, "semester_end": settings.semester_end}
    lectures = []
    if in_semester:
        lectures = [_lecture_dict(x) for x in db.query(WeeklyLecture).filter(
            WeeklyLecture.weekday == agenda_date.weekday(), WeeklyLecture.is_active.is_(True)
        ).order_by(WeeklyLecture.start_time, WeeklyLecture.id).all()]
    return {"date": date_text, "weekday": agenda_date.weekday(), "weekday_name": WEEKDAY_NAMES_AR[agenda_date.weekday()],
            "lectures": lectures, "note": "", "is_override": False, "in_semester": in_semester,
            "semester_start": settings.semester_start, "semester_end": settings.semester_end}

@app.post("/schedule/overrides", dependencies=[Depends(require_admin)])
def save_schedule_override(payload: ScheduleOverrideCreate, db: Session = Depends(get_db)):
    target_date = date.fromisoformat(payload.agenda_date)
    settings = _schedule_settings(db)
    if not (settings.semester_start <= payload.agenda_date <= settings.semester_end):
        raise HTTPException(status_code=422, detail="التاريخ خارج فترة الفصل الدراسي المحددة")
    existing = db.query(AgendaOverride).filter(AgendaOverride.agenda_date == payload.agenda_date).first()
    if existing:
        try: lectures = json.loads(existing.lectures_json)
        except (ValueError, TypeError): lectures = []
    else:
        lectures = [_lecture_dict(x) for x in db.query(WeeklyLecture).filter(
            WeeklyLecture.weekday == target_date.weekday(), WeeklyLecture.is_active.is_(True)
        ).order_by(WeeklyLecture.start_time, WeeklyLecture.id).all()]
    for update in payload.lecture_updates:
        match = next((x for x in lectures if x.get("weekly_lecture_id") == update.weekly_lecture_id), None)
        if match is None:
            raise HTTPException(status_code=404, detail="المحاضرة المحددة غير موجودة ضمن جدول هذا اليوم")
        for key in ("title", "start_time", "end_time", "location", "notes"):
            value = getattr(update, key)
            if value is not None: match[key] = value
    if existing is None:
        existing = AgendaOverride(agenda_date=payload.agenda_date, note=payload.note,
                                  lectures_json=json.dumps(lectures, ensure_ascii=False), updated_at=now_iso())
        db.add(existing)
    else:
        existing.note = payload.note
        existing.lectures_json = json.dumps(lectures, ensure_ascii=False)
        existing.updated_at = now_iso()
    commit_or_rollback(db)
    return {"date": existing.agenda_date, "note": existing.note, "lectures": lectures, "is_override": True, "updated_at": existing.updated_at}

@app.delete("/schedule/overrides/{agenda_date}", dependencies=[Depends(require_admin)])
def delete_schedule_override(agenda_date: str, db: Session = Depends(get_db)):
    try: date.fromisoformat(agenda_date)
    except ValueError: raise HTTPException(status_code=422, detail="يجب إدخال التاريخ بصيغة YYYY-MM-DD")
    item = db.query(AgendaOverride).filter(AgendaOverride.agenda_date == agenda_date).first()
    if item is None: return {"ok": True, "removed": False}
    db.delete(item); commit_or_rollback(db)
    return {"ok": True, "removed": True}

# ---------- Legacy agenda / exam ----------
@app.get("/agenda/")
def get_agenda(db: Session = Depends(get_db)):
    return db.query(DailyAgenda).order_by(DailyAgenda.id.desc()).first()

@app.post("/agenda/", dependencies=[Depends(require_admin)])
def create_agenda(payload: AgendaCreate, db: Session = Depends(get_db)):
    item = db.query(DailyAgenda).order_by(DailyAgenda.id.desc()).first()
    if item:
        for key, value in payload.model_dump().items(): setattr(item, key, value)
        item.updated_at = now_iso()
    else:
        item = DailyAgenda(**payload.model_dump(), updated_at=now_iso()); db.add(item)
    commit_or_rollback(db); db.refresh(item); return item

@app.get("/exam/")
def get_exam(db: Session = Depends(get_db)):
    return db.query(UpcomingExam).order_by(UpcomingExam.id.desc()).first()

@app.post("/exam/", dependencies=[Depends(require_admin)])
def create_exam(payload: ExamCreate, db: Session = Depends(get_db)):
    item = db.query(UpcomingExam).order_by(UpcomingExam.id.desc()).first()
    if item:
        for key, value in payload.model_dump().items(): setattr(item, key, value)
        item.updated_at = now_iso()
    else:
        item = UpcomingExam(**payload.model_dump(), updated_at=now_iso()); db.add(item)
    commit_or_rollback(db); db.refresh(item); return item

# ---------- Anonymous persistent usage analytics ----------
_online_sessions: dict[str, datetime] = {}

@app.post("/analytics/track")
def track_analytics(payload: AnalyticsTrack, db: Session = Depends(get_db)):
    """Count pseudonymous browser IDs, unique local-day activity, and unique tab sessions."""
    now = now_iso()
    device_id = payload.device_id
    session_id = payload.session_id
    # Retry once for concurrent first visits that race on the unique constraints.
    for attempt in range(2):
        try:
            user = db.query(AnalyticsUser).filter(AnalyticsUser.device_id == device_id).first()
            if user is None:
                user = AnalyticsUser(device_id=device_id, first_seen_at=now, last_seen_at=now)
                db.add(user)
                db.flush()

            session = db.query(AnalyticsSession).filter(AnalyticsSession.session_id == session_id).first()
            if session is not None and session.user_id != user.id:
                raise HTTPException(status_code=409, detail="معرّف الجلسة مرتبط بمعرّف آخر")
            if session is None:
                session = AnalyticsSession(session_id=session_id, user_id=user.id, started_at=now, last_seen_at=now)
                db.add(session)
            else:
                session.last_seen_at = now

            activity = db.query(AnalyticsDailyActivity).filter(
                AnalyticsDailyActivity.user_id == user.id,
                AnalyticsDailyActivity.activity_date == payload.local_date,
            ).first()
            if activity is None:
                db.add(AnalyticsDailyActivity(user_id=user.id, activity_date=payload.local_date, last_seen_at=now))
            else:
                activity.last_seen_at = now
            user.last_seen_at = now
            db.commit()
            break
        except IntegrityError:
            db.rollback()
            if attempt == 1:
                raise HTTPException(status_code=409, detail="تعذر تسجيل الزيارة المتزامنة؛ أعد المحاولة")
        except HTTPException:
            db.rollback()
            raise
        except SQLAlchemyError as exc:
            db.rollback()
            raise HTTPException(status_code=503, detail="تعذر حفظ إحصاءات الاستخدام مؤقتًا") from exc

    # Keep the existing admin-only live-online indicator working without retaining IP addresses.
    _online_sessions[session_id] = datetime.now(timezone.utc)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=2)
    for active_id, seen in list(_online_sessions.items()):
        if seen < cutoff:
            _online_sessions.pop(active_id, None)
    return {"status": "ok"}

@app.get("/analytics/stats", dependencies=[Depends(require_admin)])
def get_analytics_stats(local_date: Optional[str] = Query(default=None, min_length=10, max_length=10), db: Session = Depends(get_db)):
    """Return aggregate counts only; never expose persistent identifiers or per-user records."""
    target_date = date.today().isoformat() if local_date is None else local_date
    try:
        parsed = date.fromisoformat(target_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="التاريخ المحلي غير صالح") from exc
    utc_today = datetime.now(timezone.utc).date()
    if abs((parsed - utc_today).days) > 1:
        raise HTTPException(status_code=422, detail="التاريخ المحلي خارج النطاق المقبول")
    total_unique_users = db.query(func.count(AnalyticsUser.id)).scalar() or 0
    today_active_users = db.query(func.count(func.distinct(AnalyticsDailyActivity.user_id))).filter(
        AnalyticsDailyActivity.activity_date == parsed.isoformat()
    ).scalar() or 0
    total_visits = db.query(func.count(AnalyticsSession.id)).scalar() or 0
    return {
        "total_unique_users": int(total_unique_users),
        "today_active_users": int(today_active_users),
        "total_visits": int(total_visits),
        "local_date": parsed.isoformat(),
        "updated_at": now_iso(),
    }

# ---------- Anonymous online count (no IP/device fingerprint collection) ----------
@app.post("/presence")
def update_presence(payload: PresenceCreate):
    # Client generates a random temporary session ID; the server does not persist IPs or device fingerprints.
    _online_sessions[payload.session_id] = datetime.now(timezone.utc)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=2)
    for session_id, seen in list(_online_sessions.items()):
        if seen < cutoff: _online_sessions.pop(session_id, None)
    return {"status": "ok"}

@app.get("/admin/online_count", dependencies=[Depends(require_admin)])
def get_online_count():
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=2)
    for session_id, seen in list(_online_sessions.items()):
        if seen < cutoff: _online_sessions.pop(session_id, None)
    return {"count": len(_online_sessions), "details": []}
