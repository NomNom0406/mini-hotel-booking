/**
 * hotel_search.js
 * Trang /hotels/search:
 * - Khi đổi bộ lọc (sắp xếp, khoảng giá, hạng sao, tiện nghi) → gọi GET /api/hotels debounce 300 ms
 * - Vẽ lại danh sách thẻ khách sạn và số kết quả tại chỗ
 * - Cập nhật URL bằng history.replaceState
 * - Lỗi thì giữ danh sách cũ và báo toast
 *
 * DOM giả định (do template search_results.html cung cấp):
 *   #filter-sort       – <select> sắp xếp
 *   #filter-min-price  – <input number> giá từ
 *   #filter-max-price  – <input number> giá đến
 *   .filter-star       – <input checkbox> value=1..5
 *   .filter-amenity    – <input checkbox> value=<amenity_id>
 *   #hotel-list-wrap   – vùng chứa danh sách thẻ
 *   #result-count      – span số kết quả
 *   #pagination-wrap   – vùng chứa phân trang
 *   data-checkin / data-checkout / data-guests trên #filter-sort (truyền từ template)
 */

(function () {
    "use strict";

    const sortEl = document.getElementById("filter-sort");
    if (!sortEl) return; // không phải trang tìm kiếm

    const listWrap = document.getElementById("hotel-list-wrap");
    const resultCount = document.getElementById("result-count");
    const paginationWrap = document.getElementById("pagination-wrap");

    // Lấy ngày/khách từ data attribute (template render sẵn)
    const checkin = sortEl.dataset.checkin || "";
    const checkout = sortEl.dataset.checkout || "";
    const guests = sortEl.dataset.guests || "1";
    const province = sortEl.dataset.province || "";

    let debounceTimer = null;
    let currentPage = 1;

    function buildParams(page) {
        const p = new URLSearchParams();
        if (province) p.set("province", province);
        if (checkin) p.set("checkin", checkin);
        if (checkout) p.set("checkout", checkout);
        if (guests) p.set("guests", guests);

        const sort = sortEl.value;
        if (sort) p.set("sort", sort);

        const minPrice = document.getElementById("filter-min-price");
        if (minPrice && minPrice.value) p.set("min_price", minPrice.value);

        const maxPrice = document.getElementById("filter-max-price");
        if (maxPrice && maxPrice.value) p.set("max_price", maxPrice.value);

        document.querySelectorAll(".filter-star:checked").forEach((el) => {
            p.append("stars", el.value);
        });
        document.querySelectorAll(".filter-amenity:checked").forEach((el) => {
            p.append("amenity", el.value);
        });

        if (page > 1) p.set("page", page);
        return p;
    }

    function renderStars(n) {
        let s = "";
        for (let i = 0; i < 5; i++) {
            s += i < n ? "★" : "☆";
        }
        return s;
    }

    function renderPrice(price) {
        if (!price && price !== 0) return "—";
        return new Intl.NumberFormat("vi-VN").format(price) + " ₫";
    }

    function buildHotelCard(h) {
        const imgSrc = h.image_url ? h.image_url : "";
        const imgHtml = imgSrc
            ? '<img src="' + imgSrc + '" class="card-img-top" alt="" loading="lazy" style="height:200px;object-fit:cover;">'
            : '<div class="card-img-placeholder" style="height:200px;background:#e8f5ee;display:flex;align-items:center;justify-content:center;font-size:2.5rem;">🏨</div>';

        const stars = renderStars(h.star_rating || 0);
        const priceHtml = h.price_from
            ? '<div class="price-from">Giá từ</div><div class="price-value">' + renderPrice(h.price_from) + '/đêm</div>'
            : '<div class="text-muted small">Chưa có phòng</div>';

        const ci = checkin ? "&checkin=" + checkin : "";
        const co = checkout ? "&checkout=" + checkout : "";
        const gp = guests ? "&guests=" + guests : "";

        const card = document.createElement("div");
        card.className = "col";
        // Dùng textContent cho các giá trị text để tránh XSS
        const inner = document.createElement("div");
        inner.className = "hotel-card card h-100";

        const imgWrap = document.createElement("a");
        imgWrap.href = "/hotels/" + h.id;
        imgWrap.innerHTML = imgHtml; // ảnh URL từ API server của chính mình

        const body = document.createElement("div");
        body.className = "card-body d-flex flex-column";

        const name = document.createElement("div");
        name.className = "hotel-name mb-1";
        const nameLink = document.createElement("a");
        nameLink.href = "/hotels/" + h.id;
        nameLink.className = "text-decoration-none text-dark";
        nameLink.textContent = h.name;
        name.appendChild(nameLink);

        const prov = document.createElement("div");
        prov.className = "hotel-province mb-1";
        prov.textContent = "📍 " + (h.province || "");

        const starDiv = document.createElement("div");
        starDiv.className = "star-rating mb-2";
        starDiv.textContent = stars;

        const priceDiv = document.createElement("div");
        priceDiv.className = "mt-auto";
        priceDiv.innerHTML = priceHtml;

        const btnWrap = document.createElement("div");
        btnWrap.className = "mt-2";
        const btn = document.createElement("a");
        btn.href = "/hotels/" + h.id + "?" + (ci + co + gp).replace(/^&/, "");
        btn.className = "btn btn-primary btn-sm w-100";
        btn.textContent = "Xem chi tiết";
        btnWrap.appendChild(btn);

        body.appendChild(name);
        body.appendChild(prov);
        body.appendChild(starDiv);
        body.appendChild(priceDiv);
        body.appendChild(btnWrap);
        inner.appendChild(imgWrap);
        inner.appendChild(body);
        card.appendChild(inner);
        return card;
    }

    function buildPagination(current, total) {
        if (!paginationWrap || total <= 1) {
            if (paginationWrap) paginationWrap.innerHTML = "";
            return;
        }
        const ul = document.createElement("ul");
        ul.className = "pagination justify-content-center mb-0";

        function mkItem(label, page, disabled, active) {
            const li = document.createElement("li");
            li.className = "page-item" + (disabled ? " disabled" : "") + (active ? " active" : "");
            const a = document.createElement("a");
            a.className = "page-link";
            a.href = "#";
            a.textContent = label;
            if (!disabled && !active) {
                a.addEventListener("click", (e) => {
                    e.preventDefault();
                    currentPage = page;
                    doFetch();
                });
            }
            li.appendChild(a);
            ul.appendChild(li);
        }

        mkItem("«", current - 1, current === 1, false);
        for (let i = Math.max(1, current - 2); i <= Math.min(total, current + 2); i++) {
            mkItem(i, i, false, i === current);
        }
        mkItem("»", current + 1, current === total, false);

        paginationWrap.innerHTML = "";
        paginationWrap.appendChild(ul);
    }

    async function doFetch() {
        if (!listWrap) return;

        const params = buildParams(currentPage);

        // Cập nhật URL
        const newSearch = "?" + params.toString();
        history.replaceState(null, "", window.location.pathname + newSearch);

        // Loading state
        listWrap.classList.add("loading");
        const spinner = listWrap.querySelector(".loading-spinner");
        if (spinner) spinner.style.display = "flex";

        const result = await apiFetch("/api/hotels?" + params.toString());

        listWrap.classList.remove("loading");
        if (spinner) spinner.style.display = "none";

        if (!result.ok) {
            showToast(
                (result.error && result.error.message) || "Không thể tải kết quả. Vui lòng thử lại.",
                "danger"
            );
            return;
        }

        const data = result.data;
        const hotels = data.hotels || [];
        const total = data.total || 0;
        const pages = data.pages || 1;

        // Cập nhật số kết quả
        if (resultCount) {
            resultCount.textContent = total + " khách sạn";
        }

        // Vẽ lại danh sách
        const grid = listWrap.querySelector(".row.row-cols-1");
        if (grid) {
            grid.innerHTML = "";
            if (hotels.length === 0) {
                const empty = document.createElement("div");
                empty.className = "col-12 text-center py-5 text-muted";
                empty.textContent = "Không tìm thấy khách sạn phù hợp.";
                grid.appendChild(empty);
            } else {
                hotels.forEach((h) => grid.appendChild(buildHotelCard(h)));
            }
        }

        buildPagination(currentPage, pages);
    }

    function scheduleDebounce() {
        clearTimeout(debounceTimer);
        currentPage = 1;
        debounceTimer = setTimeout(doFetch, 300);
    }

    // Gắn sự kiện
    sortEl.addEventListener("change", scheduleDebounce);

    const minPrice = document.getElementById("filter-min-price");
    if (minPrice) minPrice.addEventListener("input", scheduleDebounce);

    const maxPrice = document.getElementById("filter-max-price");
    if (maxPrice) maxPrice.addEventListener("input", scheduleDebounce);

    document.querySelectorAll(".filter-star, .filter-amenity").forEach((el) => {
        el.addEventListener("change", scheduleDebounce);
    });
})();