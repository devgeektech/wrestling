from rest_framework.renderers import JSONRenderer


class StandardJSONRenderer(JSONRenderer):
    """
    Custom DRF renderer to standardize API responses into a consistent JSON envelope format:
    {
        "success": bool,
        "message": str,
        "data": dict/list (on success),
        "errors": dict/list (on error)
    }
    """
    def render(self, data, accepted_media_type=None, renderer_context=None):
        status_code = 200
        if renderer_context and 'response' in renderer_context:
            status_code = renderer_context['response'].status_code

        if data is None:
            data = {}

        # If data is already formatted with 'success' key (e.g. from exception handler or custom view response)
        if isinstance(data, dict) and 'success' in data:
            return super().render(data, accepted_media_type=accepted_media_type, renderer_context=renderer_context)

        is_success = status_code < 400

        message = ""
        if isinstance(data, dict) and "message" in data:
            message = data.pop("message")
        else:
            message = "Operation successful" if is_success else "Request failed"

        if is_success:
            response_data = {
                "success": True,
                "message": message,
                "data": data
            }
        else:
            errors = data.get("errors", data) if isinstance(data, dict) else data
            response_data = {
                "success": False,
                "message": message,
                "errors": errors
            }

        return super().render(response_data, accepted_media_type=accepted_media_type, renderer_context=renderer_context)
