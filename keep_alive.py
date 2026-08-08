import os
import threading
from flask import Flask

app = Flask(__name__)


@app.route("/")
def home():
    return "Le bot est en ligne !"


def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


def keep_alive():
    t = threading.Thread(target=run)
    t.start()
