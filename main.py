import json
import os
import shutil
import subprocess
import traceback
from datetime import datetime, timedelta
from typing import Any, Union

import asyncpg
import jinja2
import jwt  # PyJWT
import requests
import tornado.escape
import tornado.gen
import tornado.httpserver
import tornado.ioloop
import tornado.web
import tornado.websocket
from dotenv import load_dotenv
from tornado.web import Application, RequestHandler, url

import synology_uploader

load_dotenv()

loader = jinja2.FileSystemLoader("templates")
env = jinja2.Environment(loader=loader)


class Broadcast:
    def __init__(
        self,
        host: str,
        description: str,
        password: str,
        is_private: bool,
        start_time: datetime,
    ):
        self.host = host
        self.description = description
        self.password = password
        self.is_private = is_private
        self.start_time = start_time


active_broadcasts: dict[str, Broadcast] = {}
db_pool: asyncpg.Pool = None

audio_archive_cache = {
    "data": {},
    "grouped_data": {},
    "last_updated": datetime.min,
}

love_taps_cache = {
    "data": {},
    "last_updated": datetime.min,
}

active_broadcasts_chache = {
    "data": {},
    "last_updated": datetime.min,
}

schedule_chache = {
    "data": {},
    "last_updated": datetime.min,
}

recording_status_chache = {
    "data": {},
    "last_updated": datetime.min,
}

async def initialize_db_pool():
    global db_pool
    db_pool = await asyncpg.create_pool(
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT"),
        database=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        min_size=int(os.getenv("POSTGRES_MIN_SIZE", default=5)),  # Minimum number of connections
        max_size=int(os.getenv("POSTGRES_MAX_SIZE", default=10)),  # Adjust based on expected load
    )


async def fetch_audio_archives():
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM audioarchives")
            return [dict(row) for row in rows]
    except Exception as e:
        print(f"Database fetch error: {e}")
        return []


