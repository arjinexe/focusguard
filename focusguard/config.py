"""FocusGuard configuration."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List

APP_NAME    = "FocusGuard"
APP_VERSION = "5.1.0"


@dataclass
class FocusGuardConfig:
    # ── Core ────────────────────────────────────────────────────────────────
    language:              str   = "en"
    screenshot_interval:   float = 1.5
    analysis_backend:      str   = "hybrid"
    confidence_threshold:  float = 0.55
    min_dirty_streak:      int   = 2
    monitor_id:            int   = 1
    capture_scale:         float = 0.75

    # ── Ollama / vision ──────────────────────────────────────────────────────
    ollama_model:   str = "moondream"
    ollama_host:    str = "http://localhost:11434"
    ollama_timeout: int = 6

    # ── Productive native applications ───────────────────────────────────────
    # Matched against the foreground process name (app_name), not the window title.
    # If the process name matches any of these, skip all analysis immediately.
    productive_apps: List[str] = field(default_factory=lambda: [
        # Editors & IDEs
        "code", "vscode", "pycharm", "intellij", "webstorm", "clion", "rider",
        "vim", "nvim", "neovim", "emacs", "sublime", "atom", "cursor",
        "android studio", "xcode", "eclipse", "netbeans", "qtcreator",
        # Terminals
        "terminal", "iterm", "konsole", "alacritty", "wezterm", "kitty",
        "powershell", "cmd", "bash", "zsh", "hyper", "windowsterminal",
        # Office & notes
        "word", "excel", "powerpoint", "libreoffice", "openoffice",
        "notion", "obsidian", "logseq", "typora", "zettlr",
        # Design & creative
        "figma", "sketch", "affinity", "illustrator", "photoshop",
        "inkscape", "gimp", "blender",
        # Communication & work
        "slack", "teams", "zoom", "meet", "outlook", "thunderbird",
        # Document readers
        "foxit", "acrobat", "sumatrapdf", "okular", "evince", "calibre", "kindle",
        # FocusGuard itself
        "focusguard",
    ])

    # ── Productive sites — browser window title keywords ─────────────────────
    # Browsers format window titles as "<Page Title> - <Browser Name>".
    # The page title comes from the site's <title> tag and contains the SITE NAME,
    # not the domain. e.g. GitHub formats titles as "PR Title · GitHub".
    #
    # A match here ALWAYS wins over any distraction keyword. This prevents false
    # positives like "Twitter API changes · issue · GitHub" from triggering an alert
    # because "github" is matched before "twitter" is evaluated.
    productive_title_keywords: List[str] = field(default_factory=lambda: [
        # Version control & developer platforms
        "github", "gitlab", "bitbucket",
        # Q&A & developer docs
        "stack overflow", "stack exchange", "mdn web docs", "devdocs",
        # Productivity suites
        "google docs", "google sheets", "google slides", "google drive",
        "notion", "obsidian", "confluence", "sharepoint",
        # Project management
        "jira", "linear", "asana", "trello", "clickup", "basecamp",
        # Design tools
        "figma", "miro", "lucidchart",
        # AI assistants
        "claude", "chatgpt", "gemini", "microsoft copilot", "perplexity", "phind",
        # Dev platforms & online editors
        "replit", "codepen", "codesandbox", "stackblitz", "google colab", "kaggle",
        # Package registries & docs
        "npm", "pypi", "crates.io",
        # Cloud consoles
        "aws console", "google cloud", "azure portal", "digitalocean",
        "vercel", "netlify",
        # Learning platforms
        "udemy", "coursera", "khan academy", "edx", "pluralsight",
        # Research & reference
        "wikipedia", "arxiv", "google scholar",
        # Email
        "gmail", "outlook",
        # Localhost — always productive
        "localhost", "127.0.0.1",
        # Turkish educational platforms
        "eba",
    ])

    # ── Distraction sites — browser window title keywords ────────────────────
    # Checked ONLY if no productive keyword matched first.
    # These match how distraction sites appear in browser window titles.
    # e.g. Instagram: "Explore • Instagram", Twitter: "Home / X"
    distraction_title_keywords: List[str] = field(default_factory=lambda: [
        # Social media (precise patterns to avoid collision with news article titles)
        "instagram",
        "tiktok",
        "• twitter", "/ twitter", "home / x", "/ x",
        "reddit",
        "• facebook", "facebook watch",
        "snapchat",
        "• threads",
        "pinterest",
        "tumblr",
        "9gag",
        # Live streaming
        "twitch",
        # Video streaming
        "netflix",
        "prime video",
        "disney+",
        "hbo max", "max.com",
        "hulu",
        # Turkish streaming
        "exxen", "blutv", "gain.tv", "tabii", "crunchyroll",
        # Gaming platforms
        "roblox",
    ])

    # ── Distraction domains — domain-level matching ───────────────────────────
    # Checked against the full window title string (some browsers show the domain)
    # and passed to the OCR analyzer for address bar matching.
    distraction_domains: List[str] = field(default_factory=lambda: [
        "instagram.com", "tiktok.com", "twitter.com", "x.com",
        "reddit.com", "facebook.com", "snapchat.com", "threads.net",
        "pinterest.com", "tumblr.com", "9gag.com",
        "twitch.tv",
        "netflix.com", "primevideo.com", "disneyplus.com",
        "hbomax.com", "max.com", "hulu.com",
        "exxen.com", "blutv.com", "gain.tv", "tabii.com",
        "crunchyroll.com",
        "store.steampowered.com", "epicgames.com",
        "roblox.com",
    ])

    # ── Productive domains ───────────────────────────────────────────────────
    # Domain-level fallback. Some browsers include the domain in the title.
    productive_domains: List[str] = field(default_factory=lambda: [
        "github.com", "gitlab.com", "bitbucket.org",
        "stackoverflow.com", "stackexchange.com",
        "docs.google.com", "drive.google.com",
        "notion.so", "jira", "linear.app", "asana.com",
        "trello.com", "clickup.com", "figma.com", "miro.com",
        "confluence", "airtable.com",
        "claude.ai", "chat.openai.com", "chatgpt.com",
        "gemini.google.com", "copilot.microsoft.com",
        "perplexity.ai", "phind.com", "v0.dev",
        "cursor.sh", "replit.com", "colab.research.google", "kaggle.com",
        "npmjs.com", "pypi.org", "crates.io",
        "localhost", "127.0.0.1",
        "vercel.com", "netlify.com", "heroku.com",
        "aws.amazon.com", "console.cloud.google",
        "azure.microsoft.com", "digitalocean.com",
        "wikipedia.org", "arxiv.org", "scholar.google",
        "udemy.com", "coursera.org", "khanacademy.org", "edx.org",
        "eba.gov.tr",
        "mail.google.com", "outlook.live.com", "outlook.office",
    ])

    # ── YouTube video title keywords ─────────────────────────────────────────
    # Window title format: "<video title> - YouTube — <browser>"
    # Tutorials, lectures, and talks are NOT included — they are productive.
    youtube_distraction_keywords: List[str] = field(default_factory=lambda: [
        "minecraft", "roblox", "fortnite", "valorant", "league of legends",
        "counter-strike", "cs2", "csgo", "apex legends", "gta", "grand theft",
        "call of duty", "warzone", "overwatch", "dota", "hearthstone",
        "among us", "fall guys", "terraria", "stardew", "celeste",
        "dark souls", "elden ring", "cyberpunk", "baldur", "hogwarts",
        "zelda", "mario", "pokemon", "fifa", "nba 2k", "madden",
        "rust", "ark survival", "pubg", "battlegrounds",
        "let's play", "lets play", "gameplay", "gaming",
        "funny moments", "rage quit", "speedrun", "no commentary",
        "oyun", "oynanış",
        "memes", "try not to laugh", "compilation", "fails", "epic fails",
        "best moments", "vlog", "challenge", "mukbang", "asmr",
        "reaction", "reacting to", "prank", "roast",
        "official music video", "official video", "lyric video", "full album",
    ])

    # ── OCR address-bar keywords ─────────────────────────────────────────────
    # Fallback for when window title gives no signal. OCR reads the actual URL.
    ocr_domains: List[str] = field(default_factory=lambda: [
        "instagram.com", "tiktok.com", "twitter.com", "x.com",
        "reddit.com", "facebook.com", "snapchat.com",
        "netflix.com", "twitch.tv", "primevideo.com",
        "store.steampowered.com", "epicgames.com", "roblox.com",
        "9gag.com", "tumblr.com", "pinterest.com",
    ])

    # ── Visual detection ─────────────────────────────────────────────────────
    scroll_streak_threshold:   int   = 3
    card_regularity_threshold: float = 0.65

    # ── Resistance ───────────────────────────────────────────────────────────
    enable_mouse_jitter:     bool = True
    enable_brightness_dim:   bool = True
    enable_overlay_warning:  bool = True
    enable_terminal_shaming: bool = True
    enable_sound_alert:      bool = True
    enable_fullscreen_blast: bool = True
    enable_screen_shake:     bool = True
    enable_break_reminder:   bool = True

    jitter_base_intensity: int   = 14
    jitter_base_duration:  float = 8.0
    brightness_dim_target: int   = 35
    brightness_step_delay: float = 0.4
    shake_intensity:       int   = 8

    escalation_per_n_detections: int = 3
    escalation_reset_minutes:    int = 25
    max_escalation:              int = 7

    # ── Idle ─────────────────────────────────────────────────────────────────
    idle_detection_enabled:  bool = True
    idle_screen_enabled:     bool = True
    idle_screen_seconds:     int  = 180
    idle_mouse_enabled:      bool = True
    idle_mouse_seconds:      int  = 120
    idle_keyboard_enabled:   bool = True
    idle_keyboard_seconds:   int  = 300
    idle_action:             str  = "pause"
    idle_cooldown_seconds:   int  = 60

    # ── Pomodoro ─────────────────────────────────────────────────────────────
    work_session_minutes:      int = 25
    break_minutes:             int = 5
    long_break_minutes:        int = 15
    long_break_after_sessions: int = 4

    # ── Modes ────────────────────────────────────────────────────────────────
    stealth_mode: bool = False
    ghost_mode:   bool = False
    strict_mode:  bool = False
    streak_goal:  int  = 5

    # ── Gamification ─────────────────────────────────────────────────────────
    enable_achievements:       bool = True
    enable_xp_system:          bool = True
    daily_focus_goal_minutes:  int  = 120
    weekly_focus_goal_hours:   int  = 10
    show_motivational_quotes:  bool = True

    # ── UI ───────────────────────────────────────────────────────────────────
    window_always_on_top: bool = False
    minimize_to_tray:     bool = True
    theme:                str  = "dark"

    autostart_enabled:   bool = False
    autostart_minimized: bool = False
    autostart_session:   bool = False

    allowlist: List[str] = field(default_factory=list)

    ambient_enabled: bool  = False
    ambient_sound:   str   = "rain"
    ambient_volume:  float = 0.4

    window_tracking_enabled:  bool = True
    detection_cache_enabled:  bool = True
    intentions_enabled:       bool = True
    show_dwi:                 bool = True

    log_level:       str = "INFO"
    max_log_entries: int = 500


CONFIG = FocusGuardConfig()

OLLAMA_VISION_PROMPT = (
    "Productivity monitor. Look at the main page content (tab bar cropped). "
    "Is the user doing something unproductive? "
    "Unproductive: social media, entertainment video, game, news feed. "
    "Productive: coding, writing, studying, research, work tools, AI chat. "
    "If unsure, answer false. "
    'JSON only: {"is_distraction":true/false,"confidence":0.0-1.0,"reason":"<50 chars"}'
)
MOONDREAM_PROMPT = OLLAMA_VISION_PROMPT


SHAME_MESSAGES: List[str] = [
    "Hey. That was a scroll. Come back. 🎯",
    "Still? Your future is working hard. You're not.",
    "FOCUS. Whatever you're watching isn't changing your life.",
    "3rd warning. What are you actually doing?",
    "You opened this app FOR A REASON. Remember it.",
    "Now you're just stealing time from yourself.",
    "Every scroll is a minute stolen from your future.",
    "FINAL WARNING — close it and work. Now.",
]

SCREEN_TEXT_MESSAGES: List[str] = [
    "🎯 WHAT'S THE GOAL?",
    "⏰ TIME IS PASSING",
    "💤 ARE YOU AWAKE?",
    "📵 CLOSE IT AND WORK",
    "🔥 FOCUS!",
    "⚡ ISN'T IT GETTING LATE?",
    "🏆 COMPETE WITH YOURSELF",
    "💡 WHAT WILL YOU CREATE TODAY?",
    "🚀 BACK TO WORK",
    "⛔ DISTRACTION DETECTED",
]

MOTIVATION_MESSAGES: List[str] = [
    "🔥 Great work! You're in focus mode.",
    "💪 With this energy you're unstoppable!",
    "⚡ Full focus — brain running at max.",
    "🎯 That's it! Making progress towards your goals.",
    "🚀 Productivity score climbing!",
    "✨ Excellent — deep work mode active.",
    "🏆 Every clean minute moves you forward.",
    "💎 Concentration = your most valuable investment.",
    "🌊 Deep work. No distractions. Pure output.",
    "🧠 Your future self thanks you for this.",
]

ACHIEVEMENTS = {
    "first_session":   {"title": "First Blood",    "desc": "Complete your first session",       "icon": "🩸", "xp": 50},
    "clean_hour":      {"title": "Clean Hour",      "desc": "Stay clean for 60 minutes",         "icon": "⏰", "xp": 100},
    "no_distractions": {"title": "Ghost Protocol",  "desc": "Session with zero distractions",    "icon": "🛡", "xp": 150},
    "early_bird":      {"title": "Early Bird",      "desc": "Start a session before 8 AM",       "icon": "🐦", "xp": 75},
    "night_owl":       {"title": "Night Owl",       "desc": "Work past midnight",                "icon": "🦉", "xp": 75},
    "marathon":        {"title": "Marathon",        "desc": "Accumulate 5 hours of focus",       "icon": "🏃", "xp": 200},
    "week_streak":     {"title": "Week Warrior",    "desc": "Use FocusGuard 7 days in a row",    "icon": "📅", "xp": 300},
    "pomodoro_master": {"title": "Pomo Master",     "desc": "Complete 50 pomodoros",             "icon": "🍅", "xp": 500},
    "ghost_fighter":   {"title": "Ghost Fighter",   "desc": "Resist 100 distractions total",     "icon": "👻", "xp": 120},
    "deep_work":       {"title": "Deep Work",       "desc": "90 min uninterrupted focus",        "icon": "🌊", "xp": 250},
    "idle_catcher":    {"title": "Self Aware",      "desc": "Idle detection triggers 10 times",  "icon": "😴", "xp": 80},
    "speed_demon":     {"title": "Speed Demon",     "desc": "Complete session in strict mode",   "icon": "⚡", "xp": 120},
    "comeback_kid":    {"title": "Comeback Kid",    "desc": "Resume after idle 5 times",         "icon": "💪", "xp": 90},
}

SAVEABLE_KEYS: List[str] = [
    "language",
    "confidence_threshold", "screenshot_interval", "min_dirty_streak",
    "ollama_model", "ollama_host", "ollama_timeout", "monitor_id", "capture_scale",
    "enable_mouse_jitter", "enable_brightness_dim", "enable_overlay_warning",
    "enable_terminal_shaming", "enable_sound_alert", "enable_fullscreen_blast",
    "enable_screen_shake", "enable_break_reminder",
    "jitter_base_intensity", "jitter_base_duration",
    "brightness_dim_target", "brightness_step_delay", "shake_intensity",
    "escalation_per_n_detections", "escalation_reset_minutes", "max_escalation",
    "idle_detection_enabled", "idle_screen_enabled", "idle_screen_seconds",
    "idle_mouse_enabled", "idle_mouse_seconds",
    "idle_keyboard_enabled", "idle_keyboard_seconds",
    "idle_action", "idle_cooldown_seconds",
    "work_session_minutes", "break_minutes", "long_break_minutes",
    "long_break_after_sessions",
    "stealth_mode", "ghost_mode", "strict_mode", "streak_goal",
    "enable_achievements", "enable_xp_system",
    "daily_focus_goal_minutes", "weekly_focus_goal_hours",
    "show_motivational_quotes",
    "window_always_on_top", "minimize_to_tray", "theme",
    "autostart_enabled", "autostart_minimized", "autostart_session",
    "allowlist",
    "ambient_enabled", "ambient_sound", "ambient_volume",
    "window_tracking_enabled", "detection_cache_enabled",
    "intentions_enabled", "show_dwi",
]
