# Ported unchanged from the previous bot (calculator.py): reference data, maths and texts.
"""
calculator.py — Tax Savings Calculator for IT freelancers/employees in high-tax EU.

Conversational flow via inline keyboards in Telegram bot.
4 steps: residence → gross → income source → family → result.

Outputs comparison of:
- Default (no structure)
- Option 1: Estonia OÜ + Digital Nomad ВНЖ Испании
- Option 2: Cyprus Ltd + non-dom (requires relocation to Cyprus)
- Option 3: Portugal Ltd + IFICI (requires move/already there)

Each user's calculator session is tracked in state.json under
`calculator_sessions[user_id]`.
"""

# ───────────────── Reference data ─────────────────

COUNTRIES = {
    "es": {"name": "Испания", "flag": "🇪🇸", "default_pit": 0.47, "default_social": 0.064,
           "max_effective": 0.515, "note": "Прогрессивный IRPF до 47% + соц.взносы"},
    "pt": {"name": "Португалия", "flag": "🇵🇹", "default_pit": 0.48, "default_social": 0.11,
           "max_effective": 0.55, "note": "Прогрессивный IRS до 48% + соц.взносы"},
    "at": {"name": "Австрия", "flag": "🇦🇹", "default_pit": 0.50, "default_social": 0.18,
           "max_effective": 0.50, "note": "PIT до 50%, соц.взносы делятся работодатель/работник"},
    "de": {"name": "Германия", "flag": "🇩🇪", "default_pit": 0.45, "default_social": 0.20,
           "max_effective": 0.49, "note": "PIT до 45% + Solidaritätszuschlag + социалка"},
    "fr": {"name": "Франция", "flag": "🇫🇷", "default_pit": 0.45, "default_social": 0.22,
           "max_effective": 0.49, "note": "PIT до 45% + CSG/CRDS"},
    "it": {"name": "Италия", "flag": "🇮🇹", "default_pit": 0.43, "default_social": 0.10,
           "max_effective": 0.47, "note": "IRPEF до 43% + addizionali regionali"},
    "other": {"name": "Другая страна EU", "flag": "🇪🇺", "default_pit": 0.43, "default_social": 0.15,
              "max_effective": 0.50, "note": "Средняя EU high-tax юрисдикция"},
}

GROSS_BUCKETS = {
    "30-60": {"label": "€30–60k", "min": 30000, "max": 60000, "mid": 45000},
    "60-100": {"label": "€60–100k", "min": 60000, "max": 100000, "mid": 80000},
    "100-150": {"label": "€100–150k", "min": 100000, "max": 150000, "mid": 125000},
    "150-300": {"label": "€150–300k", "min": 150000, "max": 300000, "mid": 220000},
    "300+": {"label": "€300k+", "min": 300000, "max": 500000, "mid": 400000},
}

INCOME_SOURCES = {
    "intl": {"label": "🌍 Международные клиенты (не EU)", "boosts_dnv": True},
    "eu": {"label": "🇪🇺 EU клиенты (не моя страна)", "boosts_dnv": False},
    "local": {"label": "📍 Локальные клиенты", "boosts_dnv": False},
    "mixed": {"label": "🔀 Смешанный", "boosts_dnv": False},
}

FAMILY = {
    "single": {"label": "Один", "multiplier_dnv_threshold": 33600},
    "couple": {"label": "С супругом(ой)", "multiplier_dnv_threshold": 41600},
    "kids": {"label": "С детьми", "multiplier_dnv_threshold": 49600},
    "full": {"label": "Супруг + дети", "multiplier_dnv_threshold": 57600},
}