async def update_visit(file_name):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE audioarchives
            SET visit_count = COALESCE(visit_count, 0) + 1, latest_visit = $1
            WHERE filename = $2
            """,
            datetime.now(),
            file_name,
        )


async def execute_query(query: str, *params):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(query, *params)


def format_length(length_in_minutes):
    hours, minutes = divmod(int(length_in_minutes), 60)
    hours_string = f"{hours} hour{'s' if hours > 1 else ''}" if hours > 0 else ""
    minutes_string = (
        f"{minutes} minute{'s' if minutes != 1 else ''}" if minutes > 0 else ""
    )

    if hours_string and minutes_string:
        return f"{hours_string}, {minutes_string}"
    elif not minutes_string:
        return "Just Started"
    return hours_string or minutes_string


def get_duration(stream_start: str) -> float:
    start_time = datetime.strptime(stream_start, "%a, %d %b %Y %H:%M:%S %z")
    current_time = datetime.now(start_time.tzinfo)
    duration = current_time - start_time
    return duration.total_seconds() / 60


class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            now = datetime.now()
            diff_days = (now.date() - obj.date()).days

            base_str = obj.strftime("%B %d %A %Y %I:%M %p")

            if diff_days == 0:
                day_ago_str = "(Today)"
            elif diff_days == 1:
                day_ago_str = "(Yesterday)"
            else:
                day_ago_str = f"({diff_days} days ago)"

            return f"{base_str} {day_ago_str}"

        return super().default(obj)


def get_grouped_data(audio_data):
    today = datetime.today()
    groups = {
        "Today": [],
        "Yesterday": [],
        "Two Days Ago": [],
        "Three Days Ago": [],
        "Sometime This Week": [],
        "Last Week": [],
        "Sometime This Month": [],
        "Last Month": [],
        "Two Months Ago": [],
        "Three Months Ago": [],
        "Sometime This Year": [],
        "Last Year": [],
        "Two Years Ago": [],
        "Three Years Ago": [],
        "Everything Else": [],
    }

    for row in audio_data:
        item_data = dict(row)
        item_data["formatted_length"] = format_length(item_data["length"])
        item_data["static_url"] = url_for_static(item_data["filename"])

        item_date = datetime.strptime(row["date"], "%B %d %A %Y %I_%M %p")
        diff_days = (today.date() - item_date.date()).days

        item_data["item_date_obj"] = item_date

        if diff_days == 0:
            item_data["uploaded_days_ago"] = "Today"
        elif diff_days == 1:
            item_data["uploaded_days_ago"] = "Yesterday"
        else:
            item_data["uploaded_days_ago"] = f"{diff_days} days ago"

        if diff_days == 0:
            groups["Today"].append(item_data)
            continue
        elif diff_days == 1:
            groups["Yesterday"].append(item_data)
            continue
        elif diff_days == 2:
            groups["Two Days Ago"].append(item_data)
            continue
        elif diff_days == 3:
            groups["Three Days Ago"].append(item_data)
            continue
        elif diff_days <= 7:
            groups["Sometime This Week"].append(item_data)
            continue
        elif diff_days <= 14:
            groups["Last Week"].append(item_data)
            continue

        def month_diff(now: datetime, then: datetime) -> int:
            return (now.year - then.year) * 12 + (now.month - then.month)

        m_diff = month_diff(today, item_date)
        if m_diff == 0:
            groups["Sometime This Month"].append(item_data)
            continue
        elif m_diff == 1:
            groups["Last Month"].append(item_data)
            continue
        elif m_diff == 2:
            groups["Two Months Ago"].append(item_data)
            continue
        elif m_diff == 3:
            groups["Three Months Ago"].append(item_data)
            continue

        y_diff = today.year - item_date.year
        if y_diff == 0:
            groups["Sometime This Year"].append(item_data)
        elif y_diff == 1:
            groups["Last Year"].append(item_data)
        elif y_diff == 2:
            groups["Two Years Ago"].append(item_data)
        elif y_diff == 3:
            groups["Three Years Ago"].append(item_data)
        else:
            groups["Everything Else"].append(item_data)

    for group_name, items in groups.items():
        items.sort(key=lambda x: x["item_date_obj"], reverse=True)

    desired_order = [
        "Today",
        "Yesterday",
        "Two Days Ago",
        "Three Days Ago",
        "Sometime This Week",
        "Last Week",
        "Sometime This Month",
        "Last Month",
        "Two Months Ago",
        "Three Months Ago",
        "Sometime This Year",
        "Last Year",
        "Two Years Ago",
        "Three Years Ago",
        "Everything Else",
    ]

    # Build a final dict in that order, skipping empty groups
    final_groups = {}
    for key in desired_order:
        if groups[key]:  # Not empty
            final_groups[key] = groups[key]

    return final_groups


def is_broadcast_private(host: str) -> bool:
    if broadcast := active_broadcasts.get(host):
        return broadcast.is_private
    return False


async def get_active_icecast_broadcasts() -> list[dict[str, Union[str, int]]]:
    broadcast_data = []

    icecast_urls = [
        "https://hbniaudio.hbni.net",
        "https://broadcast.hbni.net",
    ]
    for icecast_url in icecast_urls:
        try:
            response = requests.get(f'{icecast_url}/status-json.xsl', timeout=5)
            if response.status_code == 200:
                json_content = response.text.replace('"title": - ,', '"title": null,') # Some broadcasts are weird
                json_data = json.loads(json_content)
            else:
                return []
        except requests.exceptions.RequestException as e:
            return []

        # Extract relevant data for rendering
        icestats = json_data.get("icestats", {})
        sources = icestats.get("source", {})

        # Prepare data for template rendering
        if sources:
            if isinstance(sources, dict):
                sources = [sources]
            for source in sources:
                mount_point = source.get("listenurl", "/").split("/")[-1]
                broadcast_data.append(
                    {
                        "admin": icestats.get("admin", "N/A"),
                        "location": icestats.get("location", "N/A"),
                        "server_name": source.get(
                            "server_name", "Unspecified name"
                        ),
                        "server_description": source.get(
                            "server_description", "Unspecified description"
                        ),
                        "genre": source.get("genre", "various"),
                        "listeners": source.get("listeners", 0),
                        "host": mount_point,
                        "colony": mount_point,
                        "moint_point": mount_point,
                        "listener_peak": source.get("listener_peak", 0),
                        "listen_url": source.get("listenurl", f"{icecast_url}/{mount_point}"),
                        "stream_start": source.get("stream_start", "N/A"),
                        "is_private": is_broadcast_private(mount_point),
                        "source_url": icecast_url,
                        "length": f"{format_length(get_duration(source.get('stream_start', 'N/A')))}",
                    }
                )
    return broadcast_data


def get_active_broadcast_count(broadcast_data) -> int:
    active_broadcast_count = 0
    for broadcast in broadcast_data:
        if not broadcast.get("is_private", False):
            active_broadcast_count += 1
    return active_broadcast_count


def get_scheduled_broadcast_count() -> int:
    return len(schedule_chache["data"])


error_messages = {
    500: "Oooops! Internal Server Error. That is, something went terribly wrong.",
    404: "Uh-oh! You seem to have ventured into the void. This page doesn't exist!",
    403: "Hold up! You're trying to sneak into a restricted area. Access denied!",
    400: "Yikes! The server couldn't understand your request. Try being clearer!",
    401: "Hey, who goes there? You need proper credentials to enter!",
    405: "Oops! You knocked on the wrong door with the wrong key. Method not allowed!",
    408: "Well, this is awkward. Your request took too long. Let's try again?",
    502: "Looks like the gateway had a hiccup. It's not you, it's us!",
    503: "We're taking a quick nap. Please try again later!",
    418: "I'm a teapot, not a coffee maker! Why would you ask me to do that?",
}


class BaseHandler(RequestHandler):
    def write_error(self, status_code: int, stack_trace: str = "", **kwargs):
        error_message = error_messages.get(status_code, "Something went majorly wrong.")
        template = env.get_template("error.html")
        rendered_template = template.render(
            error_code=status_code, error_message=error_message, stack_trace=stack_trace
        )
        self.write(rendered_template)


async def refresh_archive_data():
    global audio_archive_cache
    try:
        updated_data = await fetch_audio_archives()
        audio_archive_cache["data"] = updated_data
        audio_archive_cache["grouped_data"] = get_grouped_data(updated_data)
        audio_archive_cache["last_updated"] = datetime.now()
    except Exception as e:
        print(f"Error refreshing archive data: {e}")


async def refresh_active_broadcasts_data():
    global active_broadcasts_chache
    try:
        updated_data = await get_active_icecast_broadcasts()
        active_broadcasts_chache["data"] = updated_data
        active_broadcasts_chache["active_broadcasts_count"] = get_active_broadcast_count(updated_data)
        active_broadcasts_chache["last_updated"] = datetime.now()
    except Exception as e:
        print(f"Error refreshing active broadcasts data: {e}")


def refresh_scedule_data():
    global schedule_chache
    try:
        with open("schedule.json", "r") as f:
            updated_data = json.load(f)
        schedule_chache["data"] = updated_data
        schedule_chache["last_updated"] = datetime.now()
    except Exception as e:
        print(f"Error refreshing schedule data: {e}")


async def refresh_recording_status_data():
    global recording_status_chache
    try:
        path = os.getenv(
            "RECORDING_STATUS_PATH",
            r"\\Pinecone\web\HBNI Audio Stream Recorder\static\recording_status.json",
        )
        with open(path, "r", encoding="utf-8") as f:
            updated_data = json.load(f)
        recording_status_chache["data"] = updated_data
        recording_status_chache["recording_status_count"] = len(updated_data)
        recording_status_chache["last_updated"] = datetime.now()
    except Exception as e:
        print(f"Error refreshing recording status data: {e}")


async def refresh_love_taps_cache():
    global love_taps_cache
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT SUM(tap_count) as total_taps FROM love_taps"
        )
        total_taps = row["total_taps"] or 0
        love_taps_cache["data"] = total_taps
        love_taps_cache["last_updated"] = datetime.now()


class GetArchiveDataHandler(BaseHandler):
    def get(self):
        try:
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps(audio_archive_cache["grouped_data"], cls=DateTimeEncoder))
        except Exception as e:
            self.set_status(500)
            self.write_error(500, stack_trace=f"{str(e)} {traceback.print_exc()}")


class GetEventCountHandler(BaseHandler):
    def get(self):
        self.set_header("Content-Type", "application/json")
        self.write(
            json.dumps(
                {
                    "broadcast_count": active_broadcasts_chache["active_broadcasts_count"],
                    "scheduled_broadcast_count": recording_status_chache["recording_status_count"],
                }
            )
        )

class LoveTapsUpdateHandler(tornado.web.RequestHandler):
    async def post(self):
        try:
            data = json.loads(self.request.body)
            count = data.get("count", 0)

            if count > 0:
                async with db_pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO love_taps (tap_count, timestamp)
                        VALUES ($1, $2)
                        """,
                        count,
                        datetime.now(),
                    )
            self.write({"status": "success"})
        except Exception as e:
            self.set_status(500)
            self.write({"status": "error", "message": str(e)})


