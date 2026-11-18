import base64
import json
import os
import secrets
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, Header, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from seed_books import INITIAL_BOOKS

# كلمة مرور لوحة التحكم (يقرأها من السيرفر أو يستخدم الافتراضية)
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "bookshelf2026")

# قراءة رابط قاعدة البيانات (PostgreSQL أونلاين أو SQLite محلياً)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./bookshelf.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# --- نماذج قاعدة البيانات ---
class BookDB(Base):
    __tablename__ = "books"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    author = Column(String, index=True, nullable=False)
    category = Column(String, index=True, nullable=False)
    price = Column(Float, nullable=False)
    desc = Column(Text, default="")
    cover = Column(Text, default="logo.png")  # Text لدعم روابط الصور أو Base64


class OrderDB(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String, default="عميل المتجر")
    customer_phone = Column(String, default="")
    customer_address = Column(String, default="")
    items_json = Column(Text, nullable=False)
    total_price = Column(Float, nullable=False)
    status = Column(String, default="قيد المراجعة")
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)


def seed_database():
    db = SessionLocal()
    try:
        if db.query(BookDB).count() == 0:
            for item in INITIAL_BOOKS:
                db.add(BookDB(**item))
            db.commit()
    finally:
        db.close()


seed_database()


# --- نماذج التحقق ---
class BookCreate(BaseModel):
    title: str
    author: str
    category: str
    price: float
    desc: Optional[str] = ""
    cover: Optional[str] = "logo.png"


class BookUpdate(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    desc: Optional[str] = None


class OrderItemSchema(BaseModel):
    id: int
    title: str
    price: float
    qty: int


class OrderCreate(BaseModel):
    customer_name: Optional[str] = "عميل المتجر"
    customer_phone: Optional[str] = ""
    customer_address: Optional[str] = ""
    items: List[OrderItemSchema]
    total_price: float


class OrderStatusUpdate(BaseModel):
    status: str


class AdminLogin(BaseModel):
    password: str


# --- تطبيق FastAPI ---
app = FastAPI(title="Bookshelf 202 API", description="النظام الخلفي لمتجر رف الكتب")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_admin(x_admin_password: Optional[str] = Header(None)):
    if not x_admin_password or not secrets.compare_digest(x_admin_password, ADMIN_PASSWORD):
        raise HTTPException(status_code=401, detail="كلمة المرور غير صحيحة")
    return True


# --- مسارات عامة للعملاء ---
@app.get("/api/books")
def get_books(category: Optional[str] = None, search: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(BookDB)
    if category:
        query = query.filter(BookDB.category == category)
    if search:
        search_term = f"%{search}%"
        query = query.filter((BookDB.title.like(search_term)) | (BookDB.author.like(search_term)))
    return query.order_by(BookDB.id.desc()).all()


@app.post("/api/orders")
def create_order(order: OrderCreate, db: Session = Depends(get_db)):
    if not order.items:
        raise HTTPException(status_code=400, detail="السلة فارغة")

    items_data = [item.model_dump() for item in order.items]
    new_order = OrderDB(
        customer_name=order.customer_name,
        customer_phone=order.customer_phone,
        customer_address=order.customer_address,
        items_json=json.dumps(items_data, ensure_ascii=False),
        total_price=order.total_price
    )
    db.add(new_order)
    db.commit()
    db.refresh(new_order)
    return {"order_id": new_order.id, "message": "تم تسجيل طلبك بنجاح!"}


# --- مسارات الإدارة المحمية ---
@app.post("/api/admin/login")
def admin_login(data: AdminLogin):
    if not secrets.compare_digest(data.password, ADMIN_PASSWORD):
        raise HTTPException(status_code=401, detail="كلمة المرور غير صحيحة")
    return {"message": "تم تسجيل الدخول بنجاح"}


# تحويل الصورة المرفوعة إلى Base64 لحفظها في قاعدة البيانات السحابية بشكل دائم
@app.post("/api/upload-cover", dependencies=[Depends(verify_admin)])
async def upload_cover(file: UploadFile = File(...)):
    content = await file.read()
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="حجم الصورة كبير جداً (الحد الأقصى 2 ميجا)")
    mime_type = file.content_type or "image/png"
    b64_str = base64.b64encode(content).decode("utf-8")
    return {"filename": f"data:{mime_type};base64,{b64_str}"}


@app.get("/api/orders", dependencies=[Depends(verify_admin)])
def get_orders(db: Session = Depends(get_db)):
    orders = db.query(OrderDB).order_by(OrderDB.created_at.desc()).all()
    result = []
    for o in orders:
        result.append({
            "id": o.id,
            "customer_name": o.customer_name,
            "customer_phone": o.customer_phone,
            "customer_address": o.customer_address,
            "items": json.loads(o.items_json),
            "total_price": o.total_price,
            "status": o.status,
            "created_at": o.created_at.strftime("%Y-%m-%d %H:%M")
        })
    return result


@app.patch("/api/orders/{order_id}", dependencies=[Depends(verify_admin)])
def update_order_status(order_id: int, payload: OrderStatusUpdate, db: Session = Depends(get_db)):
    order = db.query(OrderDB).filter(OrderDB.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")
    order.status = payload.status
    db.commit()
    return {"message": "تم تحديث حالة الطلب"}


@app.delete("/api/orders/{order_id}", dependencies=[Depends(verify_admin)])
def delete_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(OrderDB).filter(OrderDB.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")
    db.delete(order)
    db.commit()
    return {"message": "تم حذف الطلب"}


@app.post("/api/books", dependencies=[Depends(verify_admin)])
def create_book(book: BookCreate, db: Session = Depends(get_db)):
    new_book = BookDB(**book.model_dump())
    db.add(new_book)
    db.commit()
    db.refresh(new_book)
    return new_book


@app.patch("/api/books/{book_id}", dependencies=[Depends(verify_admin)])
def update_book(book_id: int, payload: BookUpdate, db: Session = Depends(get_db)):
    book = db.query(BookDB).filter(BookDB.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="الكتاب غير موجود")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(book, key, value)
    db.commit()
    return {"message": "تم تحديث بيانات الكتاب"}


@app.delete("/api/books/{book_id}", dependencies=[Depends(verify_admin)])
def delete_book(book_id: int, db: Session = Depends(get_db)):
    book = db.query(BookDB).filter(BookDB.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="الكتاب غير موجود")
    db.delete(book)
    db.commit()
    return {"message": "تم حذف الكتاب بنجاح"}


app.mount("/", StaticFiles(directory="static", html=True), name="static")