"""Centralized user-facing translations."""
from .uz import STRINGS as UZ
from .ru import STRINGS as RU

SUPPORTED_LANGUAGES = {"uz": UZ, "ru": RU}


def normalize_language(language: str | None) -> str:
    return language if language in SUPPORTED_LANGUAGES else "uz"


def t(language: str | None, key: str, **kwargs) -> str:
    lang = normalize_language(language)
    template = SUPPORTED_LANGUAGES[lang].get(key, UZ.get(key, key))
    return template.format(**kwargs)
