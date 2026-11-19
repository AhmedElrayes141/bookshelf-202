let books = [];
let currentCategory = "رعب";
let searchQuery = "";
let cart = [];
let storeSettings = {
    vodafone_cash: "01097897941",
    store_address: 'دمنهور - ش عبد السلام الشاذلي (أسفل الكوبري العلوي - أول ش مدرسة الفكرية) | دسوق - "شارع الجيش"'
};

const booksGrid = document.getElementById("booksGrid");

// جلب إعدادات المتجر (رقم فودافون كاش والعنوان)
async function fetchStoreSettings() {
    try {
        const res = await fetch("/api/settings");
        if (res.ok) {
            storeSettings = await res.json();
            if (storeSettings.vodafone_cash) {
                document.getElementById("paymentAccountDisplay").textContent = storeSettings.vodafone_cash;
            }
        }
    } catch (e) {
        console.error("Error fetching settings:", e);
    }
}

// جلب الكتب من FastAPI API مع إعادة المحاولة التلقائية لو السيرفر في وضع السكون
async function fetchBooks(retries = 2) {
    booksGrid.innerHTML = `<p style="grid-column:1/-1; text-align:center; padding:40px; color:var(--muted);">⏳ جاري تحميل الكتب...</p>`;

    for (let attempt = 0; attempt <= retries; attempt++) {
        try {
            const params = new URLSearchParams();
            if (currentCategory) params.append("category", currentCategory);
            if (searchQuery) params.append("search", searchQuery);

            const response = await fetch(`/api/books?${params.toString()}`);
            if (!response.ok) throw new Error("فشل الاتصال بالسيرفر");

            books = await response.json();
            renderBooks();
            return;
        } catch (error) {
            if (attempt < retries) {
                await new Promise(resolve => setTimeout(resolve, 1500));
            } else {
                console.error("Error fetching books:", error);
                booksGrid.innerHTML = `
                    <div style="grid-column:1/-1; text-align:center; padding:40px;">
                        <p style="color:#c0392b; margin-bottom:12px;">تعذر تحميل الكتب حالياً، السيرفر يستيقظ من وضع السكون.</p>
                        <button class="btn-add" onclick="fetchBooks()" style="padding:8px 18px;">إعادة المحاولة ↻</button>
                    </div>`;
            }
        }
    }
}

function renderBooks() {
    if (books.length === 0) {
        booksGrid.innerHTML = `<p style="grid-column:1/-1; text-align:center; padding:40px; color:var(--muted);">لا توجد كتب مطابقة لبحثك في هذا القسم.</p>`;
        return;
    }

    booksGrid.innerHTML = books.map(book => {
        const isAvailable = book.is_available !== false;
        return `
        <div class="book-card" style="${!isAvailable ? 'opacity:0.82;' : ''}">
            <div class="book-cover">
                <span class="badge" style="${!isAvailable ? 'background:#c0392b; color:#fff;' : ''}">
                    ${isAvailable ? book.category : 'غير متوفر'}
                </span>
                <img src="${book.cover}" alt="${book.title}" style="${!isAvailable ? 'filter:grayscale(45%);' : ''}">
            </div>
            <div class="book-info">
                <h3 class="book-title">${book.title}</h3>
                <p class="book-author">تأليف: ${book.author}</p>
                <div class="book-footer">
                    <span class="price">${book.price} ج.م</span>
                    <div class="actions">
                        <button class="btn-details" onclick="showDetails(${book.id})">تفاصيل</button>
                        ${isAvailable
                            ? `<button class="btn-add" onclick="addToCart(${book.id})">+ للسلة</button>`
                            : `<button class="btn-add" disabled style="background:#95a5a6; cursor:not-allowed;">غير متوفر</button>`
                        }
                    </div>
                </div>
            </div>
        </div>
    `}).join("");
}

