from rest_framework.views import exception_handler
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated, PermissionDenied, Throttled, ValidationError
from rest_framework.response import Response
from rest_framework import status


def custom_exception_handler(exc, context):
    """
    Custom exception handler for DRF to enforce standard error responses across all APIs.
    """
    response = exception_handler(exc, context)

    if response is not None:
        custom_data = {
            "success": False,
            "message": "An error occurred."
        }

        if isinstance(exc, ValidationError):
            custom_data["message"] = "Validation failed"
            # Format validation errors cleanly
            if isinstance(response.data, dict):
                custom_data["errors"] = response.data
            else:
                custom_data["errors"] = {"non_field_errors": response.data}
        elif isinstance(exc, (AuthenticationFailed, NotAuthenticated)):
            detail = getattr(exc, 'detail', None)
            if isinstance(detail, dict) and 'detail' in detail:
                msg = str(detail['detail'])
            elif isinstance(detail, str):
                msg = detail
            else:
                msg = "Authentication credentials were not provided or are invalid."
            
            # Map standard simplejwt errors to generic message if required
            if "No active account" in msg or "given credentials" in msg:
                msg = "Invalid email or password."

            custom_data["message"] = msg
        elif isinstance(exc, PermissionDenied):
            custom_data["message"] = getattr(exc, 'detail', "You do not have permission to perform this action.")
        elif isinstance(exc, Throttled):
            custom_data["message"] = f"Request limit exceeded. Try again in {exc.wait} seconds." if exc.wait else "Request limit exceeded."
        else:
            if isinstance(response.data, dict) and "detail" in response.data:
                custom_data["message"] = response.data["detail"]
            elif isinstance(response.data, list) and len(response.data) > 0:
                custom_data["message"] = str(response.data[0])
            else:
                custom_data["message"] = "Request failed"
                custom_data["errors"] = response.data

        response.data = custom_data
    else:
        # Handle unhandled server errors (500)
        return Response(
            {
                "success": False,
                "message": "An unexpected error occurred."
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    return response
