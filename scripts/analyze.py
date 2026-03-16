#!/usr/bin/env python3
"""
analyze.py - Analýza článků pomocí Claude API
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import anthropic
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config" / "sources.yaml"
SCRIPT_DIR = Path(__file__).parent.parent


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_articles(config: dict, run_type: str) -> tuple:
    data_dir = SCRIPT_DIR / config["settings"]["data_dir"]
    latest_file = data_dir / f"latest_{run_type}.json"

    if not latest_file.exists():
        logger.error(f"No latest run file found: {latest_file}")
        return [], None

    with open(latest_file) as f:
        latest = json.load(f)

    run_dir = Path(latest["run_dir"])
    articles_file = run_dir / "articles.json"

    if not articles_file.exists():
        logger.error(f"Articles file not found: {articles_file}")
        return [], None

    with open(articles_file, encoding="utf-8") as f:
        data = json.load(f)

    return data.get("articles", []), str(run_dir)


def get_watched_other_names(config: dict) -> list:
    """Normalize watched_names.other — supports both plain strings and dicts with keywords."""
    result = []
    for item in config["watched_names"].get("other", []):
        if isinstance(item, dict):
            result.append(item["name"])
        else:
            result.append(item)
    return result


def get_keyword_filters(config: dict) -> dict:
    """Return {name: [keywords]} for entities that should only be flagged with specific keywords."""
    filters = {}
    for item in config["watched_names"].get("other", []):
        if isinstance(item, dict) and "only_with_keywords" in item:
            filters[item["name"]] = [kw.lower() for kw in item["only_with_keywords"]]
    return filters


def apply_keyword_filters(analysis: dict, keyword_filters: dict) -> dict:
    """Remove person_mentions entries that don't contain required keywords."""
    for entity, required_keywords in keyword_filters.items():
        if entity not in analysis.get("person_mentions", {}):
            continue
        filtered_mentions = []
        for mention in analysis["person_mentions"][entity]:
            text = (mention.get("title", "") + " " + mention.get("context", "")).lower()
            if any(kw in text for kw in required_keywords):
                filtered_mentions.append(mention)
        if filtered_mentions:
            analysis["person_mentions"][entity] = filtered_mentions
        else:
            del analysis["person_mentions"][entity]
            logger.info(f"Filtered out '{entity}' — no mentions with required keywords")

    # Also filter from article tags within categories
    for cat_articles in analysis.get("categories", {}).values():
        for article in cat_articles:
            filtered_persons = []
            for person in article.get("persons", []):
                if person in keyword_filters:
                    text = (article.get("title", "") + " " + article.get("summary_cs", "")).lower()
                    if any(kw in text for kw in keyword_filters[person]):
                        filtered_persons.append(person)
                else:
                    filtered_persons.append(person)
            article["persons"] = filtered_persons

    return analysis


SPORT_KEYWORDS = [
    "stadion", "hala", "aréna", "arena", "za lužánkami", "lužánky",
    "kajot arena", "winning group arena", "hokejová hala", "fotbalový stadion",
    "stavba stadionu", "rekonstrukce stadionu", "nový stadion", "sportovní hala",
]

def apply_category_filters(analysis: dict, config: dict) -> dict:
    """Post-processing: move sport/kriminalita articles that don't meet criteria to 'ostatni'."""
    politicians = [p.lower() for p in config["watched_names"].get("politicians", [])]

    moved = 0

    # SPORT: keep only stadium/hall articles
    sport_articles = analysis.get("categories", {}).get("sport", [])
    keep_sport, move_sport = [], []
    for article in sport_articles:
        text = (article.get("title", "") + " " + article.get("summary_cs", "")).lower()
        if any(kw in text for kw in SPORT_KEYWORDS):
            keep_sport.append(article)
        else:
            move_sport.append(article)
    if move_sport:
        analysis["categories"]["sport"] = keep_sport
        moved += len(move_sport)
        logger.info(f"Sport filter: kept {len(keep_sport)}, discarded {len(move_sport)}")

    # KRIMINALITA: keep only articles mentioning politicians
    krimi_articles = analysis.get("categories", {}).get("kriminalita", [])
    keep_krimi, move_krimi = [], []
    for article in krimi_articles:
        text = (article.get("title", "") + " " + article.get("summary_cs", "")).lower()
        persons_in_article = [p.lower() for p in article.get("persons", [])]
        has_politician = (
            any(p in text for p in politicians)
            or any(p in politicians for p in persons_in_article)
        )
        if has_politician:
            keep_krimi.append(article)
        else:
            move_krimi.append(article)
    if move_krimi:
        analysis["categories"]["kriminalita"] = keep_krimi
        moved += len(move_krimi)
        logger.info(f"Kriminalita filter: kept {len(keep_krimi)}, discarded {len(move_krimi)}")

    if moved:
        logger.info(f"Category filters: moved {moved} articles to 'ostatni' total")

    return analysis


