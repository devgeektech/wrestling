from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase
from accounts.models import User
from accounts.throttles import AuthAnonRateThrottle, AuthUserRateThrottle


@override_settings(DEBUG=True)
class AuthenticationTests(APITestCase):
    def setUp(self):
        AuthAnonRateThrottle.rate = '10000/minute'
        AuthUserRateThrottle.rate = '10000/minute'

        self.coach_password = "CoachPassword123!"
        self.coach = User.objects.create_user(
            email="coach@example.com",
            password=self.coach_password,
            first_name="John",
            last_name="Coach",
            role=User.Roles.COACH,
        )

        self.student_password = "StudentPassword123!"
        self.student = User.objects.create_user(
            email="student@example.com",
            password=self.student_password,
            first_name="Rahul",
            last_name="Sharma",
            role=User.Roles.STUDENT,
            coach_assigned=self.coach,
        )

        self.login_url = reverse('login')
        self.register_url = reverse('register')
        self.profile_url = reverse('profile')
        self.change_password_url = reverse('change-password')
        self.token_refresh_url = reverse('token-refresh')

    def test_student_registration_success(self):
        payload = {
            "first_name": "Amit",
            "last_name": "Patel",
            "email": "amit@example.com",
            "phone": "9876543211",
            "password": "StrongPassword123!",
        }
        response = self.client.post(self.register_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['email'], "amit@example.com")
        self.assertEqual(response.data['data']['role'], "STUDENT")

        new_user = User.objects.get(email="amit@example.com")
        self.assertTrue(new_user.check_password("StrongPassword123!"))
        self.assertEqual(new_user.coach_assigned, self.coach)
        self.assertEqual(new_user.coach_assigned_id, self.coach.id)

    def test_student_registration_rejects_duplicate_email(self):
        payload = {
            "first_name": "Duplicate",
            "last_name": "User",
            "email": "student@example.com",
            "password": "StrongPassword123!",
        }
        response = self.client.post(self.register_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
        self.assertIn('email', response.data['errors'])

    def test_register_ignores_role_and_creates_student(self):
        payload = {
            "first_name": "Sneaky",
            "last_name": "User",
            "email": "sneaky@example.com",
            "password": "StrongPassword123!",
            "role": "COACH",
        }
        response = self.client.post(self.register_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created_user = User.objects.get(email="sneaky@example.com")
        self.assertEqual(created_user.role, User.Roles.STUDENT)

    def test_common_login_returns_coach_role(self):
        response = self.client.post(self.login_url, {
            "email": "coach@example.com",
            "password": self.coach_password,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertIn('access', response.data['data'])
        self.assertIn('refresh', response.data['data'])
        self.assertEqual(response.data['data']['user']['role'], "COACH")

    def test_common_login_returns_student_role(self):
        response = self.client.post(self.login_url, {
            "email": "student@example.com",
            "password": self.student_password,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['user']['role'], "STUDENT")

    def test_login_invalid_password(self):
        response = self.client.post(self.login_url, {
            "email": "student@example.com",
            "password": "WrongPassword123!",
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['message'], "Invalid email or password.")

    def test_inactive_user_cannot_login(self):
        self.student.is_active = False
        self.student.save()
        response = self.client.post(self.login_url, {
            "email": "student@example.com",
            "password": self.student_password,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])

    def test_jwt_token_refresh(self):
        login_res = self.client.post(self.login_url, {
            "email": "student@example.com",
            "password": self.student_password,
        }, format='json')
        refresh_token = login_res.data['data']['refresh']

        refresh_res = self.client.post(self.token_refresh_url, {"refresh": refresh_token}, format='json')
        self.assertEqual(refresh_res.status_code, status.HTTP_200_OK)
        self.assertTrue(refresh_res.data['success'])
        self.assertIn('access', refresh_res.data['data'])

    def test_student_profile_get_and_patch(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['email'], "student@example.com")
        self.assertEqual(response.data['data']['role'], "STUDENT")
        self.assertEqual(response.data['data']['coach_id'], self.coach.id)

        patch_res = self.client.patch(self.profile_url, {
            "first_name": "Rahul",
            "last_name": "Kumar",
            "phone": "9876543210",
        }, format='json')
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.data['data']['last_name'], "Kumar")
        self.student.refresh_from_db()
        self.assertEqual(self.student.last_name, "Kumar")

    def test_coach_profile_get_and_patch(self):
        self.client.force_authenticate(user=self.coach)
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['role'], "COACH")
        self.assertIsNone(response.data['data']['coach_id'])

        patch_res = self.client.patch(self.profile_url, {
            "first_name": "Johnny",
            "phone": "1112223333",
        }, format='json')
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.coach.refresh_from_db()
        self.assertEqual(self.coach.first_name, "Johnny")

    def test_profile_cannot_change_role(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.patch(self.profile_url, {"role": "COACH"}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, User.Roles.STUDENT)

    def test_unauthenticated_cannot_access_profile(self):
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_change_password_success(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.post(self.change_password_url, {
            "old_password": self.student_password,
            "new_password": "NewStudentPassword123!",
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password("NewStudentPassword123!"))

    def test_change_password_invalid_old(self):
        self.client.force_authenticate(user=self.coach)
        response = self.client.post(self.change_password_url, {
            "old_password": "WrongOldPassword123!",
            "new_password": "NewCoachPassword123!",
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])

    def test_profile_image_upload_via_profile_patch(self):
        self.client.force_authenticate(user=self.student)
        small_gif = (
            b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff'
            b'\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00'
            b'\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b'
        )
        avatar = SimpleUploadedFile("avatar.gif", small_gif, content_type="image/gif")
        response = self.client.patch(
            self.profile_url,
            {'profile_image': avatar, 'first_name': 'Rahul'},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['first_name'], 'Rahul')
        self.assertIn('/media/profile_images/', response.data['data']['profile_image'])

        get_res = self.client.get(self.profile_url)
        self.assertEqual(get_res.status_code, status.HTTP_200_OK)
        self.assertIn('/media/profile_images/', get_res.data['data']['profile_image'])

        self.student.refresh_from_db()
        self.assertTrue(bool(self.student.profile_image))

    def test_coach_forgot_and_reset_password(self):
        forgot_url = reverse('forgot-password')
        reset_url = reverse('reset-password')

        forgot_res = self.client.post(forgot_url, {"email": "coach@example.com"}, format='json')
        self.assertEqual(forgot_res.status_code, status.HTTP_200_OK)
        self.assertTrue(forgot_res.data['success'])

        if forgot_res.data.get('data'):
            uid = forgot_res.data['data']['uid']
            token = forgot_res.data['data']['token']
        else:
            uid = urlsafe_base64_encode(force_bytes(self.coach.pk))
            token = default_token_generator.make_token(self.coach)

        new_password = "ResetCoachPassword123!"
        reset_res = self.client.post(reset_url, {
            "uid": uid,
            "token": token,
            "new_password": new_password,
        }, format='json')
        self.assertEqual(reset_res.status_code, status.HTTP_200_OK)

        self.coach.refresh_from_db()
        self.assertTrue(self.coach.check_password(new_password))

        login_res = self.client.post(self.login_url, {
            "email": "coach@example.com",
            "password": new_password,
        }, format='json')
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)
        self.assertEqual(login_res.data['data']['user']['role'], "COACH")

        # Token cannot be reused after successful reset
        reuse_res = self.client.post(reset_url, {
            "uid": uid,
            "token": token,
            "new_password": "AnotherPassword123!",
        }, format='json')
        self.assertEqual(reuse_res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_student_forgot_and_reset_password(self):
        forgot_url = reverse('forgot-password')
        reset_url = reverse('reset-password')

        forgot_res = self.client.post(forgot_url, {"email": "student@example.com"}, format='json')
        self.assertEqual(forgot_res.status_code, status.HTTP_200_OK)
        self.assertTrue(forgot_res.data['success'])

        if forgot_res.data.get('data'):
            uid = forgot_res.data['data']['uid']
            token = forgot_res.data['data']['token']
        else:
            uid = urlsafe_base64_encode(force_bytes(self.student.pk))
            token = default_token_generator.make_token(self.student)

        new_password = "ResetStudentPassword123!"
        reset_res = self.client.post(reset_url, {
            "uid": uid,
            "token": token,
            "new_password": new_password,
        }, format='json')
        self.assertEqual(reset_res.status_code, status.HTTP_200_OK)

        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password(new_password))

        login_res = self.client.post(self.login_url, {
            "email": "student@example.com",
            "password": new_password,
        }, format='json')
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)
        self.assertEqual(login_res.data['data']['user']['role'], "STUDENT")

    def test_forgot_password_unknown_email_still_ok(self):
        forgot_url = reverse('forgot-password')
        response = self.client.post(forgot_url, {"email": "unknown@example.com"}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertNotIn('data', response.data)

    def test_reset_password_invalid_token_fails(self):
        reset_url = reverse('reset-password')
        uid = urlsafe_base64_encode(force_bytes(self.student.pk))
        response = self.client.post(reset_url, {
            "uid": uid,
            "token": "invalid-token-value",
            "new_password": "ValidNewPassword123!",
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
