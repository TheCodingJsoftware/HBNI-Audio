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


async def get_db_connection():
    return await asyncpg.connect(
        host=os.environ.get("POSTGRES_HOST"),
        port=os.environ.get("POSTGRES_PORT"),
        database=os.environ.get("POSTGRES_DB"),
        user=os.environ.get("POSTGRES_USER"),
        password=os.environ.get("POSTGRES_PASSWORD"),
    )


async def fetch_audio_archives():
    conn = await get_db_connection()
    try:
        rows = await conn.fetch("SELECT * FROM audioarchives")
        return [dict(row) for row in rows]
    finally:
        await conn.close()


async def update_visit(file_name):
    conn = await get_db_connection()
    try:
        await conn.execute(
            """
            UPDATE audioarchives
            SET visit_count = COALESCE(visit_count, 0) + 1, latest_visit = $1
            WHERE filename = $2
        """,
            datetime.now(),
            file_name,
        )
    finally:
        await conn.close()


async def update_click(file_name):
    conn = await get_db_connection()
    try:
        await conn.execute(
            """
            UPDATE audioarchives
            SET click_count = COALESCE(click_count, 0) + 1, latest_click = $1
            WHERE filename = $2
        """,
            datetime.now(),
            file_name,
        )
    finally:
        await conn.close()


def format_length(length_in_minutes):
    hours, minutes = divmod(int(length_in_minutes), 60)
    hours_string = f"{hours} hour{'s' if hours > 1 else ''}" if hours > 0 else ""
    minutes_string = (
        f"{minutes} minute{'s' if minutes != 1 else ''}" if minutes > 0 else ""
    )

    if hours_string and minutes_string:
        return f"{hours_string}, {minutes_string}"
    return hours_string or minutes_string

def get_duration(stream_start: str) -> float:
    start_time = datetime.strptime(stream_start, "%a, %d %b %Y %H:%M:%S %z")
    current_time = datetime.now(start_time.tzinfo)
    duration = current_time - start_time
    return duration.total_seconds() / 60


def get_grouped_data(audio_data):
    today = datetime.today()
    current_year, current_month, current_week = (
        today.year,
        today.month,
        today.isocalendar()[1],
    )

    groups = {
        "Today": {},
        "Yesterday": {},
        "Two Days Ago": {},
        "Three Days Ago": {},
        "Sometime This Week": {},
        "Last Week": {},
        "Sometime This Month": {},
        "Last Month": {},
        "Two Months Ago": {},
        "Three Months Ago": {},
        "Sometime This Year": {},
        "Last Year": {},
        "Two Years Ago": {},
        "Three Years Ago": {},
        "Everything Else": {},
    }

    for row in audio_data:
        itemData = dict(row)
        itemData["formatted_length"] = format_length(itemData["length"])

        item_date = datetime.strptime(row["date"], "%B %d %A %Y %I_%M %p")
        item_week = item_date.isocalendar()[1]
        diff_days = (today.date() - item_date.date()).days
        item_name = row["filename"].replace("_", ":").replace(".mp3", "")

        if diff_days == 0:
            itemData["uploaded_days_ago"] = "Today"
        elif diff_days == 1:
            itemData["uploaded_days_ago"] = "Yesterday"
        else:
            itemData["uploaded_days_ago"] = f"{diff_days} days ago"

        if item_date.year == current_year:
            if item_date.month == current_month:
                if item_week == current_week:
                    if diff_days == 0:
                        groups["Today"][item_name] = itemData
                    elif diff_days == 1:
                        groups["Yesterday"][item_name] = itemData
                    elif diff_days == 2:
                        groups["Two Days Ago"][item_name] = itemData
                    elif diff_days == 3:
                        groups["Three Days Ago"][item_name] = itemData
                    else:
                        groups["Sometime This Week"][item_name] = itemData
                elif item_week == current_week - 1:
                    groups["Last Week"][item_name] = itemData
                else:
                    groups["Sometime This Month"][item_name] = itemData
            elif item_date.month == current_month - 1:
                groups["Last Month"][item_name] = itemData
            elif item_date.month == current_month - 2:
                groups["Two Months Ago"][item_name] = itemData
            elif item_date.month == current_month - 3:
                groups["Three Months Ago"][item_name] = itemData
            else:
                groups["Sometime This Year"][item_name] = itemData
        elif item_date.year == current_year - 1:
            groups["Last Year"][item_name] = itemData
        elif item_date.year == current_year - 2:
            groups["Two Years Ago"][item_name] = itemData
        elif item_date.year == current_year - 3:
            groups["Three Years Ago"][item_name] = itemData
        else:
            groups["Everything Else"][item_name] = itemData

    return {key: value for key, value in groups.items() if value}


