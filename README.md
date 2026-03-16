# Zelený radar

Automatický systém pro sledování brněnského zpravodajství s důrazem na komunální politiku. Každý den ráno a odpoledne stahuje RSS feedy z brněnských médií a oficiálních zdrojů, analyzuje obsah pomocí Claude AI a generuje přehledné HTML stránky publikované přes GitHub Pages.

## Funkce

- **Automatické stahování RSS feedů** – Český rozhlas Brno, Brněnský deník, iDNES Brno, Brno.cz, Jihomoravský kraj a volitelně Google Alerts
- **AI analýza obsahu** – Claude AI kategorizuje každý článek, přiřazuje relevanci 1–10, identifikuje zmínky sledovaných politiků a vytváří krátká česká shrnutí
- **Sledování osob** – Automatické monitorování zmínek konkrétních politiků (Vaňková, Grolich, Hladík, aj.)
- **Prioritní sekce** – Komunální politika je vždy zobrazena na prvním místě se zvýrazněným stylem
- **Denní přehledy** – Ranní (7:00), odpolední (14:00) a souhrnný večerní přehled (20:00)
- **Emailové notifikace** – Volitelné odesílání přehledu na email přes SMTP
- **Deduplication** – Každý článek je zobrazen pouze jednou, i při opakovaném spuštění
- **GitHub Pages** – Výsledky jsou automaticky publikovány jako statické HTML stránky
- **Archiv** – Přehledy jsou ukládány dle data a dostupné v měsíčním archivu

## Požadavky

- Python 3.11+
- Anthropic API klíč (Claude)
- GitHub repozitář s povoleným GitHub Pages
- Volitelně: SMTP účet pro emailové notifikace (např. Gmail App Password)

## Instalace a lokální spuštění

```bash
# Naklonujte repozitář
git clone https://github.com/VAS_UZIVATEL/zeleny-radar.git
cd zeleny-radar

# Vytvořte virtuální prostředí
python3 -m venv venv
source venv/bin/activate  # Na Windows: venv\Scripts\activate

# Nainstalujte závislosti
pip install -r requirements.txt

# Nastavte environment variables
export ANTHROPIC_API_KEY="sk-ant-..."
export SMTP_USER="vas@gmail.com"          # Volitelné
export SMTP_PASSWORD="app-password"       # Volitelné

# Spusťte manuálně
python scripts/fetch_rss.py --run manual
python scripts/analyze.py --run manual
python scripts/generate_html.py --run manual
```

Vygenerované HTML stránky najdete v adresáři `docs/`.

## Nastavení GitHub Secrets

V repozitáři přejděte do **Settings → Secrets and variables → Actions** a přidejte tyto secrets:

| Secret | Popis | Povinné |
|--------|-------|---------|
| `ANTHROPIC_API_KEY` | Váš Anthropic API klíč (získáte na console.anthropic.com) | Ano |
| `SMTP_USER` | Email adresa odesílatele (např. vas@gmail.com) | Ne |
| `SMTP_PASSWORD` | SMTP heslo nebo Gmail App Password | Ne |

### Jak získat Gmail App Password