class LoveTapsFetchHandler(BaseHandler):
    def get(self):
        try:
            self.write({"count": love_taps_cache["data"]})
        except Exception as e:
            self.set_status(500)
            self.write_error(500, stack_trace=f"{str(e)} {traceback.print_exc()}")


class MainHandler(BaseHandler):
    def get(self):
        try:
            template = env.get_template("index.html")
            rendered_template = template.render()
            self.write(rendered_template)
        except Exception as e:
            self.set_status(500)
            self.write_error(500, stack_trace=f"{str(e)} {traceback.print_exc()}")


class FaviconHandler(BaseHandler):
    def get(self):
        try:
            self.set_header("Content-Type", "image/png")
            self.write(open("static/icon.png", "rb").read())
        except Exception as e:
            self.set_status(500)
            self.write_error(500, stack_trace=f"{str(e)} {traceback.print_exc()}")


class FaqHandler(BaseHandler):
    def get(self):
        try:
            template = env.get_template("faq.html")
            rendered_template = template.render()
            self.write(rendered_template)
        except Exception as e:
            self.set_status(500)
            self.write_error(500, stack_trace=f"{str(e)} {traceback.print_exc()}")


class BroadcastingGuideHandler(BaseHandler):
    def get(self):
        try:
            template = env.get_template("broadcasting_guide.html")
            rendered_template = template.render()
            self.write(rendered_template)
        except Exception as e:
            self.set_status(500)
            self.write_error(500, stack_trace=f"{str(e)} {traceback.print_exc()}")


