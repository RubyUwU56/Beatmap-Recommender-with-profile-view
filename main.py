import customtkinter as ctk
import tkinter as tk
import tkinter.messagebox as messagebox
import requests
import threading
import webbrowser
import json
import http.server
import socketserver
import urllib.parse
from PIL import Image, ImageTk
import io
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import mplcursors

# Appearance settings
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

# Load config.json
with open("config.json", "r") as f:
    config = json.load(f)

CLIENT_ID = config["client_id"]
CLIENT_SECRET = config["client_secret"]
REDIRECT_URI = config.get("redirect_uri", "http://localhost:8080/callback")

ACCESS_TOKEN = None


class OAuthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed_path.query)

        if "code" in params:
            self.server.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                "<h1>Login successful!</h1><p>You can close this window and return to the app.</p>".encode("utf-8")
            )
        else:
            self.send_response(400)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                "<h1>Login failed.</h1><p>No authorization code received.</p>".encode("utf-8")
            )


def start_local_server():
    server_address = ("", 8080)
    httpd = socketserver.TCPServer(server_address, OAuthHandler)
    httpd.auth_code = None
    return httpd


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
    response = requests.post(token_url, data=data, timeout=10)
    response.raise_for_status()
    return response.json()["access_token"]


def get_user_profile():
    global ACCESS_TOKEN
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }
    response = requests.get("https://osu.ppy.sh/api/v2/me", headers=headers, timeout=10)
    response.raise_for_status()
    return response.json()


class LoginWindow(ctk.CTkToplevel):
    def __init__(self, master, on_success):
        super().__init__(master)
        self.master = master
        self.on_success = on_success
        self.title("osu! Login")
        self.geometry("400x250")
        self.resizable(False, False)

        self.label = ctk.CTkLabel(self, text="Log in with your osu! account", font=ctk.CTkFont(size=18))
        self.label.pack(pady=20)

        try:
            logo_img = Image.open("osu_logo.png").resize((40, 40))
            self.logo_photo = ImageTk.PhotoImage(logo_img)
        except Exception:
            self.logo_photo = None

        self.login_button = ctk.CTkButton(
            self,
            text="Log in with osu!",
            width=220,
            height=50,
            fg_color="#FF66AA",
            hover_color="#FF3399",
            command=self.start_login,
            font=ctk.CTkFont(size=16, weight="bold"),
            image=self.logo_photo,
            compound="left",
        )
        self.login_button.pack(pady=20)

        self.status_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=14))
        self.status_label.pack(pady=10)

        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def start_login(self):
        self.login_button.configure(state="disabled")
        self.status_label.configure(text="Starting login...")
        threading.Thread(target=self.login_flow, daemon=True).start()

    def login_flow(self):
        global ACCESS_TOKEN
        try:
            auth_url = (
                "https://osu.ppy.sh/oauth/authorize"
                f"?client_id={CLIENT_ID}"
                f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
                "&response_type=code"
                "&scope=public"
            )
            webbrowser.open(auth_url)
            server = start_local_server()

            # Accept only one request and close immediately
            server.handle_request()
            server.server_close()

            if server.auth_code:
                ACCESS_TOKEN = exchange_code_for_token(server.auth_code)
                user_data = get_user_profile()
                self.after(0, lambda: self.login_success(user_data))
            else:
                self.after(0, lambda: self.login_failed("No authorization code received."))
        except Exception as e:
            self.after(0, lambda: self.login_failed(str(e)))

    def login_success(self, user_data):
        self.on_success(user_data)
        self.destroy()

    def login_failed(self, msg):
        messagebox.showerror("Login error", msg)
        self.login_button.configure(state="normal")
        self.status_label.configure(text="")


class MainApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("osu! Beatmap Recommender")
        self.geometry("900x900")
        self.state("zoomed")

        self.profile_frame = ctk.CTkFrame(self, width=880, height=150)
        self.profile_frame.pack(pady=(10, 0))

        self.avatar_label = ctk.CTkLabel(self.profile_frame, text="")
        self.avatar_label.pack(side="left", padx=10)

        self.info_label = ctk.CTkLabel(self.profile_frame, text="", font=ctk.CTkFont(size=16), anchor="w", justify="left")
        self.info_label.pack(side="left", padx=10)

        self.graph_frame = ctk.CTkFrame(self, width=880, height=300)
        self.graph_frame.pack(pady=(10, 10))

        self.username_label = ctk.CTkLabel(self, text="osu! Username:", font=ctk.CTkFont(size=16))
        self.username_label.pack(pady=(20, 0))

        self.username_entry = ctk.CTkEntry(self, width=300, font=ctk.CTkFont(size=14))
        self.username_entry.pack(pady=(0, 10))
        self.username_entry.bind("<Return>", lambda e: self.start_search())

        self.search_button = ctk.CTkButton(
            self,
            text="🎵 Get Recommendations",
            width=200,
            height=40,
            command=self.start_search,
        )
        self.search_button.pack(pady=10)

        self.result_frame = ctk.CTkScrollableFrame(self, width=860, height=400)
        self.result_frame.pack(pady=10)

        self.status_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=14))
        self.status_label.pack(pady=(0, 10))

        self.withdraw()  # Hide until login done

    def set_user_profile(self, user_data):
        try:
            avatar_url = user_data["avatar_url"]
            avatar_response = requests.get(avatar_url, timeout=10)
            avatar_img = Image.open(io.BytesIO(avatar_response.content)).resize((100, 100)).convert("RGBA")
            self.avatar_photo = ImageTk.PhotoImage(avatar_img)
            self.avatar_label.configure(image=self.avatar_photo, text="")
        except Exception:
            self.avatar_label.configure(text="No Avatar")

        text = (
            f"Username: {user_data['username']}\n"
            f"Global Rank: #{user_data.get('statistics', {}).get('global_rank', 'N/A')}\n"
            f"Country: {user_data.get('country', {}).get('name', 'N/A')}\n"
            f"PP: {user_data.get('statistics', {}).get('pp', 'N/A')}\n"
            f"Playcount: {user_data.get('statistics', {}).get('play_count', 'N/A')}"
        )
        self.info_label.configure(text=text)
        self.plot_rank_graph()

    def plot_rank_graph(self):
        # Simulated dummy data for now
        days = np.arange(0, 30)
        ranks = 10000 - np.random.randint(0, 500, size=30).cumsum()

        fig, ax = plt.subplots(figsize=(8, 3))
        ax.plot(days, ranks, marker='o', color="#FF66AA")
        ax.set_title("Global Rank History")
        ax.set_xlabel("Days ago")
        ax.set_ylabel("Global Rank")
        ax.invert_yaxis()

        for widget in self.graph_frame.winfo_children():
            widget.destroy()

        canvas = FigureCanvasTkAgg(fig, master=self.graph_frame)
        canvas.draw()
        canvas.get_tk_widget().pack()

        cursor = mplcursors.cursor(ax, hover=True)
        cursor.connect("add", lambda sel: sel.annotation.set_text(f"Rank: {int(sel.target[1])}"))

    def start_search(self):
        if ACCESS_TOKEN is None:
            messagebox.showerror("Error", "You must log in first.")
            return

        username = self.username_entry.get().strip()
        if not username:
            messagebox.showerror("Error", "Please enter an osu! username.")
            return

        self.status_label.configure(text=f"Searching beatmaps for {username}...")
        # Implement search logic here


def main():
    app = MainApp()

    def after_login(user_data):
        app.set_user_profile(user_data)
        app.deiconify()

    LoginWindow(app, on_success=after_login)
    app.mainloop()


if __name__ == "__main__":
    main()
