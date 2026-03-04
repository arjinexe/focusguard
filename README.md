<div align="center">

<img src="https://img.shields.io/badge/FocusGuard-v5.1.1-blue?style=for-the-badge" />

# FocusGuard

**Local distraction detection and focus enforcement engine**

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/focusguard?style=flat-square&color=green)](https://pypi.org/project/focusguard/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey?style=flat-square)]()

[English](#english) · [Türkçe](#türkçe)

</div>

---

## English

### What is FocusGuard?

FocusGuard is a **privacy-first, fully local** focus enforcement tool. It watches your screen and — when it detects that you are wasting time — fires a series of escalating resistance mechanisms designed to pull you back to work.

Everything runs on your own machine. No account, no cloud, no telemetry. Your data never leaves your computer.

---

### How Detection Works

FocusGuard monitors only the **active foreground window** — the one you are currently looking at. A background tab with Instagram open while you are coding on GitHub will **never** trigger an alert.

Detection runs through a layered pipeline, fastest first:

| # | Method | What it checks |
|---|--------|----------------|
| 1 | **Process name** | Is the foreground app a known IDE, terminal, editor, or work tool? |
| 2 | **Window title — productive** | Does the browser title contain a productive site name (GitHub, Claude, Notion…)? |
| 3 | **Window title — distraction** | Does the browser title contain a distraction site name (Instagram, TikTok, Netflix…)? |
| 4 | **YouTube title** | Is the video title a game, meme, or entertainment content? |
| 5 | **Fullscreen detection** | Is an unknown app filling the entire screen (game, video player)? |
| 6 | **Detection cache** | Has this exact window context been classified before? |
| 7 | **OCR — address bar** | Read the actual URL from the browser address bar |
| 8 | **Ollama vision model** | AI analysis of page content (tab bar cropped out) |

Layers 1–3 resolve the vast majority of cases **instantly, without taking a screenshot**. OCR and Ollama only run for genuinely ambiguous contexts.

> **Key insight:** Productive keywords are checked *before* distraction keywords. A title like `"Twitter API changes · issue · GitHub"` is always clean — `"github"` matches first and the pipeline stops.

---

### Features

- 🔍 **Multi-layer detection** — window title, OCR, and optional local AI vision
- 🖱 **Escalating resistance** — mouse jitter, screen dim, overlay warnings, terminal messages, sound alerts, fullscreen text blast
- 🍅 **Pomodoro timer** — built-in work/break cycle with long break support
- 📊 **Deep Work Index** — session-end quality score based on focus time, detection count, and clean streaks
- 😴 **Idle detection** — auto-pauses when you walk away (screen freeze, mouse, keyboard)
- 📈 **Per-app analytics** — tracks which applications consumed your session time
- ⚡ **Detection cache** — avoids re-analyzing the same site repeatedly
- 🏆 **Gamification** — XP system and 13 achievements to reward sustained focus
- 🎵 **Ambient sounds** — rain, café, white noise, binaural beats
- 🎯 **Session intentions** — declare what you are working on before you start
- 👻 **Stealth / Ghost mode** — run silently or log only without firing resistance
- 🌍 **Bilingual UI** — English and Turkish
- 🔒 **Fully offline** — no cloud, no account, no telemetry

---

### Requirements

- Python 3.9 or later
- Windows 10+, macOS 11+, or Linux (X11)

---

### Installation

**From PyPI (recommended)**

```bash
pip install focusguard
focusguard
```

**From source**

```bash
git clone https://github.com/arjinexe/focusguard.git
cd focusguard
pip install -r requirements.txt
python -m focusguard
```

**macOS — extra step**

```bash
brew install python-tk
```

**Linux — extra step**

```bash
sudo apt install python3-tk scrot libxcb-xinerama0 libgl1 xdotool
```

---

### Optional: Ollama Vision Model

Ollama enables deep content analysis for ambiguous cases where the window title alone is not enough.

```bash
# 1. Install Ollama — https://ollama.com
# 2. Pull the model
ollama pull moondream
```

FocusGuard auto-detects Ollama on startup. No configuration needed.

---

### Usage

```bash
# GUI (default)
focusguard

# Headless terminal mode
focusguard --cli

# Start minimized to tray
focusguard --minimized
```

**All options:**

```
focusguard [--cli] [--minimized] [--lang en|tr]
           [--interval SECONDS] [--threshold 0.0-1.0]
           [--model MODEL_NAME] [--log-level DEBUG|INFO|WARNING]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--cli` | — | Headless terminal mode |
| `--minimized` | — | Start minimized to tray |
| `--lang` | `en` | UI language (`en` or `tr`) |
| `--interval` | `1.5` | Capture interval in seconds |
| `--threshold` | `0.55` | Detection confidence threshold (0–1) |
| `--model` | `moondream` | Ollama model name |
| `--log-level` | `INFO` | Logging verbosity |

---

### Configuration

Settings are saved automatically. You can change them through the GUI Settings panel or directly in `settings.json` in your user data folder.

| Setting | Default | Description |
|---------|---------|-------------|
| `confidence_threshold` | `0.55` | Minimum score to flag as distraction |
| `min_dirty_streak` | `2` | Consecutive positives before alerting |
| `screenshot_interval` | `1.5s` | How often the screen is analyzed |
| `strict_mode` | `false` | Lowers threshold, increases frequency |
| `ghost_mode` | `false` | Log only, no resistance |
| `stealth_mode` | `false` | Run silently in background |

---

### Project Structure

```
focusguard/
├── focusguard/
│   ├── __main__.py           Entry point
│   ├── config.py             Configuration and all keyword lists
│   ├── i18n.py               Internationalisation
│   ├── paths.py              Platform data/log paths
│   ├── modules/
│   │   ├── session.py        Session manager and detection pipeline
│   │   ├── analyzer.py       Hybrid analysis (CV + OCR + Ollama)
│   │   ├── screen_capture.py MSS-based screen capture
│   │   ├── window_tracker.py Active window tracking
│   │   ├── resistance.py     Resistance mechanisms
│   │   ├── fullscreen.py     Fullscreen detection
│   │   ├── detection_cache.py Persistent result cache
│   │   ├── idle_detector.py  User idle detection
│   │   ├── analytics.py      Deep Work Index and session stats
│   │   ├── intentions.py     Pre-session intention tracking
│   │   ├── ambient.py        Ambient sound playback
│   │   └── gui.py            CustomTkinter UI
│   └── locales/
│       ├── en.py             English strings
│       └── tr.py             Turkish strings
├── tests/
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

### Contributing

Pull requests are welcome. For major changes, please open an issue first.

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit your changes: `git commit -m "Add my feature"`
4. Push: `git push origin feature/my-feature`
5. Open a Pull Request

---

### License

MIT — see [LICENSE](LICENSE).

---

## Türkçe

### FocusGuard Nedir?

FocusGuard, **gizlilik odaklı ve tamamen yerel** çalışan bir odak takip aracıdır. Ekranınızı izler ve zaman kaybettiğinizi tespit ettiğinde sizi tekrar çalışmaya döndürmek için bir dizi artan yoğunlukta direnç mekanizması devreye sokar.

Her şey kendi bilgisayarınızda çalışır. Hesap yok, bulut yok, telemetri yok. Hiçbir veriniz internet'e gönderilmez.

---

### Tespit Nasıl Çalışır?

FocusGuard yalnızca **aktif ön planda açık olan pencereyi** izler — o an baktığınız şeyi. Instagram'ı arka sekmede açık tutup GitHub'da çalışıyorsanız **hiçbir uyarı gelmez**.

Tespit, en hızlıdan başlayarak katmanlı bir süreçten geçer:

| # | Yöntem | Ne Kontrol Eder |
|---|--------|-----------------|
| 1 | **Uygulama adı** | Ön plandaki uygulama bir IDE, terminal ya da iş aracı mı? |
| 2 | **Pencere başlığı — verimli** | Tarayıcı başlığında bilinen bir verimli site adı var mı (GitHub, Claude, Notion…)? |
| 3 | **Pencere başlığı — dikkat dağıtıcı** | Tarayıcı başlığında bilinen bir dikkat dağıtıcı site adı var mı (Instagram, TikTok, Netflix…)? |
| 4 | **YouTube başlığı** | Video başlığı oyun, meme ya da eğlence içeriği mi? |
| 5 | **Tam ekran tespiti** | Bilinmeyen bir uygulama ekranı tamamen kaplıyor mu? |
| 6 | **Tespit önbelleği** | Bu pencere bağlamı daha önce sınıflandırıldı mı? |
| 7 | **OCR — adres çubuğu** | Tarayıcı adres çubuğundaki URL okunur |
| 8 | **Ollama görsel modeli** | Sayfa içeriği yapay zeka ile analiz edilir (sekme çubuğu kırpılır) |

1–3 arası katmanlar vakaların büyük çoğunluğunu **ekran görüntüsü almadan, anında** çözümler.

> **Temel tasarım:** Verimli anahtar kelimeler, dikkat dağıtıcı olanlardan **önce** kontrol edilir. `"Twitter API değişiklikleri · GitHub"` gibi bir başlık her zaman temiz sayılır — `"github"` eşleşir ve pipeline durur.

---

### Özellikler

- 🔍 **Çok katmanlı tespit** — pencere başlığı, OCR ve isteğe bağlı yerel yapay zeka
- 🖱 **Artan direnç mekanizmaları** — fare titreyişi, ekran kararma, uyarı bindirmesi, terminal mesajları, ses uyarısı
- 🍅 **Pomodoro zamanlayıcı** — çalışma/mola döngüsü, uzun mola desteği
- 📊 **Derin Çalışma İndeksi** — odak süresi ve tespit sayısına dayalı oturum sonu kalite skoru
- 😴 **Boşta kalma tespiti** — ekran donması, fare ve klavye üzerinden otomatik duraklatma
- 📈 **Uygulama başına analitik** — hangi uygulama ne kadar zaman aldı
- ⚡ **Tespit önbelleği** — aynı siteyi defalarca analiz etmez
- 🏆 **Oyunlaştırma** — XP sistemi ve 13 başarım
- 🎵 **Ortam sesleri** — yağmur, kafe, beyaz gürültü
- 🎯 **Oturum niyetleri** — başlamadan önce ne yapacağını belirt
- 👻 **Gizli / Hayalet mod** — sessizce çalış ya da yalnızca kayıt tut
- 🌍 **İki dil desteği** — Türkçe ve İngilizce
- 🔒 **Tamamen çevrimdışı** — bulut yok, hesap yok, telemetri yok

---

### Gereksinimler

- Python 3.9 veya üstü
- Windows 10+, macOS 11+ veya Linux (X11)

---

### Kurulum

**PyPI üzerinden (önerilen)**

```bash
pip install focusguard
focusguard
```

**Kaynak koddan**

```bash
git clone https://github.com/arjinexe/focusguard.git
cd focusguard
pip install -r requirements.txt
python -m focusguard
```

**macOS için ek adım**

```bash
brew install python-tk
```

**Linux için ek adım**

```bash
sudo apt install python3-tk scrot libxcb-xinerama0 libgl1 xdotool
```

---

### İsteğe Bağlı: Ollama Görsel Modeli

Pencere başlığının yeterli olmadığı belirsiz durumlar için derin içerik analizi sağlar.

```bash
# 1. Ollama'yı kur — https://ollama.com
# 2. Modeli indir
ollama pull moondream
```

FocusGuard, Ollama'yı başlangıçta otomatik olarak algılar.

---

### Kullanım

```bash
# Arayüzlü mod (varsayılan)
focusguard

# Terminalde arayüzsüz çalıştır
focusguard --cli

# Sistem tepsisine küçültülmüş başlat
focusguard --minimized

# Dil ayarı
focusguard --lang tr
```

---

### Katkı

Pull request'ler memnuniyetle karşılanır. Büyük değişiklikler için önce issue açınız.

---

### Lisans

MIT — bkz. [LICENSE](LICENSE).

---

<div align="center">

Made with focus by [arjinexe](https://github.com/arjinexe)

</div>
