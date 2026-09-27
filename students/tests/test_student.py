from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from unittest.mock import patch
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from accounts.throttles import AuthAnonRateThrottle, AuthUserRateThrottle
from students.models import VideoAnalysis, WrestlingVideo
from students.tests.ai_fixtures import mock_gemini_analysis_report


@override_settings(AI_ANALYSIS_SYNC=True, GEMINI_API_KEY='test-key')
@patch('students.services.ai_pipeline.capture_frame_jpeg', return_value=None)
@patch(
    'students.services.ai_pipeline.analyze_wrestling_video',
    side_effect=lambda path: mock_gemini_analysis_report(),
)
class StudentVideoApiTests(APITestCase):
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
        self.student = User.objects.create_user(
            email="student@example.com",
            password="StudentPassword123!",
            first_name="Rahul",
            last_name="Sharma",
            role=User.Roles.STUDENT,
            coach_assigned=self.coach,
        )
        self.other_student = User.objects.create_user(
            email="other@example.com",
            password="StudentPassword123!",
            first_name="Other",
            last_name="Student",
            role=User.Roles.STUDENT,
            coach_assigned=self.coach,
        )

        self.dashboard_url = reverse('student-dashboard')
        self.upload_url = reverse('student-video-upload')
        self.videos_url = reverse('video-list')

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def _sample_video(self, name='clip.mp4'):
        return SimpleUploadedFile(name, b'\x00\x00\x00\x18ftypmp42', content_type='video/mp4')

    def test_dashboard_requires_student(self, _mock_gemini, _mock_capture):
        self._auth(self.coach)
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_dashboard_returns_profile_and_stats(self, _mock_gemini, _mock_capture):
        self._auth(self.student)
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['profile']['email'], self.student.email)
        self.assertEqual(response.data['data']['stats']['total_videos'], 0)
        self.assertIn('UPLOADED', response.data['data']['stats']['by_status'])

    def test_upload_runs_gemini_to_pending_review(self, _mock_gemini, _mock_capture):
        self._auth(self.student)
        with patch('common.notifications.notify_video_pending_review') as mock_notify:
            response = self.client.post(
                self.upload_url,
                {
                    'video': self._sample_video(),
                    'title': 'Single Leg Drill',
                    'notes_to_coach': 'Please check my level change',
                },
                format='multipart',
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assertTrue(response.data['success'])
            data = response.data['data']
            self.assertEqual(data['title'], 'Single Leg Drill')
            video = WrestlingVideo.objects.get(id=data['id'])
            self.assertEqual(video.student_id, self.student.id)
            self.assertEqual(video.coach_id, self.coach.id)
            self.assertEqual(video.status, WrestlingVideo.Status.PENDING_REVIEW)
            self.assertEqual(video.coach_review_status, WrestlingVideo.CoachReviewStatus.PENDING)
            self.assertTrue(VideoAnalysis.objects.filter(video=video).exists())
            self.assertEqual(video.analysis.movements.count(), 3)
            self.assertTrue(video.analysis.movements.filter(phase__icontains='Ankle').exists())
            mock_notify.assert_called_once()

            detail = self.client.get(reverse('video-detail', kwargs={'video_id': video.id}))
            self.assertEqual(detail.status_code, status.HTTP_200_OK)
            self.assertEqual(detail.data['data']['status'], WrestlingVideo.Status.PENDING_REVIEW)
            self.assertTrue(detail.data['data']['analysis_ready'])
            self.assertIsNone(detail.data['data']['analysis'])

    def test_upload_marks_failed_when_gemini_empty(self, mock_gemini, _mock_capture):
        mock_gemini.side_effect = RuntimeError('Gemini returned empty analysis')
        self._auth(self.student)
        response = self.client.post(
            self.upload_url,
            {
                'video': self._sample_video(),
                'title': 'Empty AI',
                'notes_to_coach': '',
            },
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        video = WrestlingVideo.objects.get(id=response.data['data']['id'])
        self.assertEqual(video.status, WrestlingVideo.Status.FAILED)
        self.assertIn('empty analysis', video.failure_reason.lower())
        self.assertFalse(VideoAnalysis.objects.filter(video=video).exists())

        detail = self.client.get(reverse('video-detail', kwargs={'video_id': video.id}))
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data['data']['status'], WrestlingVideo.Status.FAILED)
        self.assertIn('empty analysis', detail.data['data']['failure_reason'].lower())
        self.assertFalse(detail.data['data']['analysis_ready'])

    def test_list_only_own_videos(self, _mock_gemini, _mock_capture):
        self._auth(self.student)
        self.client.post(
            self.upload_url,
            {'video': self._sample_video('mine.mp4'), 'title': 'Mine'},
            format='multipart',
        )
        self._auth(self.other_student)
        self.client.post(
            self.upload_url,
            {'video': self._sample_video('theirs.mp4'), 'title': 'Theirs'},
            format='multipart',
        )

        self._auth(self.student)
        response = self.client.get(self.videos_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [row['title'] for row in response.data['data']]
        self.assertEqual(titles, ['Mine'])

    def test_list_search_by_title(self, _mock_gemini, _mock_capture):
        self._auth(self.student)
        self.client.post(
            self.upload_url,
            {
                'video': self._sample_video('a.mp4'),
                'title': 'Ankle Pick Drill',
                'notes_to_coach': 'Level change',
            },
            format='multipart',
        )
        self.client.post(
            self.upload_url,
            {'video': self._sample_video('b.mp4'), 'title': 'Sprawl Defense'},
            format='multipart',
        )

        matched = self.client.get(self.videos_url, {'q': 'ankle'})
        self.assertEqual(matched.status_code, status.HTTP_200_OK)
        self.assertEqual([row['title'] for row in matched.data['data']], ['Ankle Pick Drill'])

        empty = self.client.get(self.videos_url, {'q': 'nomatch'})
        self.assertEqual(empty.status_code, status.HTTP_200_OK)
        self.assertEqual(empty.data['data'], [])

    def test_detail_for_owner(self, _mock_gemini, _mock_capture):
        self._auth(self.student)
        create = self.client.post(
            self.upload_url,
            {'video': self._sample_video(), 'title': 'Detail Clip'},
            format='multipart',
        )
        video_id = create.data['data']['id']

        detail = self.client.get(reverse('video-detail', kwargs={'video_id': video_id}))
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data['data']['title'], 'Detail Clip')
        self.assertIsNotNone(detail.data['data']['file_url'])
        self.assertIn('/media/', detail.data['data']['file_url'])
        video = WrestlingVideo.objects.get(id=video_id)
        self.assertTrue(detail.data['data']['file_url'].endswith(video.video_file.url))

    def test_other_student_cannot_access_video(self, _mock_gemini, _mock_capture):
        self._auth(self.student)
        create = self.client.post(
            self.upload_url,
            {'video': self._sample_video(), 'title': 'Private'},
            format='multipart',
        )
        video_id = create.data['data']['id']

        self._auth(self.other_student)
        detail = self.client.get(reverse('video-detail', kwargs={'video_id': video_id}))
        self.assertEqual(detail.status_code, status.HTTP_404_NOT_FOUND)

    def test_upload_rejects_bad_extension(self, _mock_gemini, _mock_capture):
        self._auth(self.student)
        bad = SimpleUploadedFile('notes.txt', b'not a video', content_type='text/plain')
        response = self.client.post(
            self.upload_url,
            {'video': bad, 'title': 'Bad'},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])

    def test_student_sees_analysis_after_coach_approve(self, _mock_gemini, _mock_capture):
        self._auth(self.student)
        create = self.client.post(
            self.upload_url,
            {'video': self._sample_video(), 'title': 'For Approve'},
            format='multipart',
        )
        video_id = create.data['data']['id']

        self._auth(self.coach)
        review = self.client.post(
            reverse('coach-video-review', kwargs={'video_id': video_id}),
            {'action': 'approve', 'comment': 'Nice work'},
            format='json',
        )
        self.assertEqual(review.status_code, status.HTTP_200_OK)

        self._auth(self.student)
        detail = self.client.get(reverse('video-detail', kwargs={'video_id': video_id}))
        self.assertEqual(detail.data['data']['status'], WrestlingVideo.Status.APPROVED)
        self.assertIsNotNone(detail.data['data']['analysis'])
        match = detail.data['data']['analysis']['match_analysis']
        self.assertEqual(match['match_duration'], '05:18')
        self.assertIn('wrestler_1', match['wrestlers'])
        self.assertEqual(len(detail.data['data']['analysis']['frames']), 3)
        frame = detail.data['data']['analysis']['frames'][-1]
        self.assertEqual(frame['timestamp'], '00:41')
        self.assertIn('wrestler_blue', frame['technical_evaluation'])
