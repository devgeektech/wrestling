from django.core.files.uploadedfile import SimpleUploadedFile
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from unittest.mock import patch
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from accounts.throttles import AuthAnonRateThrottle, AuthUserRateThrottle
from students.models import WrestlingVideo
from students.tests.ai_fixtures import mock_gemini_analysis_report


@override_settings(AI_ANALYSIS_SYNC=True, GEMINI_API_KEY='test-key')
@patch('students.services.ai_pipeline.capture_frame_jpeg', return_value=None)
@patch(
    'students.services.ai_pipeline.analyze_wrestling_video',
    side_effect=lambda path: mock_gemini_analysis_report(),
)
class CoachVideoReviewTests(APITestCase):
    def setUp(self):
        AuthAnonRateThrottle.rate = '10000/minute'
        AuthUserRateThrottle.rate = '10000/minute'

        self.coach = User.objects.create_user(
            email="coach@example.com",
            password="CoachPassword123!",
            first_name="John",
            last_name="Coach",
            role=User.Roles.COACH,
        )
        self.other_coach = User.objects.create_user(
            email="othercoach@example.com",
            password="CoachPassword123!",
            first_name="Other",
            last_name="Coach",
            role=User.Roles.COACH,
        )
        self.student = User.objects.create_user(
            email="student@example.com",
            password="StudentPassword123!",
            first_name="Rahul",
            last_name="Sharma",
            role=User.Roles.STUDENT,
            coach_assigned=self.coach,
        )

        self.upload_url = reverse('student-video-upload')
        self.videos_url = reverse('video-list')
        self.users_url = reverse('coach-user-list')

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_coach_lists_assigned_students_only(self, _mock_gemini, _mock_capture):
        self._auth(self.coach)
        response = self.client.get(self.users_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']), 1)
        self.assertEqual(response.data['data'][0]['email'], self.student.email)

    def test_other_coach_sees_only_own_students(self, _mock_gemini, _mock_capture):
        self._auth(self.other_coach)
        response = self.client.get(self.users_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data'], [])

    def _upload(self, title='Clip'):
        self._auth(self.student)
        res = self.client.post(
            self.upload_url,
            {
                'video': SimpleUploadedFile('c.mp4', b'\x00\x00\x00\x18ftypmp42', content_type='video/mp4'),
                'title': title,
                'notes_to_coach': 'Check this',
            },
            format='multipart',
        )
        return res.data['data']['id']

    def test_student_forbidden_on_coach_review(self, _mock_gemini, _mock_capture):
        video_id = self._upload('Student cannot review')
        self._auth(self.student)
        response = self.client.post(
            reverse('coach-video-review', kwargs={'video_id': video_id}),
            {'action': 'approve'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_coach_lists_pending_with_analysis(self, _mock_gemini, _mock_capture):
        video_id = self._upload('Pending Clip')
        self._auth(self.coach)
        response = self.client.get(self.videos_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']), 1)
        row = response.data['data'][0]
        self.assertEqual(row['id'], video_id)
        self.assertEqual(row['coach_review_status'], WrestlingVideo.CoachReviewStatus.PENDING)
        self.assertTrue(row['analysis_ready'])
        self.assertIsNotNone(row['analysis'])
        self.assertEqual(
            row['analysis']['match_analysis']['event_type'],
            'Folkstyle Wrestling / Freestyle Practice Sparring',
        )
        self.assertEqual(row['analysis']['match_analysis']['match_duration'], '05:18')
        self.assertEqual(len(row['analysis']['frames']), 3)
        frame = row['analysis']['frames'][-1]
        self.assertEqual(frame['timestamp'], '00:41')
        self.assertIn('Low Ankle Pick', frame['phase'])
        self.assertIn('wrestler_blue', frame['technical_evaluation'])
        self.assertIn('wrestler_red', frame['technical_evaluation'])

        detail = self.client.get(reverse('video-detail', kwargs={'video_id': video_id}))
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data['data']['notes_to_coach'], 'Check this')
        self.assertEqual(len(detail.data['data']['analysis']['frames']), 3)

    def test_coach_search_by_title_and_student_name(self, _mock_gemini, _mock_capture):
        self._upload('Ankle Pick')
        self._upload('Sprawl')

        self._auth(self.coach)
        by_title = self.client.get(self.videos_url, {'q': 'ankle'})
        self.assertEqual(by_title.status_code, status.HTTP_200_OK)
        self.assertEqual([row['title'] for row in by_title.data['data']], ['Ankle Pick'])

        by_student = self.client.get(self.videos_url, {'q': 'rahul'})
        self.assertEqual(by_student.status_code, status.HTTP_200_OK)
        self.assertEqual(len(by_student.data['data']), 2)

        empty = self.client.get(self.videos_url, {'q': 'zzz'})
        self.assertEqual(empty.data['data'], [])

        # Default review_status=PENDING still applies with q; approved video excluded
        video_id = self._upload('Pending Keep')
        self._auth(self.coach)
        self.client.post(
            reverse('coach-video-review', kwargs={'video_id': video_id}),
            {'action': 'approve'},
            format='json',
        )
        pending_search = self.client.get(self.videos_url, {'q': 'Pending Keep'})
        self.assertEqual(pending_search.data['data'], [])
        all_search = self.client.get(
            self.videos_url, {'review_status': 'ALL', 'q': 'Pending Keep'}
        )
        self.assertEqual(len(all_search.data['data']), 1)
        self.assertEqual(all_search.data['data'][0]['title'], 'Pending Keep')

    def test_coach_approve_and_reject(self, _mock_gemini, _mock_capture):
        video_id = self._upload('Approve Me')
        self._auth(self.coach)
        mail.outbox.clear()
        with patch('coaches.views.notify_video_approved') as mock_approved:
            approve = self.client.post(
                reverse('coach-video-review', kwargs={'video_id': video_id}),
                {'action': 'approve', 'comment': 'Good'},
                format='json',
            )
            self.assertEqual(approve.status_code, status.HTTP_200_OK)
            self.assertEqual(approve.data['data']['status'], WrestlingVideo.Status.APPROVED)
            mock_approved.assert_called_once()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.student.email])
        self.assertIn('Approved', mail.outbox[0].subject)
        self.assertIn('Approve Me', mail.outbox[0].body)
        self.assertIn('Good', mail.outbox[0].body)

        video_id2 = self._upload('Reject Me')
        self._auth(self.coach)
        mail.outbox.clear()
        with patch('coaches.views.notify_video_approved') as mock_approved:
            reject = self.client.post(
                reverse('coach-video-review', kwargs={'video_id': video_id2}),
                {'action': 'reject', 'comment': 'Re-shoot'},
                format='json',
            )
            self.assertEqual(reject.status_code, status.HTTP_200_OK)
            self.assertEqual(reject.data['data']['status'], WrestlingVideo.Status.REJECTED)
            mock_approved.assert_not_called()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.student.email])
        self.assertIn('Rejected', mail.outbox[0].subject)
        self.assertIn('Reject Me', mail.outbox[0].body)
        self.assertIn('Re-shoot', mail.outbox[0].body)

        self._auth(self.student)
        detail = self.client.get(reverse('video-detail', kwargs={'video_id': video_id2}))
        self.assertEqual(detail.data['data']['status'], WrestlingVideo.Status.REJECTED)
        self.assertIsNone(detail.data['data']['analysis'])

    def test_other_coach_cannot_access(self, _mock_gemini, _mock_capture):
        video_id = self._upload('Private to coach')
        self._auth(self.other_coach)
        detail = self.client.get(reverse('video-detail', kwargs={'video_id': video_id}))
        self.assertEqual(detail.status_code, status.HTTP_404_NOT_FOUND)
        review = self.client.post(
            reverse('coach-video-review', kwargs={'video_id': video_id}),
            {'action': 'approve'},
            format='json',
        )
        self.assertEqual(review.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_review_twice(self, _mock_gemini, _mock_capture):
        video_id = self._upload('Once')
        self._auth(self.coach)
        self.client.post(
            reverse('coach-video-review', kwargs={'video_id': video_id}),
            {'action': 'approve'},
            format='json',
        )
        again = self.client.post(
            reverse('coach-video-review', kwargs={'video_id': video_id}),
            {'action': 'reject'},
            format='json',
        )
        self.assertEqual(again.status_code, status.HTTP_400_BAD_REQUEST)

    def test_coach_can_edit_frame_and_comment(self, _mock_gemini, _mock_capture):
        video_id = self._upload('Edit Frames')
        self._auth(self.coach)
        detail = self.client.get(reverse('video-detail', kwargs={'video_id': video_id}))
        frame_id = detail.data['data']['analysis']['frames'][0]['id']

        patch_res = self.client.patch(
            reverse('coach-frame-update', kwargs={'video_id': video_id, 'frame_id': frame_id}),
            {
                'phase': 'Edited Phase Name',
                'coaching_prescription': 'Focus on level change next time.',
                'visual_description': 'Updated description from coach.',
            },
            format='json',
        )
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.data['data']['phase'], 'Edited Phase Name')
        self.assertEqual(
            patch_res.data['data']['coaching_prescription'],
            'Focus on level change next time.',
        )
        self.assertNotIn('coach_comment', patch_res.data['data'])
        self.assertIsNotNone(patch_res.data['data']['coach_edited_at'])

    def test_coach_edit_and_delete_frame_comment(self, _mock_gemini, _mock_capture):
        video_id = self._upload('Comment Only')
        self._auth(self.coach)
        detail = self.client.get(reverse('video-detail', kwargs={'video_id': video_id}))
        frame_id = detail.data['data']['analysis']['frames'][0]['id']
        comment_url = reverse(
            'coach-frame-comment', kwargs={'video_id': video_id, 'frame_id': frame_id}
        )

        edit = self.client.patch(
            comment_url,
            {'coaching_prescription': 'Keep hips down.'},
            format='json',
        )
        self.assertEqual(edit.status_code, status.HTTP_200_OK)
        self.assertEqual(edit.data['data']['coaching_prescription'], 'Keep hips down.')
        self.assertIsNotNone(edit.data['data']['coach_edited_at'])

        cleared = self.client.delete(comment_url)
        self.assertEqual(cleared.status_code, status.HTTP_200_OK)
        self.assertEqual(cleared.data['data']['coaching_prescription'], '')
        self.assertIsNotNone(cleared.data['data']['coach_edited_at'])

        self._auth(self.student)
        student_res = self.client.patch(
            comment_url, {'coaching_prescription': 'Nope'}, format='json'
        )
        self.assertEqual(student_res.status_code, status.HTTP_403_FORBIDDEN)

        self._auth(self.other_coach)
        other = self.client.patch(
            comment_url, {'coaching_prescription': 'Nope'}, format='json'
        )
        self.assertEqual(other.status_code, status.HTTP_404_NOT_FOUND)

        self._auth(self.coach)
        self.client.post(
            reverse('coach-video-review', kwargs={'video_id': video_id}),
            {'action': 'approve'},
            format='json',
        )
        locked = self.client.patch(
            comment_url, {'coaching_prescription': 'Too late'}, format='json'
        )
        self.assertEqual(locked.status_code, status.HTTP_400_BAD_REQUEST)
        locked_del = self.client.delete(comment_url)
        self.assertEqual(locked_del.status_code, status.HTTP_400_BAD_REQUEST)