class GetRecordingStatusHandler(BaseHandler):
    def get(self):
        try:
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps(recording_status_chache["data"], indent=4))
        except Exception as e:
            self.set_status(500)
            self.write_error(500, stack_trace=f"{str(e)} {traceback.print_exc()}")


class AudioArchivesHandler(BaseHandler):
    def get(self):
        try:
            template = env.get_template("archives.html")
            rendered_template = template.render(
                url_for=url_for_static,
            )
            self.write(rendered_template)
        except Exception as e:
            self.set_status(500)
            self.write_error(500, stack_trace=f"{str(e)} {traceback.print_exc()}")


def url_for_static(filename):
    static_recordings_path = os.getenv(
        "STATIC_RECORDINGS_PATH", "/app/static/Recordings"
    )
    return f"{static_recordings_path}/{filename}"


class RecordingStatsHandler(BaseHandler):
    def get(self, file_name):
        matching_archive = None
        for archive in audio_archive_cache["data"]:
            if archive["filename"] == file_name:
                matching_archive = archive
                break

        self.set_header("Content-Type", "application/json")
        if matching_archive:
            self.write(
                json.dumps(
                    {
                        "visit_count": matching_archive["visit_count"] or 0,
                        "latest_visit": matching_archive["latest_visit"].strftime(
                            "%B %d %A %Y %I:%M %p"
                        )
                        if matching_archive["latest_visit"]
                        else "N/A",
                    }
                )
            )
        else:
            self.write(json.dumps({"visit_count": 0, "latest_visit": "N/A"}))