# Effective rates after structuring (research-based estimates, blended)
OPTIONS = {
    "estonia_dnv": {
        "name": "Estonia OÜ + Digital Nomad ВНЖ Испании",
        "short": "Estonia OÜ + DNV",
        "effective_rate": 0.22,
        "applies_in": ["es", "pt", "at", "de", "fr", "it", "other"],
        "highlight_for_intl": True,
        "details": (
            "— Контракты с международными заказчиками через эстонскую OÜ\n"
            "— Корп. налог 0% пока прибыль не распределяется\n"
            "— Зарплата директора €30-36k/год (Spanish flat 24% на foreign income при DNV)\n"
            "— Реинвестирование или дивиденды (20% PIT Эстонии) — управляется"
        ),
        "tradeoffs": (
            "Substance в Эстонии: визит 1 раз/год + local director ~€2-3k/год.\n"
            "Требование DNV-визы: гросс ≥ €33 600/год + €8k на члена семьи."
        ),
    },
    "cyprus_nondom": {
        "name": "Cyprus Ltd + Cyprus non-dom",
        "short": "Cyprus Ltd + non-dom",
        "effective_rate": 0.16,
        "applies_in": "all",
        "requires_relocation": True,
        "details": (
            "— Кипрская Ltd, корпоративный налог 12.5%\n"
            "— Дивиденды от Кипрской компании: 0% для non-dom 17 лет\n"
            "— SDC tax exemption для не-dom резидентов\n"
            "— Зарплата: до €19,500/год — 0% PIT"
        ),
        "tradeoffs": (
            "Требует переезда на Кипр (183+ дней или 60 дней + связи).\n"
            "Подходит если уже планируете релокацию или для founders, не привязанных к стране."
        ),
    },
    "portugal_ifici": {
        "name": "Portugal Ltd + IFICI режим",
        "short": "Portugal + IFICI",
        "effective_rate": 0.25,
        "applies_in": "all",
        "deadline": "15.01.2027",
        "requires_relocation": True,
        "details": (
            "— IFICI = 20% flat PIT на квалифицированные профессии (вкл. IT)\n"
            "— Иностранные дивиденды/проценты: 0% при выплате из non-tax-haven юрисдикций\n"
            "— Корп. налог Португалии: 21%\n"
            "— Подходит founders релоцирующимся в Португалию"
        ),
        "tradeoffs": (
            "Дедлайн подачи на IFICI: 15.01.2027 (если статус резидента в 2026).\n"
            "Требует фактического переезда. После 10 лет — стандартный режим."
        ),
    },
}


# ───────────────── Step prompts and keyboards ─────────────────

STEP_RESIDENCE = "residence"
STEP_GROSS = "gross"
STEP_SOURCE = "source"
STEP_FAMILY = "family"
STEP_RESULT = "result"

INTRO = (
    "🧮 Tax Savings Calculator\n\n"
    "Расчёт экономии налогов для IT-специалиста в EU.\n"
    "4 вопроса × 15 секунд = расчёт по 3 структурным опциям.\n\n"
    "Шаг 1 из 4 — где Вы налоговый резидент?"
)

PROMPT_GROSS = (
    "{flag} {name} зафиксирована.\n"
    "{note}\n\n"
    "Шаг 2 из 4 — годовой гросс-доход:"
)

PROMPT_SOURCE = (
    "Принято — {gross_label} в год.\n\n"
    "Шаг 3 из 4 — основной источник Ваших клиентов:"
)

PROMPT_FAMILY = (
    "Принято — {source_label}.\n\n"
    "Шаг 4 из 4 — Ваша семья:"
)

DISCLAIMER = (
    "\n\n📍 Это предварительная оценка по типовым параметрам.\n"
    "Точные цифры зависят от структуры активов, локальных deductions, дивидендной политики, существующих компаний.\n\n"
    "Для индивидуального расчёта — комплексная консультация €500 с местным адвокатом по выбранной юрисдикции.\n"
    "Запись через @Businessmanager_THE_A.\n\n"
    "📡 Регуляторные апдейты — @TheA_CapitalHouse"
)


def keyboard_residence():
    return {
        "inline_keyboard": [
            [{"text": "🇪🇸 Испания", "callback_data": "calc:residence:es"},
             {"text": "🇵🇹 Португалия", "callback_data": "calc:residence:pt"}],
            [{"text": "🇦🇹 Австрия", "callback_data": "calc:residence:at"},
             {"text": "🇩🇪 Германия", "callback_data": "calc:residence:de"}],
            [{"text": "🇫🇷 Франция", "callback_data": "calc:residence:fr"},
             {"text": "🇮🇹 Италия", "callback_data": "calc:residence:it"}],
            [{"text": "🇪🇺 Другая EU страна", "callback_data": "calc:residence:other"}],
            [{"text": "❌ Отменить", "callback_data": "calc:cancel"}],
        ]
    }


def keyboard_gross():
    rows = []
    for key, b in GROSS_BUCKETS.items():
        rows.append([{"text": b["label"], "callback_data": f"calc:gross:{key}"}])
    rows.append([{"text": "❌ Отменить", "callback_data": "calc:cancel"}])
    return {"inline_keyboard": rows}


def keyboard_source():
    rows = []
    for key, s in INCOME_SOURCES.items():
        rows.append([{"text": s["label"], "callback_data": f"calc:source:{key}"}])
    rows.append([{"text": "❌ Отменить", "callback_data": "calc:cancel"}])
    return {"inline_keyboard": rows}


def keyboard_family():
    rows = []
    for key, f in FAMILY.items():
        rows.append([{"text": f["label"], "callback_data": f"calc:family:{key}"}])
    rows.append([{"text": "❌ Отменить", "callback_data": "calc:cancel"}])
    return {"inline_keyboard": rows}


# ───────────────── Calculation engine ─────────────────

