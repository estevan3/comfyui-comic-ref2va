import json
import re
import unicodedata
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


DEFAULT_ANALYSIS_PROMPT = (
    "Inspect this single comic panel. Describe only visible evidence in English. "
    "Identify appearance, positions, posture, physical facial expressions, composition, "
    "environment, objects and visible action. Transcribe only clearly legible text, "
    "verbatim in its original language. An open mouth is not evidence of speech. "
    "Distinguish speech balloons from thoughts, narration, signs and sound effects. "
    "Leave uncertain balloon speakers null. Never invent dialogue, relationships, "
    "off-frame content, emotions or colors in monochrome artwork."
)


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Character(Record):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    appearance: str
    hair: str | None
    clothing: str | None
    accessories: str | None
    distinctive_features: list[str]
    position: str
    posture: str
    expression: str | None

    @field_validator("hair", "clothing", "accessories", "expression")
    @classmethod
    def absent_detail(cls, value):
        return "" if value is None or value.strip().lower() in ("null", "none", "n/a") else value


class Fact(Record):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    kind: Literal["environment", "object", "lighting", "action"]
    description: str = Field(min_length=1)


class VisibleText(Record):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    kind: Literal["speech", "thought", "caption", "sign", "sfx", "unknown"]
    text: str
    language: str
    legible: bool
    bbox: list[Annotated[float, Field(ge=0, le=1)]] = Field(min_length=4, max_length=4, description="Normalized decimal fractions in [0, 1]: left, top, right, bottom. Never pixel coordinates or 0-1000 coordinates.")
    speaker: str | None
    attribution_method: Literal["balloon_tail", "explicit_label", "uncertain"]
    attribution_evidence: str

    @model_validator(mode="after")
    def check_box(self):
        x1, y1, x2, y2 = self.bbox
        if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
            raise ValueError("text bbox must be normalized [left, top, right, bottom]")
        if self.speaker is not None and (self.kind != "speech" or self.attribution_method == "uncertain" or not self.attribution_evidence.strip()):
            raise ValueError("only speech with visible attribution evidence can have a speaker")
        if self.legible and not self.text.strip():
            raise ValueError("legible text requires an exact transcription")
        return self


class Observed(Record):
    palette: Literal["monochrome", "color", "unknown"]
    style: str = Field(min_length=1)
    composition: str = Field(min_length=1)
    characters: list[Character]
    facts: list[Fact]
    texts: list[VisibleText]


class Motion(Record):
    character_id: str | None
    evidence_id: str
    kind: Literal["hold", "blink", "settle", "continue_action"]
    description: str


class Sound(Record):
    kind: Literal["impact", "footsteps", "rain", "running_water", "fire", "wind"]
    evidence_id: str
    visual_evidence: str = Field(min_length=1)
    layer: Literal["event", "ambience"]
    timing: Literal["at_start", "during_action", "throughout"]


class Inferred(Record):
    motions: list[Motion]


class PanelAnalysis(Record):
    observed: Observed
    inferred: Inferred
    sounds: list[Sound]

    @model_validator(mode="after")
    def check_references(self):
        chars = {c.id: c for c in self.observed.characters}
        facts = {f.id: f for f in self.observed.facts}
        ids = [c.id for c in self.observed.characters] + [f.id for f in self.observed.facts] + [t.id for t in self.observed.texts]
        if len(ids) != len(set(ids)):
            raise ValueError("all local evidence IDs must be unique")
        for t in self.observed.texts:
            if t.speaker is not None and t.speaker not in chars:
                raise ValueError(f"unknown balloon speaker: {t.speaker}")
        for m in self.inferred.motions:
            if m.character_id is not None and m.character_id not in chars:
                raise ValueError("motion references a nonexistent character")
            if m.evidence_id not in chars and m.evidence_id not in facts:
                raise ValueError(f"motion requires observed evidence: evidence_id {m.evidence_id!r} must be one of {list(chars) + list(facts)}, or omit the motion")
            if m.kind in ("blink", "settle") and m.character_id is None:
                raise ValueError("character motion requires a visible character")
        for s in self.sounds:
            if s.evidence_id not in facts:
                raise ValueError(f"sound requires an observed fact: evidence_id {s.evidence_id!r} must be one of {list(facts)}, or use sounds: []")
            if s.kind in ("impact", "footsteps") and (facts[s.evidence_id].kind != "action" or s.layer != "event" or s.timing == "throughout"):
                raise ValueError("impact/footsteps must accompany a visible action as a point event")
            if s.layer == "ambience" and s.timing != "throughout":
                raise ValueError("ambience must be continuous within its shot")
            if s.timing == "during_action" and facts[s.evidence_id].kind != "action":
                raise ValueError("synchronized sound requires a visible action")
        return self


SECTIONS = ("subject_definitions", "summary", "retention_analysis", "detailed_description", "overall_soundscape", "non_diegetic_music")
CHROMATIC = set("red blue green yellow orange purple pink violet crimson scarlet blonde blond golden auburn chestnut turquoise teal cyan magenta brown beige indigo navy maroon burgundy emerald hazel rainbow".split())


def prose(value, monochrome=False):
    if not value:
        return
    if any(c in value for c in '<>[]\n\r"') or re.search(r"\(S\d+\)", value) or any(f"{s}:" in value for s in SECTIONS):
        raise ValueError("descriptions cannot contain prompt markup, quoted speech or sections")
    if any(c.isalpha() and "LATIN" not in unicodedata.name(c, "") for c in value):
        raise ValueError("descriptions must be in English; original-language text belongs in texts")
    words = set(re.findall(r"[a-z]+", value.lower()))
    if monochrome and words & CHROMATIC:
        raise ValueError("chromatic color claims in a monochrome panel; describe tones instead")


