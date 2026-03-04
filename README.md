<div align="center">

# FocusGuard

**Local distraction detection and resistance engine**

[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()

[English](#english) · [Türkçe](#türkçe)

</div>

---

## English

### What is FocusGuard?

FocusGuard is a privacy-first, fully local focus enforcement tool. It watches your screen and — when it detects that you are wasting time — fires a series of escalating resistance mechanisms designed to pull you back to work.

Everything runs on your own machine. No data ever leaves your computer.

### How it works

FocusGuard continuously monitors the active foreground window. Only the window you are **currently looking at** is ever analyzed. A background tab with Instagram open while you are coding on GitHub will **never** trigger an alert — the system only cares about what is in front of you.

Detection runs through several layers, each faster than the next:

| Layer | Method | What it checks |
|-------|--------|----------------|
| 1 | Window title — productive app | Is the foreground process a known IDE, terminal, editor, or work tool? |
| 2 | Window title — productive site | Does the browser title contain a known productive site name (GitHub, Claude, Notion, …)? |
| 3 | Window title — distraction site | Does the browser title contain a known distraction site name (Instagram, TikTok, Netflix, …)? |
| 4 | YouTube video title | Is the video title entertainment or gaming? |
| 5 | Fullscreen detection | Is an unknown app filling the screen (game, video player)? |
| 6 | Detection cache | Has this exact window context been seen and classified before? |
| 7 | OCR — address bar | Read the actual URL from the browser address bar |
| 8 | Ollama vision model | AI analysis of page content with the tab bar cropped out |

Layers 1–3 resolve the vast majority of cases instantly without ever taking a screenshot. The expensive layers (OCR, Ollama) only run for genuinely ambiguous contexts.

### Key design decisions

**Only the foreground window matters.**  
FocusGuard only analyzes what you are actively viewing. It does not scan all open windows or browser tabs. If you have Twitter open in the background while you work on VS Code, nothing happens.

**Productive keyword wins over distraction keyword.**  
Layer 2 runs before Layer 3. A window title like `"Twitter API changes · issue#45 · GitHub"` is classified as clean because "github" is matched in the productive keyword list before "twitter" is evaluated in the distraction list.

**Site names, not domains.**  
Browsers embed the site *name* in the window title, not the domain. Instagram's window title reads `"Explore • Instagram"`, not `"explore.instagram.com"`. The keyword lists are built around how browsers actually format titles.

**Tab bar is cropped for Ollama.**  
When page content is sent to the vision model, the top ~8 % of the frame (where the browser tab bar lives) is removed. This means an Instagram tab sitting next to your active GitHub tab will never appear in the image Ollama analyzes.

### Features

- **Multi-layer detection** — window title, OCR, and optional local AI vision
- **Escalating resistance** — mouse jitter, screen dim, overlay warnings, terminal messages, sound alerts, fullscreen blast
- **Pomodoro timer** — built-in work/break cycle with configurable durations
- **Deep Work Index** — session-end quality score based on focus time, detection count, and clean streaks
- **Idle detection** — auto-pauses the session when the user walks away
- **Per-app analytics** — tracks which applications consumed the most of your session
- **Detection cache** — avoids re-analyzing the same site repeatedly
- **Gamification** — XP system and achievements to reward sustained focus
- **Ambient sounds** — rain, café, white noise (requires `sounddevice`)
- **Session intentions** — declare what you are working on before starting
- **Stealth / Ghost mode** — run silently or log only without firing resistance
- **Fully offline** — no cloud, no telemetry, no account

### Requirements

- Python 3.9 or later
- Windows 10+, macOS 11+, or a modern Linux distribution with X11

### Installation

**1. Clone the repository**

```bash
git clone https://github.com/your-username/focusguard.git
cd focusguard
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

On **macOS**, you may also need:

```bash
brew install python-tk
```

On **Linux**, install the system packages first:

```bash
sudo apt install python3-tk scrot libxcb-xinerama0 libgl1 xdotool
```

**3. (Optional) Install Ollama for vision-based detection**

Ollama enables deep content analysis when the window title alone is not conclusive.

```bash
# Install Ollama — https://ollama.com
ollama pull moondream
```

FocusGuard auto-detects Ollama on startup. No configuration required.

**4. Run**

```bash
python -m focusguard
```

Or, if you installed via `pip install .`:

```bash
focusguard
```

### Command-line options

```
focusguard [--cli] [--minimized] [--lang en|tr]
           [--interval SECONDS] [--threshold 0.0-1.0]
           [--model MODEL_NAME] [--log-level DEBUG|INFO|WARNING]

--cli          Run in headless terminal mode (no GUI)
--minimized    Start minimized to the system tray
--lang         Override UI language (en or tr)
--interval     Screenshot capture interval in seconds (default: 1.5)
--threshold    Detection confidence threshold (default: 0.55)
--model        Ollama model name (default: moondream)
--log-level    Logging verbosity (default: INFO)
```

### Configuration

Settings are saved automatically to your user data directory. You can edit them through the Settings panel in the GUI or directly in `settings.json`.

Notable settings:

| Setting | Default | Description |
|---------|---------|-------------|
| `confidence_threshold` | 0.55 | Minimum score to classify something as a distraction |
| `min_dirty_streak` | 2 | Consecutive positive detections required before alerting |
| `screenshot_interval` | 1.5 s | How often the screen is analyzed |
| `strict_mode` | false | Lowers threshold and increases capture frequency |
| `ghost_mode` | false | Log detections but do not fire resistance mechanisms |
| `stealth_mode` | false | Run silently in the background |

### Project structure

```
focusguard/
├── focusguard/
│   ├── __main__.py          Entry point
│   ├── config.py            All configuration and keyword lists
│   ├── i18n.py              Internationalisation helper
│   ├── paths.py             Platform-specific data/log paths
│   ├── modules/
│   │   ├── session.py       Session manager and detection pipeline
│   │   ├── analyzer.py      Hybrid analysis (CV + OCR + Ollama)
│   │   ├── screen_capture.py  MSS-based screen capture
│   │   ├── window_tracker.py  Active window tracking
│   │   ├── resistance.py    Resistance mechanisms
│   │   ├── fullscreen.py    Fullscreen detection
│   │   ├── detection_cache.py  Persistent result cache
│   │   ├── idle_detector.py  User idle detection
│   │   ├── analytics.py     Session analytics and Deep Work Index
│   │   ├── intentions.py    Pre-session intention tracking
│   │   ├── ambient.py       Ambient sound playback
│   │   └── gui.py           CustomTkinter UI
│   └── locales/
│       ├── en.py            English strings
│       └── tr.py            Turkish strings
├── tests/
├── requirements.txt
├── pyproject.toml
└── README.md
```

### License

MIT — see [LICENSE](LICENSE).

---

## Türkçe

### FocusGuard Nedir?

FocusGuard, gizlilik odaklı ve tamamen yerel olarak çalışan bir odak takip aracıdır. Ekranınızı izler ve zaman kaybettiğinizi tespit ettiğinde sizi tekrar çalışmaya döndürmek için bir dizi artan yoğunlukta direnç mekanizması devreye sokar.

Her şey kendi bilgisayarınızda çalışır. Hiçbir veri internete gönderilmez.

### Nasıl Çalışır?

FocusGuard, sürekli olarak yalnızca **aktif ön planda açık olan pencereyi** izler. Şu anda baktığınız pencere analiz edilir — Instagram'ı arka sekmede açık tutup GitHub'da çalışıyorsanız hiçbir uyarı gelmez. Sistem yalnızca önünüzdekiyle ilgilenir.

Tespit işlemi birkaç katmandan geçer:

| Katman | Yöntem | Ne Kontrol Eder |
|--------|--------|-----------------|
| 1 | Pencere başlığı — verimli uygulama | Ön plandaki uygulama bir IDE, terminal, editör veya iş aracı mı? |
| 2 | Pencere başlığı — verimli site | Tarayıcı başlığında bilinen bir verimli site adı var mı (GitHub, Claude, Notion, …)? |
| 3 | Pencere başlığı — dikkat dağıtıcı site | Tarayıcı başlığında bilinen bir dikkat dağıtıcı site adı var mı (Instagram, TikTok, Netflix, …)? |
| 4 | YouTube video başlığı | Video başlığı eğlence veya oyun içeriği mi? |
| 5 | Tam ekran tespiti | Bilinmeyen bir uygulama ekranı tamamen kaplıyor mu (oyun, video oynatıcı)? |
| 6 | Tespit önbelleği | Bu pencere bağlamı daha önce sınıflandırıldı mı? |
| 7 | OCR — adres çubuğu | Tarayıcı adres çubuğundaki gerçek URL okunur |
| 8 | Ollama görsel modeli | Sekme çubuğu kırpılarak sayfa içeriği yapay zeka ile analiz edilir |

1–3 arası katmanlar vakaların büyük çoğunluğunu anında çözümler — hiç ekran görüntüsü almadan. OCR ve Ollama yalnızca gerçekten belirsiz durumlar için çalışır.

### Temel Tasarım Kararları

**Yalnızca ön plandaki pencere önemlidir.**  
FocusGuard yalnızca aktif olarak baktığınız şeyi analiz eder. Tüm açık pencereleri veya tarayıcı sekmelerini taramaz. VS Code'da çalışırken arka planda Twitter açık olsa bile hiçbir şey olmaz.

**Verimli anahtar kelime, dikkat dağıtıcı anahtar kelimeden önce gelir.**  
Katman 2, Katman 3'ten önce çalışır. `"Twitter API değişiklikleri · GitHub issue"` gibi bir pencere başlığı, "github" verimli listedeki anahtar kelime olarak eşleştiğinden temiz olarak sınıflandırılır. "twitter" asla değerlendirilmez.

**Domain değil, site adları.**  
Tarayıcılar pencere başlıklarına domain yerine site *adını* ekler. Instagram'ın pencere başlığı `"Explore • Instagram"` şeklindedir, `"explore.instagram.com"` değil. Anahtar kelime listeleri tarayıcıların başlıkları nasıl biçimlendirdiğine göre oluşturulmuştur.

**Ollama için sekme çubuğu kırpılır.**  
Sayfa içeriği görsel modele gönderildiğinde, karenin üst ~%8'i (tarayıcı sekme çubuğunun bulunduğu yer) kaldırılır. Bu sayede aktif GitHub sekmenizin yanında duran bir Instagram sekmesi Ollama'nın analiz ettiği görüntüde hiçbir zaman görünmez.

### Özellikler

- **Çok katmanlı tespit** — pencere başlığı, OCR ve isteğe bağlı yerel yapay zeka görsel analizi
- **Artan yoğunlukta direnç** — fare titremesi, ekran karartma, uyarı bindirmesi, terminal mesajları, ses uyarıları, tam ekran patlaması
- **Pomodoro zamanlayıcı** — yapılandırılabilir çalışma/mola döngüsü
- **Derin Çalışma İndeksi** — odak süresi, tespit sayısı ve temiz serilere dayalı oturum sonu kalite skoru
- **Boşta kalma tespiti** — kullanıcı uzaklaşınca oturumu otomatik duraklatır
- **Uygulama başına analitik** — hangi uygulamaların en fazla zaman tükettiğini takip eder
- **Tespit önbelleği** — aynı siteyi defalarca analiz etmekten kaçınır
- **Oyunlaştırma** — sürekli odaklanmayı ödüllendiren XP sistemi ve başarımlar
- **Ortam sesleri** — yağmur, kafe, beyaz gürültü (`sounddevice` gerektirir)
- **Oturum niyetleri** — başlamadan önce ne üzerinde çalıştığınızı belirtin
- **Gizli / Hayalet mod** — sessizce çalışın veya yalnızca kayıt tutun
- **Tamamen çevrimdışı** — bulut yok, telemetri yok, hesap yok

### Gereksinimler

- Python 3.9 veya üstü
- Windows 10+, macOS 11+ veya X11 destekli modern bir Linux dağıtımı

### Kurulum

**1. Depoyu klonlayın**

```bash
git clone https://github.com/your-username/focusguard.git
cd focusguard
```

**2. Bağımlılıkları yükleyin**

```bash
pip install -r requirements.txt
```

**macOS** için ek olarak:

```bash
brew install python-tk
```

**Linux** için önce sistem paketlerini yükleyin:

```bash
sudo apt install python3-tk scrot libxcb-xinerama0 libgl1 xdotool
```

**3. (İsteğe bağlı) Görsel analiz için Ollama**

Ollama, pencere başlığının yeterli olmadığı durumlarda derin içerik analizi sağlar.

```bash
# Ollama kurulumu — https://ollama.com
ollama pull moondream
```

FocusGuard, Ollama'yı başlangıçta otomatik olarak algılar. Yapılandırma gerekmez.

**4. Çalıştırın**

```bash
python -m focusguard
```

Ya da `pip install .` ile kurulduysa:

```bash
focusguard
```

### Komut Satırı Seçenekleri

```
focusguard [--cli] [--minimized] [--lang en|tr]
           [--interval SANIYE] [--threshold 0.0-1.0]
           [--model MODEL_ADI] [--log-level DEBUG|INFO|WARNING]

--cli          Arayüzsüz terminal modunda çalıştır
--minimized    Sistem tepsisine küçültülmüş başlat
--lang         Arayüz dilini geçersiz kıl (en veya tr)
--interval     Ekran yakalama aralığı saniye cinsinden (varsayılan: 1.5)
--threshold    Tespit güven eşiği (varsayılan: 0.55)
--model        Ollama model adı (varsayılan: moondream)
--log-level    Günlük ayrıntı seviyesi (varsayılan: INFO)
```

### Yapılandırma

Ayarlar otomatik olarak kullanıcı veri dizinine kaydedilir. GUI'deki Ayarlar paneli üzerinden veya doğrudan `settings.json` dosyasını düzenleyerek değiştirilebilir.

Önemli ayarlar:

| Ayar | Varsayılan | Açıklama |
|------|------------|----------|
| `confidence_threshold` | 0.55 | Bir şeyi dikkat dağıtıcı olarak sınıflandırmak için gereken minimum skor |
| `min_dirty_streak` | 2 | Uyarı vermeden önce gereken ardışık pozitif tespit sayısı |
| `screenshot_interval` | 1.5 sn | Ekranın ne sıklıkla analiz edileceği |
| `strict_mode` | kapalı | Eşiği düşürür ve yakalama sıklığını artırır |
| `ghost_mode` | kapalı | Tespitleri kayıt altına alır ama direnç mekanizmalarını çalıştırmaz |
| `stealth_mode` | kapalı | Arka planda sessizce çalışır |

### Proje Yapısı

```
focusguard/
├── focusguard/
│   ├── __main__.py          Giriş noktası
│   ├── config.py            Tüm yapılandırma ve anahtar kelime listeleri
│   ├── i18n.py              Çoklu dil desteği
│   ├── paths.py             Platforma özgü veri/log yolları
│   ├── modules/
│   │   ├── session.py       Oturum yöneticisi ve tespit hattı
│   │   ├── analyzer.py      Hibrit analiz (CV + OCR + Ollama)
│   │   ├── screen_capture.py  MSS tabanlı ekran yakalama
│   │   ├── window_tracker.py  Aktif pencere takibi
│   │   ├── resistance.py    Direnç mekanizmaları
│   │   ├── fullscreen.py    Tam ekran tespiti
│   │   ├── detection_cache.py  Kalıcı sonuç önbelleği
│   │   ├── idle_detector.py  Kullanıcı boşta kalma tespiti
│   │   ├── analytics.py     Oturum analitiği ve Derin Çalışma İndeksi
│   │   ├── intentions.py    Oturum öncesi niyet takibi
│   │   ├── ambient.py       Ortam sesi oynatma
│   │   └── gui.py           CustomTkinter arayüzü
│   └── locales/
│       ├── en.py            İngilizce metinler
│       └── tr.py            Türkçe metinler
├── tests/
├── requirements.txt
├── pyproject.toml
└── README.md
```

### Lisans

MIT — bkz. [LICENSE](LICENSE).
