"""
Data module for schema-assistent.
Provides access to realistic hospital data.
"""

from .loader import (
    load_realistic_data,
    get_personal,
    get_bemanningsbehov,
    get_regler,
    get_avdelning,
    generate_shifts_for_period,
    get_scenario,
    clear_cache
)

__all__ = [
    'load_realistic_data',
    'get_personal',
    'get_bemanningsbehov',
    'get_regler',
    'get_avdelning',
    'generate_shifts_for_period',
    'get_scenario',
    'clear_cache'
]
