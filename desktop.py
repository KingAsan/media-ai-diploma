import webview

URL = "https://media-ai-diploma.onrender.com"

if __name__ == "__main__":
    webview.create_window(
        "Media AI Universe",
        URL,
        width=1200,
        height=800
    )

    webview.start()
