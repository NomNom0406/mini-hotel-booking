/**
 * booking_status.js
 * Trang /manage/bookings:
 * Mỗi dòng có form đổi trạng thái; thay vì submit form thật,
 * gọi PUT /api/bookings/<id>/status và cập nhật badge tại chỗ.
 *
 * DOM giả định cho mỗi dòng booking:
 *   <tr data-booking-id="<id>">
 *     <td class="td-status">  ← badge sẽ cập nhật ở đây
 *     <form class="status-form" data-booking-id="<id>">
 *       <select name="status">...</select>
 *       <input name="reason" ...>   ← optional, hiện khi chọn Cancelled
 *       <button type="submit">Lưu</button>
 *     </form>
 *   </tr>
 */

(function () {
    "use strict";

    const STATUS_LABELS = {
        Pending: "Chờ xác nhận",
        Confirmed: "Đã xác nhận",
        Cancelled: "Đã hủy",
        Completed: "Hoàn tất",
    };
    const STATUS_BADGE = {
        Pending: "badge-pending",
        Confirmed: "badge-confirmed",
        Cancelled: "badge-cancelled",
        Completed: "badge-completed",
    };

    function makeBadge(status) {
        const span = document.createElement("span");
        span.className = "badge rounded-pill " + (STATUS_BADGE[status] || "bg-secondary");
        span.textContent = STATUS_LABELS[status] || status;
        return span;
    }

    document.querySelectorAll(".status-form").forEach((form) => {
        const select = form.querySelector("select[name='status']");
        const reasonWrap = form.querySelector(".reason-wrap");
        const reasonInput = form.querySelector("input[name='cancel_reason'], textarea[name='cancel_reason']");

        // Hiện/ẩn ô lý do khi chọn Cancelled
        if (select && reasonWrap) {
            function toggleReason() {
                const need = select.value === "Cancelled";
                reasonWrap.style.display = need ? "" : "none";
                if (reasonInput) reasonInput.required = need;
            }
            select.addEventListener("change", toggleReason);
            toggleReason();
        }

        form.addEventListener("submit", async (e) => {
            e.preventDefault();

            const bookingId = form.dataset.bookingId;
            if (!bookingId) return;

            const status = select ? select.value : null;
            if (!status) return;

            const reason = reasonInput ? reasonInput.value.trim() : "";
            if (status === "Cancelled" && !reason) {
                showToast("Vui lòng nhập lý do hủy.", "warning");
                if (reasonInput) reasonInput.focus();
                return;
            }

            const btn = form.querySelector("button[type='submit']");
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<span class="spinner-inline"></span>';
            }

            const body = { status };
            if (reason) body.reason = reason;

            const result = await apiFetch("/api/bookings/" + bookingId + "/status", {
                method: "PUT",
                body: JSON.stringify(body),
            });

            if (btn) {
                btn.disabled = false;
                btn.textContent = "Lưu";
            }

            if (!result.ok) {
                const msg =
                    (result.error && result.error.message) ||
                    (result.status === 409 ? "Chuyển trạng thái không hợp lệ." : "Lỗi " + result.status);
                showToast(msg, "danger");
                return;
            }

            // Cập nhật badge
            const newStatus = result.data.status;
            const row = form.closest("tr[data-booking-id]") || form.closest("tr");
            if (row) {
                const tdStatus = row.querySelector(".td-status");
                if (tdStatus) {
                    tdStatus.innerHTML = "";
                    tdStatus.appendChild(makeBadge(newStatus));
                }
            }

            // Cập nhật select về trạng thái mới
            if (select) select.value = newStatus;

            showToast("Cập nhật trạng thái thành công.", "success");
        });
    });
})();