class PlayRecordingHandler(BaseHandler):
    async def get(self, file_name):
        await update_visit(file_name)  # Keep the visit count update

        matching_archive = None
        for archive in audio_archive_cache["data"]:
            if archive["filename"] == file_name:
                matching_archive = archive
                break

        if matching_archive:
            visit_count = matching_archive["visit_count"] or 0
            latest_visit = (
                matching_archive["latest_visit"].strftime("%B %d %A %Y %I:%M %p")
                if matching_archive["latest_visit"]
                else "N/A"
            )
            date = matching_archive["date"] or "N/A"
            description = matching_archive["description"] or "N/A"
            length = format_length(matching_archive["length"]) or "N/A"
        else:
            visit_count = 0
            latest_visit = "N/A"
            date = "N/A"
            description = "N/A"
            length = format_length(0)

        template = env.get_template("play_recording.html")
        rendered_template = template.render(
            title=file_name.split(" - ")[0],
            file_name=file_name,
            visit_count=visit_count,
            latest_visit=latest_visit,
            date=date,
            description=description,
            length=length,
            downloadableRecordings=audio_archive_cache["grouped_data"],
            url_for=url_for_static,
        )
        self.write(rendered_template)


class ValidatePasswordHandler(RequestHandler):
    def post(self):
        try:
            data: dict[str, str] = tornado.escape.json_decode(self.request.body)
            password = data.get("password")

            correct_password = os.getenv("ICECAST_BROADCASTING_PASSWORD")

            if password == correct_password:
                self.write({"success": True})
            else:
                self.set_status(401)
                self.write({"success": False, "error": "Invalid password"})
        except Exception as e:
            print(e)
            self.set_status(500)
            self.write({"success": False, "error": str(e)})


def cleanup_old_schedules():
    try:
        if not os.path.exists("schedule.json"):
            return

        with open("schedule.json", "r") as f:
            schedule: dict[str, dict[str, str]] = json.load(f)

        now = datetime.now()

        # Parse the schedule dates and remove old entries
        updated_schedule = {
            key: value
            for key, value in schedule.items()
            if datetime.strptime(value["start_time"], "%Y-%m-%d %H:%M") > now
        }

        # Save the updated schedule
        with open("schedule.json", "w") as f:
            json.dump(updated_schedule, f, indent=4)

        refresh_scedule_data()

    except Exception as e:
        print(f"Error during schedule cleanup: {e}")


class ScheduleBroadcastHandler(BaseHandler):
    def post(self):
        try:
            data: dict[str, str] = tornado.escape.json_decode(self.request.body)
            host = data.get("host")
            description = data.get("description")
            start_time = data.get("startTime")
            parsed_time = datetime.strptime(start_time, "%Y-%m-%d %H:%M")
            formatted_time = parsed_time.strftime("%A, %B %d, %Y at %I:%M %p")

            if not (host and description and start_time):
                self.set_status(400)
                self.write({"success": False, "error": "Missing required fields"})
                return

            if not os.path.exists("schedule.json"):
                with open("schedule.json", "w") as f:
                    json.dump({}, f)

            with open("schedule.json", "r") as f:
                schedule = json.load(f)

            schedule[datetime.now().isoformat()] = {
                "host": host,
                "description": description,
                "start_time": formatted_time,
            }

            with open("schedule.json", "w") as f:
                json.dump(schedule, f, indent=4)

            refresh_scedule_data()

            self.set_status(200)
            self.write({"success": True})
        except Exception as e:
            self.set_status(500)
            self.write_error(500, stack_trace=f"{str(e)} {traceback.print_exc()}")