def compute(answers):
    """Compute default tax + 3 structural options."""
    country = COUNTRIES[answers["residence"]]
    bucket = GROSS_BUCKETS[answers["gross"]]
    source = INCOME_SOURCES[answers["source"]]
    family = FAMILY[answers["family"]]

    gross_mid = bucket["mid"]
    default_rate = min(country["max_effective"], country["default_pit"] + country["default_social"] * 0.5)
    default_tax = gross_mid * default_rate
    default_net = gross_mid - default_tax

    options_out = []
    for opt_key, opt in OPTIONS.items():
        applies = opt["applies_in"] == "all" or answers["residence"] in opt.get("applies_in", [])
        if not applies:
            continue
        eff = opt["effective_rate"]
        # Slight uplift for the right source/structure match
        if opt_key == "estonia_dnv" and not source["boosts_dnv"]:
            eff += 0.02  # 24% if not international clients
        opt_tax = gross_mid * eff
        opt_net = gross_mid - opt_tax
        savings = default_tax - opt_tax

        options_out.append({
            "key": opt_key,
            "name": opt["name"],
            "short": opt["short"],
            "effective_rate": eff,
            "tax": opt_tax,
            "net": opt_net,
            "savings": savings,
            "savings_pct": savings / default_tax if default_tax else 0,
            "details": opt["details"],
            "tradeoffs": opt["tradeoffs"],
            "deadline": opt.get("deadline"),
            "requires_relocation": opt.get("requires_relocation", False),
        })

    return {
        "country": country,
        "gross_label": bucket["label"],
        "gross_mid": gross_mid,
        "source_label": source["label"],
        "family_label": family["label"],
        "default_rate": default_rate,
        "default_tax": default_tax,
        "default_net": default_net,
        "options": sorted(options_out, key=lambda x: -x["savings"]),  # highest savings first
    }


def fmt_money(amount):
    return f"€{int(amount/1000)}k" if amount >= 10000 else f"€{int(amount)}"


def format_result(answers, c):
    country = c["country"]
    lines = []
    lines.append("📊 Ваш расчёт готов")
    lines.append("")
    lines.append("ВВОДНЫЕ:")
    lines.append(f"{country['flag']} {country['name']} · {c['gross_label']}/год · {c['source_label'].split(' ', 1)[1] if ' ' in c['source_label'] else c['source_label']} · {c['family_label']}")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"DEFAULT (без структуры в {country['name']}):")
    lines.append(f"Effective rate: ~{int(c['default_rate']*100)}%")
    lines.append(f"Налог в год: ~{fmt_money(c['default_tax'])}")
    lines.append(f"Чистыми в год: ~{fmt_money(c['default_net'])}")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    for i, opt in enumerate(c["options"], 1):
        lines.append(f"ОПЦИЯ {i} — {opt['name']}")
        lines.append(f"Effective rate: ~{int(opt['effective_rate']*100)}%")
        lines.append(f"Налог в год: ~{fmt_money(opt['tax'])}")
        lines.append(f"Чистыми в год: ~{fmt_money(opt['net'])}")
        lines.append(f"✅ Экономия vs default: ~{fmt_money(opt['savings'])} ({int(opt['savings_pct']*100)}%)")
        if opt["deadline"]:
            lines.append(f"⏳ Дедлайн режима: {opt['deadline']}")
        if opt["requires_relocation"]:
            lines.append(f"📍 Требует переезда")
        lines.append("")

    lines.append(DISCLAIMER.strip())
    return "\n".join(lines)


# ───────────────── Master notification ─────────────────

def format_master_notification(user, answers, c):
    """Telegram message to Ksenia when someone completes the calculator."""
    country = c["country"]
    top_opt = c["options"][0] if c["options"] else None
    name = " ".join(filter(None, [user.get("first_name"), user.get("last_name")])).strip() or "—"
    handle = f"@{user['username']}" if user.get("username") else f"id:{user.get('id')}"
    lines = [
        "🧮 Tax Calculator завершён — горячий лид",
        "",
        f"От: {name} ({handle})",
        f"chat_id: {user.get('id')}",
        "",
        f"{country['flag']} {country['name']}",
        f"💰 Гросс: {c['gross_label']}/год",
        f"🌍 Источник: {c['source_label']}",
        f"👨‍👩‍👧 Семья: {c['family_label']}",
        "",
        f"Default rate: ~{int(c['default_rate']*100)}% (~{fmt_money(c['default_tax'])} налогов)",
    ]
    if top_opt:
        lines.append(f"Топ-рекомендация: {top_opt['short']} → ~{int(top_opt['effective_rate']*100)}%")
        lines.append(f"Потенциальная экономия: ~{fmt_money(top_opt['savings'])}/год")
    lines.append("")
    lines.append(f"Связаться: {handle if user.get('username') else 'через бот'}")
    return "\n".join(lines)
