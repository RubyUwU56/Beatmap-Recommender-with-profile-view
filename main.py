import os
import json
import threading
import webbrowser
import tkinter as tk
import customtkinter as ctk
from http.server import HTTPServer, BaseHTTPRequestHandler
from PIL import Image, ImageTk
from random import randint, choice
import requests
import time
from io import BytesIO

# --- CONFIG ---
CONFIG_FILE = "config.json"
REDIRECT_URI = "http://localhost:8080/callback"
TOKEN_URL = "https://osu.ppy.sh/oauth/token"
API_ME_URL = "https://osu.ppy.sh/api/v2/me"
API_USER_BEST_SCORES_URL = "https://osu.ppy.sh/api/v2/users/{user_id}/scores/best"  # Für Best Scores

# --- SETUP ---
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

MOD_OPTIONS = ["NM", "HD", "HR", "HDHR", "DT", "HDDT", "HDHRDT", "HT"]
MODE_OPTIONS = ["osu", "taiko", "fruits", "mania"]
LANGUAGES = ["English", "Deutsch"]

TRANSLATIONS = {
    "English": {
        "username_label": "Username:",
        "mode_label": "Mode:",
        "mods_select": "Select Mods:",
        "login_button": "Login with osu!",
        "logout_button": "Logout",
        "search_button": "Search Scores",
        "profile_title": "Profile & Stats",
        "rank_graph_title": "Rank History (hover for info)",
        "pp_text": "PP",
        "level_text": "Level",
        "rank_text": "Global Rank",
        "error_login": "Please login first.",
        "error_username": "Username cannot be empty.",
        "scores_title": "Best Scores",
        "no_scores": "No scores found."
    },
    "Deutsch": {
        "username_label": "Benutzername:",
        "mode_label": "Modus:",
        "mods_select": "Mods auswählen:",
        "login_button": "Mit osu! einloggen",
        "logout_button": "Ausloggen",
        "search_button": "Scores suchen",
        "profile_title": "Profil & Statistik",
        "rank_graph_title": "Rangverlauf (hover für Info)",
        "pp_text": "PP",
        "level_text": "Level",
        "rank_text": "Globaler Rang",
        "error_login": "Bitte zuerst einloggen.",
        "error_username": "Benutzername darf nicht leer sein.",
        "scores_title": "Beste Scores",
        "no_scores": "Keine Scores gefunden."
    }
}

class OAuthHandler(BaseHTTPRequestHandler):
    auth_code = None
    def do_GET(self):
        if self.path.startswith("/callback?code="):
            code = self.path.split("code=")[-1].split("&")[0]
            OAuthHandler.auth_code = code
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<html><body><h1>Login successful! You can close this window.</h1></body></html>")
        else:
            self.send_error(404)

def start_server():
    server = HTTPServer(("localhost", 8080), OAuthHandler)
    return server

def exchange_token(code, client_id, client_secret):
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI
    }
    response = requests.post(TOKEN_URL, json=data)
    response.raise_for_status()
    return response.json()

def get_user_profile(token):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(API_ME_URL, headers=headers)
    response.raise_for_status()
    return response.json()

def get_user_best_scores(token, user_id, mode, mods=None):
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "mode": mode,
        "limit": 20,
    }
    if mods:
        params["mods"] = mods

    url = API_USER_BEST_SCORES_URL.format(user_id=user_id)
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()

class MainApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("osu! Viewer")
        self.geometry("1100x700")
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        # Variablen
        self.language = tk.StringVar(master=self, value="English")
        self.translations = TRANSLATIONS[self.language.get()]
        self.username = tk.StringVar(master=self, value="")
        self.mode = tk.StringVar(master=self, value=MODE_OPTIONS[0])
        self.selected_mod = tk.StringVar(master=self, value="NM")
        self.mod_buttons = {}
        self.rank_data = []
        self.access_token = None
        self.user_id = None

        # Hintergrund Canvas
        self.bg_canvas = tk.Canvas(self, bg="#111111", highlightthickness=0)
        self.bg_canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.bg_canvas.lower("all")

        # UI Frame transparent
        self.ui_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.ui_frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.create_widgets()
        self.animate_background()

    def create_widgets(self):
        # Obere Leiste
        top = ctk.CTkFrame(self.ui_frame, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=10)

        try:
            osu_logo_img = Image.open("osu_logo.png").resize((24, 24))
            self.osu_logo = ImageTk.PhotoImage(osu_logo_img)
        except Exception:
            self.osu_logo = None

        self.login_btn = ctk.CTkButton(
            top,
            text=self.translations["login_button"],
            image=self.osu_logo,
            compound="left",
            fg_color="#ff66aa",
            hover_color="#ff99cc",
            text_color="white",
            command=self.start_osu_login
        )
        self.login_btn.pack(side="left", padx=5)

        self.logout_btn = ctk.CTkButton(top, text=self.translations["logout_button"], command=self.logout)
        self.logout_btn.pack(side="left", padx=5)

        self.logged_in_label = ctk.CTkLabel(top, text="", width=150)
        self.logged_in_label.pack(side="left", padx=10)

        self.language_menu = ctk.CTkOptionMenu(top, values=LANGUAGES, variable=self.language, command=self.change_language)
        self.language_menu.pack(side="right", padx=5)

        self.mode_menu = ctk.CTkOptionMenu(top, values=MODE_OPTIONS, variable=self.mode)
        self.mode_menu.pack(side="right", padx=5)
        self.mode.trace_add("write", lambda *args: self.load_profile() if self.access_token else None)
        self.mode.trace_add("write", lambda *args: self.load_scores() if self.access_token else None)

        # Mods Frame
        mods_frame = ctk.CTkFrame(self.ui_frame, fg_color="transparent")
        mods_frame.pack(padx=10, pady=5, fill="x")
        self.mods_label = ctk.CTkLabel(mods_frame, text=self.translations["mods_select"])
        self.mods_label.pack(anchor="w")
        mod_btn_frame = ctk.CTkFrame(mods_frame, fg_color="transparent")
        mod_btn_frame.pack(anchor="w")

        for mod in MOD_OPTIONS:
            btn = ctk.CTkButton(mod_btn_frame, text=mod, width=60, command=lambda m=mod: self.select_mod(m))
            btn.pack(side="left", padx=4, pady=5)
            self.mod_buttons[mod] = btn

        self.select_mod("NM")

        # Profil & Stats + Scores Bereich
        profile_wrapper = ctk.CTkFrame(self.ui_frame)
        profile_wrapper.pack(fill="both", expand=True, padx=10, pady=10)

        # Links Profil
        left = ctk.CTkFrame(profile_wrapper)
        left.pack(side="left", fill="y", padx=10, pady=10)

        self.avatar_label = ctk.CTkLabel(left, text="")
        self.avatar_label.pack(pady=10)

        self.stats_label = ctk.CTkLabel(left, justify="left")
        self.stats_label.pack()

        # Rechts Scores + Rank Graph
        right = ctk.CTkFrame(profile_wrapper)
        right.pack(side="right", fill="both", expand=True)

        # Rank Graph
        self.rank_graph_label = ctk.CTkLabel(right, text=self.translations["rank_graph_title"])
        self.rank_graph_label.pack(anchor="w")

        self.graph_canvas = tk.Canvas(right, height=150, bg="#222222", highlightthickness=0)
        self.graph_canvas.pack(fill="x")
        self.graph_canvas.bind("<Motion>", self.on_graph_hover)

        self.tooltip = ctk.CTkLabel(self.graph_canvas, text="", fg_color="gray25", text_color="white", corner_radius=5)
        self.tooltip.place_forget()

        # Separator
        sep = ctk.CTkLabel(right, text="")  # einfacher Abstand
        sep.pack(pady=5)

        # Scores Titel
        self.scores_title_label = ctk.CTkLabel(right, text=self.translations["scores_title"], font=ctk.CTkFont(size=18, weight="bold"))
        self.scores_title_label.pack(anchor="w", padx=5, pady=(5,0))

        # Scrollbarer Scores Bereich
        self.scores_canvas = tk.Canvas(right, bg="#111", height=350, highlightthickness=0)
        self.scores_scrollbar = ctk.CTkScrollbar(right, orientation="vertical", command=self.scores_canvas.yview)
        self.scores_canvas.configure(yscrollcommand=self.scores_scrollbar.set)

        self.scores_scrollbar.pack(side="right", fill="y")
        self.scores_canvas.pack(side="left", fill="both", expand=True)

        self.scores_inner_frame = ctk.CTkFrame(self.scores_canvas, fg_color="#222")
        self.scores_canvas.create_window((0,0), window=self.scores_inner_frame, anchor="nw")

        self.scores_inner_frame.bind("<Configure>", lambda e: self.scores_canvas.configure(scrollregion=self.scores_canvas.bbox("all")))

    def select_mod(self, mod):
        self.selected_mod.set(mod)
        for m, btn in self.mod_buttons.items():
            btn.configure(fg_color="#444" if m != mod else "#ff66aa")
        if self.access_token:
            self.load_scores()

    def change_language(self, choice):
        self.translations = TRANSLATIONS[choice]
        self.update_ui_texts()

    def update_ui_texts(self):
        self.login_btn.configure(text=self.translations["login_button"])
        self.logout_btn.configure(text=self.translations["logout_button"])
        self.mods_label.configure(text=self.translations["mods_select"])
        self.rank_graph_label.configure(text=self.translations["rank_graph_title"])
        self.scores_title_label.configure(text=self.translations["scores_title"])
        # ggf mehr Texte aktualisieren

    def start_osu_login(self):
        # Lese ClientID und Secret aus config.json
        if not os.path.exists(CONFIG_FILE):
            ctk.CTkMessageBox.show_error("Config file missing. Please create config.json with client_id and client_secret.")
            return

        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
        client_id = config.get("client_id")
        client_secret = config.get("client_secret")
        if not client_id or not client_secret:
            ctk.CTkMessageBox.show_error("client_id or client_secret missing in config.json")
            return

        # Öffne Auth URL
        scope = "public"
        auth_url = f"https://osu.ppy.sh/oauth/authorize?client_id={client_id}&redirect_uri={REDIRECT_URI}&response_type=code&scope={scope}"

        # Server starten, um Code zu empfangen
        server = start_server()
        threading.Thread(target=server.serve_forever, daemon=True).start()

        webbrowser.open(auth_url)

        def wait_for_code():
            while OAuthHandler.auth_code is None:
                time.sleep(0.5)
            server.shutdown()
            try:
                token_data = exchange_token(OAuthHandler.auth_code, client_id, client_secret)
                self.access_token = token_data["access_token"]
                profile = get_user_profile(self.access_token)
                self.user_id = profile["id"]
                self.logged_in_label.configure(text=profile["username"])
                self.load_profile()
                self.load_scores()
            except Exception as e:
                ctk.CTkMessageBox.show_error(f"Login failed: {e}")

        threading.Thread(target=wait_for_code, daemon=True).start()

    def logout(self):
        self.access_token = None
        self.user_id = None
        self.logged_in_label.configure(text="")
        self.avatar_label.configure(image=None, text="")
        self.stats_label.configure(text="")
        for widget in self.scores_inner_frame.winfo_children():
            widget.destroy()
        self.graph_canvas.delete("all")

    def load_profile(self):
        if not self.access_token:
            return
        try:
            profile = get_user_profile(self.access_token)
            avatar_url = profile.get("avatar_url") or profile.get("avatar_url")
            avatar_img = self.load_image_from_url(avatar_url, (100, 100)) if avatar_url else None
            if avatar_img:
                self.avatar_label.configure(image=avatar_img, text="")
                self.avatar_label.image = avatar_img
            else:
                self.avatar_label.configure(image=None, text="No Avatar")

            level = profile.get("statistics", {}).get("level", 0)
            pp = profile.get("statistics", {}).get("pp", 0)
            global_rank = profile.get("statistics", {}).get("global_rank", 0)

            stats_text = (
                f"{self.translations['level_text']}: {level}\n"
                f"{self.translations['pp_text']}: {pp}\n"
                f"{self.translations['rank_text']}: #{global_rank if global_rank else 'N/A'}"
            )
            self.stats_label.configure(text=stats_text)
        except Exception as e:
            ctk.CTkMessageBox.show_error(f"Failed to load profile: {e}")

    def load_scores(self):
        if not self.access_token or not self.user_id:
            return

        mode = self.mode.get()
        mod = self.selected_mod.get()

        # Modstring übersetzen (nur Beispiel, ggf API kompatibel anpassen)
        modstr = ""
        if mod != "NM":
            modstr = mod

        def fetch_scores():
            try:
                scores = get_user_best_scores(self.access_token, self.user_id, mode)
                self.display_scores(scores)
            except Exception as e:
                ctk.CTkMessageBox.show_error(f"Failed to load scores: {e}")

        threading.Thread(target=fetch_scores, daemon=True).start()

    def display_scores(self, scores):
        # Aufruf aus Thread -> im Hauptthread ausführen
        self.after(0, self._display_scores_ui, scores)

    def _display_scores_ui(self, scores):
        for widget in self.scores_inner_frame.winfo_children():
            widget.destroy()

        if not scores:
            label = ctk.CTkLabel(self.scores_inner_frame, text=self.translations["no_scores"])
            label.pack()
            return

        for score in scores:
            frame = ctk.CTkFrame(self.scores_inner_frame, fg_color="#333", height=100)
            frame.pack(fill="x", pady=5, padx=5)

            # Beatmap Cover laden (klein)
            beatmapset = score.get("beatmapset", {})
            cover_url = beatmapset.get("covers", {}).get("cover") or beatmapset.get("covers", {}).get("list")
            cover_img = self.load_image_from_url(cover_url, (80, 80)) if cover_url else None

            if cover_img:
                cover_label = ctk.CTkLabel(frame, image=cover_img)
                cover_label.image = cover_img
                cover_label.pack(side="left", padx=5, pady=5)
            else:
                cover_label = ctk.CTkLabel(frame, text="No Image", width=10)
                cover_label.pack(side="left", padx=5, pady=5)

            info_frame = ctk.CTkFrame(frame, fg_color="transparent")
            info_frame.pack(side="left", fill="both", expand=True, padx=5)

            title = beatmapset.get("title", "Unknown Title")
            artist = beatmapset.get("artist", "Unknown Artist")
            difficulty = score.get("beatmap", {}).get("version", "Unknown")
            length = score.get("beatmap", {}).get("total_length", 0)
            stars = score.get("beatmap", {}).get("difficulty_rating", 0)
            mods = score.get("mods", [])
            pp = score.get("pp", 0)
            rank = score.get("rank", "?")
            score_value = score.get("score", 0)
            date = score.get("created_at", "").split("T")[0]

            # Titel
            title_label = ctk.CTkLabel(info_frame, text=f"{artist} - {title} [{difficulty}]", font=ctk.CTkFont(size=14, weight="bold"))
            title_label.pack(anchor="w")

            # Details
            detail_text = (
                f"Length: {length//60}:{length%60:02d} min  "
                f"Stars: {stars:.2f}  "
                f"PP: {pp:.1f}  "
                f"Rank: {rank}  "
                f"Mods: {''.join(mods) if mods else 'NM'}  "
                f"Score: {score_value}  "
                f"Date: {date}"
            )
            detail_label = ctk.CTkLabel(info_frame, text=detail_text, font=ctk.CTkFont(size=12))
            detail_label.pack(anchor="w")

    def load_image_from_url(self, url, size):
        try:
            response = requests.get(url)
            response.raise_for_status()
            img_data = response.content
            image = Image.open(BytesIO(img_data))
            image = image.resize(size, Image.LANCZOS)
            return ImageTk.PhotoImage(image)
        except Exception:
            return None

    def animate_background(self):
        self.bg_canvas.delete("all")
        width = self.winfo_width() or 1100
        height = self.winfo_height() or 700
        for _ in range(30):
            x = randint(0, width)
            y = randint(0, height)
            r = randint(2, 5)
            color = f"#{randint(100, 255):02x}{randint(100, 255):02x}{randint(100, 255):02x}"
            self.bg_canvas.create_oval(x-r, y-r, x+r, y+r, fill=color, outline="")
        self.after(2000, self.animate_background)

    def on_graph_hover(self, event):
        # Beispiel Tooltip - hier könntest du Datenpunkte aus rank_data anzeigen
        if self.rank_data:
            idx = int(event.x / (self.graph_canvas.winfo_width() / len(self.rank_data)))
            idx = max(0, min(idx, len(self.rank_data)-1))
            text = f"Rank on day {idx+1}: #{self.rank_data[idx]}"
            self.tooltip.configure(text=text)
            self.tooltip.place(x=event.x+10, y=event.y+10)
        else:
            self.tooltip.place_forget()


if __name__ == "__main__":
    app = MainApp()
    app.mainloop()