KOMUNALNI_KEYWORDS = [
    "zastupitel", "rada města", "radnice", "magistrát", "primátor", "hejtman",
    "koalice", "opozice", "volby", "zastupitelstvo", "radní", "starosta",
    "vedení města", "vedení brna", "brněnská radnice", "investice města",
    "schválil", "schválila", "schválilo", "hlasoval", "hlasování",
    "rozpočet", "dotace", "projekt města", "město brno",
]

def filter_managerske_shrnuti(analysis: dict, config: dict) -> dict:
    """Keep only truly communal-political items in managerske_shrnuti."""
    ms = analysis.get("managerske_shrnuti")
    if not ms:
        return analysis

    politicians = [p.lower() for p in config["watched_names"].get("politicians", [])]

    def is_political(text: str) -> bool:
        t = text.lower()
        return any(kw in t for kw in KOMUNALNI_KEYWORDS) or any(p in t for p in politicians)

    # Filter hlavni_body — keep only political items, normalize to {text, link} objects
    raw_body = ms.get("hlavni_body", [])
    filtered = []
    for item in raw_body:
        if isinstance(item, dict):
            text = item.get("text", "")
            link = item.get("link", "")
        else:
            text = str(item)
            link = ""
        if text and is_political(text):
            filtered.append({"text": text, "link": link})
    ms["hlavni_body"] = filtered[:3]

    # If no political body items, try to fill from top komunalni_politika articles
    if not ms["hlavni_body"]:
        top_articles = analysis.get("categories", {}).get("komunalni_politika", [])
        for art in top_articles[:3]:
            ms["hlavni_body"].append({
                "text": art.get("summary_cs") or art.get("title", ""),
                "link": art.get("link", ""),
            })

    # Adjust importance level
    has_persons = bool([p for p in ms.get("sledovane_osoby_dnes", []) if p])
    has_komunalni = bool(analysis.get("categories", {}).get("komunalni_politika"))
    if has_persons or (has_komunalni and ms["hlavni_body"]):
        ms["uroven_dulezitosti"] = "vysoka"
    elif has_komunalni:
        ms["uroven_dulezitosti"] = "stredni"
    else:
        ms["uroven_dulezitosti"] = "nizka"
        ms["hlavni_body"] = []

    analysis["managerske_shrnuti"] = ms
    return analysis


