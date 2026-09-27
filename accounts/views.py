from django.conf import settings
from django.core.mail import send_mail
from rest_framework import status, permissions, parsers
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema, OpenApiResponse

from accounts.serializers import (
    LoginSerializer,
    RegisterSerializer,
    UserSummarySerializer,
    UserProfileSerializer,
    ChangePasswordSerializer,
    ForgotPasswordSerializer,
    ResetPasswordSerializer,
)
from accounts.throttles import AuthAnonRateThrottle, AuthUserRateThrottle
from common.email import send_student_welcome_email
from common.notifications import upsert_device_token
from common.responses import success_response, error_response


def _auth_payload(user, *, fcm_token=None, platform='unknown'):
    """JWT + user summary, plus saved/updated FCM token echo for mobile."""
    device = upsert_device_token(user, fcm_token, platform or 'unknown')
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": UserSummarySerializer(user).data,
        "fcm_token": device.token if device else None,
        "platform": device.platform if device else None,
    }


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthAnonRateThrottle]
    serializer_class = LoginSerializer

    @extend_schema(
        summary="Login",
        description=(
            "Authenticate with email and password. Backend resolves whether the account "
            "is COACH or STUDENT and returns user.role. "
            "Send the current device `fcm_token` (+ optional `platform`); it is updated "
            "and returned in the response."
        ),
        request=LoginSerializer,
        responses={
            200: OpenApiResponse(description="Login successful"),
            400: OpenApiResponse(description="Invalid credentials"),
            429: OpenApiResponse(description="Rate limit exceeded"),
        },
        tags=["Authentication - Common"]
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = serializer.validated_data['user']
            return success_response(
                "Login successful",
                _auth_payload(
                    user,
                    fcm_token=serializer.validated_data.get('fcm_token'),
                    platform=serializer.validated_data.get('platform') or 'unknown',
                ),
            )
        return error_response("Invalid email or password.")


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthAnonRateThrottle]
    serializer_class = RegisterSerializer

    @extend_schema(
        summary="Register",
        description=(
            "Register a new student account with email and password. "
            "Always creates role=STUDENT and assigns the active coach. "
            "Returns access and refresh tokens (same shape as login) so the client "
            "can authenticate immediately. "
            "Send device `fcm_token` (+ optional `platform`); it is saved and returned "
            "in the response. Coach registration is not available on this endpoint."
        ),
        request=RegisterSerializer,
        responses={
            201: OpenApiResponse(description="Student registered successfully; returns access, refresh, user, fcm_token"),
            400: OpenApiResponse(description="Validation error"),
            429: OpenApiResponse(description="Rate limit exceeded"),
        },
        tags=["Authentication - Common"]
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={'request': request})
        if serializer.is_valid():
            fcm_token = serializer.validated_data.get('fcm_token')
            platform = serializer.validated_data.get('platform') or 'unknown'
            user = serializer.save()
            send_student_welcome_email(user)
            return success_response(
                "Student registered successfully",
                _auth_payload(user, fcm_token=fcm_token, platform=platform),
                status_code=status.HTTP_201_CREATED,
            )
        return error_response("Validation failed", serializer.errors)


class ProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.JSONParser, parsers.MultiPartParser, parsers.FormParser]
    serializer_class = UserProfileSerializer

    @extend_schema(
        summary="View Profile",
        description="Retrieve profile for the authenticated user (coach or student), including profile_image URL.",
        responses={
            200: OpenApiResponse(description="Profile retrieved successfully"),
            401: OpenApiResponse(description="Unauthorized"),
        },
        tags=["Profile"]
    )
    def get(self, request, *args, **kwargs):
        serializer = self.serializer_class(request.user, context={'request': request})
        return success_response("Profile retrieved successfully", serializer.data)

    @extend_schema(
        summary="Update Profile",
        description=(
            "Update profile fields and/or profile_image for the authenticated user. "
            "Accepts JSON or multipart/form-data (use multipart when uploading an image)."
        ),
        request={
            'multipart/form-data': {
                'type': 'object',
                'properties': {
                    'first_name': {'type': 'string'},
                    'last_name': {'type': 'string'},
                    'phone': {'type': 'string'},
                    'profile_image': {
                        'type': 'string',
                        'format': 'binary',
                        'description': 'Optional profile image (JPEG, PNG, etc.)',
                    },
                },
            },
            'application/json': UserProfileSerializer,
        },
        responses={
            200: OpenApiResponse(description="Profile updated successfully"),
            400: OpenApiResponse(description="Validation error"),
            401: OpenApiResponse(description="Unauthorized"),
        },
        tags=["Profile"]
    )
    def patch(self, request, *args, **kwargs):
        serializer = self.serializer_class(
            request.user,
            data=request.data,
            partial=True,
            context={'request': request},
        )
        if serializer.is_valid():
            serializer.save()
            return success_response("Profile updated successfully", serializer.data)
        return error_response("Validation failed", serializer.errors)


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [AuthUserRateThrottle]
    serializer_class = ChangePasswordSerializer

    @extend_schema(
        summary="Change Password",
        description="Change password for the authenticated coach or student.",
        request=ChangePasswordSerializer,
        responses={
            200: OpenApiResponse(description="Password changed successfully"),
            400: OpenApiResponse(description="Invalid old password or weak new password"),
            401: OpenApiResponse(description="Unauthorized"),
        },
        tags=["Profile"]
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return success_response("Password changed successfully")
        return error_response("Validation failed", serializer.errors)


class ForgotPasswordView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthAnonRateThrottle]
    serializer_class = ForgotPasswordSerializer

    @extend_schema(
        summary="Forgot Password",
        description=(
            "Request a password reset for a coach or student account (email only). "
            "When the account exists, `data.uid` and `data.token` are returned for the mobile "
            "reset step (`POST /auth/reset-password/` with uid, token, new_password). "
            "A reset email is also sent when mail is configured. Tokens expire after 1 hour and "
            "become invalid after a successful password reset."
        ),
        request=ForgotPasswordSerializer,
        responses={
            200: OpenApiResponse(description="Reset instructions processed; data may include uid/token"),
            429: OpenApiResponse(description="Rate limit exceeded"),
        },
        tags=["Authentication - Common"]
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        reset_payload = serializer.save()

        if reset_payload:
            reset_message = (
                f"Use this link data to reset your Wrestling Guide password:\n\n"
                f"uid: {reset_payload['uid']}\n"
                f"token: {reset_payload['token']}\n\n"
                f"This link expires in 1 hour and can only be used once."
            )
            send_mail(
                subject="Wrestling Guide – Password Reset",
                message=reset_message,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@wrestlingguide.local'),
                recipient_list=[reset_payload['email']],
                fail_silently=True,
            )

        data = None
        if settings.PASSWORD_RESET_RETURN_TOKEN_IN_RESPONSE and reset_payload:
            data = {
                "uid": reset_payload["uid"],
                "token": reset_payload["token"],
            }

        return success_response(
            "If an account exists for this email, password reset instructions have been sent.",
            data=data,
        )


class ResetPasswordView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthAnonRateThrottle]
    serializer_class = ResetPasswordSerializer

    @extend_schema(
        summary="Reset Password",
        description=(
            "Reset password for a coach or student using uid and token from the forgot-password flow. "
            "After success the token cannot be reused."
        ),
        request=ResetPasswordSerializer,
        responses={
            200: OpenApiResponse(description="Password reset successfully"),
            400: OpenApiResponse(description="Invalid/expired token or weak password"),
            429: OpenApiResponse(description="Rate limit exceeded"),
        },
        tags=["Authentication - Common"]
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return success_response("Password reset successfully")
        return error_response("Validation failed", serializer.errors)


class CustomTokenRefreshView(TokenRefreshView):
    throttle_classes = [AuthAnonRateThrottle]

    @extend_schema(
        summary="Refresh JWT Access Token",
        description="Obtain a fresh access token using a valid refresh token.",
        tags=["Authentication - Common"]
    )
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            return success_response("Token refreshed successfully", response.data)
        return response
