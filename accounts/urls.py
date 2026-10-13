from django.urls import path
from accounts.views import (
    LoginView,
    RegisterView,
    ProfileView,
    ChangePasswordView,
    AccountDeleteView,
    ForgotPasswordView,
    ResetPasswordView,
    CustomTokenRefreshView,
    NotificationListView,
    NotificationMarkReadView,
    NotificationMarkAllReadView,
)

urlpatterns = [
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/forgot-password/', ForgotPasswordView.as_view(), name='forgot-password'),
    path('auth/reset-password/', ResetPasswordView.as_view(), name='reset-password'),
    path('auth/profile/', ProfileView.as_view(), name='profile'),
    path('auth/change-password/', ChangePasswordView.as_view(), name='change-password'),
    path('auth/account/', AccountDeleteView.as_view(), name='account-delete'),
    path('auth/token/refresh/', CustomTokenRefreshView.as_view(), name='token-refresh'),
    path('notifications/', NotificationListView.as_view(), name='notifications-list'),
    path('notifications/read-all/', NotificationMarkAllReadView.as_view(), name='notifications-read-all'),
    path(
        'notifications/<int:notification_id>/read/',
        NotificationMarkReadView.as_view(),
        name='notifications-mark-read',
    ),
]
