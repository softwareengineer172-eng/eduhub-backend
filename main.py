from pydantic import BaseModel
from fastapi import FastAPI, Depends, HTTPException, status, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import create_engine, Column, Integer, String, Float, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from fastapi import Request # تأكدي من إضافة Request هنا إذا لم تكن موجودة
from datetime import datetime

# 1. إعداد قاعدة البيانات وتوليد الملف تلقائياً
SQLALCHEMY_DATABASE_URL = "postgresql+psycopg2://neondb_owner:npg_EDprP1fHxR5n@ep-hidden-thunder-ahprk4ag-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 2. الجداول البرمجية المؤمنة
class Announcement(Base):
    __tablename__ = "announcements"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    content = Column(Text, nullable=False)

class AcademicFile(Base):
    __tablename__ = "academic_files"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    course_name = Column(String(100), nullable=False)
    type_section = Column(String(50), nullable=False)
    file_category = Column(String(50), nullable=False)
    title = Column(String(150), nullable=False)
    file_url = Column(Text, nullable=False)

class StudentGrade(Base):
    __tablename__ = "student_grades"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    student_name = Column(String(150), unique=True, nullable=False)
    course_name = Column(String(100), nullable=False)
    theory_grade = Column(Float, default=0.0)
    practical_grade = Column(Float, default=0.0)

class DailyAgenda(Base):
    __tablename__ = "daily_agenda"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    lecture_1 = Column(String(100), nullable=False)
    time_1 = Column(String(50), nullable=False)
    lecture_2 = Column(String(100), nullable=False)
    time_2 = Column(String(50), nullable=False)
    status_msg = Column(String(100), nullable=False) # مثل: لا توجد اختبارات أو تسليمات

class UpcomingExam(Base):
    __tablename__ = "upcoming_exams"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    course_name = Column(String(100), nullable=False)
    exam_date_text = Column(String(100), nullable=False) # مثل: الخميس, 30 يوليو 2026
    exam_time = Column(String(50), nullable=False) # مثل: 09:00 صباحاً
    timestamp = Column(String(100), nullable=False) # لبرمجة المؤقت: 2026-07-30T09:00:00

class AgendaCreate(BaseModel):
    lecture_1: str
    time_1: str
    lecture_2: str
    time_2: str
    status_msg: str

class ExamCreate(BaseModel):
    course_name: str
    exam_date_text: str
    exam_time: str
    timestamp: str



Base.metadata.create_all(bind=engine)

# 3. حماية النظام وتشفير لوحة التحكم
app = FastAPI(title="EduHub Secured API v2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()
ADMIN_SECRET_CODE = "Ayman_Jarran_2026" 

def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    if credentials.credentials != ADMIN_SECRET_CODE:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="رمز الأمان خاطئ! غير مصرح لك بالدخول")
    return True

def get_db():
    db_session = SessionLocal()
    try:
        yield db_session
    finally:
        db_session.close()

# 4. مسارات الـ API المفتوحة والمحمية
@app.get("/announcements")
def get_announcements(db: Session = Depends(get_db)):
    return db.query(Announcement).order_by(Announcement.id.desc()).all()

@app.post("/announcements", dependencies=[Depends(verify_token)])
def add_announcement(content: str, db: Session = Depends(get_db)):
    new_ann = Announcement(content=content)
    db.add(new_ann) 
    db.commit()
    return {"status": "success"}

@app.get("/files")
def get_files(db: Session = Depends(get_db)):
    return db.query(AcademicFile).order_by(AcademicFile.id.desc()).all()

@app.post("/files", dependencies=[Depends(verify_token)])
def add_file(course_name: str, type_section: str, file_category: str, title: str, file_url: str, db: Session = Depends(get_db)):
    new_file = AcademicFile(course_name=course_name, type_section=type_section, file_category=file_category, title=title, file_url=file_url)
    db.add(new_file)
    db.commit()
    return {"status": "success"}

@app.get("/grades")
def get_grades(db: Session = Depends(get_db)):
    return db.query(StudentGrade).all()

@app.post("/grades", dependencies=[Depends(verify_token)])
def add_grade(student_name: str, course_name: str, theory: float, practical: float, db: Session = Depends(get_db)):
    new_grade = StudentGrade(student_name=student_name, course_name=course_name, theory_grade=theory, practical_grade=practical)
    db.add(new_grade)
    db.commit()
    return {"status": "success"}

@app.delete("/admin/students/{student_id}", dependencies=[Depends(verify_token)])
def remove_student(student_id: int, db: Session = Depends(get_db)):
    db.query(StudentGrade).filter(StudentGrade.id == student_id).delete()
    db.commit()
    return {"status": "success"}

# -- قسم الأجندة اليومية --
@app.get("/agenda/")
def get_agenda(db: Session = Depends(get_db)):
    # جلب أحدث أجندة فقط (آخر صف تم إضافته)
    return db.query(DailyAgenda).order_by(DailyAgenda.id.desc()).first()

@app.post("/agenda/")
def create_agenda(agenda: AgendaCreate, db: Session = Depends(get_db), token: str = Depends(verify_token)):
    new_agenda = DailyAgenda(**agenda.dict())
    db.add(new_agenda)
    db.commit()
    db.refresh(new_agenda)
    return new_agenda

# -- قسم الاختبار القادم --
@app.get("/exam/")
def get_exam(db: Session = Depends(get_db)):
    # جلب أحدث اختبار تم رفعه
    return db.query(UpcomingExam).order_by(UpcomingExam.id.desc()).first()

@app.post("/exam/")
def create_exam(exam: ExamCreate, db: Session = Depends(get_db), token: str = Depends(verify_token)):
    new_exam = UpcomingExam(**exam.dict())
    db.add(new_exam)
    db.commit()
    db.refresh(new_exam)
    return new_exam

# قاموس سري في الذاكرة المؤقتة لتخزين الأجهزة المتصلة
online_users = {}

# 1. مسار مخفي لاستقبال نبضات الطلاب بصمت
@app.get("/ping")
async def silent_ping(request: Request, device: str = "جهاز غير معروف"):
    # سحب رقم الـ IP بطريقة آمنة جداً لا تزعج Pylance
    client_host = request.client.host if request.client else "unknown_ip"
    client_ip = request.headers.get("x-forwarded-for", client_host).split(",")[0]
    
    # تسجيل الجهاز ووقت تواجده الآن
    online_users[client_ip] = {
        "device": device,
        "last_active": datetime.now()
    }
    return {"status": "ok"}

# 2. مسار للمندوب لمعرفة العدد الحي
@app.get("/admin/online_count")
async def get_online_stats():
    now = datetime.now()
    # تنظيف النظام: أي طالب يغلق الموقع ولن يرسل نبضة لمدة دقيقتين سيتم حذفه
    active_users = {ip: data for ip, data in online_users.items() if (now - data["last_active"]).total_seconds() < 120}
    
    # تحديث القائمة
    online_users.clear()
    online_users.update(active_users)
    
    # حصر أنواع الأجهزة
    devices = [data["device"] for data in active_users.values()]
    return {
        "count": len(active_users),
        "details": devices
    }