def build_analysis_prompt(articles: list, config: dict) -> str:
    watched_politicians = config["watched_names"]["politicians"]
    watched_other = get_watched_other_names(config)
    high_priority = config["analysis_focus"]["high_priority"]
    medium_priority = config["analysis_focus"]["medium_priority"]

    articles_text = ""
    for i, article in enumerate(articles, 1):
        articles_text += f"""
---
CLANEK {i}:
Zdroj: {article['source']}
Titulek: {article['title']}
Odkaz: {article['link']}
Datum: {article['published']}
Shrnuti: {article['summary'][:500]}
"""

    prompt = f"""Jsi analytik zpravodajstvi zamereny na Brno a Jihomoravsky kraj. Analyzuj nasledujici seznam clanku a vrat strukturovany JSON.

SLEDOVANE OSOBY (politici):
{', '.join(watched_politicians)}

SLEDOVANE SUBJEKTY:
{', '.join(watched_other)}

TEMATA VYSOKE PRIORITY (komunalni politika):
{', '.join(high_priority)}

TEMATA STREDNI PRIORITY:
{', '.join(medium_priority)}

CLANKY K ANALYZE:
{articles_text}

INSTRUKCE:
1. Kazdy clanek zar do JEDNE primarni kategorie: komunalni_politika, doprava, kultura, sport, kriminalita, ekonomika, zdravotnictvi, skolstvi, zivotni_prostredi, ostatni
2. Priraď relevanci 1-10 (10 = velmi dulezite pro Brno)
3. Identifikuj zminky sledovanych osob a subjektu
4. Vytvor kratke ceske shrnuti kazdeho clanku (max 150 znaku)
5. Ignoruj clanky bez vztahu k Brnu nebo JMK
6. Pole "managerske_shrnuti": Toto je manažerský briefing PRO KOMUNÁLNÍ POLITIKU BRNA. Zaměř se VÝHRADNĚ na věci relevantní pro komunální politiku a veřejnou správu. Pravidla:
   - hlavni_body: PŘESNĚ 3 položky (nebo méně pokud není dost politicky relevantních zpráv), každá jako objekt s "text" (jedna stručná věta co se stalo) a "link" (URL přímo odpovídajícího článku ze seznamu výše). POUZE komunální politika: rozhodnutí rady/zastupitelstva, investice města, klíčové projekty, zmínky sledovaných politiků, závažné věci fungování Brna. NEZAHRNUJ obecnou dopravu, ekonomiku, kulturu ani sport. Pokud takové zprávy NEJSOU, pole nech PRÁZDNÉ [].
   - uroven_dulezitosti: "vysoka" = jsou komunálněpolitické zprávy nebo zmínky sledovaných osob; "stredni" = jsou důležité infrastrukturní zprávy dotýkající se rozhodnutí města; "nizka" = žádné komunálně-politické zprávy.
   - sledovane_osoby_dnes: jen jména ze seznamu SLEDOVANYCH OSOB která se SKUTEČNĚ vyskytují v článcích tohoto batche.
7. Kategorie "doprava": zahrn VŠECHNY clanky tykajici se dopravy v sirokem smyslu — auta, MHD, tramvaje, autobusy, vlaky, ale TAKÉ cyklisticka doprava, cyklostezky, chodci, pesi zona, chodnik, prechody pro chodce. Vse co se tyka pohybu lidi a vozidel po meste.
8. Kategorie "sport": zahrn POUZE clanky tykajici se stadionu, sportovni haly nebo jejich vystavby/rekonstrukce (napr. hala Komety, fotbalovy stadion Za Luzankami). Ostatni sportovni zpravy (vysledky zapasu, prestupy hracu apod.) uplne vynech — do zadne kategorie je nezarazuj.
7. Kategorie "kriminalita": zahrn POUZE clanky, kde je kriminalita spojena s nekterym ze sledovanych politiku nebo verejnych cinitel. Beznou kriminalitu (kradeze, nehody, nasilne trestne ciny bez politickeho kontextu) uplne vynech — do zadne kategorie ji nezarazuj.

VRAT POUZE VALIDNI JSON v tomto formatu (bez markdown backticks):
{{
  "analyzed_at": "ISO datetime",
  "categories": {{
    "komunalni_politika": [
      {{
        "title": "...",
        "link": "...",
        "source": "...",
        "published": "...",
        "summary_cs": "kratke ceske shrnuti",
        "relevance": 8,
        "persons": ["Marketa Vankova"],
        "tags": ["zastupitelstvo", "koalice"]
      }}
    ],
    "doprava": [],
    "kultura": [],
    "sport": [],
    "kriminalita": [],
    "ekonomika": [],
    "zdravotnictvi": [],
    "skolstvi": [],
    "zivotni_prostredi": [],
    "ostatni": []
  }},
  "person_mentions": {{
    "Marketa Vankova": [
      {{"title": "...", "link": "...", "context": "kratky kontext"}}
    ]
  }},
  "managerske_shrnuti": {{
    "uroven_dulezitosti": "vysoka|stredni|nizka",
    "hlavni_body": [
      {{"text": "Jedna věta co se stalo.", "link": "https://url-clanku"}},
      {{"text": "Druhá věta co se stalo.", "link": "https://url-clanku"}},
      {{"text": "Třetí věta co se stalo.", "link": "https://url-clanku"}}
    ],
    "sledovane_osoby_dnes": ["jméno osoby pokud se vyskytuje ve zprávách, jinak prázdné pole"]
  }},
  "stats": {{
    "total_analyzed": 0,
    "total_relevant": 0,
    "komunalni_politika_count": 0,
    "top_persons": ["..."],
    "top_topics": ["..."]
  }}
}}"""

    return prompt


