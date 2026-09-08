from django.contrib.auth.models import AbstractBaseUser
from django.db import models
from django.utils.translation import gettext_lazy as _

from accounts.managers import CustomUserManager


class User(AbstractBaseUser):
    """
    Custom user with email login and COACH / STUDENT roles only.

    No Django groups, permissions, is_staff, or is_superuser —
    authorization is role-based via common.permissions.
    """

    class Roles(models.TextChoices):
        COACH = 'COACH', _('Coach')
        STUDENT = 'STUDENT', _('Student')

    email = models.EmailField(_('email address'), unique=True, db_index=True)
    first_name = models.CharField(_('first name'), max_length=150)
    last_name = models.CharField(_('last name'), max_length=150)
    phone = models.CharField(_('phone number'), max_length=20, blank=True, null=True)
    profile_image = models.ImageField(upload_to='profile_images/', blank=True, null=True)

    role = models.CharField(
        max_length=10,
        choices=Roles.choices,
        default=Roles.STUDENT,
        db_index=True,
    )

    # Students point at their coach; coaches remain NULL (multi-coach ready).
    coach_assigned = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_students',
        db_column='coach_assigned_id',
        limit_choices_to={'role': 'COACH'},
    )

    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_full_name()} ({self.email}) - {self.role}"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_coach(self):
        return self.role == self.Roles.COACH

    @property
    def is_student(self):
        return self.role == self.Roles.STUDENT
