(function () {
    "use strict";

    var root = document.getElementById("calendar");
    if (!root) { return; }

    var form = document.getElementById("cal-form");
    var hotelSel = document.getElementById("hotel_id");
    var monthInp = document.getElementById("month");
    var prevLink = document.getElementById("cal-prev");
    var nextLink = document.getElementById("cal-next");

    var COLORS = {
        Pending: "bg-warning",
        Confirmed: "bg-success",
        Completed: "bg-primary",
        Cancelled: "bg-secondary"
    };

    var MONTH_RE = /^\d{4}-(0[1-9]|1[0-2])$/;

    function pad(n) { return n < 10 ? "0" + n : String(n); }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) { node.className = className; }
        if (text !== undefined) { node.textContent = text; }
        return node;
    }

    function showMessage(text, kind) {
        root.replaceChildren(el("div", "alert alert-" + kind, text));
    }

    function render(data) {
        if (!data.rooms.length) {
            showMessage("Khách sạn này chưa có phòng hoạt động.", "info");
            return;
        }
        var now = new Date();
        var thisMonth = now.getFullYear() + "-" + pad(now.getMonth() + 1);
        var todayDay = (data.month === thisMonth) ? now.getDate() : null;

        var table = el("table", "table table-bordered table-sm text-center align-middle mb-0");
        var head = el("tr");
        head.appendChild(el("th", "text-start", "Phòng"));
        for (var d = 1; d <= data.days; d++) {
            head.appendChild(el("th", d === todayDay ? "table-info" : "", String(d)));
        }
        var thead = el("thead");
        thead.appendChild(head);
        table.appendChild(thead);

        var tbody = el("tbody");
        data.rooms.forEach(function (room) {
            var row = el("tr");
            var label = el("th", "text-start text-nowrap", room.room_number);
            label.appendChild(el("div", "small fw-normal text-muted", room.type));
            row.appendChild(label);
            for (var day = 1; day <= data.days; day++) {
                var cell = el("td", "p-0");
                var info = room.cells[day];
                if (info) {
                    cell.className = "p-0 " + (COLORS[info.status] || "");
                    cell.title = info.code + " · " + info.status;
                    cell.textContent = "\u00a0";
                } else if (day === todayDay) {
                    cell.className = "p-0 table-info";
                }
                row.appendChild(cell);
            }
            tbody.appendChild(row);
        });
        table.appendChild(tbody);

        var wrap = el("div", "table-responsive");
        wrap.appendChild(table);
        root.replaceChildren(wrap);
    }

    /* -------- Điều hướng tháng / khách sạn bằng AJAX -------- */

    function shiftMonth(month, delta) {
        var p = month.split("-");
        var d = new Date(Number(p[0]), Number(p[1]) - 1 + delta, 1);
        return d.getFullYear() + "-" + pad(d.getMonth() + 1);
    }

    function pageUrl(hotel, month) {
        var base = form ? new URL(form.action, window.location.href).pathname : window.location.pathname;
        return base + "?hotel_id=" + encodeURIComponent(hotel) + "&month=" + encodeURIComponent(month);
    }

    function syncControls(hotel, month) {
        if (hotelSel) { hotelSel.value = hotel; }
        if (monthInp) { monthInp.value = month; }
        if (MONTH_RE.test(month)) {
            if (prevLink) { prevLink.href = pageUrl(hotel, shiftMonth(month, -1)); }
            if (nextLink) { nextLink.href = pageUrl(hotel, shiftMonth(month, 1)); }
        }
    }

    var current = { hotel: root.dataset.hotel, month: root.dataset.month };
    var seq = 0;

    async function load(hotel, month) {
        if (!hotel) {
            showMessage("Chưa có khách sạn nào.", "info");
            return;
        }
        var mySeq = ++seq;
        var hasCalendar = !!root.querySelector("table");
        if (!hasCalendar) {
            showMessage("Đang tải lịch…", "secondary");
        }
        root.setAttribute("aria-busy", "true");

        var url = root.dataset.url + "?hotel_id=" + encodeURIComponent(hotel) +
            "&month=" + encodeURIComponent(month);
        var result = await apiFetch(url);
        if (mySeq !== seq) { return; } // đã có yêu cầu mới hơn
        root.removeAttribute("aria-busy");

        if (!result.ok) {
            var msg = (result.error && result.error.message) || "Không tải được lịch.";
            if (hasCalendar) {
                // giữ lưới cũ, trả ô chọn về giá trị cũ
                showToast(msg, "danger");
                syncControls(current.hotel, current.month);
            } else {
                showMessage(msg, "danger");
            }
            return;
        }

        current = { hotel: hotel, month: month };
        render(result.data);
        syncControls(hotel, month);
        history.replaceState(null, "", pageUrl(hotel, month));
    }

    function loadFromControls() {
        var hotel = hotelSel ? hotelSel.value : current.hotel;
        var month = monthInp ? monthInp.value : current.month;
        if (!MONTH_RE.test(month)) {
            showToast("Vui lòng chọn tháng hợp lệ.", "warning");
            return;
        }
        load(hotel, month);
    }

    if (form) {
        form.addEventListener("submit", function (e) {
            e.preventDefault();
            loadFromControls();
        });
    }
    if (hotelSel) { hotelSel.addEventListener("change", loadFromControls); }
    if (monthInp) { monthInp.addEventListener("change", loadFromControls); }

    function bindStep(link, delta) {
        if (!link) { return; }
        link.addEventListener("click", function (e) {
            if (e.ctrlKey || e.metaKey || e.shiftKey) { return; } // cho mở tab mới như link thường
            if (!MONTH_RE.test(current.month)) { return; }
            e.preventDefault();
            load(current.hotel, shiftMonth(current.month, delta));
        });
    }
    bindStep(prevLink, -1);
    bindStep(nextLink, 1);

    /* -------- Tải lần đầu -------- */
    if (MONTH_RE.test(current.month)) {
        syncControls(current.hotel, current.month);
    }
    load(current.hotel, current.month);
})();