def analysis_request(user_prompt):
    return (
        DEFAULT_ANALYSIS_PROMPT
        + ("\nAdditional inspection focus (not image evidence): " + user_prompt if user_prompt != DEFAULT_ANALYSIS_PROMPT else "")
        + "\nReturn only the JSON object constrained by the supplied output schema. Field guide:\n"
        "observed: palette (monochrome/color/unknown), style, composition, characters, facts, texts.\n"
        "characters: give each visible character an id c1, c2, etc.; describe appearance, hair, clothing, accessories, "
        "distinctive_features, position, posture, expression. Use null for absent optional details. "
        "Distinctive features are specific identifying marks, not generic age/gender. Expressions describe eyes, brows and mouth, not inferred emotions.\n"
        "facts: give each visible environment/object/lighting/action fact an id f1, f2, etc., a kind and a description.\n"
        "texts: [] if there is no legible or identifiable printed text. Never create a placeholder record. Otherwise give each region id t1, t2, etc., "
        "kind (speech/thought/caption/sign/sfx/unknown), exact text, language name in English, legible, bbox, speaker, attribution_method and attribution_evidence. "
        "bbox contains FOUR DECIMAL FRACTIONS between 0 and 1: left, top, right, bottom. Divide image coordinates by image width/height; do not output pixels. "
        "Only a visible speech balloon tail or explicit label permits attribution_method balloon_tail/explicit_label with speaker c1/c2/etc. "
        "Otherwise set speaker null and attribution_method uncertain. Thoughts and captions are never speech.\n"
        "inferred.motions: [] for a static panel is acceptable. For subtle movement, use character_id c1/c2/etc. or null, "
        "evidence_id copied EXACTLY from an id already declared in observed.characters or observed.facts, kind hold/blink/settle/continue_action, and description. "
        "Never create new evidence IDs. continue_action requires an already-observed action fact. Keep movement within the frame.\n"
        "sounds: [] by default, including panels with speech balloons. Speech is NOT wind, impact or ambient sound. "
        "Only for an explicitly visible physical source actively producing sound, give kind impact/footsteps/rain/running_water/fire/wind, "
        "evidence_id copied EXACTLY from an observed fact, visual_evidence, layer event/ambience and timing at_start/during_action/throughout. "
        "Idle objects and indoor/outdoor settings do not establish sound. Ambience uses throughout; impacts/footsteps require observed actions and event layer.\n"
        "All descriptions must be English without quotations or control tags. Only exact visible text preserves its original language. "
        "Use literal JSON null, never the string null. No invented colors in monochrome art. No unobserved characters, objects, speech, sound or relationships."
    )


def clear_non_speech_speakers(response):
    """Remove model speaker guesses from thoughts, captions, signs and SFX."""
    raw = response.strip()
    if raw.startswith("```") and raw.endswith("```"):
        lines = raw.splitlines()
        if lines[0] in ("```", "```json"):
            raw = "\n".join(lines[1:-1])
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return response, 0
    if not isinstance(data, dict) or not isinstance(data.get("observed"), dict):
        return response, 0
    texts = data["observed"].get("texts")
    if not isinstance(texts, list):
        return response, 0
    cleared = 0
    for text in texts:
        if isinstance(text, dict) and text.get("kind") != "speech" and text.get("speaker") not in (None, ""):
            text["speaker"] = None
            text["attribution_method"] = "uncertain"
            text["attribution_evidence"] = ""
            cleared += 1
    return (json.dumps(data, ensure_ascii=False) if cleared else response), cleared


def parse_analysis(response, panel_index, monochrome):
    try:
        raw = response.strip()
        if raw.startswith("```") and raw.endswith("```"):
            lines = raw.splitlines()
            if lines[0] not in ("```", "```json"):
                raise ValueError("unsupported response wrapper")
            raw = "\n".join(lines[1:-1])
        data = PanelAnalysis.model_validate_json(raw)
        mono = monochrome or data.observed.palette == "monochrome"
        if monochrome and data.observed.palette == "color":
            raise ValueError("analysis claims color in a grayscale image")
        if mono:
            data.observed.palette = "monochrome"
        prose(data.observed.style, mono)
        prose(data.observed.composition, mono)
        for c in data.observed.characters:
            for k, value in c.model_dump().items():
                if k != "id":
                    for part in value if isinstance(value, list) else [value]:
                        prose(part, mono)
        for f in data.observed.facts:
            prose(f.description, mono)
        for t in data.observed.texts:
            prose(t.language)
            prose(t.attribution_evidence)
            # H3 offers no escaping syntax for its control tags. Fail instead of altering source words.
            if any(x in t.text for x in ("<", ">", "[Shot")) or any(f"{s}:" in t.text for s in SECTIONS) or re.search(r"\(S\d+\)", t.text):
                raise ValueError("visible text contains reserved H3 syntax; manual review is required")
            if t.kind == "speech" and t.legible and not t.language.strip():
                raise ValueError("legible speech requires its original language")
        for m in data.inferred.motions:
            prose(m.description, mono)
        for s in data.sounds:
            prose(s.visual_evidence, mono)
        return data
    except (ValueError, ValidationError, AttributeError) as error:
        raise ValueError(f"Panel {panel_index}: invalid visual analysis. {error}") from error
