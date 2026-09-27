"""Unit tests for Gemini analysis JSON normalizer."""

from decimal import Decimal

from django.test import SimpleTestCase, override_settings

from students.services.ai_pipeline import (
    WRESTLING_ANALYSIS_PROMPT,
    build_wrestling_analysis_prompt,
    normalize_analysis_report,
)


class BuildWrestlingPromptTests(SimpleTestCase):
    def test_prompt_build_injects_ground_truth_and_max_moments(self):
        prompt = build_wrestling_analysis_prompt(
            40,
            fps=29.97,
            duration_seconds=318.5,
            duration_hms='05:18',
        )
        self.assertIn('at most 40 frames may be stored', prompt)
        self.assertIn('29.97 fps', prompt)
        self.assertIn('05:18 (318.5 seconds)', prompt)
        self.assertNotIn('{max_moments}', prompt)
        self.assertNotIn('{fps}', prompt)
        self.assertNotIn('{duration_hms}', prompt)
        self.assertIn('"match_analysis"', prompt)
        self.assertIn('KEY MOMENT DETECTION', prompt)
        self.assertIn('Do NOT sample at fixed time intervals', prompt)
        self.assertIn('WRESTLER IDENTITY', prompt)
        self.assertIn('NEVER swap identities', prompt)
        self.assertIn('GROUND TRUTH FOR THIS VIDEO', prompt)
        self.assertIn('joint angles', prompt)
        self.assertIn('ONLY visual evidence', prompt)
        self.assertIn('{max_moments}', WRESTLING_ANALYSIS_PROMPT)
        self.assertIn('{fps}', WRESTLING_ANALYSIS_PROMPT)


class NormalizeAnalysisReportTests(SimpleTestCase):
    def test_normalizes_canonical_payload(self):
        payload = {
            'match_analysis': {
                'event_type': 'Folkstyle Practice',
                'match_duration': '01:10',
                'wrestlers': {
                    'wrestler_1': 'Blue singlet',
                    'wrestler_2': 'Red singlet',
                },
                'winner': None,
                'finish': None,
                'summary': 'A short sparring bout.',
            },
            'overall_score': 80,
            'frames': [
                {
                    'phase': 'Single Leg',
                    'timestamp_seconds': 9.5,
                    'ai_score': 71,
                    'visual_description': 'Blue shoots a single.',
                    'technical_evaluation': {
                        'wrestler_blue': {
                            'correct_actions': ['Level change'],
                            'faults': [],
                            'correction': 'Drive through.',
                        },
                        'wrestler_red': {
                            'correct_actions': ['Sprawl'],
                            'faults': ['Late hips'],
                            'correction': 'Hips back sooner.',
                        },
                    },
                    'coaching_prescription': 'Blue finish; Red sprawl earlier.',
                },
                {
                    'phase': 'Earlier Tie',
                    'timestamp_seconds': 3.0,
                    'visual_description': 'Collar tie.',
                    'technical_evaluation': {},
                },
            ],
        }
        report = normalize_analysis_report(payload, max_moments=40, fps=30)

        self.assertEqual(report['match_analysis']['event_type'], 'Folkstyle Practice')
        self.assertEqual(report['overall_score'], Decimal('80.00'))
        self.assertEqual(len(report['frames']), 2)
        self.assertEqual(report['frames'][0]['phase'], 'Earlier Tie')
        self.assertEqual(report['frames'][0]['sort_order'], 1)
        self.assertEqual(report['frames'][1]['sort_order'], 2)
        self.assertEqual(report['frames'][1]['timestamp_seconds'], 9.5)
        self.assertEqual(report['frames'][1]['frame'], int(round(9.5 * 30)))
        self.assertTrue(report['frames'][1]['screenshot_file'].endswith('.jpg'))
        self.assertIn('wrestler_blue', report['frames'][1]['technical_evaluation'])
        self.assertEqual(
            report['frames'][1]['coaching_prescription'],
            'Blue finish; Red sprawl earlier.',
        )

    def test_maps_wrestler_1_2_and_timestamp_label(self):
        payload = {
            'match_analysis': {
                'event_type': 'Practice',
                'match_duration': '00:30',
                'wrestlers': {'wrestler_1': 'A', 'wrestler_2': 'B'},
                'summary': 's',
            },
            'frames': [
                {
                    'phase': 'Shot',
                    'timestamp': '00:41',
                    'ai_score': None,
                    'visual_description': 'Level change',
                    'technical_evaluation': {
                        'wrestler_1': {
                            'correct_actions': ['Penetration'],
                            'faults': [],
                            'correction': 'Keep head up.',
                        },
                        'wrestler_2': {
                            'correct_actions': [],
                            'faults': ['Square feet'],
                            'correction': 'Stay in staggered stance.',
                        },
                    },
                    'coaching_prescription': 'Keep head up on the shot.',
                }
            ],
        }
        report = normalize_analysis_report(payload, max_moments=40, fps=30)
        frame = report['frames'][0]
        self.assertEqual(frame['timestamp_seconds'], 41.0)
        self.assertEqual(frame['ai_score'], Decimal('70.00'))
        self.assertEqual(
            frame['technical_evaluation']['wrestler_blue']['correction'],
            'Keep head up.',
        )
        self.assertEqual(
            frame['technical_evaluation']['wrestler_red']['faults'],
            ['Square feet'],
        )

    def test_caps_max_moments(self):
        frames = [
            {
                'phase': f'Moment {i}',
                'timestamp_seconds': float(i),
                'visual_description': 'x',
                'technical_evaluation': {},
            }
            for i in range(10)
        ]
        report = normalize_analysis_report(
            {
                'match_analysis': {
                    'event_type': 'Test',
                    'match_duration': '00:20',
                    'wrestlers': {'wrestler_1': 'A', 'wrestler_2': 'B'},
                    'summary': 's',
                },
                'frames': frames,
            },
            max_moments=3,
        )
        self.assertEqual(len(report['frames']), 3)
        self.assertEqual([f['sort_order'] for f in report['frames']], [1, 2, 3])

    def test_rejects_empty_frames(self):
        with self.assertRaises(ValueError):
            normalize_analysis_report(
                {
                    'match_analysis': {
                        'event_type': 'Test',
                        'match_duration': '00:01',
                        'wrestlers': {'wrestler_1': 'A', 'wrestler_2': 'B'},
                        'summary': 's',
                    },
                    'frames': [],
                }
            )

    @override_settings(AI_MAX_KEY_MOMENTS=2)
    def test_uses_settings_cap_when_not_passed(self):
        frames = [
            {
                'phase': f'Moment {i}',
                'timestamp_seconds': float(i),
                'visual_description': 'x',
                'technical_evaluation': {},
            }
            for i in range(5)
        ]
        report = normalize_analysis_report(
            {
                'match_analysis': {
                    'event_type': 'Test',
                    'match_duration': '00:10',
                    'wrestlers': {'wrestler_1': 'A', 'wrestler_2': 'B'},
                    'summary': 's',
                },
                'frames': frames,
            }
        )
        self.assertEqual(len(report['frames']), 2)
