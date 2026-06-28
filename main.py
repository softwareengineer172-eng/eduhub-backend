from fastapi import FastAPI, Depends, HTTPException, status, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import create_engine, Column, Integer, String, Float, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# 1. إعداد قاعدة البيانات وتوليد الملف تلقائياً
SQLALCHEMY_DATABASE_URL = "postgresql+psycopg2://neondb_owner:كلمة_المرور_الحقيقية_هنا@ep-hidden-thunder-ahprk4ag-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
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