def extract_json(text: str) -> dict:
    """Extract and parse JSON from Claude response, handling markdown and extra text."""
    text = text.strip()

    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[: text.rfind("```")]
        text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Extract the outermost JSON object (handles extra text before/after)
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError("Could not extract valid JSON", text, 0)


def analyze_batch(client: anthropic.Anthropic, articles: list, config: dict) -> dict:
    model = config["settings"]["summary_model"]
    prompt = build_analysis_prompt(articles, config)

    logger.info(f"Sending {len(articles)} articles to Claude API (model: {model})")

    for attempt in range(2):
        message = client.messages.create(
            model=model,
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )
        response_text = message.content[0].text
        try:
            result = extract_json(response_text)
            break
        except json.JSONDecodeError as e:
            if attempt == 0:
                logger.warning(f"JSON parse failed (attempt 1), retrying: {e}")
            else:
                raise

    # Apply keyword filters (e.g. Kometa/Zbrojovka only for stadium mentions)
    keyword_filters = get_keyword_filters(config)
    if keyword_filters:
        result = apply_keyword_filters(result, keyword_filters)

    # Post-process: filter sport and kriminalita categories
    result = apply_category_filters(result, config)

    # Post-process: keep only political content in managerske_shrnuti
    result = filter_managerske_shrnuti(result, config)

    return result


def merge_analysis_results(results: list) -> dict:
    if len(results) == 1:
        return results[0]

    merged = {
        "analyzed_at": results[0]["analyzed_at"],
        "categories": {
            "komunalni_politika": [],
            "doprava": [],
            "kultura": [],
            "sport": [],
            "kriminalita": [],
            "ekonomika": [],
            "zdravotnictvi": [],
            "skolstvi": [],
            "zivotni_prostredi": [],
            "ostatni": [],
        },
        "person_mentions": {},
        "managerske_shrnuti": results[0].get("managerske_shrnuti", {}),
        "stats": {
            "total_analyzed": 0,
            "total_relevant": 0,
            "komunalni_politika_count": 0,
            "top_persons": [],
            "top_topics": [],
        },
    }

    for result in results:
        for category, articles in result.get("categories", {}).items():
            if category in merged["categories"]:
                merged["categories"][category].extend(articles)

        for person, mentions in result.get("person_mentions", {}).items():
            if person not in merged["person_mentions"]:
                merged["person_mentions"][person] = []
            merged["person_mentions"][person].extend(mentions)

        stats = result.get("stats", {})
        merged["stats"]["total_analyzed"] += stats.get("total_analyzed", 0)
        merged["stats"]["total_relevant"] += stats.get("total_relevant", 0)
        merged["stats"]["komunalni_politika_count"] += stats.get(
            "komunalni_politika_count", 0
        )

        # Merge managerske_shrnuti: first batch is primary, subsequent batches add unique body points
        ms = result.get("managerske_shrnuti", {})
        existing_ms = merged["managerske_shrnuti"]
        if ms.get("hlavni_body"):
            existing_body = existing_ms.get("hlavni_body", [])
            existing_text = {
                (b["text"] if isinstance(b, dict) else b).lower()[:40]
                for b in existing_body
            }
            for bod in ms["hlavni_body"]:
                text = (bod["text"] if isinstance(bod, dict) else bod).lower()[:40]
                if text not in existing_text:
                    existing_body.append(bod)
                    existing_text.add(text)
            existing_ms["hlavni_body"] = existing_body
        if ms.get("sledovane_osoby_dnes") and existing_ms.get("sledovane_osoby_dnes"):
            existing_ms["sledovane_osoby_dnes"] = list(set(
                existing_ms["sledovane_osoby_dnes"] + ms["sledovane_osoby_dnes"]
            ))
        # Use highest priority level
        priority_order = {"vysoka": 3, "stredni": 2, "nizka": 1}
        if priority_order.get(ms.get("uroven_dulezitosti", "nizka"), 0) > priority_order.get(existing_ms.get("uroven_dulezitosti", "nizka"), 0):
            existing_ms["uroven_dulezitosti"] = ms["uroven_dulezitosti"]
            existing_ms["nejdulezitejsi_zprava"] = ms.get("nejdulezitejsi_zprava", "")

    # Sort articles in each category by relevance
    for category in merged["categories"]:
        merged["categories"][category].sort(
            key=lambda x: x.get("relevance", 0), reverse=True
        )

    return merged


