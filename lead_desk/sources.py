"""Per-source payload normalization to the one canonical lead shape
(name/email/phone/company/role/message). Meta Lead Ads, Google Lead Form,
Webflow and GHL forms are all configured, in practice, to POST their native
webhook or a Zapier/Make passthrough at a fixed field mapping -- so those are
treated as 'generic' (the operator maps fields once at setup, per the plan's
own listing of 'a webhook' as an equivalent source). Typeform's raw webhook
shape is genuinely different (nested answers-by-type) and is normalized here
as the concrete proof this isn't just one hardcoded form."""


class UnsupportedSource(Exception):
    pass


def _typeform_answer_text(answer: dict) -> str:
    for key in ("text", "email", "phone_number", "number"):
        if key in answer:
            return str(answer[key])
    if "choice" in answer:
        return answer["choice"].get("label", "")
    return ""


def normalize_typeform(payload: dict) -> dict:
    response = payload.get("form_response", payload)
    fields = {a["field"].get("ref", a["field"].get("id", "")): a for a in response.get("answers", [])}
    by_type = {}
    for ref, answer in fields.items():
        by_type.setdefault(answer.get("type"), []).append(_typeform_answer_text(answer))
    return {
        "name": (by_type.get("text") or by_type.get("short_text") or [None])[0],
        "email": (by_type.get("email") or [None])[0],
        "phone": (by_type.get("phone_number") or [None])[0],
        "company": None,
        "role": None,
        "message": " ".join(v for values in by_type.values() for v in values if v),
    }


def normalize_generic(payload: dict) -> dict:
    return {"name": payload.get("name"), "email": payload.get("email"), "phone": payload.get("phone"),
            "company": payload.get("company"), "role": payload.get("role"), "message": payload.get("message", "")}


NORMALIZERS = {"typeform": normalize_typeform}


def normalize(source: str, payload: dict) -> dict:
    return NORMALIZERS.get(source, normalize_generic)(payload)
