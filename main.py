import customtkinter as ctk
import tkinter.messagebox as mb
import threading
import webbrowser
import requests
import json
import urllib.parse

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

CLIENT_ID = "deine_client_id"
CLIENT_SECRET = "dein_client_secret"
REDIRECT_URI = "http://localhost:8080/callback"

ACCESS_TOKEN = None


def exchange_code_for_token(auth_code):
    token_url = "https://osu.ppy.sh/oauth/token"
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": auth_code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
        "scope": "public",
    }
    r = requests.post(token_url, data=data)
    r.raise_for_status()
    return r.json()["access_token"]


def get_user_profile(token):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get("https://osu.ppy.sh/api/v2/me", headers=headers)
    r.raise_for_status()
    return r.json()


class LoginWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("osu! Login")
        self.geometry("400x200")

        self.label = ctk.CTkLabel(self, text="osu! OAuth Login", font=ctk.CTkFont(size=20))
        self.label.pack(pady=10)

        self.button = ctk.CTkButton(self, text="Login bei osu! öffnen", command=self.open_oauth)
        self.button.pack(pady=5)

        self.code_entry = ctk.CTkEntry(self, placeholder_text="Hier Code einfügen")
        self.code_entry.pack(pady=5, fill="x", padx=20)

        self.submit_button = ctk.CTkButton(self, text="Code absenden", command=self.submit_code)
        self.submit_button.pack(pady=5)

        self.status_label = ctk.CTkLabel(self, text="")
        self.status_label.pack(pady=5)

    def open_oauth(self):
        url = (
            "https://osu.ppy.sh/oauth/authorize?"
            f"client_id={CLIENT_ID}&"
            f"redirect_uri={urllib.parse.quote(REDIRECT_URI)}&"
            "response_type=code&"
            "scope=public"
        )
        webbrowser.open(url)
        self.status_label.configure(text="Browser geöffnet, bitte Code einfügen")

    def submit_code(self):
        code = self.code_entry.get().strip()
        if not code:
            mb.showerror("Fehler", "Bitte Code eingeben")
            return

        self.status_label.configure(text="Token wird geholt...")
        self.submit_button.configure(state="disabled")

        def worker():
            global ACCESS_TOKEN
            try:
                ACCESS_TOKEN = exchange_code_for_token(code)
                profile = get_user_profile(ACCESS_TOKEN)
                self.after(0, lambda: self.login_success(profile))
            except Exception as e:
                self.after(0, lambda: self.login_failed(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def login_success(self, profile):
        self.status_label.configure(text=f"Erfolgreich eingeloggt als {profile['username']}")
        print("Profil:", profile)
        # Hier könntest du das Hauptfenster öffnen oder weiterarbeiten

    def login_failed(self, msg):
        mb.showerror("Login Fehler", msg)
        self.status_label.configure(text="")
        self.submit_button.configure(state="normal")


if __name__ == "__main__":
    app = LoginWindow()
    app.mainloop()