class BroadcastWSHandler(tornado.websocket.WebSocketHandler):
    def open(self):
        load_dotenv()

        self.host: str = ""
        self.description: str = ""
        self.password: str = ""
        self.is_private: bool = False
        self.ffmpeg_process = None
        self.output_filename: str = ""
        self.starting_time: datetime = None
        self.ending_time: datetime = None

    def generate_silence(self, duration_ms, sample_rate=48000, channels=2):
        num_samples = int(sample_rate * (duration_ms / 1000.0) * channels)
        return b"\x00" * num_samples * 2  # 16-bit PCM (2 bytes per sample)

    def on_message(self, message):
        # If the received message is JSON metadata, start the ffmpeg process
        if isinstance(message, str):
            try:
                metadata: dict[str, str] = json.loads(message)
                self.password = metadata.get("password", "")
                if self.password != os.getenv("ICECAST_BROADCASTING_PASSWORD"):
                    self.write_message("Invalid password.")
                    return

                self.host = (
                    metadata.get("host", "unknown")
                )
                self.description = metadata.get(
                    "description", "Unspecified description"
                )
                self.is_private = metadata.get("isPrivate", False)
                self.mount_point = metadata.get("mountPoint", "unknown")
                self.starting_time = datetime.now()
                self.output_filename = f'{self.host.title()} - {self.description} - {self.starting_time.strftime("%B %d %A %Y %I_%M %p")} - BROADCAST_LENGTH.wav'

                ICECAST_BROADCASTING_IP = os.getenv("ICECAST_BROADCASTING_IP") if not self.is_private else os.getenv("PRIVATE_ICECAST_BROADCASTING_IP")
                ICECAST_BROADCASTING_PORT = os.getenv("ICECAST_BROADCASTING_PORT") if not self.is_private else os.getenv("PRIVATE_ICECAST_BROADCASTING_PORT")
                ICECAST_BROADCASTING_SOURCE = os.getenv("ICECAST_BROADCASTING_SOURCE") if not self.is_private else os.getenv("PRIVATE_ICECAST_BROADCASTING_SOURCE")

                self.ffmpeg_process = subprocess.Popen(
                    [
                        "ffmpeg",
                        "-re",
                        "-i",
                        "-",
                        "-c:a",
                        "libmp3lame",  # Use MP3 codec
                        "-b:a",
                        "128k",  # Audio bitrate
                        "-content_type",
                        "audio/mpeg",  # Set MIME type
                        "-y",  # Overwrite output file if it already exists
                        "-metadata",
                        f"title={self.description}",
                        "-metadata",
                        f"artist={self.host}",
                        "-metadata",
                        "genre=RECORDING",
                        "-metadata",
                        "comment=RECORDING",
                        "-ice_name",
                        self.host,
                        "-ice_description",
                        self.description,
                        "-ice_genre",
                        "RECORDING",
                        "-ice_url",
                        f"{ICECAST_BROADCASTING_SOURCE}/{self.mount_point}",
                        "-ice_public",
                        f"{'0' if self.is_private else '1'}",  # Whether the stream is public (1) or private (0)
                        "-f",
                        "mp3",
                        f"icecast://source:{self.password}@{ICECAST_BROADCASTING_IP}:{ICECAST_BROADCASTING_PORT}/{self.mount_point}",  # Icecast URL
                        "-f",
                        "wav",
                        self.output_filename,
                    ],
                    stdin=subprocess.PIPE,  # We want to send binary audio data
                )

                # Check if the process started successfully
                if self.ffmpeg_process.poll() is None:
                    print(
                        f"FFmpeg process started successfully for {self.output_filename}"
                    )
                    active_broadcasts[self.host] = Broadcast(
                        self.host,
                        self.description,
                        self.password,
                        self.is_private,
                        datetime.now(),
                    )
                else:
                    print(f"FFmpeg process failed to start for {self.output_filename}")

            except json.JSONDecodeError:
                self.write_message("Invalid metadata format.")
            except Exception as e:
                print(f"Error starting FFmpeg process: {e}")

        # If the received message is binary (audio data)
        elif isinstance(message, bytes):
            silence_buffer = self.generate_silence(1) # 1ms
            if self.ffmpeg_process and self.ffmpeg_process.stdin:
                try:
                    if message:  # Non-empty audio data
                        self.ffmpeg_process.stdin.write(message)
                    else:  # Silence during pause
                        self.ffmpeg_process.stdin.write(silence_buffer)
                except BrokenPipeError:
                    print("FFmpeg process has ended. Unable to write more data.")
                except Exception as e:
                    print(f"Error writing to FFmpeg process stdin: {e}")

    def on_close(self):
        if self.ffmpeg_process:
            try:
                if self.ffmpeg_process.stdin:
                    self.ffmpeg_process.stdin.close()
            except Exception as e:
                print(f"Error closing stdin: {e}")

            # Terminate FFmpeg process gracefully
            self.ffmpeg_process.terminate()

            try:
                self.ffmpeg_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Kill FFmpeg process not so gracefully
                self.ffmpeg_process.kill()
            print("FFmpeg process has gracefully been terminated.")

            self.ending_time = datetime.now()

            delta = self.ending_time - self.starting_time
            total_minutes = delta.total_seconds() / 60
            hours, remainder = divmod(delta.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)

            if hours <= 0:
                formated_length = f"{minutes:02d}m {seconds:02d}s"
            else:
                formated_length = f"{hours:02d}h {minutes:02d}m {seconds:02d}s"

            new_output_filename = self.output_filename.replace(
                "BROADCAST_LENGTH", formated_length
            )
            static_recordings_path = (
                os.getenv("STATIC_RECORDINGS_PATH", "/app/static/Recordings")
                .replace("\\", "/")
                .replace("//", "/")
                .replace("//", "\\\\")
                .replace("/", "\\")
            )
            if total_minutes >= 10.0 and not (self.is_private or self.host == "test"):
                shutil.move(
                    self.output_filename,
                    f"{static_recordings_path}\\{new_output_filename}",
                )
                synology_uploader.upload(
                    new_output_filename,
                    f"{static_recordings_path}\\{new_output_filename}",
                    self.host,
                    self.description,
                    self.starting_time.strftime("%B %d %A %Y %I_%M %p"),
                    total_minutes,
                )
            elif not self.is_private:
                shutil.move(
                    self.output_filename,
                    f"{static_recordings_path}\\TESTS\\{new_output_filename}",
                )


