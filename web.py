"""Local Flask interface; the existing CLI owns all video generation logic."""
import re
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_from_directory, url_for

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output" / "web"
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 4096
generation_lock = threading.Lock()


@app.get("/")
def index():
    return render_template("index.html")


def generation_error(stderr: str) -> str:
    """Explain known failures without returning process logs or credentials."""
    if "No offline script" in stderr:
        return ("The AI service could not generate this topic. Check your API key, model, "
                "connection, or free-model availability, then try again. Offline mode only "
                "supports sky color, photosynthesis, rainbows, gravity, and volcanoes.")
    if "Required tool not found" in stderr:
        return "A required local tool is missing. Check that say, FFmpeg, and ffprobe are available."
    if "Pillow is required" in stderr:
        return "A required dependency is missing. Install requirements.txt in the virtual environment."
    if "say" in stderr or "Narration" in stderr:
        return "Local narration failed. Check your installed speech voice and macOS speech-service access."
    if "timed out" in stderr:
        return "Generation timed out. Please try again; free AI models may be temporarily busy."
    return "Video generation failed. Check the server terminal for details, then try again."


@app.post("/generate")
def generate():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("topic"), str):
        return jsonify(error="Enter a topic or question."), 400
    topic = " ".join(data["topic"].split())
    if not topic or len(topic) > 200:
        return jsonify(error="Enter a question between 1 and 200 characters."), 400
    if not generation_lock.acquire(blocking=False):
        return jsonify(error="A video is already generating. Wait for it to finish, then try again."), 409
    try:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        filename = "autoshorts-{}.mp4".format(uuid.uuid4().hex)
        output = OUTPUT / filename
        # Put the topic after -- so topics beginning with '-' remain plain input.
        result = subprocess.run(
            [sys.executable, str(ROOT / "main.py"), "--output", str(output), "--", topic],
            cwd=str(ROOT), capture_output=True, text=True, timeout=600,
        )
        if result.returncode != 0 or not output.is_file():
            app.logger.error("Generator failed: %s", result.stderr[-2500:])
            return jsonify(error=generation_error(result.stderr)), 500
        return jsonify(video_url=url_for("video", filename=filename),
                       download_url=url_for("download", filename=filename))
    except subprocess.TimeoutExpired:
        return jsonify(error="Generation took too long. Please try a shorter question or try again later."), 504
    except OSError:
        app.logger.exception("Unable to run the generator")
        return jsonify(error="Could not start generation or save the video. Check the server terminal."), 500
    finally:
        generation_lock.release()


def video_file(filename: str, attachment: bool = False):
    if not re.fullmatch(r"autoshorts-[0-9a-f]{32}\.mp4", filename):
        abort(404)
    return send_from_directory(OUTPUT, filename, mimetype="video/mp4", conditional=True,
                               as_attachment=attachment, download_name=filename, max_age=0)


@app.get("/videos/<filename>")
def video(filename):
    return video_file(filename)


@app.get("/download/<filename>")
def download(filename):
    return video_file(filename, attachment=True)


@app.errorhandler(413)
def too_large(_error):
    return jsonify(error="Your question is too long. Use at most 200 characters."), 413


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True, use_reloader=False, load_dotenv=False)
