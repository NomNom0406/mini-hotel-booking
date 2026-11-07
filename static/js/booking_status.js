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

    // Các trạng thái đích hợp lệ theo ALLOWED_TRANSITIONS (khớp templates/manage/bookings.html)
    const NEXT_OPTIONS = {
        Pending: [["Confirmed", "Xác nhận"], ["Cancelled", "Hủy"]],
        Confirmed: [["Completed", "Hoàn tất"], ["Cancelled", "Hủy"]],
    };

    // Dựng lại ô "Đổi trạng thái" theo trạng thái mới
    function renderStatusControl(form, select, reasonInput, newStatus) {
        const options = NEXT_OPTIONS[newStatus];
        if (!options) {
            // Cancelled / Completed: trạng thái cuối, không còn thao tác
            const done = document.createElement("span");
            done.className = "text-muted small";
            done.textContent = "Đã kết thúc";
            form.replaceWith(done);
            return;
        }
        if (!select) return;
        select.textContent = "";
        options.forEach(function (pair) {
            const opt = document.createElement("option");
            opt.value = pair[0];
            opt.textContent = pair[1];
            select.appendChild(opt);
        });
        select.value = options[0][0];
        if (reasonInput) reasonInput.value = "";
        // chạy lại toggleReason để ẩn ô lý do
        select.dispatchEvent(new Event("change"));
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

            // Cập nhật badge (kèm lý do hủy giống template khi F5)
            const newStatus = result.data.status;
            const row = form.closest("tr[data-booking-id]") || form.closest("tr");
            if (row) {
                const tdStatus = row.querySelector(".td-status");
                if (tdStatus) {
                    tdStatus.innerHTML = "";
                    tdStatus.appendChild(makeBadge(newStatus));
                    if (newStatus === "Cancelled" && reason) {
                        tdStatus.appendChild(document.createElement("br"));
                        const small = document.createElement("small");
                        small.className = "text-muted";
                        small.textContent = reason;
                        tdStatus.appendChild(small);
                    }
                }
            }

            // Dựng lại ô đổi trạng thái theo trạng thái mới
            renderStatusControl(form, select, reasonInput, newStatus);

            showToast("Cập nhật trạng thái thành công.", "success");
        });
    });
})();