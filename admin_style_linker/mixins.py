import json
from typing import Any, Dict, List, Optional, Set, Tuple

from django import forms
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models

try:
    from modeltranslation.settings import AVAILABLE_LANGUAGES, DEFAULT_LANGUAGE
    from modeltranslation.translator import translator
    from modeltranslation.utils import build_localized_fieldname

    MODELTRANSLATION_INSTALLED = True
except ImportError:
    MODELTRANSLATION_INSTALLED = False

try:
    from django_monaco_editor import MonacoField
    from tinymce.models import HTMLField
except ImportError:
    raise ImproperlyConfigured("django_admin_monaco_editor or django_tinymce is not installed")


class LinkStyleAdminMixin:
    """
    A mixin for ModelAdmin to link a CSS editor field (e.g., Monaco)
    with an HTML editor field (e.g., TinyMCE) for a live preview.

    Usage:
    - In your ModelAdmin, inherit from this mixin.
    - Define a `link_styles` attribute as a list of dictionaries, where each dictionary
      is {'styles_field': 'style_field_name', 'html_fields': ['html_field_name_1', 'html_field_name_2']}.

    Example:
    class MyModelAdmin(LinkStyleAdminMixin, admin.ModelAdmin):
        link_styles = [
            {
                'styles_field': 'monaco_field',
                'html_fields': ['tinyMCE_field', 'tinyMCE_field_2'],
            },
            {
                'styles_field': 'monaco_field_2',
                'html_fields': ['tinyMCE_field_3'],
            },
        ]
    """

    link_styles: List[Dict[str, Any]] = []

    def get_form(self, request, obj=None, **kwargs):
        """
        Orchestrates the process of linking style and HTML fields.
        """
        form = super().get_form(request, obj, **kwargs)

        if not self.link_styles:
            return form

        # 1. Validate the user-defined configuration in `link_styles`.
        self._validate_link_styles_configuration()

        # 2. Prepare a map of actual (localized) fields to be linked.
        prepared_links_map = self._prepare_style_links_map()

        # 3. Apply the necessary data attributes to the form widgets.
        self._apply_attributes_to_widgets(form, prepared_links_map)

        return form

    def _validate_link_styles_configuration(self) -> None:
        """
        Validates that fields specified in `link_styles` exist on the model
        and have the correct field types (MonacoField, HTMLField).
        """
        translatable_fields = self._get_translatable_fields()

        for config in self.link_styles:
            style_field_name = config["styles_field"]
            html_field_names = config.get("html_fields", [])

            # Validate the styles_field
            self._validate_field(style_field_name, MonacoField, translatable_fields)

            # Validate each html_field
            for html_field_name in html_field_names:
                self._validate_field(html_field_name, HTMLField, translatable_fields)

    def _validate_field(self, field_name: str, expected_type: type, translatable_fields: Set[str]) -> None:
        """
        Helper to validate a single field's existence and type.
        """
        base_field_name = self._get_base_field_name(field_name, translatable_fields)
        try:
            field_instance = self.model._meta.get_field(base_field_name)
        except models.FieldDoesNotExist:
            raise ImproperlyConfigured(
                f"Field '{field_name}' (base: '{base_field_name}') does not exist in model {self.model.__name__}. "
                f"Check the link_styles configuration in {self.__class__.__name__}."
            )

        if not isinstance(field_instance, expected_type):
            raise ImproperlyConfigured(
                f"Field '{field_name}' (base: '{base_field_name}') in model {self.model.__name__} "
                f"must be an instance of {expected_type.__name__}, but found {type(field_instance).__name__}. "
                f"Check the link_styles configuration in {self.__class__.__name__}."
            )

    def _prepare_style_links_map(self) -> Dict[str, List[str]]:
        """
        Processes `link_styles` configuration, considering modeltranslation,
        and returns a final map of source style fields to target HTML fields.
        """
        if not MODELTRANSLATION_INSTALLED:
            # Якщо modeltranslation не встановлено, повертаємо просту мапу
            simple_map = {}
            for config in self.link_styles:
                style_field = config["styles_field"]
                html_fields = config.get("html_fields", [])
                simple_map.setdefault(style_field, []).extend(html_fields)
            return simple_map

        translation_opts = translator.get_options_for_model(self.model)
        translatable_fields = set(translation_opts.get_field_names())

        prepared_map: Dict[str, List[str]] = {}

        for config in self.link_styles:
            style_field = config["styles_field"]
            html_fields = list(config["html_fields"])

            base_style_field, style_lang = self._detect_localized_field(style_field, translatable_fields)

            is_base_translatable = style_field in translatable_fields
            is_localized = style_lang is not None

            if is_localized:
                # Case 1: The style field is already localized (e.g., 'styles_en').
                # Link it to HTML fields of the same language.
                resolved_html = []
                for html_field in html_fields:
                    base_html, html_lang = self._detect_localized_field(html_field, translatable_fields)
                    if html_lang == style_lang:
                        resolved_html.append(html_field)
                    elif html_field in translatable_fields:
                        resolved_html.append(build_localized_fieldname(html_field, style_lang))
                    elif html_lang is None:
                        resolved_html.append(html_field)

                prepared_map.setdefault(style_field, []).extend(
                    r for r in resolved_html if r not in prepared_map.get(style_field, [])
                )

            elif is_base_translatable:
                # Case 2: The style field is a base translatable field (e.g., 'styles').
                # Expand it for each language.
                for lang in AVAILABLE_LANGUAGES:
                    target_style_field = build_localized_fieldname(style_field, lang)
                    resolved_html = []
                    for html_field in html_fields:
                        base_html, html_lang = self._detect_localized_field(html_field, translatable_fields)
                        if html_lang == lang:
                            resolved_html.append(html_field)
                        elif html_field in translatable_fields:
                            resolved_html.append(build_localized_fieldname(html_field, lang))
                        elif html_lang is None and lang == DEFAULT_LANGUAGE:
                            # Non-translatable HTML fields link only to the default language style
                            resolved_html.append(html_field)

                    if resolved_html:
                        prepared_map.setdefault(target_style_field, []).extend(
                            r for r in resolved_html if r not in prepared_map.get(target_style_field, [])
                        )

            else:
                # Case 3: The style field is not translatable.
                # Link it to all localized versions of translatable HTML fields.
                resolved_html = []
                for html_field in html_fields:
                    if html_field in translatable_fields:
                        translated = translation_opts.all_fields.get(html_field, [])
                        resolved_html.extend([f.name for f in translated])
                    else:
                        resolved_html.append(html_field)

                prepared_map.setdefault(style_field, []).extend(
                    r for r in resolved_html if r not in prepared_map.get(style_field, [])
                )

        return prepared_map

    def _apply_attributes_to_widgets(self, form: forms.Form, prepared_links_map: Dict[str, List[str]]) -> None:
        """
        Applies 'data-style-source-for' and 'data-style-target-of' attributes
        to the appropriate form field widgets.
        """
        for style_field, html_fields in prepared_links_map.items():
            if style_field not in form.base_fields:
                continue

            valid_html_fields = [hf for hf in html_fields if hf in form.base_fields]
            if not valid_html_fields:
                continue

            style_widget = form.base_fields[style_field].widget
            style_widget.attrs["data-style-source-for"] = json.dumps(valid_html_fields)

            for html_field in valid_html_fields:
                html_widget = form.base_fields[html_field].widget
                html_widget.attrs["data-style-target-of"] = style_field

    def _get_base_field_name(self, field_name: str, translatable_fields: Set[str]) -> str:
        """
        Returns the base name of a field if it's localized, otherwise the name itself.
        Example: 'title_en' -> 'title'
        """
        if not MODELTRANSLATION_INSTALLED:
            return field_name
        base_field, _ = self._detect_localized_field(field_name, translatable_fields)
        return base_field

    def _detect_localized_field(self, field_name: str, translatable_fields: Set[str]) -> Tuple[str, Optional[str]]:
        """
        Checks if a field name is a localized version of a translatable field.
        Returns a tuple of (base_field_name, language_code) or (field_name, None).
        """
        if not MODELTRANSLATION_INSTALLED:
            return field_name, None
        for base in translatable_fields:
            for lang in AVAILABLE_LANGUAGES:
                if build_localized_fieldname(base, lang) == field_name:
                    return base, lang
        return field_name, None

    def _get_translatable_fields(self) -> Set[str]:
        """
        Returns a set of translatable fields for the model.
        """
        if not MODELTRANSLATION_INSTALLED:
            return set()
        return set(translator.get_options_for_model(self.model).get_field_names())

    @property
    def media(self):
        """
        Adds the JavaScript required for the live preview functionality.
        """
        original_media = super().media
        custom_js = [
            "admin_style_linker/js/live_style_preview.js",
        ]
        return original_media + forms.Media(js=custom_js)
