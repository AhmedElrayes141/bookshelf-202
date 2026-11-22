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
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime, Boolean, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from seed_books import INITIAL_BOOKS

# كلمة مرور لوحة التحكم
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "bookshelf2026")

# قراءة رابط قاعدة البيانات
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./bookshelf.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

DEFAULT_VODAFONE = "01097897941"
DEFAULT_ADDRESS = 'دمنهور - ش عبد السلام الشاذلي (أسفل الكوبري العلوي - أول ش مدرسة الفكرية) | دسوق - "شارع الجيش"'


# --- نماذج قاعدة البيانات ---
class BookDB(Base):
    __tablename__ = "books"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    author = Column(String, index=True, nullable=False)
    category = Column(String, index=True, nullable=False)
    price = Column(Float, nullable=False)
    is_available = Column(Boolean, default=True, nullable=False)
    desc = Column(Text, default="")
    cover = Column(Text, default="logo.png")


class OrderDB(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String, default="عميل المتجر")
    customer_phone = Column(String, default="")
    customer_address = Column(String, default="")
    payment_method = Column(String, default="الدفع عند الاستلام")
    payment_reference = Column(String, default="")
    payment_screenshot = Column(Text, default="")
    items_json = Column(Text, nullable=False)
    total_price = Column(Float, nullable=False)
    status = Column(String, default="قيد المراجعة")
    created_at = Column(DateTime, default=datetime.utcnow)


class StoreSettingsDB(Base):
    __tablename__ = "store_settings"
    id = Column(Integer, primary_key=True, index=True)
    vodafone_cash = Column(String, default=DEFAULT_VODAFONE)
    instapay = Column(String, default="")
    store_address = Column(Text, default=DEFAULT_ADDRESS)


def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        with engine.begin() as conn:
            for col_def in [
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_method VARCHAR DEFAULT 'الدفع عند الاستلام'",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_reference VARCHAR DEFAULT ''",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_screenshot TEXT DEFAULT ''",
                "ALTER TABLE books ADD COLUMN IF NOT EXISTS is_available BOOLEAN DEFAULT TRUE"
            ]:
                try:
                    conn.execute(text(col_def))
                except Exception:
                    pass
    except Exception as e:
        print("DB init warning:", e)


init_db()


def seed_database():
    db = SessionLocal()
    try:
        if db.query(BookDB).count() == 0:
            for item in INITIAL_BOOKS:
                book_data = {**item}
                book_data.setdefault("is_available", True)
                db.add(BookDB(**book_data))
            db.commit()
        settings = db.query(StoreSettingsDB).first()
        if not settings:
            db.add(StoreSettingsDB(
                id=1,
                vodafone_cash=DEFAULT_VODAFONE,
                instapay="",
                store_address=DEFAULT_ADDRESS
            ))
            db.commit()
        elif settings.vodafone_cash == "01000000000":
            settings.vodafone_cash = DEFAULT_VODAFONE
            settings.store_address = DEFAULT_ADDRESS
            db.commit()
    except Exception as e:
        print("Seed warning:", e)
    finally:
        db.close()


seed_database()


# --- نماذج التحقق ---
class BookCreate(BaseModel):
    title: str
    author: str
    category: str
    price: float
    is_available: bool = True
    desc: Optional[str] = ""
    cover: Optional[str] = "logo.png"


class BookUpdate(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    is_available: Optional[bool] = None
    cover: Optional[str] = None
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
    payment_method: Optional[str] = "الدفع عند الاستلام"
    payment_reference: Optional[str] = ""
    payment_screenshot: Optional[str] = ""
    items: List[OrderItemSchema]
    total_price: float


class OrderStatusUpdate(BaseModel):
    status: str


class AdminLogin(BaseModel):
    password: str


class StoreSettingsUpdate(BaseModel):
    vodafone_cash: str
    store_address: str


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
@app.get("/api/settings")
def get_store_settings(db: Session = Depends(get_db)):
    settings = db.query(StoreSettingsDB).first()
    if not settings:
        return {
            "vodafone_cash": DEFAULT_VODAFONE,
            "store_address": DEFAULT_ADDRESS
        }
    return {
        "vodafone_cash": settings.vodafone_cash or DEFAULT_VODAFONE,
        "store_address": settings.store_address or DEFAULT_ADDRESS
    }


@app.get("/api/books")
def get_books(category: Optional[str] = None, search: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(BookDB)
    if category:
        query = query.filter(BookDB.category == category)
    if search:
        search_term = f"%{search}%"
        query = query.filter((BookDB.title.like(search_term)) | (BookDB.author.like(search_term)))
    return query.order_by(BookDB.id.desc()).all()


@app.post("/api/upload-receipt")
async def upload_receipt(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="يرجى اختيار ملف صورة صالح")
    content = await file.read()
    if len(content) > 3 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="حجم الصورة كبير جداً (الحد الأقصى 3 ميجا)")
    b64_str = base64.b64encode(content).decode("utf-8")
    return {"screenshot": f"data:{file.content_type};base64,{b64_str}"}


@app.post("/api/orders")
def create_order(order: OrderCreate, db: Session = Depends(get_db)):
    if not order.items:
        raise HTTPException(status_code=400, detail="السلة فارغة")

    for item in order.items:
        book = db.query(BookDB).filter(BookDB.id == item.id).first()
        if book and book.is_available is False:
            raise HTTPException(status_code=400, detail=f"عذراً، كتاب '{book.title}' غير متوفر حالياً.")

    items_data = [item.model_dump() for item in order.items]
    new_order = OrderDB(
        customer_name=order.customer_name,
        customer_phone=order.customer_phone,
        customer_address=order.customer_address,
        payment_method=order.payment_method or "الدفع عند الاستلام",
        payment_reference=order.payment_reference or "",
        payment_screenshot=order.payment_screenshot or "",
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


@app.put("/api/admin/settings", dependencies=[Depends(verify_admin)])
def update_store_settings(payload: StoreSettingsUpdate, db: Session = Depends(get_db)):
    settings = db.query(StoreSettingsDB).first()
    if not settings:
        settings = StoreSettingsDB(id=1)
        db.add(settings)
    settings.vodafone_cash = payload.vodafone_cash.strip()
    settings.store_address = payload.store_address.strip()
    db.commit()
    return {"message": "تم حفظ إعدادات المتجر بنجاح"}


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
            "payment_method": o.payment_method or "الدفع عند الاستلام",
            "payment_reference": o.payment_reference or "",
            "payment_screenshot": o.payment_screenshot or "",
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
    try:
        new_book = BookDB(**book.model_dump())
        db.add(new_book)
        db.commit()
        db.refresh(new_book)
        return new_book
    except Exception as exc:
        db.rollback()
        try:
            db.execute(text(
                "SELECT setval(pg_get_serial_sequence('books', 'id'), "
                "COALESCE((SELECT MAX(id) FROM books), 1), true)"
            ))
            db.commit()
            new_book = BookDB(**book.model_dump())
            db.add(new_book)
            db.commit()
            db.refresh(new_book)
            return new_book
        except Exception as retry_exc:
            db.rollback()
            print("create_book error:", exc, "| retry error:", retry_exc)
            raise HTTPException(status_code=500, detail=f"فشل حفظ الكتاب: {exc}")


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