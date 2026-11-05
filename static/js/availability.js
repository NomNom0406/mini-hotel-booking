/**
 * availability.js
 * Dùng ở: trang chi tiết khách sạn, bước 1 đặt phòng, trang danh sách phòng
 *
 * DOM giả định:
 *   #avail-checkin   – <input type="date">
 *   #avail-checkout  – <input type="date">
 *   #avail-guests    – <input type="number"> hoặc <select>
 *   #avail-hotel-id  – <input hidden> hotel_id (trang chi tiết KS, trang /rooms)
 *   #avail-result    – vùng hiển thị kết quả
 *   #avail-submit    – nút "Tiếp tục" hoặc "Xem phòng trống" (bị disable khi hết)
 *
 * Nếu không có #avail-checkin thì script không làm gì.
 */

(function () {
    "use strict";

    const checkinEl = document.getElementById("avail-checkin");
    if (!checkinEl) return;

    const checkoutEl = document.getElementById("avail-checkout");
    const guestsEl = document.getElementById("avail-guests");
    const hotelIdEl = document.getElementById("avail-hotel-id");
    const resultEl = document.getElementById("avail-result");
    const submitEl = document.getElementById("avail-submit");
    const roomIdEl = document.getElementById("avail-room-id"); // chỉ có ở bước 1 đặt phòng

    let debounceTimer = null;
    let seq = 0;

    function isoDate(el) {
        return el && el.value ? el.value : "";
    }

    function buildUrl() {
        const ci = isoDate(checkinEl);
        const co = isoDate(checkoutEl);
        const g = guestsEl ? guestsEl.value : "1";
        const hotelId = hotelIdEl ? hotelIdEl.value : "";

        if (!ci || !co) return null;

        const p = new URLSearchParams({ checkin: ci, checkout: co, guests: g });
        if (hotelId) p.set("hotel_id", hotelId);
        return "/api/rooms/available?" + p.toString();
    }

    function strong(text) {
        const s = document.createElement("strong");
        s.textContent = text;
        return s;
    }

    function spinner() {
        const s = document.createElement("span");
        s.className = "spinner-inline";
        return s;
    }

    // nodes: chuỗi (thành text) hoặc Node; không dùng innerHTML
    function setResult(cls, ...nodes) {
        if (!resultEl) return;
        resultEl.className = "availability-indicator " + (cls || "");
        resultEl.replaceChildren(...nodes);
    }

    function setSubmitDisabled(val) {
        if (!submitEl) return;
        submitEl.disabled = val;
    }

    async function check() {
        const url = buildUrl();
        const mySeq = ++seq;

        if (!url) {
            setResult("");
            setSubmitDisabled(false);
            return;
        }

        setResult("checking", spinner(), " Đang kiểm tra…");
        setSubmitDisabled(true);

        const result = await apiFetch(url);
        if (mySeq !== seq) return; // đã có lần kiểm tra mới hơn

        if (!result.ok) {
            if (result.status === 400) {
                const msg = (result.error && result.error.message) || "Ngày không hợp lệ.";
                setResult("unavailable", "⚠️ " + msg);
                setSubmitDisabled(true);
            } else {
                setResult("unavailable", "Không thể kiểm tra phòng trống.");
                setSubmitDisabled(false); // server vẫn validate khi submit
            }
            return;
        }

        let rooms = result.data.rooms || [];
        const nights = result.data.nights || 0;
        // Bước 1 đặt phòng: chỉ xét đúng phòng đang đặt
        if (roomIdEl) {
            const rid = Number(roomIdEl.value);
            rooms = rooms.filter((r) => r.id === rid);
        }

        if (rooms.length === 0) {
            setResult("unavailable", "❌ Không còn phòng trống trong khoảng thời gian này.");
            setSubmitDisabled(true);
        } else {
            const minPrice = Math.min(...rooms.map((r) => Number(r.total_price) || 0));
            const fmt = new Intl.NumberFormat("vi-VN").format(minPrice);
            setResult(
                "available",
                "✅ Còn ", strong(rooms.length + " phòng"), " trống · " + nights + " đêm · từ ",
                strong(fmt + " ₫")
            );
            setSubmitDisabled(false);
        }
    }

    function schedule() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(check, 300);
    }

    checkinEl.addEventListener("change", schedule);
    if (checkoutEl) checkoutEl.addEventListener("change", schedule);
    if (guestsEl) guestsEl.addEventListener("change", schedule);

    // Kiểm tra ngay nếu đã có giá trị sẵn
    if (checkinEl.value && checkoutEl && checkoutEl.value) {
        check();
    }
})();