/**
 * my_bookings.js
 * Trang /my-bookings (Customer):
 * - Sửa họ tên, điện thoại, ghi chú của booking Pending qua PATCH /api/bookings/<id>
 * - Cập nhật dòng tại chỗ, báo lỗi 409 nếu booking đã đổi trạng thái
 * (Hủy booking là form POST kèm CSRF trong template, không xử lý ở file này.)
 *
 * DOM giả định cho mỗi dòng / thẻ:
 *   [data-booking-id="<id>"]  ← tr hoặc card
 *   .btn-edit-booking         ← nút mở form sửa (chỉ Pending)
 *   .edit-form-wrap           ← wrap ẩn chứa các input
 *   input[name="guest_name"]
 *   input[name="guest_phone"]
 *   textarea[name="note"]
 *   .btn-save-edit            ← submit sửa
 *   .btn-cancel-edit          ← hủy sửa (đóng form)
 *   .display-guest-name       ← span hiển thị tên (để cập nhật sau khi sửa)
 *   .display-guest-phone
 *   .display-note
 */

(function () {
    "use strict";

    /* -------- Sửa thông tin -------- */
    document.querySelectorAll(".btn-edit-booking").forEach((btn) => {
        btn.addEventListener("click", () => {
            const row = btn.closest("[data-booking-id]");
            if (!row) return;
            // Form sửa nằm ở <tr> kế bên (cùng data-booking-id), nên tìm trên toàn trang
            const wrap = document.querySelector(
                '[data-booking-id="' + row.dataset.bookingId + '"] .edit-form-wrap'
            );
            if (wrap) wrap.style.display = wrap.style.display === "none" ? "" : "none";
        });
    });

    document.querySelectorAll(".btn-cancel-edit").forEach((btn) => {
        btn.addEventListener("click", () => {
            const row = btn.closest("[data-booking-id]");
            if (!row) return;
            const wrap = row.querySelector(".edit-form-wrap");
            if (wrap) wrap.style.display = "none";
        });
    });

    document.querySelectorAll(".btn-save-edit").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const row = btn.closest("[data-booking-id]");
            if (!row) return;
            const bookingId = row.dataset.bookingId;

            const nameEl = row.querySelector("input[name='guest_name']");
            const phoneEl = row.querySelector("input[name='guest_phone']");
            const noteEl = row.querySelector("textarea[name='note']");

            const body = {};
            if (nameEl) body.guest_name = nameEl.value.trim();
            if (phoneEl) body.guest_phone = phoneEl.value.trim();
            if (noteEl) body.note = noteEl.value.trim();

            btn.disabled = true;
            btn.innerHTML = '<span class="spinner-inline"></span>';

            const result = await apiFetch("/api/bookings/" + bookingId, {
                method: "PATCH",
                body: JSON.stringify(body),
            });

            btn.disabled = false;
            btn.textContent = "Lưu";

            if (!result.ok) {
                if (result.status === 409) {
                    showToast("Booking đã thay đổi trạng thái, không thể sửa.", "warning");
                } else {
                    const msg = (result.error && result.error.message) || "Lỗi khi lưu.";
                    showToast(msg, "danger");
                }
                return;
            }

            // Cập nhật hiển thị
            const d = result.data;
            const dispName = row.querySelector(".display-guest-name");
            const dispPhone = row.querySelector(".display-guest-phone");
            const dispNote = row.querySelector(".display-note");
            if (dispName && d.guest_name) dispName.textContent = d.guest_name;
            if (dispPhone && d.guest_phone) dispPhone.textContent = d.guest_phone;
            if (dispNote) dispNote.textContent = d.note || "";

            const wrap = row.querySelector(".edit-form-wrap");
            if (wrap) wrap.style.display = "none";

            showToast("Đã cập nhật thông tin đặt phòng.", "success");
        });
    });
})();