error_messages = {
    500: "Oooops! Internal Server Error. That is, something went terribly wrong.",
    404: "Uh-oh! You seem to have ventured into the void. This page doesn't exist!",
    403: "Hold up! You’re trying to sneak into a restricted area. Access denied!",
    400: "Yikes! The server couldn't understand your request. Try being clearer!",
    401: "Hey, who goes there? You need proper credentials to enter!",
    405: "Oops! You knocked on the wrong door with the wrong key. Method not allowed!",
    408: "Well, this is awkward. Your request took too long. Let's try again?",
    502: "Looks like the gateway had a hiccup. It’s not you, it’s us!",
    503: "We’re taking a quick nap. Please try again later!",
    418: "I’m a teapot, not a coffee maker! Why would you ask me to do that?",
}


class BaseHandler(RequestHandler):
    def write_error(self, status_code: int, stack_trace: str = "", **kwargs):
        error_message = error_messages.get(status_code, "Something went majorly wrong.")
        template = env.get_template("error.html")
        rendered_template = template.render(
            error_code=status_code, error_message=error_message, stack_trace=stack_trace
        )
        self.write(rendered_template)


class MainHandler(BaseHandler):
    async def get(self):
        try:
            audio_data = await fetch_audio_archives()
            grouped_data = get_grouped_data(audio_data)

            try:
                path = os.getenv("RECORDING_STATUS_PATH", r"\\Pinecone\web\HBNI Audio Stream Recorder\static\recording_status.json")
                with open(path, "r", encoding="utf-8") as f:
                    recording_status = json.load(f)
            except Exception as e:
                recording_status = {
                    "ERROR": str(e)
                }

            template = env.get_template("index.html")
            rendered_template = template.render(
                downloadableRecordings=grouped_data,
                recording_status=recording_status,
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
    async def get(self, file_name):
        conn = await get_db_connection()
        try:
            result = await conn.fetchrow(
                """
                SELECT visit_count, latest_visit
                FROM audioarchives
                WHERE filename = $1
                """,
                file_name,
            )
        finally:
            await conn.close()


        self.set_header("Content-Type", "application/json")
        if result:
            self.write(json.dumps({
                "visit_count": result["visit_count"] or 0,
                "latest_visit": result["latest_visit"].strftime("%B %d %A %Y %I:%M %p") or "N/A",
            }))
        else:
            self.write(json.dumps({"visit_count": 0, "latest_visit": "N/A"}))


class PlayRecordingHandler(BaseHandler):
    async def get(self, file_name):
        await update_visit(file_name)  # Await the async database update

        conn = await get_db_connection()
        try:
            result = await conn.fetchrow(
                """
                SELECT visit_count, latest_visit, date, description, length
                FROM audioarchives
                WHERE filename = $1
            """,
                file_name,
            )
        finally:
            await conn.close()

        if result:
            visit_count = result["visit_count"] or 0
            latest_visit = result["latest_visit"].strftime("%B %d %A %Y %I:%M %p") or "N/A"
            date = result["date"] or "N/A"
            description = result["description"] or "N/A"
            length = format_length(result["length"]) or "N/A"
        else:
            visit_count = 0
            latest_visit = "N/A"
            date = "N/A"
            description = "N/A"
            length = format_length(0)

        audio_data = await fetch_audio_archives()
        grouped_data = get_grouped_data(audio_data)

        template = env.get_template("play_recording.html")
        rendered_template = template.render(
            title=file_name.split(" - ")[0],
            file_name=file_name,
            visit_count=visit_count,
            latest_visit=latest_visit,
            date=date,
            description=description,
            length=length,
            downloadableRecordings=grouped_data,
            url_for=url_for_static,
        )
        self.write(rendered_template)


class ValidatePasswordHandler(RequestHandler):
    async def post(self):
        try:
            data: dict[str, str] = tornado.escape.json_decode(self.request.body)
            password = data.get("password")

            correct_password = os.getenv("HBNI_STREAMING_PASSWORD")

            if password == correct_password:
                # Generate a token valid for a limited time
                token = jwt.encode(
                    {
                        "exp": datetime.now() + timedelta(hours=1),
                        "iat": datetime.now(),
                        "scope": "broadcast",
                    },
                    os.getenv("SECRET_KEY"),
                    algorithm="HS256",
                )
                self.write({"success": True, "token": token})
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

        # Load the existing schedule
        with open("schedule.json", "r") as f:
            schedule: dict[str, dict[str, str]] = json.load(f)

        # Get current time
        now = datetime.now()

        # Remove old schedules
        updated_schedule = {
            key: value
            for key, value in schedule.items()
            if datetime.fromisoformat(value["start_time"]) > now
        }

        # Save the updated schedule
        with open("schedule.json", "w") as f:
            json.dump(updated_schedule, f, indent=4)

        # print("Old schedules cleaned up successfully.")
    except Exception as e:
        print(f"Error during schedule cleanup: {e}")


class ScheduleBroadcastHandler(BaseHandler):
    async def post(self):
        try:
            data: dict[str, str] = tornado.escape.json_decode(self.request.body)
            host = data.get("host")
            description = data.get("description")
            start_time = data.get("startTime")

            if not host or not description or not start_time:
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
                "start_time": start_time,
            }

            with open("schedule.json", "w") as f:
                json.dump(schedule, f, indent=4)

            self.set_status(200)
            self.write({"success": True})
        except Exception as e:
            self.set_status(500)
            self.write_error(500, stack_trace=f"{str(e)} {traceback.print_exc()}")


