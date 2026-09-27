from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsCoach(BasePermission):
    """
    Allows access only to authenticated users with the COACH role.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.is_active and
            request.user.role == 'COACH'
        )


class IsStudent(BasePermission):
    """
    Allows access only to authenticated users with the STUDENT role.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.is_active and
            request.user.role == 'STUDENT'
        )


class IsCoachOrStudent(BasePermission):
    """
    Allows access to authenticated COACH or STUDENT users.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.is_active and
            getattr(request.user, 'role', None) in ('COACH', 'STUDENT')
        )


class IsOwner(BasePermission):
    """
    Object-level permission to allow users to access/modify only their own objects.
    """
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Check direct ownership on user object or object's user relation
        if hasattr(obj, 'user'):
            return obj.user == request.user
        return obj == request.user
