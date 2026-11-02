(function () {
    "use strict";

    var root = document.getElementById("calendar");
    if (!root) { return; }

    var COLORS = {
        Pending: "bg-warning",
        Confirmed: "bg-success",
        Completed: "bg-primary",
        Cancelled: "bg-secondary"
    };

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
        var todayDay = (data.month === now.toISOString().slice(0, 7)) ? now.getDate() : null;

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

    var hotelId = root.dataset.hotel;
    if (!hotelId) {
        showMessage("Chưa có khách sạn nào.", "info");
        return;
    }

    var url = root.dataset.url + "?hotel_id=" + encodeURIComponent(hotelId) +
              "&month=" + encodeURIComponent(root.dataset.month);

    fetch(url, { credentials: "same-origin", headers: { "Accept": "application/json" } })
        .then(function (resp) {
            return resp.json().then(function (body) { return { ok: resp.ok, body: body }; });
        })
        .then(function (result) {
            if (!result.ok) {
                var msg = (result.body.error && result.body.error.message) || "Không tải được lịch.";
                showMessage(msg, "danger");
                return;
            }
            render(result.body.data);
        })
        .catch(function () {
            showMessage("Không kết nối được máy chủ.", "danger");
        });
})();