class BroadcastWSHandler(tornado.websocket.WebSocketHandler):
    def open(self):
        self.host: str = ""
        self.description: str = ""
        self.password: str = ""
        self.is_private: bool = False
        self.ffmpeg_process = None
        self.output_filename: str = ""
        self.starting_time: datetime = None
        self.ending_time: datetime = None

    def on_message(self, message):
        # If the received message is JSON metadata, start the ffmpeg process
        if isinstance(message, str):
            try:
                metadata: dict[str, str] = json.loads(message)
                self.host = (
                    metadata.get("host", "unknown")
                    .lower()
                    .strip()
                    .replace(" ", "_")
                    .replace("/", "")
                )
                self.description = metadata.get(
                    "description", "Unspecified description"
                ).replace("&amp;", "&")
                self.password = metadata.get("password", "")
                if self.password != os.getenv("HBNI_STREAMING_PASSWORD"):
                    self.write_message("Invalid password.")
                    return
                self.is_private = metadata.get("isPrivate", False)
                self.starting_time = datetime.now()

                self.output_filename = f'{self.host.title()} - {self.description} - {self.starting_time.strftime("%B %d %A %Y %I_%M %p")} - BROADCAST_LENGTH.wav'

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
                        "audio/mpeg",
                        "-y",  # Overwrite output file if it already exists
                        # Add metadata for the Icecast stream
                        "-metadata",
                        f"title={self.description}",
                        "-metadata",
                        f"artist={self.host}",
                        "-metadata",
                        "genre=various",
                        "-metadata",
                        f"comment={self.description}",
                        # Output 1: Icecast stream
                        "-f",
                        "mp3",
                        f"icecast://source:{self.password}@hbniaudio.hbni.net:8000/{self.host}",
                        # Output 2: Local MP3 file to save the broadcast
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
            if self.ffmpeg_process and self.ffmpeg_process.stdin:
                try:
                    # Write the audio data directly as bytes
                    self.ffmpeg_process.stdin.write(message)
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
    async def get(self):
        try:
            broadcast_data = await self.get_active_hbni_broadcasts()
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps(broadcast_data if broadcast_data else []))
        except Exception as e:
            self.set_status(500)
            self.write_error(json.dumps({"error": str(e)}))

    def is_broadcast_private(self, host: str) -> bool:
        if broadcast := active_broadcasts.get(host):
            return broadcast.is_private
        return False

    async def get_active_hbni_broadcasts(self) -> list[dict[str, Union[str, int]]]:
        # URL for fetching the JSON data
        status_url = "http://hbniaudio.hbni.net:8000/status-json.xsl"

        # Attempt to get the JSON data from the URL
        try:
            response = requests.get(status_url)
            if response.status_code == 200:
                json_content = response.text.replace('"title": - ,', '"title": null,')
                json_data = json.loads(json_content)
            else:
                self.set_status(500)
                self.write_error(500)
                return []
        except requests.exceptions.RequestException as e:
            self.set_status(500)
            self.write_error(
                500, stack_trace=f"Error while fetching JSON data: {str(e)}"
            )
            return []
        # Extract relevant data for rendering
        icestats = json_data.get("icestats", {})
        sources = icestats.get("source", {})
        broadcast_data = []

        # Prepare data for template rendering
        if sources:
            if isinstance(sources, dict):  # Only one broadcast is currently online
                host = sources.get("listenurl", "/").split("/")[-1]
                broadcast_data.append(
                    {
                        "admin": icestats.get("admin", "N/A"),
                        "location": icestats.get("location", "N/A"),
                        "server_name": sources.get("server_name", "Unspecified name"),
                        "server_description": sources.get(
                            "server_description", "Unspecified description"
                        ),
                        "genre": sources.get("genre", "N/A"),
                        "listeners": sources.get("listeners", 0),
                        "host": host,
                        "listener_peak": sources.get("listener_peak", 0),
                        "listen_url": sources.get("listenurl", "#"),
                        "stream_start": sources.get("stream_start", "N/A"),
                        "is_private": self.is_broadcast_private(host),
                        "length": f"{format_length(get_duration(sources.get('stream_start', 'N/A')))}",
                    }
                )
            elif isinstance(sources, list):  # Multiple broadcasts are currently online
                for source in sources:
                    host = source.get("listenurl", "/").split("/")[-1]
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
                            "genre": source.get("genre", "N/A"),
                            "listeners": source.get("listeners", 0),
                            "host": host,
                            "listener_peak": source.get("listener_peak", 0),
                            "listen_url": source.get("listenurl", "#"),
                            "stream_start": source.get("stream_start", "N/A"),
                            "is_private": self.is_broadcast_private(host),
                            "length": f"{format_length(get_duration(source.get('stream_start', 'N/A')))}",
                        }
                    )
        return broadcast_data


