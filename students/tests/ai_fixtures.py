"""Shared Gemini mock report for API tests (no live Gemini / no stub pipeline)."""

from decimal import Decimal


def mock_gemini_analysis_report():
    """Normalized report shape expected by ai_pipeline._persist_report."""
    return {
        'match_analysis': {
            'event_type': 'Folkstyle Wrestling / Freestyle Practice Sparring',
            'match_duration': '05:18',
            'wrestlers': {
                'wrestler_1': 'Dark blue t-shirt, grey athletic shorts',
                'wrestler_2': 'White singlet with red/yellow accent trim',
            },
            'winner': None,
            'finish': None,
            'summary': (
                'Practice wrestling match featuring tie-ups, leg attacks, '
                'and mat scrambles.'
            ),
        },
        'overall_score': Decimal('78.50'),
        'frames': [
            {
                'phase': 'Setup / Tie Break',
                'timestamp_seconds': 12.0,
                'frame': 360,
                'screenshot_file': 'frame_00_12.jpg',
                'ai_score': Decimal('72.00'),
                'visual_description': 'Blue works off a collar tie toward Red.',
                'technical_evaluation': {
                    'wrestler_blue': {
                        'correct_actions': ['Clears the tie'],
                        'faults': ['Hands leave early'],
                        'correction': 'Keep head control',
                    },
                    'wrestler_red': {
                        'correct_actions': ['Strong base'],
                        'faults': ['Lead foot flat'],
                        'correction': 'Stay light on the feet',
                    },
                },
                'coaching_prescription': 'Blue keep head control; Red stay light.',
                'sort_order': 1,
            },
            {
                'phase': 'Sprawl Defense',
                'timestamp_seconds': 28.5,
                'frame': 855,
                'screenshot_file': 'frame_00_28.jpg',
                'ai_score': Decimal('81.00'),
                'visual_description': 'Red sprawls as Blue drives a single.',
                'technical_evaluation': {
                    'wrestler_blue': {
                        'correct_actions': ['Keeps driving'],
                        'faults': ['Chest lifts early'],
                        'correction': 'Stay flat under the hips',
                    },
                    'wrestler_red': {
                        'correct_actions': ['Hips drop back'],
                        'faults': ['Cross-face late'],
                        'correction': 'Cross-face earlier',
                    },
                },
                'coaching_prescription': 'Blue stay connected; Red cross-face sooner.',
                'sort_order': 2,
            },
            {
                'phase': 'Low Ankle Pick / Single Leg Attack',
                'timestamp_seconds': 41.0,
                'frame': 1230,
                'screenshot_file': 'frame_00_41.jpg',
                'ai_score': Decimal('75.00'),
                'visual_description': "Blue snatches Red's lead ankle.",
                'technical_evaluation': {
                    'wrestler_blue': {
                        'correct_actions': ['Deep level change'],
                        'faults': ['No head control'],
                        'correction': 'Pull head down over the ankle',
                    },
                    'wrestler_red': {
                        'correct_actions': ['Kicks lead leg back'],
                        'faults': ['Lead leg heavy'],
                        'correction': 'Circle off the attack',
                    },
                },
                'coaching_prescription': 'Blue needs head control on the ankle pick.',
                'sort_order': 3,
            },
        ],
    }
