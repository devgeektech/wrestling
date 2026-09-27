"""
Wrestling Guide AI pipeline — single module.

Flow: enqueue_analysis → run_gemini_analysis → Gemini report → save DB rows
      → ffmpeg stills → PENDING_REVIEW (or FAILED with failure_reason).
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.files import File
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# =============================================================================
# 1. Gemini prompt + JSON response schema
# =============================================================================

WRESTLING_ANALYSIS_PROMPT = """
ROLE

You are an expert wrestling video analyst and coach. Analyze the
attached video using ONLY visual evidence. Your output feeds a Python
pipeline that extracts screenshots (via ffmpeg) and stores a coaching
analysis — you never generate images yourself, only timestamps,
frame numbers, and analysis text.

GROUND TRUTH FOR THIS VIDEO (use these, don't estimate)
- Frame rate: {fps} fps
- Duration: {duration_hms} ({duration_seconds} seconds)
- frame = round(timestamp_seconds * {fps})

DYNAMIC ANALYSIS — DO NOT HARD-CODE
Determine everything from the video itself: wrestler identities and
appearance, winner, finish, match duration, techniques, number of key
moments, faults, corrections, and scores. Never assume a color implies
attacker/defender, that wrestler_1 is stronger or wins, or that a
specific technique occurred. If something isn't clearly supported by
the video, use null.

WRESTLER IDENTITY
Track two primary wrestlers as wrestler_1 and wrestler_2 (use real
names only if reliably available). Describe each by stable visual
traits (singlet/shirt color, shorts, shoes, knee sleeve, hair, gear).
Once assigned, NEVER swap identities due to camera cuts, occlusion,
scrambles, or a third person entering frame. Ignore coaches, referees,
and spectators unless they directly affect the action.

MATCH OVERVIEW
Determine event_type, match_duration, wrestler descriptions, and a
summary. Set winner and finish to null unless clearly supported.

KEY MOMENT DETECTION
Do NOT sample at fixed time intervals purely for even spacing. Instead
detect meaningful wrestling events: engagement, hand fighting, level
change, shot attempts (single/double leg, ankle pick), underhook/
overhook, body lock, throw, takedown, sprawl, go-behind, scramble,
reversal, mat return, par terre transition, breakdown, escape,
pinning situation, defensive recovery, major positional shift, a
notable mistake or a notable successful technique, and the match-
ending sequence. Skip only truly insignificant movement: walking
between engagements, idle standing with no hand fighting, camera
motion with no wrestling action, or a dead pause with no exchange.

DO NOT MERGE distinct exchanges just because they look similar. Two
separate shot attempts, two separate sprawls, or two separate
scrambles are DIFFERENT moments if separated by a reset, a break in
contact, or a change in control. Only combine sub-actions that are
part of one continuous, uninterrupted sequence.
{moment_guidance}
The final count must come from what you actually observe in THIS
video — never copy a count from habit or from a different video.
Cover the whole match chronologically; do not skip large stretches
of visible action to stay under a number.
Server hard limit: at most {max_moments} frames may ever be stored.


PER-MOMENT TIMING
For each moment provide timestamp (MM:SS), timestamp_seconds (number),
and frame (integer, computed with the fps above from real evidence —
never invent a frame number you can't justify).

SCREENSHOT FILENAME
screenshot_file = "frame_MM_SS.jpg" derived from the moment's MM:SS
(e.g. timestamp "01:24" -> "frame_01_24.jpg"). Never embed image data.

TECHNICAL ANALYSIS PER MOMENT
For each moment, determine attacker/defender (null if unclear — not
every sequence has one), and for each wrestler give: correct_actions
(only with visual evidence), faults (only with visual evidence, e.g.
"head dropped during entry", "feet became square", "lost inside
control"), and one specific, actionable correction (never generic
advice like "improve technique" — say what to change and how, e.g.
"keep the head up and drive the trail leg while maintaining chest-to-
hip connection"). Evaluate mechanics such as stance, base, balance,
posture, hand fighting, level change, penetration step, hip position,
angle creation, finishing/landing mechanics, defensive reaction, and
scrambling/recovery only where evidence supports it. Never invent
joint angles, velocities, forces, or statistics.

AI SCORE
Optional 0-100 score for the quality/importance of the technical
sequence (not who "won" it): 0-39 poor, 40-59 below average, 60-74
moderate, 75-89 strong, 90-100 excellent. Use null if evidence is
insufficient. Don't inflate.

COACHING PRESCRIPTION
One concise, useful takeaway per moment. Include both wrestlers'
corrections if both are actionable.

ORDERING
sort_order starts at 1 for the earliest moment and increases
chronologically; timestamps must also be chronological.

OUTPUT — RETURN ONLY VALID JSON, NO MARKDOWN, NO CODE FENCES, NO PROSE

{
  "match_analysis": {
    "event_type": "",
    "match_duration": "",
    "wrestlers": { "wrestler_1": "", "wrestler_2": "" },
    "winner": null,
    "finish": null,
    "summary": ""
  },
  "overall_score": null,
  "frames": [
    {
      "phase": "",
      "timestamp": "",
      "timestamp_seconds": 0,
      "frame": 0,
      "screenshot_file": "",
      "ai_score": null,
      "visual_description": "",
      "technical_evaluation": {
        "wrestler_1": { "correct_actions": [], "faults": [], "correction": "" },
        "wrestler_2": { "correct_actions": [], "faults": [], "correction": "" }
      },
      "coaching_prescription": "",
      "sort_order": 1
    }
  ]
}
""".strip()


def build_wrestling_analysis_prompt(
    max_moments: int,
    *,
    fps: float = 30.0,
    duration_seconds: float = 0.0,
    duration_hms: str | None = None,
) -> str:
    if not duration_hms:
        total = max(0, int(round(float(duration_seconds or 0))))
        minutes, secs = divmod(total, 60)
        duration_hms = f'{minutes:02d}:{secs:02d}'

    duration_seconds = float(duration_seconds or 0)

    if duration_seconds <= 0:
        moment_guidance = (
            "Duration unknown — determine the moment count purely from "
            "the content you observe; do not assume any particular number."
        )
    else:
        low = max(2, int(duration_seconds // 20))
        high = max(low + 1, int(duration_seconds // 12))
        high = min(high, int(max_moments))
        low = min(low, high)
        moment_guidance = (
            f"This video is {duration_hms} ({int(duration_seconds)}s) long. "
            f"Based on runtime alone, a plausible range for continuous "
            f"action is roughly {low}-{high} key moments. This is a "
            f"content-derived estimate, NOT a quota — go below it for "
            f"idle/dead stretches, above it (up to the hard cap) for dense, "
            f"continuous action. Never default to a small fixed number "
            f"like 5-6 out of habit if the actual content supports more."
        )

    return (
        WRESTLING_ANALYSIS_PROMPT.replace('{fps}', str(fps))
        .replace('{duration_seconds}', str(duration_seconds))
        .replace('{duration_hms}', str(duration_hms))
        .replace('{max_moments}', str(max_moments))
        .replace('{moment_guidance}', moment_guidance)
    )


_WRESTLER_EVAL_SCHEMA: dict[str, Any] = {
    'type': 'object',
    'properties': {
        'correct_actions': {
            'type': 'array',
            'items': {'type': 'string'},
        },
        'faults': {
            'type': 'array',
            'items': {'type': 'string'},
        },
        'correction': {'type': 'string'},
    },
    'required': ['correct_actions', 'faults', 'correction'],
}

# Schema Gemini must follow when returning structured JSON.
RESPONSE_SCHEMA: dict[str, Any] = {
    'type': 'object',
    'properties': {
        'match_analysis': {
            'type': 'object',
            'properties': {
                'event_type': {'type': 'string'},
                'match_duration': {'type': 'string'},
                'wrestlers': {
                    'type': 'object',
                    'properties': {
                        'wrestler_1': {'type': 'string'},
                        'wrestler_2': {'type': 'string'},
                    },
                    'required': ['wrestler_1', 'wrestler_2'],
                },
                'winner': {},
                'finish': {},
                'summary': {'type': 'string'},
            },
            'required': [
                'event_type',
                'match_duration',
                'wrestlers',
                'summary',
            ],
        },
        'overall_score': {},
        'frames': {
            'type': 'array',
            'minItems': 3,
            'items': {
                'type': 'object',
                'properties': {
                    'phase': {'type': 'string'},
                    'timestamp': {'type': 'string'},
                    'timestamp_seconds': {'type': 'number'},
                    'frame': {'type': 'integer'},
                    'screenshot_file': {'type': 'string'},
                    'ai_score': {},
                    'visual_description': {'type': 'string'},
                    'technical_evaluation': {
                        'type': 'object',
                        'properties': {
                            'wrestler_1': _WRESTLER_EVAL_SCHEMA,
                            'wrestler_2': _WRESTLER_EVAL_SCHEMA,
                            'wrestler_blue': _WRESTLER_EVAL_SCHEMA,
                            'wrestler_red': _WRESTLER_EVAL_SCHEMA,
                        },
                    },
                    'coaching_prescription': {'type': 'string'},
                    'sort_order': {'type': 'integer'},
                },
                'required': [
                    'phase',
                    'timestamp_seconds',
                    'visual_description',
                    'technical_evaluation',
                    'coaching_prescription',
                ],
            },
        },
    },
    'required': ['match_analysis', 'frames'],
}

# =============================================================================
# 2. Frame capture (ffmpeg) helpers
# =============================================================================


def probe_video(video_path: str | Path) -> dict[str, Any]:
    """
    Probe real fps, duration, and resolution with ffprobe.

    Returns dict with fps, duration_seconds, duration_hms, width, height.
    Falls back to fps=30 / duration=0 when ffprobe is unavailable.
    """
    defaults = {
        'fps': 30.0,
        'duration_seconds': 0.0,
        'duration_hms': '00:00',
        'width': None,
        'height': None,
    }
    if not shutil.which('ffprobe'):
        logger.warning('ffprobe not on PATH; using default fps=30')
        return defaults

    video_path = Path(video_path)
    if not video_path.is_file():
        return defaults

    cmd = [
        'ffprobe',
        '-v',
        'error',
        '-select_streams',
        'v:0',
        '-show_entries',
        'stream=avg_frame_rate,width,height',
        '-show_entries',
        'format=duration',
        '-of',
        'json',
        str(video_path),
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
        data = json.loads(out.stdout or '{}')
        streams = data.get('streams') or []
        stream = streams[0] if streams else {}
        duration = float((data.get('format') or {}).get('duration') or 0)
        width = stream.get('width')
        height = stream.get('height')
        rate = str(stream.get('avg_frame_rate') or '0/1')
        if '/' in rate:
            num_s, den_s = rate.split('/', 1)
            num, den = float(num_s), float(den_s)
            fps = (num / den) if den else 30.0
        else:
            fps = float(rate) if rate else 30.0
        if fps <= 0:
            fps = 30.0
        duration = max(0.0, duration)
        minutes, secs = divmod(int(duration), 60)
        return {
            'fps': round(fps, 3),
            'duration_seconds': round(duration, 2),
            'duration_hms': f'{minutes:02d}:{secs:02d}',
            'width': width,
            'height': height,
        }
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, ValueError, json.JSONDecodeError, ZeroDivisionError, IndexError):
        logger.warning('ffprobe metadata failed for %s; using defaults', video_path, exc_info=True)
        return defaults


def probe_duration_seconds(video_path: str | Path) -> float | None:
    """Read video length in seconds via ffprobe, or None if unavailable."""
    meta = probe_video(video_path)
    duration = meta.get('duration_seconds')
    if duration and float(duration) > 0:
        return float(duration)
    return None


def _clamp_timestamp(timestamp_seconds: float, duration: float | None) -> float:
    """Keep a seek time inside the video (slightly before EOF)."""
    ts = max(0.0, float(timestamp_seconds))
    if duration is None:
        return ts
    return min(ts, max(0.0, duration - 0.25))


def _run_ffmpeg_capture(video_path: Path, timestamp_seconds: float, *, accurate: bool) -> Path | None:
    """Run ffmpeg once to grab a JPEG at the given timestamp; return temp path or None."""
    out = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
    out_path = Path(out.name)
    out.close()

    if accurate:
        # -ss after -i is slower but more accurate near EOF.
        cmd = [
            'ffmpeg',
            '-y',
            '-i',
            str(video_path),
            '-ss',
            f'{timestamp_seconds:.3f}',
            '-frames:v',
            '1',
            '-q:v',
            '2',
            str(out_path),
        ]
    else:
        cmd = [
            'ffmpeg',
            '-y',
            '-ss',
            f'{timestamp_seconds:.3f}',
            '-i',
            str(video_path),
            '-frames:v',
            '1',
            '-q:v',
            '2',
            str(out_path),
        ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
        if out_path.stat().st_size <= 0:
            out_path.unlink(missing_ok=True)
            return None
        return out_path
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        logger.warning(
            'ffmpeg frame capture failed at %.2fs (accurate=%s): %s',
            timestamp_seconds,
            accurate,
            exc,
        )
        out_path.unlink(missing_ok=True)
        return None


def capture_frame_jpeg(video_path: str | Path, timestamp_seconds: float) -> Path | None:
    """
    Pull one JPEG still from the video at a timestamp.

    Clamps near EOF and retries earlier/accurate seeks if needed.
    Returns a temp file path, or None if ffmpeg is missing / fails.
    Caller must delete or move the file.
    """
    if not shutil.which('ffmpeg'):
        logger.warning('ffmpeg not on PATH; skipping frame capture')
        return None

    video_path = Path(video_path)
    if not video_path.is_file():
        logger.warning('Video missing for frame capture: %s', video_path)
        return None

    duration = probe_duration_seconds(video_path)
    ts = _clamp_timestamp(timestamp_seconds, duration)

    still = _run_ffmpeg_capture(video_path, ts, accurate=False)
    if still is not None:
        return still

    # Retry slightly earlier (helps when timestamp is at/after last keyframe).
    earlier = _clamp_timestamp(max(0.0, ts - 1.0), duration)
    if earlier != ts:
        still = _run_ffmpeg_capture(video_path, earlier, accurate=False)
        if still is not None:
            return still

    # Final attempt: accurate seek near EOF.
    return _run_ffmpeg_capture(video_path, ts, accurate=True)

# =============================================================================
# 3. Gemini call + JSON normalize helpers
# =============================================================================


def _to_decimal(value: Any, default: str = '0.00') -> Decimal:
    """Convert a score-like value to Decimal(0.01), or use default."""
    try:
        if value is None or value == '':
            return Decimal(default)
        return Decimal(str(value)).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _as_str_list(value: Any) -> list[str]:
    """Normalize Gemini list/string fields into a clean list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    return [str(value)]


def _wrestler_block(raw: Any) -> dict[str, Any]:
    """Normalize one wrestler's coaching block (correct / faults / correction)."""
    data = raw if isinstance(raw, dict) else {}
    return {
        'correct_actions': _as_str_list(data.get('correct_actions')),
        'faults': _as_str_list(data.get('faults')),
        'correction': str(data.get('correction') or '').strip(),
    }


def _format_mm_ss(seconds: float) -> str:
    """Format seconds as MM_SS for screenshot filenames."""
    total = max(0, int(round(float(seconds))))
    minutes, secs = divmod(total, 60)
    return f'{minutes:02d}_{secs:02d}'


def _parse_timestamp_seconds(item: dict[str, Any]) -> float:
    """Prefer timestamp_seconds; fall back to MM:SS `timestamp` string."""
    raw = item.get('timestamp_seconds')
    if raw is not None and raw != '':
        try:
            return max(0.0, float(raw))
        except (TypeError, ValueError):
            pass

    label = str(item.get('timestamp') or '').strip()
    if not label:
        return 0.0
    parts = label.split(':')
    try:
        if len(parts) == 2:
            minutes, secs = int(parts[0]), float(parts[1])
            return max(0.0, minutes * 60 + secs)
        if len(parts) == 3:
            hours, minutes, secs = int(parts[0]), int(parts[1]), float(parts[2])
            return max(0.0, hours * 3600 + minutes * 60 + secs)
    except (TypeError, ValueError):
        return 0.0
    return 0.0


def normalize_analysis_report(
    payload: dict[str, Any],
    *,
    max_moments: int | None = None,
    fps: float = 30.0,
) -> dict[str, Any]:
    """
    Clean/validate Gemini JSON into our canonical report shape for the DB.

    Maps wrestler_1/2 → wrestler_blue/red for the mobile API.
    Raises ValueError if required structure is missing.
    """
    if not isinstance(payload, dict):
        raise ValueError('Analysis payload must be an object')

    cap = max_moments
    if cap is None:
        cap = int(getattr(settings, 'AI_MAX_KEY_MOMENTS', 40))
    cap = max(1, min(int(cap), 40))

    ma_raw = payload.get('match_analysis')
    if not isinstance(ma_raw, dict):
        raise ValueError('match_analysis is required')

    wrestlers = ma_raw.get('wrestlers') if isinstance(ma_raw.get('wrestlers'), dict) else {}
    match_analysis = {
        'event_type': str(ma_raw.get('event_type') or '').strip() or 'Wrestling Match',
        'match_duration': str(ma_raw.get('match_duration') or '').strip() or '00:00',
        'wrestlers': {
            'wrestler_1': str(wrestlers.get('wrestler_1') or '').strip() or 'Wrestler 1',
            'wrestler_2': str(wrestlers.get('wrestler_2') or '').strip() or 'Wrestler 2',
        },
        'winner': ma_raw.get('winner'),
        'finish': ma_raw.get('finish'),
        'summary': str(ma_raw.get('summary') or '').strip(),
    }
    if match_analysis['winner'] in ('',):
        match_analysis['winner'] = None
    if match_analysis['finish'] in ('',):
        match_analysis['finish'] = None

    frames_in = payload.get('frames') or []
    if not isinstance(frames_in, list) or not frames_in:
        raise ValueError('frames must be a non-empty array')

    fps = float(fps) if fps and fps > 0 else 30.0
    normalized_frames: list[dict[str, Any]] = []

    for item in frames_in:
        if not isinstance(item, dict):
            continue
        ts = _parse_timestamp_seconds(item)

        tech = item.get('technical_evaluation') if isinstance(item.get('technical_evaluation'), dict) else {}
        blue = tech.get('wrestler_blue') or tech.get('wrestler_1') or {}
        red = tech.get('wrestler_red') or tech.get('wrestler_2') or {}

        frame_idx = item.get('frame')
        try:
            frame_idx = int(frame_idx) if frame_idx is not None else int(round(ts * fps))
        except (TypeError, ValueError):
            frame_idx = int(round(ts * fps))

        screenshot = str(item.get('screenshot_file') or '').strip()
        if not screenshot:
            screenshot = f'frame_{_format_mm_ss(ts)}.jpg'

        phase = str(item.get('phase') or '').strip() or 'Key Moment'
        ai_raw = item.get('ai_score')
        ai_score = _to_decimal(ai_raw, '70.00') if ai_raw is not None and ai_raw != '' else _to_decimal(None, '70.00')

        normalized_frames.append(
            {
                'phase': phase,
                'timestamp_seconds': ts,
                'frame': frame_idx,
                'screenshot_file': screenshot,
                'ai_score': ai_score,
                'visual_description': str(item.get('visual_description') or '').strip(),
                'technical_evaluation': {
                    'wrestler_blue': _wrestler_block(blue),
                    'wrestler_red': _wrestler_block(red),
                },
                'coaching_prescription': str(item.get('coaching_prescription') or '').strip(),
                'sort_order': 0,
            }
        )

    if not normalized_frames:
        raise ValueError('No valid frames in analysis payload')

    normalized_frames.sort(key=lambda f: f['timestamp_seconds'])
    normalized_frames = normalized_frames[:cap]
    for i, frame in enumerate(normalized_frames, start=1):
        frame['sort_order'] = i
        tech = frame['technical_evaluation']
        for side in ('wrestler_blue', 'wrestler_red'):
            block = tech.get(side) or {}
            has_notes = bool(
                block.get('correct_actions')
                or block.get('faults')
                or block.get('correction')
            )
            if not has_notes:
                logger.warning(
                    'Frame %s (%s) missing coaching notes for %s',
                    i,
                    frame.get('phase'),
                    side,
                )

    overall = payload.get('overall_score')
    if overall is None and normalized_frames:
        avg = sum(float(f['ai_score']) for f in normalized_frames) / len(normalized_frames)
        overall_score = _to_decimal(avg)
    else:
        overall_score = _to_decimal(overall, '75.00')

    return {
        'match_analysis': match_analysis,
        'overall_score': overall_score,
        'frames': normalized_frames,
    }


def _wait_for_file_active(client, uploaded, *, timeout_sec: float = 300.0):
    """Poll Gemini Files API until the uploaded video is ready (ACTIVE)."""
    deadline = time.time() + timeout_sec
    name = getattr(uploaded, 'name', None)
    state = getattr(uploaded, 'state', None)
    state_name = getattr(state, 'name', state)

    while state_name and str(state_name).upper() not in ('ACTIVE', 'STATE_UNSPECIFIED'):
        if str(state_name).upper() == 'FAILED':
            raise RuntimeError(f'Gemini file processing failed: {name}')
        if time.time() > deadline:
            raise TimeoutError(f'Timed out waiting for Gemini file ACTIVE: {name}')
        time.sleep(2)
        uploaded = client.files.get(name=name)
        state = getattr(uploaded, 'state', None)
        state_name = getattr(state, 'name', state)
    return uploaded


def analyze_wrestling_video(video_path: str | Path) -> dict[str, Any]:
    """
    Probe video metadata, upload to Gemini Flash, return normalized analysis.

    Gemini returns JSON only; ffmpeg stills are attached later in _persist_report.
    Raises on missing key, API errors, empty/invalid JSON, or no key moments.
    """
    api_key = (getattr(settings, 'GEMINI_API_KEY', None) or '').strip()
    if not api_key:
        raise RuntimeError('GEMINI_API_KEY is not configured')

    path = Path(video_path)
    if not path.is_file():
        raise FileNotFoundError(f'Video file not found: {path}')

    from google import genai
    from google.genai import types

    meta = probe_video(path)
    model = (getattr(settings, 'GEMINI_MODEL', None) or 'gemini-3.6-flash').strip()
    max_moments = int(getattr(settings, 'AI_MAX_KEY_MOMENTS', 40))
    prompt = build_wrestling_analysis_prompt(
        max_moments,
        fps=meta['fps'],
        duration_seconds=meta['duration_seconds'],
        duration_hms=meta['duration_hms'],
    )
    
    
    logger.info('Gemini moment guidance for video %s: computed from %ss duration', path.name, meta['duration_seconds'])
    print("PROMPT: =================================================", prompt)
    print("max_moments=============================================", max_moments)

    client = genai.Client(api_key=api_key)
    logger.info(
        'Gemini: uploading %s model=%s fps=%s duration=%s',
        path.name,
        model,
        meta['fps'],
        meta['duration_hms'],
    )
    uploaded = client.files.upload(file=str(path))
    uploaded = _wait_for_file_active(client, uploaded)

    try:
        response = client.models.generate_content(
            model=model,
            contents=[
                uploaded,
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_mime_type='application/json',
                response_schema=RESPONSE_SCHEMA,
                temperature=0.4,
                max_output_tokens=16384,
            ),
        )
    finally:
        try:
            if getattr(uploaded, 'name', None):
                client.files.delete(name=uploaded.name)
        except Exception:
            logger.debug('Gemini: could not delete uploaded file', exc_info=True)

    text = (getattr(response, 'text', None) or '').strip()
    if not text:
        raise RuntimeError('Gemini returned empty analysis')

    if text.startswith('```'):
        text = text.split('```', 2)[1]
        if text.lstrip().startswith('json'):
            text = text.lstrip()[4:]
        text = text.strip()

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'Gemini returned invalid JSON: {exc}') from exc

    if not isinstance(payload, dict) or not payload.get('frames'):
        raise RuntimeError('Gemini returned analysis with no key moments')

    return normalize_analysis_report(payload, max_moments=max_moments, fps=meta['fps'])

# =============================================================================
# 4. Persist report + video status helpers
# =============================================================================


def start_processing(video_id: int) -> None:
    """Mark the video as PROCESSING and clear any previous failure reason."""
    from students.models import WrestlingVideo

    WrestlingVideo.objects.filter(id=video_id).update(
        status=WrestlingVideo.Status.PROCESSING,
        failure_reason='',
    )


def _mark_failed(video_id: int, reason: str) -> None:
    """Mark the video FAILED and store a short user-facing failure_reason."""
    from students.models import WrestlingVideo

    message = str(reason).strip() or 'AI analysis failed'
    if not message.lower().startswith('ai analysis failed'):
        message = f'AI analysis failed: {message}'
    WrestlingVideo.objects.filter(id=video_id).update(
        status=WrestlingVideo.Status.FAILED,
        failure_reason=message[:500],
    )


def _video_filesystem_path(video) -> Path | None:
    """Resolve the uploaded video to a local filesystem path, if available."""
    try:
        path = Path(video.video_file.path)
        return path if path.is_file() else None
    except Exception:
        return None


@contextmanager
def _local_video_path(video):
    """Local path for analysis/ffmpeg — downloads from S3 when needed."""
    from common.storage import local_file_for_field

    with local_file_for_field(video.video_file, suffix='.mp4') as path:
        yield path


def _persist_report(
    video,
    report: dict,
    *,
    provider: str,
    raw_payload: dict | None = None,
    capture_screenshots: bool = False,
    video_path: Path | None = None,
) -> None:
    """
    Save VideoAnalysis + key-moment rows, optionally attach ffmpeg stills,
    then move the video to PENDING_REVIEW for the coach.
    """
    from students.models import AnalysisMovement, VideoAnalysis

    match_analysis = report['match_analysis']
    frames = report['frames']
    overall = report['overall_score']
    if capture_screenshots and video_path is None:
        video_path = _video_filesystem_path(video)

    payload = {
        'provider': provider,
        'video_id': video.id,
        'frame_count': len(frames),
        **(raw_payload or {}),
    }

    analysis, _ = VideoAnalysis.objects.update_or_create(
        video=video,
        defaults={
            'match_analysis': match_analysis,
            'summary': match_analysis.get('summary') or '',
            'overall_score': overall,
            'raw_payload': payload,
            'processed_at': timezone.now(),
        },
    )
    analysis.movements.all().delete()

    for frame in frames:
        movement = AnalysisMovement(
            analysis=analysis,
            phase=frame['phase'],
            movement_name=frame['phase'],
            timestamp_seconds=frame['timestamp_seconds'],
            visual_description=frame['visual_description'],
            technical_evaluation=frame['technical_evaluation'],
            ai_score=frame['ai_score'],
            ai_suggestion=frame.get('coaching_prescription') or '',
            sort_order=frame['sort_order'],
        )
        movement.save()

        if capture_screenshots and video_path and video_path.is_file():
            still = capture_frame_jpeg(video_path, frame['timestamp_seconds'])
            if still is not None:
                try:
                    name = frame.get('screenshot_file') or f"frame_{frame['sort_order']:02d}.jpg"
                    with still.open('rb') as fh:
                        movement.frame_image.save(name, File(fh), save=True)
                finally:
                    still.unlink(missing_ok=True)

    video.status = video.Status.PENDING_REVIEW
    video.coach_review_status = video.CoachReviewStatus.PENDING
    video.failure_reason = ''
    video.save(
        update_fields=[
            'status',
            'coach_review_status',
            'failure_reason',
            'updated_at',
        ]
    )


def _notify_pending(video_id: int) -> None:
    """Send FCM (if configured) that a video is ready for coach review."""
    try:
        from common.notifications import notify_video_pending_review
        from students.models import WrestlingVideo

        video = WrestlingVideo.objects.select_related('student', 'coach').get(id=video_id)
        if video.status == WrestlingVideo.Status.PENDING_REVIEW:
            notify_video_pending_review(video)
    except Exception:
        logger.exception('FCM notify pending review failed for video %s', video_id)

# =============================================================================
# 5. Public entrypoints
# =============================================================================


def run_gemini_analysis(video_id: int) -> None:
    """
    End-to-end: process one video with Gemini, save analysis, notify coach.

    On any failure, keeps the video and sets status=FAILED + failure_reason.
    """
    from students.models import WrestlingVideo

    try:
        api_key = (getattr(settings, 'GEMINI_API_KEY', '') or '').strip()
        if not api_key:
            raise RuntimeError('GEMINI_API_KEY is not configured')

        video = WrestlingVideo.objects.get(id=video_id)
        video.status = WrestlingVideo.Status.PROCESSING
        video.failure_reason = ''
        video.save(update_fields=['status', 'failure_reason', 'updated_at'])

        with _local_video_path(video) as local_path:
            if local_path is None or not local_path.is_file():
                raise FileNotFoundError('Uploaded video file is not available')

            report = analyze_wrestling_video(local_path)
            if not report.get('frames'):
                raise RuntimeError('Gemini returned no key moments')

            with transaction.atomic():
                video = WrestlingVideo.objects.select_for_update().get(id=video_id)
                _persist_report(
                    video,
                    report,
                    provider='gemini',
                    raw_payload={
                        'model': getattr(settings, 'GEMINI_MODEL', ''),
                        'report': {
                            'match_analysis': report['match_analysis'],
                            'overall_score': str(report['overall_score']),
                            'frames': [
                                {
                                    **{k: v for k, v in f.items() if k != 'ai_score'},
                                    'ai_score': str(f['ai_score']),
                                }
                                for f in report['frames']
                            ],
                        },
                    },
                    capture_screenshots=True,
                    video_path=local_path,
                )

        _notify_pending(video_id)
    except WrestlingVideo.DoesNotExist:
        logger.warning('Gemini AI: video %s not found', video_id)
    except Exception as exc:
        logger.exception('Gemini AI failed for video %s', video_id)
        _mark_failed(video_id, str(exc))


def run_analysis(video_id: int) -> None:
    """Run Gemini analysis for a video (alias used by enqueue)."""
    run_gemini_analysis(video_id)


def enqueue_analysis(video_id: int) -> None:
    """
    Start analysis for a video.

    Sync when AI_ANALYSIS_SYNC=True (tests); otherwise a background thread.
    """
    if getattr(settings, 'AI_ANALYSIS_SYNC', False):
        run_analysis(video_id)
        return

    def _worker():
        run_analysis(video_id)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
