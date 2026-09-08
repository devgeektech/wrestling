from django.contrib.auth.base_user import BaseUserManager
from django.utils.translation import gettext_lazy as _


class CustomUserManager(BaseUserManager):
    """
    Custom user manager — email is the unique identifier.
    No staff / superuser concepts; roles are COACH or STUDENT only.
    """

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_('The Email field must be set'))
        email = self.normalize_email(email)
        extra_fields.setdefault('is_active', True)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_coach(self, email, password=None, **extra_fields):
        """Create a coach user (used by seed command / future coach registration)."""
        extra_fields['role'] = 'COACH'
        return self.create_user(email, password, **extra_fields)

    def create_student(self, email, password=None, **extra_fields):
        """Create a student user."""
        extra_fields['role'] = 'STUDENT'
        return self.create_user(email, password, **extra_fields)
