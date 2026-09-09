from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AppSettingsIn(BaseModel):
    source_language: str = "English"
    target_language: str = "Arabic"
    style: str = "Academic"
    domain: str = "General"
    chunk_target_chars: int = 4000
    use_global_dictionary: bool = True
    use_domain_dictionary: bool = True
    use_custom_dictionary: bool = True
    use_translation_memory: bool = True


class AppSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_language: str
    target_language: str
    style: str
    domain: str
    chunk_target_chars: int
    use_global_dictionary: bool
    use_domain_dictionary: bool
    use_custom_dictionary: bool
    use_translation_memory: bool