class ListenHandler(BaseHandler):
    def is_broadcast_private(self, host: str) -> bool:
        if broadcast := active_broadcasts.get(host):
            return broadcast.is_private
        return False

    def get_active_broadcast_count(self, broadcast_data) -> int:
        active_broadcast_count = 0
        for broadcast in broadcast_data:
            if not broadcast.get("is_private", False):
                active_broadcast_count += 1
        return active_broadcast_count

    async def get_active_hbni_broadcasts(self) -> list[dict[str, Union[str, int]]]:
        # URL for fetching the JSON data
        status_url = "http://hbniaudio.hbni.net:8000/status-json.xsl"

        # Attempt to get the JSON data from the URL
        try:
            response = requests.get(status_url)
            if response.status_code == 200:
                json_content = response.text.replace('"title": - ,', '"title": null,')
                json_data = json.loads(json_content)
            else:
                self.set_status(500)
                self.write_error(500)
                return []
        except requests.exceptions.RequestException as e:
            self.set_status(500)
            self.write_error(
                500, stack_trace=f"Error while fetching JSON data: {str(e)}"
            )
            return []

        # Extract relevant data for rendering
        icestats = json_data.get("icestats", {})
        sources = icestats.get("source", {})
        broadcast_data = []

        # Prepare data for template rendering
        if sources:
            if isinstance(sources, dict):  # Only one broadcast is currently online
                host = sources.get("listenurl", "/").split("/")[-1]
                broadcast_data.append(
                    {
                        "admin": icestats.get("admin", "N/A"),
                        "location": icestats.get("location", "N/A"),
                        "server_name": sources.get("server_name", "Unspecified name"),
                        "server_description": sources.get(
                            "server_description", "Unspecified description"
                        ),
                        "genre": sources.get("genre", "N/A"),
                        "listeners": sources.get("listeners", 0),
                        "host": host,
                        "listener_peak": sources.get("listener_peak", 0),
                        "listen_url": sources.get("listenurl", "#"),
                        "stream_start": sources.get("stream_start", "N/A"),
                        "is_private": self.is_broadcast_private(host),
                        "length": f"{format_length(get_duration(sources.get('stream_start', 'N/A')))}",
                    }
                )
            elif isinstance(sources, list):  # Multiple broadcasts are currently online
                for source in sources:
                    host = source.get("listenurl", "/").split("/")[-1]
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
                            "genre": source.get("genre", "N/A"),
                            "listeners": source.get("listeners", 0),
                            "host": host,
                            "listener_peak": source.get("listener_peak", 0),
                            "listen_url": source.get("listenurl", "#"),
                            "stream_start": source.get("stream_start", "N/A"),
                            "is_private": self.is_broadcast_private(host),
                            "length": f"{format_length(get_duration(source.get('stream_start', 'N/A')))}",
                        }
                    )
        return broadcast_data

    def get_scheduled_broadcast_count(self) -> int:
        with open("schedule.json", "r") as f:
            schedule = json.load(f)

        return len(schedule)

    async def get(self):
        try:
            broadcast_data = await self.get_active_hbni_broadcasts()
            broadcast_count = self.get_active_broadcast_count(broadcast_data)
            scheduled_broadcast_count = self.get_scheduled_broadcast_count()

            with open("schedule.json", "r") as f:
                schedule = json.load(f)

            template = env.get_template("listeners_page.html")
            rendered_template = template.render(
                broadcast_status=broadcast_data,
                schedule=schedule,
                broadcast_count=broadcast_count,
                scheduled_broadcast_count=scheduled_broadcast_count,
            )
            self.write(rendered_template)
        except Exception as e:
            self.set_status(500)
            self.write_error(500, stack_trace=f"{str(e)} {traceback.print_exc()}")