class BroadcastHandler(BaseHandler):
    def get(self):
        template = env.get_template("broadcasting_page.html")
        rendered_template = template.render()
        self.write(rendered_template)


class CurrentBroadcastStatsHandler(RequestHandler):
    def get(self):
        try:
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps(active_broadcasts_chache["data"]))
        except Exception as e:
            self.set_status(500)
            self.write_error(json.dumps({"error": str(e)}))


class ListenHandler(BaseHandler):
    def get(self):
        try:
            template = env.get_template("listeners_page.html")
            rendered_template = template.render(
                broadcast_status=active_broadcasts_chache["data"],
                schedule=schedule_chache["data"],
                broadcast_count=active_broadcasts_chache["active_broadcasts_count"],
                scheduled_broadcast_count=recording_status_chache["recording_status_count"],
            )
            self.write(rendered_template)
        except Exception as e:
            self.set_status(500)
            self.write_error(500, stack_trace=f"{str(e)} {traceback.print_exc()}")


class DownloadLinksJSONHandler(BaseHandler):
    def get(self):
        try:
            json_response = {}
            for row in audio_archive_cache["data"]:
                file_name = row["filename"]
                file_description = row["description"]
                file_date = row["date"]
                file_length = row["length"]
                host = row["host"]
                file_id = row["id"]
                download_link = row["download_link"]

                json_response[file_name] = {
                    "date": file_date,
                    "description": file_description,
                    "downloadLink": download_link,
                    "length": file_length,
                    "host": host,
                    "id": file_id,
                }

            self.set_header("Content-Type", "application/json")
            self.write(json.dumps(json_response, indent=4))
        except Exception as e:
            self.set_status(500)
            self.write_error(500, stack_trace=f"{str(e)} {traceback.print_exc()}")



