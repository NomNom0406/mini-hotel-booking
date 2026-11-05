from flask import jsonify, request


class ApiError(Exception):
    """Lỗi nghiệp vụ/kiểm tra của API; được đổi thành {error: {code, message, fields}}."""

    def __init__(self, status, message, fields=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.fields = fields or {}


def error_response(status, message, fields=None):
    response = jsonify(error={"code": status, "message": message, "fields": fields or {}})
    return response, status


def register_error_handlers(bp):
    @bp.errorhandler(ApiError)
    def handle_api_error(e):
        return error_response(e.status, e.message, e.fields)

    # 405 và 429 là lỗi ở mức ứng dụng; chỉ đổi sang JSON cho đường dẫn /api/.
    @bp.app_errorhandler(405)
    @bp.app_errorhandler(429)
    def handle_http_error(e):
        if not request.path.startswith("/api/"):
            return e
        messages = {405: "Phương thức không được hỗ trợ.",
                    429: "Vượt giới hạn tần suất, vui lòng thử lại sau."}
        return error_response(e.code, messages.get(e.code, e.description))