import os
import logging
from datetime import date

logger = logging.getLogger(__name__)

_supabase_client = None


def get_supabase_client():
    """Lazy-initialize Supabase client from environment variables."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_KEY')

    if not url or not key:
        logger.warning('SUPABASE_URL/SUPABASE_KEY not configured — audit logging disabled')
        return None

    try:
        from supabase import create_client
        _supabase_client = create_client(url, key)
        logger.info('Supabase client initialized')
        return _supabase_client
    except Exception as e:
        logger.error(f'Failed to initialize Supabase client: {e}')
        return None


def save_audit_log(
    period,
    schedule_data,
    metrics,
    konflikter,
    solver_status,
    antal_personal,
    duration_ms=None,
    personal_overrides=None,
    user_input=None,
    ai_reasoning=None,
):
    """
    Save an audit log entry to Supabase.

    Graceful failure: logs warning but never crashes the app.
    """
    client = get_supabase_client()
    if client is None:
        return

    try:
        # Serialize date objects in konflikter
        def serialize(obj):
            if isinstance(obj, date):
                return obj.isoformat()
            return obj

        clean_konflikter = []
        for k in (konflikter or []):
            if hasattr(k, '__dict__'):
                entry = {}
                for key, val in k.__dict__.items():
                    entry[key] = serialize(val)
                    if hasattr(val, 'value'):  # Enum
                        entry[key] = val.value
                clean_konflikter.append(entry)
            elif isinstance(k, dict):
                clean_konflikter.append(k)

        row = {
            'period': period,
            'user_input': user_input,
            'ai_reasoning': ai_reasoning,
            'personal_overrides': personal_overrides or [],
            'schedule_data': schedule_data,
            'metrics': metrics,
            'konflikter': clean_konflikter,
            'solver_status': solver_status,
            'antal_personal': antal_personal,
            'duration_ms': duration_ms,
        }

        client.table('audit_log').insert(row).execute()
        logger.info(f'Audit log saved for period {period}')

    except Exception as e:
        logger.error(f'Failed to save audit log: {e}')
