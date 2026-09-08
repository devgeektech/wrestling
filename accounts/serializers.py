from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import serializers

from accounts.models import User


class UserSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'email', 'role', 'first_name', 'last_name')


class LoginSerializer(serializers.Serializer):
    """
    Common login — mobile sends email + password only.
    Backend resolves COACH vs STUDENT from the database.
    """

    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, required=True)

    def validate(self, attrs):
        email = attrs.get('email', '').strip().lower()
        password = attrs.get('password', '')

        if not email or not password:
            raise serializers.ValidationError("Invalid email or password.")

        user = authenticate(request=self.context.get('request'), email=email, password=password)

        if not user or not user.is_active:
            raise serializers.ValidationError("Invalid email or password.")

        if user.role not in (User.Roles.COACH, User.Roles.STUDENT):
            raise serializers.ValidationError("Invalid email or password.")

        attrs['user'] = user
        return attrs


class RegisterSerializer(serializers.ModelSerializer):
    """
    Public registration creates STUDENT accounts only.
    Coach self-registration remains disabled / seed-only for now.
    """

    password = serializers.CharField(write_only=True, required=True)
    phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = User
        fields = ('id', 'email', 'first_name', 'last_name', 'phone', 'password', 'role')
        read_only_fields = ('id', 'role')

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError("A user with this email address already exists.")
        return email

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value

    def create(self, validated_data):
        password = validated_data.pop('password')
        validated_data.pop('role', None)

        active_coach = User.objects.filter(role=User.Roles.COACH, is_active=True).first()
        user = User.objects.create_user(
            password=password,
            role=User.Roles.STUDENT,
            coach_assigned=active_coach,
            **validated_data,
        )
        return user


class CoachRegisterSerializer(serializers.ModelSerializer):
    """
    Ready for future public coach registration.
    Not wired to any public URL while ALLOW_COACH_REGISTRATION is False.
    """

    password = serializers.CharField(write_only=True, required=True)
    phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = User
        fields = ('id', 'email', 'first_name', 'last_name', 'phone', 'password', 'role')
        read_only_fields = ('id', 'role')

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError("A user with this email address already exists.")
        return email

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value

    def create(self, validated_data):
        if not getattr(settings, 'ALLOW_COACH_REGISTRATION', False):
            raise serializers.ValidationError("Coach registration is not enabled.")

        password = validated_data.pop('password')
        validated_data.pop('role', None)
        return User.objects.create_user(
            password=password,
            role=User.Roles.COACH,
            coach_assigned=None,
            **validated_data,
        )


class UserProfileSerializer(serializers.ModelSerializer):
    coach_id = serializers.IntegerField(source='coach_assigned_id', read_only=True, allow_null=True)
    profile_image = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = User
        fields = (
            'id', 'email', 'first_name', 'last_name', 'phone',
            'profile_image', 'role', 'coach_id',
        )
        read_only_fields = ('id', 'email', 'role', 'coach_id')

    def validate(self, attrs):
        attrs.pop('role', None)
        attrs.pop('id', None)
        attrs.pop('email', None)
        attrs.pop('coach_assigned', None)
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if instance.profile_image and request:
            data['profile_image'] = request.build_absolute_uri(instance.profile_image.url)
        elif instance.profile_image:
            data['profile_image'] = instance.profile_image.url
        else:
            data['profile_image'] = None
        return data


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Incorrect old password.")
        return value

    def validate_new_password(self, value):
        user = self.context['request'].user
        if user.check_password(value):
            raise serializers.ValidationError("New password cannot be the same as the current password.")
        try:
            validate_password(value, user=user)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value

    def save(self, **kwargs):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save(update_fields=['password', 'updated_at'])
        return user


class ForgotPasswordSerializer(serializers.Serializer):
    """Common forgot-password for COACH and STUDENT (email only)."""

    email = serializers.EmailField(required=True)

    def validate(self, attrs):
        email = attrs.get('email', '').strip().lower()
        attrs['email'] = email
        user = User.objects.filter(
            email=email,
            is_active=True,
            role__in=[User.Roles.COACH, User.Roles.STUDENT],
        ).first()
        attrs['user'] = user
        return attrs

    def save(self, **kwargs):
        user = self.validated_data.get('user')
        if not user:
            return None

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        return {'uid': uid, 'token': token, 'email': user.email}


class ResetPasswordSerializer(serializers.Serializer):
    """Common reset-password — token expires by timeout and after successful use."""

    uid = serializers.CharField(required=True)
    token = serializers.CharField(required=True)
    new_password = serializers.CharField(write_only=True, required=True)

    def validate_new_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value

    def validate(self, attrs):
        try:
            uid = force_str(urlsafe_base64_decode(attrs['uid']))
            user = User.objects.get(
                pk=uid,
                is_active=True,
                role__in=[User.Roles.COACH, User.Roles.STUDENT],
            )
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError("Invalid or expired reset link.")

        if not default_token_generator.check_token(user, attrs['token']):
            raise serializers.ValidationError("Invalid or expired reset link.")

        attrs['user'] = user
        return attrs

    def save(self, **kwargs):
        user = self.validated_data['user']
        user.set_password(self.validated_data['new_password'])
        user.save(update_fields=['password', 'updated_at'])
        return user
