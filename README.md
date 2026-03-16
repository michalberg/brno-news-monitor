# Zelený radar

Automatický systém pro sledování brněnského zpravodajství s důrazem na komunální politiku. Každý den v 7:00 stahuje RSS feedy, scrapuje weby a Google Alerts, analyzuje obsah pomocí Claude AI a generuje přehledné HTML stránky publikované přes GitHub Pages.

**Web:** https://michalberg.github.io/brno-news-monitor/

## Funkce

- **Automatické stahování** – RSS feedy, webové zdroje bez RSS (Brněnská Drbna, Novinky.cz) a Google Alerts
- **AI analýza** – Claude Haiku kategorizuje každý článek, přiřazuje relevanci 1–10, identifikuje sledované osoby a tvoří česká shrnutí
- **Manažerské shrnutí dne** – 3 nejdůležitější věci z komunální politiky s přímými odkazy
- **Sledování osob** – Monitorování zmínek politiků a dalších subjektů (Kometa, Zbrojovka, DPMB aj.)
- **Emailové notifikace** – Přehled odesílán každý den na nakonfigurovaný email
- **Deduplication** – Každý článek zobrazen pouze jednou i při opakovaném spuštění
- **GitHub Pages** – Výsledky automaticky publikovány jako statické HTML
- **Archiv** – Měsíční kalendář s proklikávatelnými dny

## Požadavky

- Python 3.11+
- Anthropic API klíč (Claude Haiku)
- GitHub repozitář s GitHub Pages nakonfigurovaným na větev `main`, složka `/docs`
- SMTP účet pro emailové notifikace

## Lokální spuštění

```bash
git clone https://github.com/michalberg/brno-news-monitor.git
cd brno-news-monitor

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

export ANTHROPIC_API_KEY="sk-ant-..."
export SMTP_USER="radar.brno@zeleni.cz"
export SMTP_PASSWORD="..."

python scripts/fetch_rss.py --run manual
python scripts/analyze.py --run manual
python scripts/generate_html.py --run manual
python scripts/send_email.py --run manual  # volitelné
```

Vygenerované stránky jsou v adresáři `docs/`.

## Nastavení GitHub Secrets

**Settings → Secrets and variables → Actions:**

| Secret | Popis |
|--------|-------|
| `ANTHROPIC_API_KEY` | Anthropic API klíč z console.anthropic.com |
| `SMTP_USER` | Email odesílatele (`radar.brno@zeleni.cz`) |
| `SMTP_PASSWORD` | SMTP heslo |

## Nastavení GitHub Pages (jednorázově)

1. **Settings → Pages**
2. Source: **Deploy from a branch**
3. Branch: `main`, složka: `/docs`
4. Uložit

Po nastavení se web automaticky aktualizuje po každém denním běhu.

## Konfigurace

Vše se konfiguruje v `config/sources.yaml`:

- **`rss_sources`** – RSS feedy médií a úřadů
- **`google_alerts`** – Google Alerts RSS pro osoby a témata
- **`web_scrape`** – Weby bez RSS (regex pattern pro extrakci odkazů)
- **`watched_names.politicians`** – Seznam sledovaných politiků
- **`watched_names.other`** – Další subjekty (volitelně s `only_with_keywords`)
- **`notifications`** – SMTP nastavení a seznam příjemců
- **`settings.base_url`** – Veřejná URL webu (pro správné odkazy v emailu)

### Přidání RSS zdroje

```yaml
rss_sources:
  - name: "Název zdroje"
    url: "https://priklad.cz/rss.xml"
    category: "media"
```

### Přidání sledované osoby

```yaml
watched_names:
  politicians:
    - "Jméno Příjmení"
```

## Struktura projektu

```
brno-news-monitor/
├── config/
│   └── sources.yaml          # Konfigurace zdrojů, osob, SMTP, base_url
├── scripts/
│   ├── fetch_rss.py          # Stahování RSS, Google Alerts a web scraping
│   ├── analyze.py            # Analýza článků přes Claude API
│   ├── generate_html.py      # Generování HTML z Jinja2 šablon
│   └── send_email.py         # Odesílání emailových notifikací
├── templates/
│   ├── daily.html            # Denní přehled
│   ├── month.html            # Měsíční kalendář
│   └── index.html            # Hlavní stránka
├── docs/                     # Výstup pro GitHub Pages
│   ├── index.html
│   ├── YYYY/MM/DD.html       # Denní přehledy
│   └── assets/               # CSS a JS
├── data/                     # Surová data a cache (seen_urls.json)
├── .github/workflows/
│   └── daily.yml             # Cron workflow – každý den 7:00 CET
├── requirements.txt
└── .gitignore
```

## Pipeline

1. **GitHub Actions** spustí `daily.yml` každý den v 7:00 CET
2. `fetch_rss.py` stáhne zdroje, odfiltruje duplicity a uloží `articles.json`
3. `analyze.py` odešle články v dávkách (max 30) do Claude Haiku, výsledek uloží jako `analysis.json`
4. `generate_html.py` vygeneruje `docs/YYYY/MM/DD.html`, měsíční přehled a `index.html`
5. `send_email.py` odešle HTML přehled na nakonfigurovaný email
6. Workflow commitne `docs/` a `data/` a pushne do `main`
7. GitHub Pages automaticky publikuje nový obsah

## Řešení problémů

**Workflow selže na analýze** – Zkontrolujte secret `ANTHROPIC_API_KEY` a kredit na Anthropic účtu.

**Žádné články** – Ověřte dostupnost RSS URL. Dočasné výpadky zdrojů jsou normální.

**Email nefunguje** – Zkontrolujte secrets `SMTP_USER` a `SMTP_PASSWORD` a příjemce v `config/sources.yaml`.

**Pages ukazují README** – Zkontrolujte Settings → Pages, zda je source nastaven na branch `main`, složka `/docs`.