document.querySelectorAll(".cat-btn").forEach(btn => {
    btn.addEventListener("click", () => {
        document.querySelectorAll(".cat-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        currentCategory = btn.dataset.cat;
        fetchBooks();
    });
});

document.getElementById("searchInput").addEventListener("input", (e) => {
    searchQuery = e.target.value.trim();
    fetchBooks();
});

function showDetails(id) {
    const book = books.find(b => b.id === id);
    if (!book) return;
    const isAvailable = book.is_available !== false;

    document.getElementById("detailsContent").innerHTML = `
        <div style="display:flex; gap:20px; flex-wrap:wrap; align-items:center;">
            <img src="${book.cover}" style="width:140px; border-radius:8px; box-shadow:0 4px 12px rgba(0,0,0,0.2);">
            <div style="flex:1; min-width:200px;">
                <span style="background:var(--primary); color:var(--logo-gold); padding:3px 10px; border-radius:12px; font-size:0.8rem;">${book.category}</span>
                <h2 style="margin:10px 0 5px; color:var(--primary-dark);">${book.title}</h2>
                <p style="color:var(--muted); margin-bottom:6px;">المؤلف: <strong>${book.author}</strong></p>
                <p style="font-size:0.85rem; margin-bottom:10px; color:${isAvailable ? '#27ae60' : '#c0392b'}; font-weight:700;">
                    ${isAvailable ? '✅ متوفر حالياً' : '❌ غير متوفر حالياً'}
                </p>
                <p style="margin-bottom:15px;">${book.desc || ''}</p>
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span class="price" style="font-size:1.4rem;">${book.price} ج.م</span>
                    ${isAvailable
                        ? `<button class="btn-add" style="padding:10px 18px;" onclick="addToCart(${book.id}); closeModal('detailsModal');">أضف إلى السلة</button>`
                        : `<button class="btn-add" disabled style="padding:10px 18px; background:#95a5a6; cursor:not-allowed;">غير متوفر</button>`
                    }
                </div>
            </div>
        </div>
    `;
    document.getElementById("detailsModal").style.display = "flex";
}

function addToCart(id) {
    const book = books.find(b => b.id === id);
    if (!book) return;
    if (book.is_available === false) return alert("عذراً، هذا الكتاب غير متوفر حالياً.");

    const item = cart.find(i => i.id === id);
    if (item) {
        item.qty++;
    } else {
        cart.push({...book, qty: 1});
    }
    updateCartUI();
}

function changeQty(id, delta) {
    const item = cart.find(i => i.id === id);
    if (!item) return;
    item.qty += delta;
    if (item.qty <= 0) {
        cart = cart.filter(i => i.id !== id);
    }
    updateCartUI();
}

function updateCartUI() {
    const count = cart.reduce((sum, i) => sum + i.qty, 0);
    const total = cart.reduce((sum, i) => sum + (i.price * i.qty), 0);
    document.getElementById("cartCount").textContent = count;
    document.getElementById("cartTotal").textContent = total;

    const cartItemsDiv = document.getElementById("cartItems");
    if (cart.length === 0) {
        cartItemsDiv.innerHTML = `<p style="text-align:center; color:var(--muted); padding:20px;">السلة فارغة حالياً.</p>`;
        return;
    }

    cartItemsDiv.innerHTML = cart.map(item => `
        <div class="cart-item">
            <div>
                <strong>${item.title}</strong>
                <div style="font-size:0.85rem; color:var(--muted);">${item.price} ج.م × ${item.qty}</div>
            </div>
            <div class="qty-controls">
                <button onclick="changeQty(${item.id}, -1)">-</button>
                <span style="margin:0 8px;">${item.qty}</span>
                <button onclick="changeQty(${item.id}, 1)">+</button>
            </div>
        </div>
    `).join("");
}

function handlePaymentChange() {
    const method = document.getElementById("paymentMethod").value;
    const box = document.getElementById("onlinePaymentBox");
    const accEl = document.getElementById("paymentAccountDisplay");

    if (method === "فودافون كاش") {
        box.style.display = "block";
        accEl.textContent = storeSettings.vodafone_cash || "01097897941";
    } else {
        box.style.display = "none";
    }
}

function copyPaymentAccount() {
    const text = document.getElementById("paymentAccountDisplay").textContent;
    navigator.clipboard.writeText(text).then(() => {
        alert("تم نسخ رقم فودافون كاش: " + text);
    });
}

function openCart() {
    updateCartUI();
    handlePaymentChange();
    document.getElementById("cartModal").style.display = "flex";
}

function closeModal(id) {
    document.getElementById(id).style.display = "none";
}

async function checkout() {
    if (cart.length === 0) return alert("السلة فارغة!");

    const customerName = document.getElementById("custName").value.trim();
    const customerPhone = document.getElementById("custPhone").value.trim();
    const customerAddress = document.getElementById("custAddress").value.trim();
    const paymentMethod = document.getElementById("paymentMethod").value;
    const paymentReference = document.getElementById("paymentReference").value.trim();
    const screenshotInput = document.getElementById("paymentScreenshot");

    if (!customerName || !customerPhone || !customerAddress) {
        return alert("من فضلك أدخل الاسم ورقم الموبايل والعنوان لإتمام الطلب.");
    }

    let screenshotData = "";
    if (paymentMethod === "فودافون كاش") {
        if (!paymentReference && (!screenshotInput || screenshotInput.files.length === 0)) {
            return alert("من فضلك اكتب رقم المحفظة المحوّل منها أو ارفع سكرين شوت التحويل.");
        }
        if (screenshotInput && screenshotInput.files.length > 0) {
            const formData = new FormData();
            formData.append("file", screenshotInput.files[0]);
            const upRes = await fetch("/api/upload-receipt", {
                method: "POST",
                body: formData
            });
            const upData = await upRes.json();
            if (!upRes.ok) {
                return alert(upData.detail || "فشل رفع صورة التحويل، جرب صورة أصغر.");
            }
            screenshotData = upData.screenshot;
        }
    }

    const total = cart.reduce((sum, i) => sum + (i.price * i.qty), 0);
    const orderPayload = {
        customer_name: customerName,
        customer_phone: customerPhone,
        customer_address: customerAddress,
        payment_method: paymentMethod,
        payment_reference: paymentMethod === "الدفع عند الاستلام" ? "" : paymentReference,
        payment_screenshot: paymentMethod === "الدفع عند الاستلام" ? "" : screenshotData,
        items: cart.map(item => ({
            id: item.id,
            title: item.title,
            price: item.price,
            qty: item.qty
        })),
        total_price: total
    };

    try {
        const response = await fetch("/api/orders", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(orderPayload)
        });

        const result = await response.json();
        if (!response.ok) {
            alert(result.detail || "حدث خطأ أثناء تسجيل الطلب");
            fetchBooks();
            return;
        }

        alert(`تم استلام طلبك بنجاح يا ${customerName}! رقم الطلب: #${result.order_id}`);

        cart = [];
        document.getElementById("custName").value = "";
        document.getElementById("custPhone").value = "";
        document.getElementById("custAddress").value = "";
        document.getElementById("paymentMethod").value = "الدفع عند الاستلام";
        document.getElementById("paymentReference").value = "";
        if (screenshotInput) screenshotInput.value = "";
        handlePaymentChange();
        updateCartUI();
        closeModal("cartModal");
    } catch (error) {
        console.error("Checkout error:", error);
        alert("تعذر إرسال الطلب للسيرفر، حاول مرة أخرى.");
    }
}

fetchStoreSettings();
fetchBooks();