class RecordingStatusJSONHandler(BaseHandler):
    def get(self):
        try:
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps(recording_status_chache["data"], indent=4))
        except Exception as e:
            self.set_status(500)
            self.write_error(500, stack_trace=f"{str(e)} {traceback.print_exc()}")


def make_app():
    return Application(
        [
            url(r"/", MainHandler),
            url(r"/update-love-taps", LoveTapsUpdateHandler),
            url(r"/fetch-love-taps", LoveTapsFetchHandler),
            url(r"/favicon.ico", FaviconHandler),
            url(r"/faq", FaqHandler),
            url(r"/frequently_asked_questions", FaqHandler),
            url(r"/recording_stats/(.*)", RecordingStatsHandler),
            url(r"/play_recording/(.*)", PlayRecordingHandler),
            url(r"/broadcast_ws", BroadcastWSHandler),
            url(r"/schedule_broadcast", ScheduleBroadcastHandler),
            url(r"/listeners_page", ListenHandler),
            url(r"/listening", ListenHandler),
            url(r"/events", ListenHandler),
            url(r"/broadcasting_page", BroadcastHandler),
            url(r"/broadcasting", BroadcastHandler),
            url(r"/broadcasting_guide", BroadcastingGuideHandler),
            url(r"/archives", AudioArchivesHandler),
            url(r"/audio_archive", AudioArchivesHandler),
            url(r"/validate-password", ValidatePasswordHandler),
            url(r"/get_broadcast_data", CurrentBroadcastStatsHandler),
            url(r"/get_archive_data", GetArchiveDataHandler),
            url(r"/get_event_count", GetEventCountHandler),
            url(r"/get_recording_status", GetRecordingStatusHandler),
            url(r"/download_links.json", DownloadLinksJSONHandler),
            url(
                r"/app/static/Recordings/(.*)",
                tornado.web.StaticFileHandler,
                {"path": os.getenv("STATIC_RECORDINGS_PATH", "/app/static/Recordings")},
            ),
            url(r"/recording_status.json", RecordingStatusJSONHandler),
            url(r"/.*", BaseHandler),
        ],
        static_path=os.path.join(os.path.dirname(__file__), "static"),
    )


if __name__ == "__main__":
    app = tornado.httpserver.HTTPServer(make_app())
    app.bind(int(os.getenv("PORT", default=5053)))
    app.start(1)
    # Run at startup
    tornado.ioloop.IOLoop.current().run_sync(initialize_db_pool)
    tornado.ioloop.IOLoop.current().run_sync(refresh_archive_data)
    tornado.ioloop.IOLoop.current().run_sync(refresh_active_broadcasts_data)
    tornado.ioloop.IOLoop.current().run_sync(refresh_scedule_data)
    tornado.ioloop.IOLoop.current().run_sync(refresh_recording_status_data)
    tornado.ioloop.IOLoop.current().run_sync(refresh_love_taps_cache)
    # Run every 5 minutes
    tornado.ioloop.PeriodicCallback(refresh_archive_data, 5 * 60 * 1000).start()
    tornado.ioloop.PeriodicCallback(refresh_active_broadcasts_data, 5 * 60 * 1000).start()
    tornado.ioloop.PeriodicCallback(refresh_recording_status_data, 5 * 60 * 1000).start()
    tornado.ioloop.PeriodicCallback(refresh_scedule_data, 5 * 60 * 1000).start()
    tornado.ioloop.PeriodicCallback(refresh_love_taps_cache, 5 * 60 * 1000).start()
    tornado.ioloop.PeriodicCallback(cleanup_old_schedules, 5 * 60 * 1000).start()
    tornado.ioloop.IOLoop.instance().start()