1. Přejděte na [myaccount.google.com/security](https://myaccount.google.com/security)
2. Zapněte dvoufaktorové ověření
3. V sekci "Přihlašování do Googlu" klikněte na "Hesla aplikací"
4. Vytvořte nové heslo pro "Pošta" a "Jiné zařízení" (název: Zelený radar)
5. Vygenerované 16znakové heslo použijte jako `SMTP_PASSWORD`

## Nastavení GitHub Pages

1. Přejděte do **Settings → Pages**
2. Pod "Source" vyberte **Deploy from a branch**
3. Vyberte větev `main` a adresář `/docs`
4. Uložte – stránky budou dostupné na `https://VAS_UZIVATEL.github.io/zeleny-radar/`

## Nastavení Google Alerts

Google Alerts umožňuje sledovat libovolná klíčová slova a dostávat RSS feed s výsledky.

1. Přejděte na [google.com/alerts](https://www.google.com/alerts)
2. Zadejte hledaný výraz (např. `"Brno zastupitelstvo"`)
3. Klikněte na "Zobrazit možnosti" a nastavte:
   - Jak často: "Okamžitě" nebo "Jednou denně"
   - Zdroje: "Zprávy"
   - Jazyk: čeština
   - Oblast: Česká republika
4. Pod "Doručovat do" vyberte **RSS feed**
5. Klikněte na "Vytvořit upozornění"
6. Klikněte na ikonu RSS u vytvořeného alertu a zkopírujte URL
7. Vložte URL do `config/sources.yaml` místo `DOPLNIT_GOOGLE_ALERTS_RSS_URL`

## Přidání nových zdrojů

Upravte soubor `config/sources.yaml` – sekce `rss_sources`:

```yaml
rss_sources:
  - name: "Název zdroje"
    url: "https://priklad.cz/rss.xml"
    category: "media"  # nebo "official", "topic"
```

## Sledované osoby

V souboru `config/sources.yaml` upravte sekci `watched_names`:

```yaml
watched_names:
  politicians:
    - "Jméno Příjmení"
  other:
    - "Název organizace"
```

## Emailové notifikace

Zapněte a nakonfigurujte v `config/sources.yaml`:

```yaml
notifications:
  enabled: true
  recipients:
    - "vas@email.cz"
  smtp:
    host: "smtp.gmail.com"
    port: 587
    use_tls: true
```

Nezapomeňte nastavit GitHub Secrets `SMTP_USER` a `SMTP_PASSWORD`.

## Struktura projektu

```
zeleny-radar/
├── config/
│   └── sources.yaml          # Konfigurace zdrojů, sledovaných osob, nastavení
├── scripts/
│   ├── fetch_rss.py          # Stahování RSS feedů
│   ├── analyze.py            # Analýza článků pomocí Claude API
│   ├── generate_html.py      # Generování HTML stránek z Jinja2 šablon
│   ├── send_email.py         # Odesílání emailových notifikací
│   └── daily_summary.py      # Orchestrace denního souhrnu
├── templates/
│   ├── daily.html            # Šablona pro denní přehled
│   ├── month.html            # Šablona pro měsíční přehled
│   └── index.html            # Šablona pro hlavní stránku
├── docs/                     # Výstupní adresář (GitHub Pages)
│   ├── index.html            # Hlavní stránka (přepisována při běhu)
│   └── assets/
│       ├── style.css         # CSS styly
│       └── script.js         # JavaScript
├── data/                     # Data z jednotlivých běhů (gitignore)
│   └── .gitkeep
├── .github/
│   └── workflows/
│       ├── morning.yml       # Ranní workflow (07:00 CET)
│       ├── afternoon.yml     # Odpolední workflow (14:00 CET)
│       └── daily-summary.yml # Denní souhrn (20:00 CET)
├── requirements.txt
├── .gitignore
└── README.md
```

## Jak funguje pipeline

1. **GitHub Actions** spustí workflow dle cronu
2. `fetch_rss.py` stáhne všechny RSS feedy a uloží nové články do `data/YYYY/MM/DD/HH-MM/articles.json`
3. `analyze.py` odešle články v dávkách (max 30) do Claude API, které je kategorizuje, přiřadí relevanci a identifikuje osoby; výsledek uloží do `analysis.json`
4. `generate_html.py` načte analýzu a vygeneruje HTML stránky do `docs/` pomocí Jinja2 šablon
5. `send_email.py` odešle HTML přehled emailem (volitelné)
6. GitHub Actions commitne změny v `docs/` a `data/` do repozitáře
7. GitHub Pages automaticky publikuje nový obsah

## Řešení problémů

**Workflow selže na "Analyze articles"**
- Zkontrolujte, zda je správně nastaven secret `ANTHROPIC_API_KEY`
- Ověřte, zda má váš Anthropic účet dostatečný kredit

**Žádné články nejsou stahovány**
- Zkontrolujte dostupnost RSS URL v prohlížeči
- Některé zdroje mohou mít dočasné výpadky – to je normální

**Emailové notifikace nefungují**
- Zkontrolujte secrets `SMTP_USER` a `SMTP_PASSWORD`
- Pro Gmail: ujistěte se, že používáte App Password, ne heslo Google účtu
- Zkontrolujte, zda je v `config/sources.yaml` správně vyplněn email příjemce

**GitHub Pages nezobrazují nový obsah**
- Počkejte 1–2 minuty po commitu
- Zkontrolujte v Settings → Pages, zda je Pages správně nakonfigurováno

## Licence

MIT License – volně použitelné pro osobní i komerční účely.