def main():
    parser = argparse.ArgumentParser(description="Analyze articles with Claude API")
    parser.add_argument(
        "--run",
        choices=["daily", "manual"],
        default="manual",
    )
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY environment variable not set")
        sys.exit(1)

    logger.info(f"Starting analysis - run type: {args.run}")

    config = load_config()
    articles, run_dir_str = load_articles(config, args.run)

    if not articles:
        logger.warning("No articles to analyze")
        # Create empty analysis result
        empty_result = {
            "analyzed_at": datetime.now().isoformat(),
            "run_type": args.run,
            "categories": {
                cat: []
                for cat in [
                    "komunalni_politika",
                    "doprava",
                    "kultura",
                    "sport",
                    "kriminalita",
                    "ekonomika",
                    "zdravotnictvi",
                    "skolstvi",
                    "zivotni_prostredi",
                    "ostatni",
                ]
            },
            "person_mentions": {},
            "stats": {
                "total_analyzed": 0,
                "total_relevant": 0,
                "komunalni_politika_count": 0,
                "top_persons": [],
                "top_topics": [],
            },
        }
        if run_dir_str:
            run_dir = Path(run_dir_str)
            analysis_file = run_dir / "analysis.json"
        else:
            data_dir = SCRIPT_DIR / config["settings"]["data_dir"]
            analysis_file = data_dir / f"latest_analysis_{args.run}.json"

        with open(analysis_file, "w", encoding="utf-8") as f:
            json.dump(empty_result, f, ensure_ascii=False, indent=2)

        # Also write the pointer file
        data_dir = SCRIPT_DIR / config["settings"]["data_dir"]
        latest_analysis_file = data_dir / f"latest_analysis_{args.run}.json"
        with open(latest_analysis_file, "w") as f:
            json.dump(
                {
                    "analysis_file": str(analysis_file),
                    "analyzed_at": empty_result["analyzed_at"],
                },
                f,
            )
        return 0

    client = anthropic.Anthropic(api_key=api_key)

    # Process in batches of 30 articles
    BATCH_SIZE = 30
    batches = [articles[i : i + BATCH_SIZE] for i in range(0, len(articles), BATCH_SIZE)]
    logger.info(f"Processing {len(articles)} articles in {len(batches)} batch(es)")

    results = []
    for i, batch in enumerate(batches, 1):
        logger.info(f"Processing batch {i}/{len(batches)} ({len(batch)} articles)")
        try:
            result = analyze_batch(client, batch, config)
            results.append(result)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude response as JSON: {e}")
            continue
        except anthropic.APIError as e:
            logger.error(f"Claude API error: {e}")
            continue
        except Exception as e:
            logger.error(f"Unexpected error in batch {i}: {e}")
            continue

    if not results:
        logger.error("All batches failed")
        sys.exit(1)

    final_result = merge_analysis_results(results)
    final_result["run_type"] = args.run
    final_result["analyzed_at"] = datetime.now().isoformat()

    # Save to run dir
    run_dir = Path(run_dir_str)
    analysis_file = run_dir / "analysis.json"
    with open(analysis_file, "w", encoding="utf-8") as f:
        json.dump(final_result, f, ensure_ascii=False, indent=2)

    # Save latest analysis pointer
    data_dir = SCRIPT_DIR / config["settings"]["data_dir"]
    latest_analysis_file = data_dir / f"latest_analysis_{args.run}.json"
    with open(latest_analysis_file, "w") as f:
        json.dump(
            {
                "analysis_file": str(analysis_file),
                "analyzed_at": final_result["analyzed_at"],
            },
            f,
        )

    total = final_result["stats"]["total_relevant"]
    politik = final_result["stats"]["komunalni_politika_count"]
    logger.info(
        f"Analysis complete: {total} relevant articles, {politik} politics articles"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