class DownloadLinksJSONHandler(RequestHandler):
    async def get(self):
        audio_data = await fetch_audio_archives()

        json_response = {}
        for row in audio_data:
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


class RecordingStatusJSONHandler(RequestHandler):
    def get(self):
        try:
            path = os.getenv("RECORDING_STATUS_PATH", r"\\Pinecone\web\HBNI Audio Stream Recorder\static\recording_status.json")
            with open(path, "r", encoding="utf-8") as f:
                recording_status = json.load(f)
        except Exception:
            recording_status = {"ERROR": "Could not load recording status JSON file."}

        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(recording_status, indent=4))


def make_app():
    return Application(
        [
            url(r"/", MainHandler),
            url(r"/recording_stats/(.*)", RecordingStatsHandler),
            url(r"/play_recording/(.*)", PlayRecordingHandler),
            url(r"/broadcast_ws", BroadcastWSHandler),
            url(r"/schedule_broadcast", ScheduleBroadcastHandler),
            url(r"/broadcasting_page", BroadcastHandler),
            url(r"/validate-password", ValidatePasswordHandler),
            url(r"/get_broadcast_data", CurrentBroadcastStatsHandler),
            url(r"/listeners_page", ListenHandler),
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
    app.listen(int(os.getenv("PORT", default=5053)))

    tornado.ioloop.PeriodicCallback(cleanup_old_schedules, 5 * 60 * 1000).start()

    tornado.ioloop.IOLoop.instance().start()
