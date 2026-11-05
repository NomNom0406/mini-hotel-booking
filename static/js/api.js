/**
 * api.js – Cầu nối JWT cho mọi AJAX
 *
 * - Lấy access_token (15 phút) từ GET /auth/api-token (session Flask)
 * - Tự gắn header Authorization: Bearer
 * - Nếu nhận 401 thì xin token mới một lần rồi thử lại
 * - Xuất: apiFetch(url, options) → Promise<{ok, status, data|error}>
 * - Xuất: showToast(message, type)  ('success'|'danger'|'warning')
 */

(function (global) {
    "use strict";

    /* -------- Token cache -------- */
    let _token = null;
    let _tokenExpiry = 0; // timestamp ms

    async function _getToken() {
        const now = Date.now();
        if (_token && now < _tokenExpiry - 30_000) return _token; // còn > 30 giây
        try {
            const res = await fetch("/auth/api-token", { credentials: "same-origin" });
            if (!res.ok) return null; // chưa đăng nhập
            const json = await res.json();
            _token = json.data.access_token;
            const expiresIn = (json.data.expires_in || 900) * 1000;
            _tokenExpiry = Date.now() + expiresIn;
            return _token;
        } catch {
            return null;
        }
    }

    /* -------- apiFetch -------- */
    async function apiFetch(url, options = {}) {
        const token = await _getToken();
        const headers = Object.assign({}, options.headers || {}, {
            "Content-Type": "application/json",
        });
        if (token) headers["Authorization"] = "Bearer " + token;

        let res;
        try {
            res = await fetch(url, { ...options, headers, credentials: "same-origin" });
        } catch (err) {
            return { ok: false, status: 0, error: { message: "Không kết nối được mạng." } };
        }

        // 401 → xin token mới, thử lại một lần
        if (res.status === 401 && token) {
            _token = null;
            _tokenExpiry = 0;
            const newToken = await _getToken();
            if (newToken) {
                headers["Authorization"] = "Bearer " + newToken;
                try {
                    res = await fetch(url, { ...options, headers, credentials: "same-origin" });
                } catch {
                    return { ok: false, status: 0, error: { message: "Không kết nối được mạng." } };
                }
            }
        }

        let json;
        try {
            json = await res.json();
        } catch {
            return { ok: false, status: res.status, error: { message: "Phản hồi không hợp lệ từ máy chủ." } };
        }

        if (res.ok) {
            return { ok: true, status: res.status, data: json.data ?? json };
        }
        return {
            ok: false,
            status: res.status,
            error: json.error || { message: "Lỗi " + res.status },
        };
    }

    /* -------- Toast -------- */
    function _ensureContainer() {
        let c = document.getElementById("toast-container");
        if (!c) {
            c = document.createElement("div");
            c.id = "toast-container";
            document.body.appendChild(c);
        }
        return c;
    }

    function showToast(message, type) {
        // type: 'success' | 'danger' | 'warning' | '' (default dark)
        const container = _ensureContainer();
        const el = document.createElement("div");
        el.className = "toast-item" + (type ? " toast-" + type : "");
        el.textContent = message;
        container.appendChild(el);
        setTimeout(() => {
            el.style.opacity = "0";
            el.style.transition = "opacity 0.3s";
            setTimeout(() => el.remove(), 320);
        }, 4000);
    }

    /* -------- Export -------- */
    global.apiFetch = apiFetch;
    global.showToast = showToast;
})(window);