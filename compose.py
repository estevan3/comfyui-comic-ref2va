import json
import re
import unicodedata
from collections import defaultdict

from .analysis import SECTIONS


CAMERAS = {
    "static": "While this reference composition is established, the camera holds its original framing.",
    "slow_zoom_in": "While this reference composition is established, the camera zooms in very slightly at slow speed, staying inside the original image boundaries; carry the motion smoothly through any concealed join.",
}
SOUNDS = {
    "impact": "a brief impact sound",
    "footsteps": "footsteps aligned with the visible foot contacts",
    "rain": "the patter of the visible rainfall",
    "running_water": "the sound of the visibly flowing water",
    "fire": "the crackle of the visible flames",
    "wind": "a soft wind accompanying the visibly wind-driven movement",
}
EMOTIONS = set("happy sad angry anxious terrified frightened jealous loving romantic confident confused disgusted determined worried excited nervous afraid furious fearful hopeful hopeless desperate suspicious embarrassed amused".split())


def timing(duration, count):
    if type(duration) is not int or not 4 <= duration <= 15:
        raise ValueError("duration must be an integer from 4 to 15 seconds")
    if not 1 <= count <= 9:
        raise ValueError("connect between 1 and 9 individual panel images")
    return [(i * duration * 1000 // count, (i + 1) * duration * 1000 // count) for i in range(count)]


def timestamp(ms):
    return f"{ms // 60000:02d}:{ms // 1000 % 60:02d}.{ms % 1000:03d}"


def direction(text):
    controls = {"camera": "static", "pace": "natural", "motion": "subtle"}
    allowed = {"camera": set(CAMERAS), "pace": {"slow", "natural"}, "motion": {"subtle", "hold"}}
    warnings = []
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        key, separator, value = part.partition("=")
        key, value = key.strip().lower(), value.strip().lower()
        if not separator or key not in allowed or value not in allowed[key]:
            warnings.append("An extra instruction was not applied. Use camera=static|slow_zoom_in; pace=slow|natural; motion=subtle|hold.")
        else:
            controls[key] = value
    return controls, list(dict.fromkeys(warnings))


def normalized(text):
    return " ".join(text.lower().split()).rstrip(".")


def reconcile(panels):
    # Exact matching deliberately favors missed matches over merging lookalikes.
    candidates = defaultdict(list)
    identities = {}
    characters = {}
    for panel_index, panel in enumerate(panels, 1):
        for c in panel.observed.characters:
            key = (panel_index, c.id)
            characters[key] = c
            identities[key] = key
            marks = tuple(sorted({normalized(x) for x in c.distinctive_features if x.strip()}))
            if len(marks) >= 2 and c.hair.strip() and c.clothing.strip():
                signature = (normalized(c.appearance), normalized(c.hair), normalized(c.clothing), normalized(c.accessories), marks)
                candidates[signature].append(key)
    groups = {}
    warnings = []
    for occurrences in candidates.values():
        if len(occurrences) < 2:
            continue
        if len({p for p, _ in occurrences}) != len(occurrences):
            warnings.append("Ambiguous lookalikes remain separate; no shared subject or speaker identity was assigned.")
            continue
        representative = occurrences[0]
        groups[representative] = occurrences
        for key in occurrences:
            identities[key] = representative
    order = []
    for key in characters:
        representative = identities[key]
        if representative not in order:
            order.append(representative)
    subjects = []
    for number, representative in enumerate(order, 1):
        occurrences = groups.get(representative, [representative])
        subjects.append({"number": number, "identity": representative, "origin": representative[0],
                         "occurrences": occurrences, "character": characters[representative],
                         "observations": [characters[key] for key in occurrences]})
    return identities, subjects, characters, warnings


SUBJECT_FIELDS = ("appearance", "hair", "clothing", "accessories", "distinctive_features")


def safe_subject_text(value, field):
    if not isinstance(value, str) or not value.strip() or len(value) > 400:
        raise ValueError(f"subject override {field} must be a non-empty string of at most 400 characters")
    sections = ("subject_definitions:", "summary:", "retention_analysis:", "detailed_description:", "overall_soundscape:", "non_diegetic_music:")
    if any(mark in value for mark in ("<", ">", "[Shot")) or any(section in value.lower() for section in sections) or re.search(r"\(S\d+\)|\b(?:say|says|said|speak|speaks|dialogue|speech|speaker|thought)\b", value, re.I) or any(unicodedata.category(char).startswith("C") for char in value):
        raise ValueError(f"subject override {field} cannot contain prompt structure, speaker IDs, or dialogue")
    if any(char.isalpha() and not unicodedata.name(char, "").startswith("LATIN ") for char in value):
        raise ValueError(f"subject override {field} must be written in English")
    return value.strip()


def parse_subject_overrides(raw, subjects, strict_mode):
    if raw is None or raw == "":
        return {}, []
    if not isinstance(raw, str):
        raise ValueError("subject_overrides must be a JSON string")
    if not raw.strip():
        return {}, []
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate subject override key: {key}")
            result[key] = value
        return result

    try:
        overrides = json.loads(raw, object_pairs_hook=unique_keys)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("subject_overrides must be a JSON object keyed by Subject number") from error
    if not isinstance(overrides, dict):
        raise ValueError("subject_overrides must be a JSON object keyed by Subject number")
    by_number = {str(item["number"]): item for item in subjects}
    result, edited = {}, []
    for number, values in overrides.items():
        if not isinstance(number, str) or number not in by_number:
            raise ValueError(f"subject_overrides references unknown Subject {number}")
        if not isinstance(values, dict) or not values or set(values) - set(SUBJECT_FIELDS):
            raise ValueError(f"Subject {number} override must contain only {', '.join(SUBJECT_FIELDS)}")
        subject = by_number[number]
        # Recurrent characters have the same validated visual signature; check every occurrence.
        observed_chars = subject["observations"]
        clean = {}
        for field, value in values.items():
            if field == "distinctive_features":
                if not isinstance(value, list):
                    raise ValueError(f"Subject {number} distinctive_features must be a list")
                clean[field] = [safe_subject_text(item, field) for item in value]
            else:
                clean[field] = safe_subject_text(value, field)
            if strict_mode:
                if field == "distinctive_features":
                    known = {normalized(feature) for character in observed_chars for feature in character.distinctive_features}
                    if any(normalized(feature) not in known for feature in clean[field]):
                        raise ValueError(f"Subject {number} override adds an unobserved distinctive feature")
                else:
                    known = [normalized(getattr(character, field) or "") for character in observed_chars]
                    candidate = normalized(clean[field])
                    if not any(candidate and candidate == text for text in known):
                        raise ValueError(f"Subject {number} override {field} is not supported as a complete observed value; use strict_mode=False for edits")
        result[int(number)] = clean
        if not strict_mode:
            edited.append(int(number))
    return result, edited


def dialogue_seconds(text):
    # A warning heuristic, not a speech synthesizer; neither edits nor accelerates text.
    compact = sum(1 for c in text if any(name in unicodedata.name(c, "") for name in ("CJK", "HIRAGANA", "KATAKANA", "HANGUL")))
    words = re.findall(r"[^\W\d_]+", "".join(" " if any(n in unicodedata.name(c, "") for n in ("CJK", "HIRAGANA", "KATAKANA", "HANGUL")) else c for c in text))
    return compact / 4 + len(words) / 2.5 + 0.3


def assemble(panels, duration, extra_instructions, strict_mode, subject_overrides=""):
    times = timing(duration, len(panels))
    controls, warnings = direction(extra_instructions)
    identities, subjects, _, identity_warnings = reconcile(panels)
    warnings.extend(identity_warnings)
    overrides, edited_subjects = parse_subject_overrides(subject_overrides, subjects, strict_mode)
    definitions, retention, shots = [], [], []
    speakers = {}
    ambience = defaultdict(list)
    diagnostics = []
    subject_numbers = {item["identity"]: item["number"] for item in subjects}
    def label(panel_index, character_id):
        identity = identities[panel_index, character_id]
        return f"<Subject {subject_numbers[identity]}>"

    for i in range(1, len(panels) + 1):
        definitions.append(f"<Picture {i}> is the first-frame reference for [Shot {i}].")
        retention.append(f"<Picture {i}> ([Shot {i}] first frame): fully_preserved - Preserve composition, visible characters, physical features, clothing, objects, environment, artwork and original colors or monochrome tones.")
    for subject in subjects:
        number, occurrences, c = subject["number"], subject["occurrences"], subject["character"]
        values = {field: getattr(c, field) for field in SUBJECT_FIELDS}
        values["distinctive_features"] = list(c.distinctive_features)
        values.update(overrides.get(number, {}))
        origin = subject["origin"]
        details = "; ".join(value for field in SUBJECT_FIELDS for value in (values[field] if field == "distinctive_features" else [values[field]]) if value)
        details = details or "No further appearance details are verified"
        later = [f"<Picture {p}>" for p, _ in occurrences if p != origin]
        definition = f"<Subject {number}> from <Picture {origin}>: {details}."
        if later:
            definition += f" Also visible in {', '.join(later)}."
        definitions.append(definition)
        appearances = ", ".join(f"[Shot {p}]" for p, _ in occurrences)
        preservation = "partially_preserved" if number in edited_subjects else "fully_preserved"
        retention.append(f"<Subject {number}> (appears in {appearances}): {preservation} - Preserve the verified identity and visual features in each reference.")
        if number in edited_subjects:
            for picture, _ in occurrences:
                idx = picture - 1
                retention[idx] = retention[idx].replace("fully_preserved -", "partially_preserved -")

    for i, (panel, (start, end)) in enumerate(zip(panels, times), 1):
        o = panel.observed
        parts = [f"[Shot {i}] The continuous take begins from <Picture {i}>." if i == 1 else f"[Shot {i}] At {timestamp(start)}, the same apparent take arrives seamlessly at the composition established by <Picture {i}>, continuing from <Picture {i - 1}> without a visible cut or camera reset."]
        parts.extend(x for x in (o.style, o.composition) if x)
        if o.palette == "monochrome":
            parts.append("Retain the original monochrome tones; do not colorize the image.")
        for c in o.characters:
            expression = c.expression
            if strict_mode and set(re.findall(r"[a-z]+", expression.lower())) & EMOTIONS:
                expression = "Preserve the visible facial configuration in the reference"
                warnings.append(f"Shot {i}: an emotional interpretation for {c.id} was replaced with a reference-preservation instruction.")
            visual = "; ".join(x for x in [c.position, c.posture, expression] if x)
            parts.append(f"{label(i, c.id)}: {visual}.")
        parts.extend(f.description for f in o.facts)
        facts = {f.id: f for f in o.facts}
        parts.append(CAMERAS[controls["camera"]])
        if controls["motion"] == "hold" or not panel.inferred.motions:
            parts.append("Hold the visible poses and composition without adding events.")
        else:
            for m in panel.inferred.motions:
                who = label(i, m.character_id) if m.character_id else "The visible subject"
                who_prefix = f"{who}: " if m.character_id else ""
                if m.kind == "continue_action" and (m.evidence_id not in facts or facts[m.evidence_id].kind != "action"):
                    parts.append("Hold the visible pose without adding events.")
                    warnings.append(f"Shot {i}: motion without an observed action was limited to holding the reference pose.")
                elif not strict_mode and m.description:
                    parts.append(who_prefix + m.description)
                elif m.kind == "continue_action":
                    parts.append(f"{who_prefix}Develop only the movement already indicated by this visible action: {facts[m.evidence_id].description} Keep its development small and within the existing frame, without adding a new event.")
                elif m.kind == "blink":
                    parts.append(f"{who} makes one subtle blink, retaining the reference pose.")
                elif m.kind == "settle":
                    parts.append(f"{who} makes a slight settling movement within the visible pose.")
                else:
                    parts.append("Hold the visible pose without adding events.")
        parts.append("Movement develops slowly." if controls["pace"] == "slow" else "Keep movement restrained and naturally paced.")
        spoken = []
        for t in o.texts:
            if not t.legible:
                warnings.append(f"Shot {i}: illegible text {t.id} was not transcribed or voiced.")
                continue
            if t.kind == "speech" and t.speaker is not None:
                identity = identities[i, t.speaker]
                speakers.setdefault(identity, len(speakers) + 1)
                parts.append(f"{label(i, t.speaker)} (S{speakers[identity]}) says, <d>[{t.language}] {t.text}</d>")
                spoken.append(t.text)
            else:
                parts.append(f'Preserve the visible {t.kind} text "{t.text}" without voicing it.')
                if t.kind == "speech":
                    warnings.append(f"Shot {i}: balloon {t.id} has an uncertain speaker; retained as visible text only.")
        required_seconds = sum(dialogue_seconds(t) for t in spoken)
        if required_seconds > (end - start) / 1000:
            warnings.append(f"Shot {i}: dialogue may need about {required_seconds:.1f}s but has {(end - start) / 1000:.3f}s. Increase duration or review panels; words and speed were not changed.")
        for s in panel.sounds:
            if s.layer == "ambience":
                ambience[s.kind].append(i)
            else:
                when = {"at_start": "At the opening of this shot", "during_action": "Synchronized with the visible action", "throughout": "Throughout this shot"}[s.timing]
                parts.append(f"{when}, use {SOUNDS[s.kind]}, grounded in {s.visual_evidence}.")
        parts.append(f"Keep all action and complete speech within this shot's {(end - start) / 1000:.3f}-second interval. Preserve the original frame boundaries.")
        if i < len(panels):
            parts.append(f"During the closing part of this interval, conceal the join from <Picture {i}> to <Picture {i + 1}> inside a brief, smoothly directed image-plane motion blur made only from these two references. Match visible shapes and motion where supported, keeping characters, objects and settings intact. Resolve the blur into the next reference composition exactly at the start of the next interval, within the existing duration; leave dialogue and event sounds at their assigned times.")
        shots.append(" ".join(parts))
        diagnostics.append({"picture": i, "shot": i, "start_ms": start, "end_ms": end, "analysis": panel.model_dump()})

    soundscape = " ".join(f"In {', '.join('Shot ' + str(i) for i in indices)}, use {SOUNDS[kind]}; it is absent from other shots unless visibly supported there." for kind, indices in ambience.items())
    if not soundscape:
        soundscape = "Keep the sound bed minimal; no unverified ambient layer. Only the explicitly described, visually grounded events and confirmed speech are audible."
    if ambience and len(panels) > 1:
        soundscape += " Smooth the changes between visually supported ambient layers at the concealed joins, without adding transition sounds or extending speech across intervals."
    anchors = "; ".join(f"<Picture {i}> for [Shot {i}]" for i in range(1, len(panels) + 1))
    take = "one continuous take" if len(panels) == 1 else "one simulated continuous take (faux one-shot)"
    summary = f"[keyframe completion] Create a {duration}-second video presented as {take}, with exactly {len(panels)} reference-anchored shots in reference order. First-frame anchors: {anchors}. Develop only the visible action within each reference composition. No hard cuts, jump cuts, fades to black or visible dissolves. End the final shot at {duration} seconds."
    continuity = "Preserve the visual style of each supplied comic panel and the appearance of one uninterrupted take."
    if len(panels) > 1:
        summary += " Shot labels and timestamps identify reference intervals joined by concealed edits, with no perceptible scene break."
        continuity += " Conceal each reference change within the described motion blur, using only content visible in the adjacent references; do not reveal unseen surroundings, invent travel between locations, imply unverified shared space or morph one character or object into another."
    sections = ["\n".join(definitions), summary, "\n".join(retention), continuity + "\n" + "\n".join(shots), soundscape, "N/A"]
    prompt = "\n\n".join(f"{name}:\n{body}" if name != "non_diegetic_music" else f"{name}: {body}" for name, body in zip(SECTIONS, sections))
    panel_subjects = [[subject_numbers[identities[i, c.id]] for c in panel.observed.characters]
                      for i, panel in enumerate(panels, 1)]
    validate_prompt(prompt, len(panels), duration,
                    sum(len([t for t in p.observed.texts if t.kind == 'speech' and t.legible and t.speaker is not None]) for p in panels),
                    subjects, panel_subjects)
    result = {"panels": diagnostics,
              "subjects": [{"subject": item["number"], "origin_picture": item["origin"],
                            "occurrences": [{"picture": p, "character_id": cid} for p, cid in item["occurrences"]],
                            "source_pictures": sorted({p for p, _ in item["occurrences"]}),
                            "definition": next(line for line in definitions if line.startswith(f"<Subject {item['number']}>") )}
                           for item in subjects],
              "subject_overrides": {"applied": overrides, "edited_subjects": edited_subjects,
                                    "example": '{"1":{"appearance":"A slim adult with a narrow face","hair":"Short straight dark hair","clothing":"A light jacket with diagonal seams","accessories":"A triangular pendant","distinctive_features":["A crescent scar on the left cheek"]}}'},
              "speakers": [{"identity": identity, "speaker": n} for identity, n in speakers.items()], "warnings": list(dict.fromkeys(warnings))}
    for number in edited_subjects:
        warnings.append(f"Subject {number} has a manually edited definition; its visual fidelity was not revalidated.")
        result["warnings"] = list(dict.fromkeys(warnings))
    return prompt, json.dumps(result, ensure_ascii=False, indent=2), result["warnings"]


def validate_prompt(prompt, count, duration, dialogue_count, subjects, panel_subjects):
    headers = re.findall(r"^(" + "|".join(SECTIONS) + r"):", prompt, re.MULTILINE)
    if tuple(headers) != SECTIONS:
        raise ValueError("invalid Ref2VA section order or duplicate section")
    body = prompt.split("detailed_description:\n", 1)[1].split("\n\noverall_soundscape:", 1)[0]
    marks = re.findall(r"^\[Shot (\d+)\](?: At (\d{2}:\d{2}\.\d{3}),)?", body, re.MULTILINE)
    expected = [(str(i), "" if i == 1 else timestamp(start)) for i, (start, _) in enumerate(timing(duration, count), 1)]
    if marks != expected or prompt.count("<d>") != dialogue_count or prompt.count("</d>") != dialogue_count:
        raise ValueError("invalid shot timing or dialogue tags")
    if "<Audio" in prompt or not prompt.endswith("non_diegetic_music: N/A"):
        raise ValueError("invalid generated audio reference or music")
    if not dialogue_count and re.search(r"\(S\d+\)", prompt):
        raise ValueError("silent characters cannot receive speaker IDs")
    pictures = set(int(x) for x in re.findall(r"<Picture (\d+)>", prompt))
    if pictures != set(range(1, count + 1)):
        raise ValueError("undefined or missing picture reference")
    subject_marks = [int(x) for x in re.findall(r"<Subject (\d+)>", prompt)]
    definitions = prompt.split("\n\nsummary:", 1)[0]
    defined = [int(x) for x in re.findall(r"^<Subject (\d+)> from <Picture \d+>:", definitions, re.MULTILINE)]
    expected = [item["number"] for item in subjects]
    if defined != expected or set(subject_marks) - set(expected):
        raise ValueError("undefined, duplicate, or misnumbered Subject reference")
    shot_lines = list(re.finditer(r"^\[Shot (\d+)\].*$", body, re.MULTILINE))
    if len(shot_lines) != count:
        raise ValueError("invalid detailed_description shot count")
    for panel_index, panel_match in enumerate(shot_lines, 1):
        if int(panel_match.group(1)) != panel_index:
            raise ValueError("shot order mismatch")
        end = shot_lines[panel_index].start() if panel_index < count else len(body)
        block = body[panel_match.start():end]
        found = [int(n) for n in re.findall(r"<Subject (\d+)>", block)]
        if set(found) != set(panel_subjects[panel_index - 1]):
            raise ValueError(f"Shot {panel_index} has missing or foreign Subject references")
