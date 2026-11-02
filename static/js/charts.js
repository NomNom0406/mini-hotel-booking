(function () {
    "use strict";

    var root = document.getElementById("dashboard");
    if (!root || typeof Chart === "undefined") { return; }

    var STATUS_LABELS = {
        Pending: "Chờ xác nhận", Confirmed: "Đã xác nhận",
        Completed: "Hoàn tất", Cancelled: "Đã hủy"
    };
    var STATUS_COLORS = {
        Pending: "#ffc107", Confirmed: "#198754",
        Completed: "#0d6efd", Cancelled: "#6c757d"
    };
    var STATUS_ORDER = ["Pending", "Confirmed", "Completed", "Cancelled"];

    function monthLabel(value) {            // "2026-11" -> "11/2026"
        var parts = value.split("-");
        return parts[1] + "/" + parts[0];
    }

    function money(value) {
        return Number(value).toLocaleString("vi-VN") + " ₫";
    }

    function showError(text) {
        var box = document.getElementById("dashboard-error");
        box.textContent = text;
        box.classList.remove("d-none");
    }

    function draw(canvasId, config) {
        var canvas = document.getElementById(canvasId);
        if (canvas) { new Chart(canvas, config); }
    }

    function render(data) {
        draw("chart-revenue", {
            type: "bar",
            data: {
                labels: data.revenue.map(function (r) { return monthLabel(r.month); }),
                datasets: [{
                    label: "Doanh thu",
                    data: data.revenue.map(function (r) { return r.revenue; }),
                    backgroundColor: "#0d6efd"
                }]
            },
            options: {
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: function (ctx) { return money(ctx.parsed.y); } } }
                },
                scales: { y: { beginAtZero: true } }
            }
        });

        draw("chart-occupancy", {
            type: "line",
            data: {
                labels: data.occupancy.map(function (r) { return monthLabel(r.month); }),
                datasets: [{
                    label: "Công suất (%)",
                    data: data.occupancy.map(function (r) { return r.occupancy; }),
                    borderColor: "#198754", backgroundColor: "#19875433",
                    fill: true, tension: 0.25
                }]
            },
            options: {
                plugins: { legend: { display: false } },
                scales: { y: { beginAtZero: true, max: 100 } }
            }
        });

        var b = data.bookings;
        draw("chart-bookings", {
            type: "bar",
            data: {
                labels: b.months.map(monthLabel),
                datasets: STATUS_ORDER.map(function (status) {
                    return {
                        label: STATUS_LABELS[status],
                        data: b.series[status],
                        backgroundColor: STATUS_COLORS[status]
                    };
                })
            },
            options: {
                scales: {
                    x: { stacked: true },
                    y: { stacked: true, beginAtZero: true, ticks: { precision: 0 } }
                }
            }
        });

        draw("chart-ratio", {
            type: "doughnut",
            data: {
                labels: STATUS_ORDER.map(function (s) { return STATUS_LABELS[s]; }),
                datasets: [{
                    data: STATUS_ORDER.map(function (s) { return b.ratio[s]; }),
                    backgroundColor: STATUS_ORDER.map(function (s) { return STATUS_COLORS[s]; })
                }]
            },
            options: {
                plugins: {
                    tooltip: { callbacks: { label: function (ctx) {
                        return ctx.label + ": " + ctx.parsed + "%";
                    } } }
                }
            }
        });
    }

    var url = root.dataset.url;
    if (root.dataset.hotel) {
        url += "?hotel_id=" + encodeURIComponent(root.dataset.hotel);
    }

    fetch(url, { credentials: "same-origin", headers: { "Accept": "application/json" } })
        .then(function (resp) {
            if (!resp.ok) { throw new Error("HTTP " + resp.status); }
            return resp.json();
        })
        .then(render)
        .catch(function () { showError("Không tải được số liệu biểu đồ."); });
})();