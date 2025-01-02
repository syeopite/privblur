import sys
import gettext
import typing
import functools

import sanic
import babel
import babel.dates
import npf_renderer

from .i18n_data import LOCALE_DATA


class NPFRendererGettextFallback(gettext.NullTranslations):
    def gettext(self, message):
        return npf_renderer.DEFAULT_LOCALIZATION[message]

    def ngettext(self, msgid1: str, msgid2: str, n: int) -> str:
        return npf_renderer.DEFAULT_LOCALIZATION[msgid1]


class NPFRendererLocalizer:
    def __init__(self, language, locale):
        self.language = language
        self.locale = locale

        self.format_functions = {
            "format_duration_func": functools.partial(babel.dates.format_timedelta, threshold=1.1, locale=language),
            "format_datetime_func": functools.partial(babel.dates.format_datetime, format=f"short", locale=language),
        }

    def __getitem__(self, key : str):
        # Starts with format_
        if key[:7] == "format_":
            return self.format_functions[key]
        # Starts with plural_
        elif key[:7] == "plural_":
            return lambda number : translate(self.language, key[7:], number, priviblur_translations=False)

        translate("en_US", "poll_remaining_time", priviblur_translations=False)

        return translate(self.language, key, priviblur_translations=False)


class Language:
    """Stores metadata about supported translations"""
    def __init__(self, locale, priviblur_gettext, npf_renderer_gettext) -> None:
        self.locale = locale

        self.babel_locale = babel.Locale.parse(locale)

        self.priviblur_translations = priviblur_gettext

        self.npf_renderer_translations = npf_renderer_gettext
        self.npf_renderer_localizer = NPFRendererLocalizer(locale, self.babel_locale)

        self.name, self.translation_percentage = LOCALE_DATA[locale]

SUPPORTED_LANGUAGES = [
    "en_US", "cs_CZ", "fr", "ja", "uk", "zh_Hans", "zh_Hant", "es"
]

SUPPORTED_LANGUAGES.sort()


def initialize_locales() -> typing.Mapping[str, Language]:
    """Initializes locales into GNUTranslations instances"""
    try:
        # Initialize english locale first so that we may use it as a fallback

        priviblur_english_instance = gettext.translation("priviblur", localedir="locales", languages=("en_US",))

        npf_renderer_english_instance = gettext.translation("npf_renderer", localedir="locales", languages=("en_US",))
        npf_renderer_english_instance.add_fallback(NPFRendererGettextFallback())

        languages = {
            "en_US": Language("en_US", priviblur_english_instance, npf_renderer_english_instance)
        }

        for locale in SUPPORTED_LANGUAGES:
            if locale == "en_US":
                continue

            instance = gettext.translation("priviblur", localedir="locales", languages=(locale,))
            instance.add_fallback(priviblur_english_instance)

            try:
                npf_renderer_instance = gettext.translation("npf_renderer", localedir="locales", languages=(locale,))
            except FileNotFoundError:
                npf_renderer_instance = npf_renderer_english_instance

            languages[locale] = Language(locale, instance, npf_renderer_instance)
    except FileNotFoundError as e:
        print(
            'Error: Unable to find locale files. '
            'Did you forget to compile them?'
        )

        sys.exit()
    except Exception as e:
        raise e

    return languages


def translate(language : str, id : str, number : int | float | None = None,
              substitution : str | dict | None = None, priviblur_translations : bool = True) -> str:
    app = sanic.Sanic.get_app("Priviblur")

    if priviblur_translations:
        gettext_instance = app.ctx.LANGUAGES[language].priviblur_translations
    else:
        gettext_instance = app.ctx.LANGUAGES[language].npf_renderer_translations

    if number is not None:
        translated = gettext_instance.ngettext(id, f"{id}_plural", number)
    else:
        translated = gettext_instance.gettext(id)

    if isinstance(substitution, str):
        translated = translated.format(substitution)
    elif isinstance(substitution, dict):
        translated = translated.format(**substitution)

    return translated
