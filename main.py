import json
import os
import re
import subprocess
import traceback
from datetime import datetime
from urllib.parse import unquote, urlparse

import aiofiles
import aiohttp
import asyncpg
import firebase_admin
import jinja2
import requests
import tornado.escape
import tornado.gen
import tornado.httpserver
import tornado.ioloop
import tornado.web
import tornado.websocket
from dotenv import load_dotenv
from firebase_admin import credentials, messaging
from tornado.web import Application, HTTPError, RequestHandler, url

cred = credentials.Certificate("hbni-audio-1c43f2c03734.json")
firebase_admin.initialize_app(cred)

load_dotenv()

loader = jinja2.FileSystemLoader("dist/html")
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
    "active_broadcasts_count": 0,
    "last_updated": datetime.min,
}

schedule_chache = {
    "all_schedules": [],
    "active_schedules": [],
    "active_schedules_count": 0,
    "last_updated": datetime.min,
}

trending_archives_cache = {"data": {}, "last_update": datetime.min}

recording_status_chache = {
    "data": {},
    "recording_status_count": 0,
    "last_updated": datetime.min,
}
db_settings = {
    "host": os.getenv("POSTGRES_HOST"),
    "port": int(os.getenv("POSTGRES_PORT", 5434)),
    "database": os.getenv("POSTGRES_DB"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}
recording_files_share_hashes = {}
FILEBROWSER_URL = os.getenv("FILEBROWSER_URL")
FILEBROWSER_USERNAME = os.getenv("FILEBROWSER_USERNAME")
FILEBROWSER_PASSWORD = os.getenv("FILEBROWSER_PASSWORD")
FILEBROWSER_UPLOAD_PATH = os.getenv("FILEBROWSER_UPLOAD_PATH", "HBNI-Audio/Recordings")

# Global dict of filebrowser items {name: full_path}
FILEBROWSER_ITEMS = {}


async def get_filebrowser_token():
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{os.getenv('FILEBROWSER_URL')}/api/login",
            json={
                "username": os.getenv("FILEBROWSER_USERNAME"),
                "password": os.getenv("FILEBROWSER_PASSWORD"),
            },
        ) as response:
            token = await response.text()
            return token.strip()


async def get_public_share_url(file_relative_path: str, token: str) -> str:
    headers = {"X-Auth": token.strip(), "accept": "*/*"}
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{FILEBROWSER_URL}/api/share/{file_relative_path}",
            headers=headers,
            json={"path": f"/{file_relative_path}"},
        ) as response:
            if response.status != 200:
                body = await response.text()
                raise Exception(f"Failed to create share link: {response.status} - {body}")
            data = await response.json()
            return data["hash"]


async def list_filebrowser_items():
    global FILEBROWSER_ITEMS
    token = await get_filebrowser_token()
    headers = {"X-Auth": token, "Accept": "application/json"}

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{FILEBROWSER_URL}/api/resources/{FILEBROWSER_UPLOAD_PATH}",
            headers=headers,
        ) as response:
            if response.status != 200:
                body = await response.text()
                raise Exception(f"Failed to list items: {response.status} - {body}")
            data = await response.json()

    items = data.get("items", [])
    FILEBROWSER_ITEMS = {item["name"]: item["path"].lstrip("/") for item in items if not item["isDir"]}


def extract_filename_from_download_link(download_link: str) -> str:
    path = urlparse(download_link).path
    return unquote(os.path.basename(path)).replace("&amp;", "&").replace("&Amp;", "&")


async def update_audio_hashes():
    await list_filebrowser_items()
    token = await get_filebrowser_token()

    async with db_pool.acquire() as conn:
        query = """
        SELECT * FROM audioarchives
        WHERE download_link LIKE '%play_recording%'
        ORDER BY date DESC;
        """
        rows = await conn.fetch(query)
        for row in rows:
            download_link = row["download_link"]
            filename = extract_filename_from_download_link(download_link)
            current_hash = row["share_hash"]

            # if current_hash:
            #     print(f"✅ Already has share_hash: {filename} → {current_hash}")
            #     continue

            filebrowser_path = FILEBROWSER_ITEMS.get(filename)
            if not filebrowser_path:
                print(f"⚠️ File not found in FileBrowser: {filename}")
                continue

            try:
                share_hash = await get_public_share_url(filebrowser_path, token)
                update_query = "UPDATE audioarchives SET share_hash = $1 WHERE download_link = $2;"
                await conn.execute(update_query, share_hash, download_link)
                print(f"✅ Added share_hash for: {filename} → {share_hash}")
            except Exception as e:
                print(f"❌ Failed to create share for {filename}: {str(e)}")


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
    minutes_string = f"{minutes} minute{'s' if minutes != 1 else ''}" if minutes > 0 else ""

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
    if (broadcast := active_broadcasts.get(host)) and broadcast.is_private:
        return True

    host_lc = host.lower()
    return any(keyword in host_lc for keyword in ("priv", "prv", "private"))


def get_active_icecast_broadcasts() -> list[dict[str, str | int]] | None:
    broadcast_data = []

    icecast_urls = [
        "https://hbniaudio.hbni.net",
    ]
    for icecast_url in icecast_urls:
        try:
            response = requests.get(f"{icecast_url}/status-json.xsl", timeout=10)
            if response.status_code == 200:
                json_content = response.text.replace('"title": - ,', '"title": null,')  # Some broadcasts are weird
                json_data = json.loads(json_content)
            else:
                continue
        except Exception as e:
            print(e)
            continue

        # Extract relevant data for rendering
        icestats = json_data.get("icestats", {})
        sources = icestats.get("source", {})

        # Prepare data for template rendering
        if sources:
            if isinstance(sources, dict):
                sources = [sources]
            for source in sources:
                is_private_by_genre = source.get("genre", "various") == "private"
                mount_point = source.get("listenurl", "/").split("/")[-1]
                broadcast_data.append(
                    {
                        "admin": icestats.get("admin", "N/A"),
                        "location": icestats.get("location", "N/A"),
                        "server_name": source.get("server_name", "Unspecified name"),
                        "server_description": source.get("server_description", "Unspecified description"),
                        "genre": source.get("genre", "various"),
                        "listeners": source.get("listeners", 0),
                        "host": mount_point,
                        "colony": mount_point,
                        "mount_point": mount_point,
                        "listener_peak": source.get("listener_peak", 0),
                        "listen_url": source.get("listenurl", f"{icecast_url}/{mount_point}"),
                        "stream_start": source.get("stream_start", "N/A"),
                        "is_private": is_broadcast_private(mount_point) or is_private_by_genre,
                        "source_url": icecast_url,
                        "length": f"{format_length(get_duration(source.get('stream_start', 'N/A')))}",
                    }
                )
    return broadcast_data


async def get_recording_files_share_hashes():
    global recording_files_share_hashes
    token = await get_filebrowser_token()
    headers = {"X-Auth": token.strip(), "accept": "*/*"}
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{os.getenv('FILEBROWSER_URL')}/api/shares",
            headers=headers,
        ) as response:
            if response.status != 200:
                body = await response.text()
                raise Exception(f"Failed to create share link: {response.status} - {body}")
            data = await response.json()

    for shared_file in data:
        recording_files_share_hashes.update({shared_file["hash"]: shared_file["path"].split("/")[-1]})


def get_active_broadcast_count(broadcast_data) -> int:
    active_broadcast_count = 0
    for broadcast in broadcast_data:
        if not broadcast.get("is_private", False):
            active_broadcast_count += 1
    return active_broadcast_count


class AnalyticsMixin:
    async def track_visit(self):
        try:
            path = self.request.path
            user_agent = self.request.headers.get("User-Agent", "Unknown")
            ip_address = self.request.remote_ip
            referrer = self.request.headers.get("Referer", "Direct")

            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO page_analytics
                    (path, user_agent, ip_address, referrer)
                    VALUES ($1, $2, $3, $4)
                """,
                    path,
                    user_agent,
                    ip_address,
                    referrer,
                )
        except Exception as e:
            print(f"Error tracking analytics: {e}")


class BaseHandler(RequestHandler, AnalyticsMixin):
    async def prepare(self):
        await self.track_visit()

        if broadcast_name := self._extract_broadcast_name():
            for broadcast in active_broadcasts_chache["data"]:
                if broadcast.get("host") == broadcast_name:
                    self.redirect(f"/play_live/{broadcast_name}")
                    self._finished = True
                    return

    def write_error(self, status_code: int, **kwargs):
        error_message = error_messages.get(status_code, "Something went majorly wrong.")
        template = env.get_template("error.html")
        rendered_template = template.render(error_code=status_code, error_message=error_message)
        self.write(rendered_template)

    def _extract_broadcast_name(self) -> str | None:
        # Extracts the broadcast name from the URL if it looks like /play_live/<broadcast_name> or similar
        path = self.request.path
        match = re.search(r"/([a-zA-Z0-9_-]+)", path)
        return match.group(1) if match else None


async def refresh_archive_data():
    global audio_archive_cache, recording_files_share_hashes
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("""
                                    SELECT * FROM audioarchives
                                    WHERE download_link IS NOT NULL
                                        AND download_link <> ''
                                        AND NOT (
                                            download_link LIKE '%mega.nz%' OR
                                            download_link LIKE '%mega.co.nz%'
                                        )
                                    """)
            updated_data = [dict(row) for row in rows]
            audio_archive_cache["data"] = updated_data
            audio_archive_cache["grouped_data"] = get_grouped_data(updated_data)
            audio_archive_cache["last_updated"] = datetime.now()
    except Exception as e:
        print(f"Error refreshing archive data: {e}")


def refresh_active_broadcasts_data():
    global active_broadcasts_chache
    try:
        updated_data = get_active_icecast_broadcasts()
        if updated_data is None:
            return
        active_broadcasts_chache["data"] = updated_data
        active_broadcasts_chache["active_broadcasts_count"] = get_active_broadcast_count(updated_data)
        active_broadcasts_chache["last_updated"] = datetime.now()
    except Exception as e:
        print(f"Error refreshing active broadcasts data: {e}")


async def refresh_scedule_data():
    global schedule_chache
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, host, description, duration, speakers, start_time
                FROM scheduledbroadcasts
                ORDER BY created_at DESC
            """)

            updated_data = {}
            for row in rows:
                parsed_time = datetime.strptime(row["start_time"], "%Y-%m-%d %H:%M")
                formatted_time = parsed_time.strftime("%A, %B %d, %Y at %I:%M %p")
                updated_data[row["id"]] = {
                    "id": row["id"],
                    "host": row["host"],
                    "description": row["description"],
                    "speakers": row["speakers"],
                    "duration": row["duration"],
                    "start_time": row["start_time"],
                    "formatted_time": formatted_time,
                }

        schedule_chache["all_schedules"] = updated_data

        current_time = datetime.now()  # Filter schedules where start_time is in the future or within the last 2 hours
        filtered_schedules = []
        for schedule_id, schedule in updated_data.items():
            try:
                start_time = datetime.strptime(schedule["start_time"], "%Y-%m-%d %H:%M")
                time_diff = start_time - current_time
                hours_diff = time_diff.total_seconds() / 3600
                if hours_diff >= -2:
                    filtered_schedules.append((start_time, schedule_id, schedule))
            except ValueError as e:
                print(f"Error parsing date for schedule {schedule_id}: {e}")
                continue

        # Sort the filtered schedules by datetime
        filtered_schedules.sort()

        # Rebuild the active_schedules dict in sorted order
        active_schedules = {schedule_id: schedule for _, schedule_id, schedule in filtered_schedules}
        active_schedules_count = len(active_schedules)

        schedule_chache["active_schedules"] = active_schedules
        schedule_chache["active_schedules_count"] = active_schedules_count
        schedule_chache["last_updated"] = datetime.now()
    except Exception as e:
        print(f"Error refreshing schedule data: {e}")


async def ensure_recording_status_table():
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS recording_status (
                host TEXT PRIMARY KEY,
                link TEXT NOT NULL,
                length TEXT NOT NULL,
                description TEXT,
                starting_time TEXT NOT NULL,
                last_updated TIMESTAMPTZ DEFAULT NOW()
            );
        """)


async def refresh_recording_status_data():
    global recording_status_chache
    # await ensure_recording_status_table()
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("SELECT host, link, length, description, starting_time FROM recording_status")
            updated_data = {
                row["host"]: {
                    "link": row["link"],
                    "length": row["length"],
                    "description": row["description"],
                    "starting_time": row["starting_time"],
                }
                for row in rows
            }

            recording_status_chache["data"] = updated_data
            recording_status_chache["recording_status_count"] = len(updated_data)
            recording_status_chache["last_updated"] = datetime.now()
    except Exception as e:
        print(f"Error refreshing recording status data: {e}")


async def refresh_love_taps_cache():
    global love_taps_cache
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT SUM(tap_count) as total_taps FROM love_taps")
        total_taps = row["total_taps"] or 0
        love_taps_cache["data"] = total_taps
        love_taps_cache["last_updated"] = datetime.now()


async def refresh_trending_archives():
    global trending_archives_cache
    try:
        async with db_pool.acquire() as conn:
            # Get the most visited recording_stats pages from the last 24 hours
            trending_recordings = await conn.fetch("""
                SELECT
                    path,
                    COUNT(*) as visit_count
                FROM page_analytics
                WHERE
                    path LIKE '/recording_stats/%'
                    AND timestamp >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
                GROUP BY path
                ORDER BY visit_count DESC
                LIMIT 10
            """)

            trending_archives = []
            for record in trending_recordings:
                filename = record["path"].replace("/recording_stats/", "")
                filename = tornado.escape.url_unescape(filename)

                matching_archive = None
                for archive in audio_archive_cache["data"]:
                    if archive["filename"] == filename:
                        item_date = datetime.strptime(archive["date"], "%B %d %A %Y %I_%M %p")
                        diff_days = (datetime.today().date() - item_date.date()).days
                        uploaded_days_ago = f"{diff_days} days ago"

                        if diff_days == 0:
                            uploaded_days_ago = "Today"
                        elif diff_days == 1:
                            uploaded_days_ago = "Yesterday"

                        matching_archive = {
                            **archive,
                            "analytic_visit_count": record["visit_count"],
                            "trending_rank": len(trending_archives) + 1,
                            "formatted_length": format_length(archive["length"]),
                            "uploaded_days_ago": uploaded_days_ago,
                        }
                        break

                if matching_archive:
                    trending_archives.append(matching_archive)

            trending_archives_cache["data"] = trending_archives
            trending_archives_cache["last_updated"] = datetime.now()
    except Exception as e:
        print(f"Error refreshing trending archives: {e}")


class GetArchiveDataHandler(BaseHandler):
    def get(self):
        try:
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps(audio_archive_cache["grouped_data"], cls=DateTimeEncoder))
        except Exception as e:
            self.set_status(500)
            self.write_error(500, stack_trace=f"{str(e)} {traceback.print_exc()}")


class GetScheduleDataHandler(BaseHandler):
    def get(self):
        try:
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps(schedule_chache["all_schedules"], cls=DateTimeEncoder))
        except Exception as e:
            self.set_status(500)
            self.write_error(500, stack_trace=f"{str(e)} {traceback.print_exc()}")


class GetActiveSchedulesDataHandler(BaseHandler):
    def get(self):
        try:
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps(schedule_chache["active_schedules"], cls=DateTimeEncoder))
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
                    "scheduled_broadcast_count": schedule_chache["active_schedules_count"],
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


class SubscribeToTopicHandler(BaseHandler):
    def post(self):
        try:
            data = json.loads(self.request.body)
            token = data.get("token")
            topic = data.get("topic", "broadcasts")  # Default topic if not provided

            if not token:
                self.set_status(400)
                self.write({"error": "Token is required"})
                return

            # Subscribe the token to the topic
            response = messaging.subscribe_to_topic([token], topic)

            # Extract relevant fields from the response
            result = {
                "success_count": response.success_count,
                "failure_count": response.failure_count,
                "errors": [str(error) for error in response.errors],
            }

            self.set_status(200)
            self.write(
                {
                    "success": True,
                    "message": f"Successfully subscribed to topic {topic}",
                    "response": result,  # Include extracted information
                }
            )
        except Exception as e:
            self.set_status(500)
            self.write({"error": f"An error occurred: {str(e)}"})


def send_notification_to_topic(topic, title, body):
    try:
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
                image="/static/icon.png",
            ),
            data={
                "link": "https://broadcasting.hbni.net/events",
            },
            topic=topic,
        )
        response = messaging.send(message)
        print(f"Successfully sent message to topic {topic}: {response}")
    except Exception as e:
        print(f"Failed to send message: {e}")


class MainHandler(BaseHandler):
    def get(self):
        try:
            template = env.get_template("index.html")
            rendered_template = template.render()
            self.set_header("Cache-Control", "max-age=3600")
            self.set_header("Content-Type", "text/html")
            self.write(rendered_template)
        except Exception as e:
            self.set_status(500)
            self.write_error(500, stack_trace=f"{str(e)} {traceback.print_exc()}")


class GoogleHandler(BaseHandler):
    def get(self):
        self.write("google-site-verification: google9d968a11b4bf61f7.html")


class SitemapHandler(BaseHandler):
    def get(self):
        with open("static/sitemap.xml", "r") as f:
            self.set_header("Content-Type", "application/xml")
            self.write(f.read())


class SystemInfoHandler(BaseHandler):
    def get(self):
        try:
            self.set_header("Content-Type", "application/json")
            system_info = {
                "hostname": os.getenv("HOSTNAME"),
                "port": os.getenv("PORT"),
                "timezone": os.getenv("TZ"),
            }
            self.write(json.dumps(system_info, indent=4))
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
            self.set_header("Cache-Control", "max-age=3600")
            self.set_header("Content-Type", "text/html")
            self.write(rendered_template)
        except Exception as e:
            self.set_status(500)
            self.write_error(500, stack_trace=f"{str(e)} {traceback.print_exc()}")


class BroadcastingGuideHandler(BaseHandler):
    def get(self):
        try:
            template = env.get_template("broadcasting_guide.html")
            rendered_template = template.render()
            self.set_header("Cache-Control", "max-age=3600")
            self.set_header("Content-Type", "text/html")
            self.write(rendered_template)
        except Exception as e:
            self.set_status(500)
            self.write_error(500, stack_trace=f"{str(e)} {traceback.print_exc()}")


class PrivacyHandler(BaseHandler):
    def get(self):
        try:
            template = env.get_template("privacy.html")
            rendered_template = template.render()
            self.set_header("Cache-Control", "max-age=3600")
            self.set_header("Content-Type", "text/html")
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
            self.set_header("Cache-Control", "max-age=3600")
            self.set_header("Content-Type", "text/html")
            self.write(rendered_template)
        except Exception as e:
            self.set_status(500)
            self.write_error(500, stack_trace=f"{str(e)} {traceback.print_exc()}")


def url_for_static(filename):
    static_recordings_path = os.getenv("STATIC_RECORDINGS_PATH", "/app/static/Recordings")
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
                        "latest_visit": matching_archive["latest_visit"].strftime("%B %d %A %Y %I:%M %p") if matching_archive["latest_visit"] else "N/A",
                    }
                )
            )
        else:
            self.write(json.dumps({"visit_count": 0, "latest_visit": "N/A"}))


class LoadRecordingHandler(BaseHandler):
    async def get(self, hash):
        url = f"{os.getenv('FILEBROWSER_URL')}/api/public/dl/{hash}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    self.set_status(resp.status)
                    self.finish(f"Failed to load recording: {resp.reason}")
                    return

                content = await resp.read()
                self.set_header("Access-Control-Allow-Origin", "*")
                self.set_header("Content-Type", resp.headers.get("Content-Type", "audio/mp3"))
                self.set_header("Content-Length", str(len(content)))
                self.set_header("Accept-Ranges", "bytes")
                self.set_header("content-Range", f"bytes 0-{len(content)}/{len(content)}")  # For resuming downloads
                self.set_header(
                    "Content-Disposition",
                    f'inline; filename="{recording_files_share_hashes[hash]}.mp3"',
                )
                self.set_header("Cache-Control", "public, max-age=86400")
                self.write(content)
                self.finish()


class RecordingProxyHandler(RequestHandler):
    async def get(self, index: str):
        try:
            idx = int(index)
        except ValueError:
            raise HTTPError(400, "Index must be an integer")

        # Ensure cache has data
        recordings = audio_archive_cache.get("data", [])
        if not recordings:
            raise HTTPError(404, "No recordings available")

        # Sort recordings by date (latest first)
        sorted_data = sorted(recordings, key=lambda r: r.get("id") or "", reverse=True)

        if idx < 0 or idx >= len(sorted_data):
            raise HTTPError(404, f"No recording at index {idx}")

        recording = sorted_data[idx]
        share_hash = recording.get("share_hash")
        if not share_hash:
            raise HTTPError(404, f"No share hash for index {idx}")

        # Build internal load_recording URL
        load_url = f"https://broadcasting.hbni.net/load_recording/{share_hash}"
        # ↑ adjust host/port to your Tornado server

        timeout = aiohttp.ClientTimeout(total=None, sock_read=None)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(load_url) as resp:
                if resp.status != 200:
                    self.set_status(502)
                    self.write("Error: Could not fetch recording")
                    return

                # Pass through headers
                ctype = resp.headers.get("Content-Type", "audio/mpeg")
                self.set_header("Content-Type", ctype)
                self.set_header("Cache-Control", "no-cache")
                self.set_header("Pragma", "no-cache")
                self.set_header("Transfer-Encoding", "chunked")

                # Stream in chunks
                try:
                    async for chunk in resp.content.iter_chunked(4096):
                        self.write(chunk)
                        await self.flush()
                except Exception:
                    # client disconnected or network issue
                    return


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
            share_hash = matching_archive["share_hash"] or ""
            latest_visit = matching_archive["latest_visit"].strftime("%B %d %A %Y %I:%M %p") if matching_archive["latest_visit"] else "N/A"
            date = matching_archive["date"] or "N/A"
            description = matching_archive["description"] or "N/A"
            length = format_length(matching_archive["length"]) or "N/A"
        else:
            visit_count = 0
            latest_visit = "N/A"
            date = "N/A"
            description = "N/A"
            share_hash = ""
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
            share_hash=share_hash,
        )
        self.write(rendered_template)


class LiveProxyHandler(RequestHandler):
    async def get(self, index: str):
        # if self.request.connection:
        #     self.request.connection.set_max_body_size(10**12)
        #     self.request.connection.stream.set_close_call_back(lambda: None)

        idx = int(index)

        broadcasts = active_broadcasts_chache.get("data", [])
        if idx >= len(broadcasts):
            self.set_status(404)
            self.write("Error: No such live index")
            return

        broadcast = broadcasts[idx]
        listen_url = broadcast["listen_url"]

        # Proxy audio from Icecast
        timeout = aiohttp.ClientTimeout(total=None, sock_read=None)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(listen_url) as resp:
                if resp.status != 200:
                    self.set_status(502)
                    self.write("Error: Could not fetch audio")
                    return

                # Pass through headers
                ctype = resp.headers.get("Content-Type", "audio/mpeg")
                self.set_header("Content-Type", ctype)
                self.set_header("Cache-Control", "no-cache")
                self.set_header("Pragma", "no-cache")
                self.set_header("Transfer-Encoding", "chunked")

                # Stream audio in chunks
                try:
                    async for chunk in resp.content.iter_chunked(4096):
                        # if not chunk:
                        #     break
                        self.write(chunk)
                        await self.flush()
                except Exception:
                    # client disconnected or network issue
                    return


class PlayLiveHandler(BaseHandler):
    def get(self, broadcast_name):
        broadcast_data = None
        date = None
        colony = None
        length = None
        listeners = None
        description = None
        source_url = "https://hbniaudio.hbni.net"
        is_private = False

        for broadcast_data in active_broadcasts_chache["data"]:
            if broadcast_data.get("host") == broadcast_name:
                colony = broadcast_data.get("colony", broadcast_name)
                date = broadcast_data.get("stream_start")
                length = broadcast_data.get("length")
                listeners = broadcast_data.get("listeners")
                description = broadcast_data.get("server_description")
                source_url = broadcast_data.get("source_url")
                is_private = broadcast_data.get("is_private")
                listener_peak = broadcast_data.get("listener_peak")
                break

        if not date or not colony or not description or not source_url:
            self.set_status(404)
            self.write_error(404)
            return

        if not broadcast_data:
            self.set_status(404)
            self.write_error(404)
            return

        template = env.get_template("play_live.html")
        rendered_template = template.render(
            title=broadcast_name,
            colony=colony.title(),
            broadcast=broadcast_name,
            date=date,
            length=length,
            listeners=listeners,
            description=description,
            is_private=is_private,
            listener_peak=listener_peak,
            data_url=f"{source_url}/{broadcast_name}",
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


class ScheduleBroadcastHandler(BaseHandler):
    async def post(self):
        try:
            data: dict[str, str] = tornado.escape.json_decode(self.request.body)
            host = data.get("host")
            description = data.get("description")
            speakers = data.get("speakers", "")  # Optional field
            start_time = data.get("startTime")
            duration = data.get("duration")

            if not (host and description and start_time and duration):
                self.set_status(400)
                self.write({"success": False, "error": "Missing required fields"})
                return

            # Insert into database
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO scheduledbroadcasts
                    (host, description, duration, speakers, start_time)
                    VALUES ($1, $2, $3, $4, $5)
                """,
                    host,
                    description,
                    duration,
                    speakers,
                    start_time,
                )

            await refresh_scedule_data()

            send_notification_to_topic("broadcasts", f"{host} scheduled a broadcast", description)

            self.set_status(200)
            self.write({"success": True})
        except Exception as e:
            self.set_status(500)
            self.write_error(500, stack_trace=f"{str(e)} {traceback.print_exc()}")


class GetScheduleHandler(BaseHandler):
    async def get(self, schedule_id: int):
        try:
            await refresh_scedule_data()
            self.set_header("Content-Type", "application/json")
            self.write(
                json.dumps(
                    schedule_chache["all_schedules"][int(schedule_id)],
                    cls=DateTimeEncoder,
                )
            )
        except Exception as e:
            self.set_status(500)
            self.write_error(500, stack_trace=f"{str(e)} {traceback.print_exc()}")


class EditScheduleHandler(BaseHandler):
    async def post(self, schedule_id):
        try:
            data: dict[str, str] = tornado.escape.json_decode(self.request.body)
            host = data.get("host")
            description = data.get("description")
            speakers = data.get("speakers", "")  # Optional field
            start_time = data.get("startTime")
            duration = data.get("duration")

            if not (host and description and start_time and duration):
                self.set_status(400)
                self.write({"success": False, "error": "Missing required fields"})
                return

            # Insert into database
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE scheduledbroadcasts
                    SET host = $1, description = $2, speakers = $3, duration = $4, start_time = $5
                    WHERE id = $6
                """,
                    host,
                    description,
                    speakers,
                    duration,
                    start_time,
                    int(schedule_id),
                )

            await refresh_scedule_data()

            self.set_status(200)
            self.write({"success": True})
        except Exception as e:
            self.set_status(500)
            self.write_error(500, stack_trace=f"{str(e)} {traceback.print_exc()}")

    async def delete(self, schedule_id):
        try:
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    DELETE FROM scheduledbroadcasts
                    WHERE id = $1
                """,
                    int(schedule_id),
                )

            await refresh_scedule_data()

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
        global active_broadcasts
        # If the received message is JSON metadata, start the ffmpeg process
        if isinstance(message, str):
            try:
                metadata: dict[str, str] = json.loads(message)
                print(metadata)
                self.password = metadata.get("password", "")
                if self.password != os.getenv("ICECAST_BROADCASTING_PASSWORD"):
                    self.write_message("Invalid password.")
                    return

                self.host = metadata.get("host", "unknown")
                self.description = metadata.get("description", "Unspecified description")
                self.is_private = metadata.get("isPrivate", False)
                self.mount_point = metadata.get("mountPoint", "unknown")
                self.starting_time = datetime.now()
                self.output_filename = f"{self.host.title()} - {self.description} - {self.starting_time.strftime('%B %d %A %Y %I_%M %p')} - BROADCAST_LENGTH.wav"

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
                        f"genre={'private' if self.is_private else 'public'}",
                        "-metadata",
                        f"comment={'private' if self.is_private else 'public'}",
                        "-ice_name",
                        self.host,
                        "-ice_description",
                        self.description,
                        "-ice_genre",
                        f"{'private' if self.is_private else 'public'}",
                        "-ice_url",
                        f"{ICECAST_BROADCASTING_SOURCE}/{self.mount_point}",
                        "-ice_public",
                        f"{'0' if self.is_private else '1'}",  # Whether the stream is public (1) or private (0)
                        "-f",
                        "mp3",
                        f"icecast://source:{self.password}@{ICECAST_BROADCASTING_IP}:{ICECAST_BROADCASTING_PORT}/{self.mount_point}",  # Icecast URL
                        # "-f",
                        # "wav",
                        # self.output_filename,
                    ],
                    stdin=subprocess.PIPE,
                )
                # Check if the process started successfully
                if self.ffmpeg_process.poll() is None:
                    print(f"FFmpeg process started successfully for {self.output_filename}")
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
            silence_buffer = self.generate_silence(1)  # 1ms
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
        global active_broadcasts
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
            del active_broadcasts[self.host]
            # remove_silence.remove_silence_everywhere(self.output_filename)
            # total_minutes = audio_file.get_audio_length(self.output_filename)
            # hours = total_minutes // 60
            # minutes = total_minutes % 60
            # seconds = (total_minutes - int(total_minutes)) * 60

            # if hours <= 0:
            #     formated_length = f"{minutes:02d}m {seconds:02d}s"
            # else:
            #     formated_length = f"{hours:02d}h {minutes:02d}m {seconds:02d}s"

            # new_output_filename = self.output_filename.replace(
            #     "BROADCAST_LENGTH", formated_length
            # )
            # # static_recordings_path = (
            # #     os.getenv("STATIC_RECORDINGS_PATH", "/app/static/Recordings")
            # #     .replace("\\", "/")
            # #     .replace("//", "/")
            # #     .replace("//", "\\\\")
            # #     .replace("/", "\\")
            # # )
            # if total_minutes >= 10.0 and not (self.is_private or self.host == "test"):
            #     shutil.move(
            #         self.output_filename,
            #         new_output_filename,
            #     )
            #     filebrowser_uploader.upload(
            #         new_output_filename,
            #         new_output_filename,
            #         self.host,
            #         self.description,
            #         self.starting_time.strftime("%B %d %A %Y %I_%M %p"),
            #         total_minutes,
            #     )
            # else:
            #     remove_silence.remove_silence_everywhere(self.output_filename)
            # os.remove(self.output_filename)
            # elif not self.is_private:
            # shutil.move(
            #     self.output_filename,
            #     f"{static_recordings_path}\\TESTS\\{new_output_filename}",
            # )


class BroadcastHandler(BaseHandler):
    def get(self):
        template = env.get_template("broadcasting_page.html")
        rendered_template = template.render()
        self.set_header("Cache-Control", "max-age=3600")
        self.set_header("Content-Type", "text/html")
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
                scheduled_broadcast=schedule_chache["active_schedules"],
                broadcast_count=active_broadcasts_chache["active_broadcasts_count"],
                scheduled_broadcast_count=schedule_chache["active_schedules_count"],
            )
            self.set_header("Content-Type", "text/html")
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


class FirebaseServiceWorkerHandler(BaseHandler):
    def get(self):
        try:
            file_path = "firebase-messaging-sw.js"
            if os.path.exists(file_path):
                self.set_header("Content-Type", "application/javascript")
                with open(file_path, "r", encoding="utf-8") as f:
                    self.write(f.read())
            else:
                self.set_status(404)
                self.write("Service Worker file not found.")
        except Exception as e:
            self.set_status(500)
            self.write(f"An error occurred: {str(e)}")


class ManifestHandler(BaseHandler):
    def get(self):
        try:
            self.set_header("Content-Type", "application/json")
            self.write(open("manifest.json", "rb").read())
        except Exception as e:
            self.set_status(500)
            self.write(f"An error occurred: {str(e)}")


class AssetLinksHandler(BaseHandler):
    def get(self):
        try:
            self.set_header("Content-Type", "application/json")
            self.write(open(".well-known/assetlinks.json", "rb").read())
        except Exception as e:
            self.set_status(500)
            self.write(f"An error occurred: {str(e)}")


async def initialize_analytics_table():
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS page_analytics (
                id SERIAL PRIMARY KEY,
                path TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user_agent TEXT,
                ip_address TEXT,
                referrer TEXT,
                day_bucket DATE GENERATED ALWAYS AS (DATE(timestamp)) STORED
            );

            -- Create an index on the day_bucket for faster querying
            CREATE INDEX IF NOT EXISTS idx_page_analytics_day_bucket
            ON page_analytics(day_bucket);
        """)


class AnalyticsHandler(BaseHandler):
    async def get(self):
        try:
            async with db_pool.acquire() as conn:
                # Get visits per day for the last 30 days
                daily_visits = await conn.fetch("""
                    SELECT
                        day_bucket,
                        COUNT(*) as visit_count
                    FROM page_analytics
                    WHERE day_bucket >= CURRENT_DATE - INTERVAL '30 days'
                    GROUP BY day_bucket
                    ORDER BY day_bucket DESC
                """)

                # Get most visited pages
                popular_pages = await conn.fetch("""
                    SELECT
                        path,
                        COUNT(*) as visit_count
                    FROM page_analytics
                    WHERE timestamp >= CURRENT_DATE - INTERVAL '30 days'
                    GROUP BY path
                    ORDER BY visit_count DESC
                    LIMIT 10
                """)
                # Convert date objects to strings for JSON serialization
                daily_visits_data = [
                    {
                        **dict(row),
                        "day_bucket": row["day_bucket"].isoformat() if row["day_bucket"] else None,
                    }
                    for row in daily_visits
                ]

                self.write(
                    {
                        "daily_visits": daily_visits_data,
                        "popular_pages": [dict(row) for row in popular_pages],
                    }
                )
        except Exception as e:
            self.set_status(500)
            self.write({"error": str(e)})


async def cleanup_old_analytics():
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM page_analytics
                WHERE timestamp < CURRENT_DATE - INTERVAL '90 days'
            """)
    except Exception as e:
        print(f"Error cleaning analytics: {e}")


class TrendingArchivesHandler(BaseHandler):
    async def get(self):
        try:
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps(trending_archives_cache["data"], cls=DateTimeEncoder))
        except Exception as e:
            self.set_status(500)
            self.write({"error": str(e)})


def make_app():
    return Application(
        [
            url(r"/", MainHandler),
            url(r"/google9d968a11b4bf61f7.html", GoogleHandler),
            url(r"/sitemap.xml", SitemapHandler),
            url(r"/system-info", SystemInfoHandler),
            url(r"/update-love-taps", LoveTapsUpdateHandler),
            url(r"/fetch-love-taps", LoveTapsFetchHandler),
            url(r"/subscribe-to-topic", SubscribeToTopicHandler),
            url(r"/favicon.ico", FaviconHandler),
            url(r"/faq", FaqHandler),
            url(r"/frequently_asked_questions", FaqHandler),
            url(r"/recording_stats/(.*)", RecordingStatsHandler),
            url(r"/recording/([0-9]+)", RecordingProxyHandler),
            url(r"/play_recording/(.*)", PlayRecordingHandler),
            url(r"/play_live/(.*)", PlayLiveHandler),
            url(r"/live/([0-9]+)", LiveProxyHandler),
            url(r"/load_recording/(.*)", LoadRecordingHandler),
            url(r"/broadcast_ws", BroadcastWSHandler),
            url(r"/schedule_broadcast", ScheduleBroadcastHandler),
            url(r"/get_schedule/(.*)", GetScheduleHandler),
            url(r"/edit_schedule/(.*)", EditScheduleHandler),
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
            url(r"/get_schedule_data", GetScheduleDataHandler),
            url(r"/get_active_schedules_data", GetActiveSchedulesDataHandler),
            url(r"/get_event_count", GetEventCountHandler),
            url(r"/get_recording_status", GetRecordingStatusHandler),
            url(r"/download_links.json", DownloadLinksJSONHandler),
            url(r"/firebase-messaging-sw.js", FirebaseServiceWorkerHandler),
            url(r"/manifest.json", ManifestHandler),
            url(r"/.well-known/assetlinks.json", AssetLinksHandler),
            url(r"/privacy", PrivacyHandler),
            url(r"/dist/(.*)", tornado.web.StaticFileHandler, {"path": "dist"}),
            url(
                r"/app/static/Recordings/(.*)",
                tornado.web.StaticFileHandler,
                {"path": os.getenv("STATIC_RECORDINGS_PATH", "/app/static/Recordings")},
            ),
            url(r"/recording_status.json", RecordingStatusJSONHandler),
            url(r"/analytics", AnalyticsHandler),
            url(r"/trending_archives", TrendingArchivesHandler),
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
    tornado.ioloop.IOLoop.current().run_sync(initialize_analytics_table)
    # To add hashes from FileBrowser to load audio archives
    # tornado.ioloop.IOLoop.current().run_sync(update_audio_hashes)

    loop = tornado.ioloop.IOLoop.current()
    loop.add_callback(get_recording_files_share_hashes)
    loop.add_callback(refresh_archive_data)
    loop.add_callback(refresh_active_broadcasts_data)
    loop.add_callback(refresh_scedule_data)
    loop.add_callback(refresh_recording_status_data)
    loop.add_callback(refresh_love_taps_cache)
    loop.add_callback(refresh_trending_archives)
    # tornado.ioloop.IOLoop.current().run_sync(refresh_active_broadcasts_data)
    # tornado.ioloop.IOLoop.current().run_sync(refresh_scedule_data)
    # tornado.ioloop.IOLoop.current().run_sync(refresh_recording_status_data)
    # tornado.ioloop.IOLoop.current().run_sync(refresh_love_taps_cache)

    # Stagger the periodic callbacks by 1 minute each
    # First callback starts immediately (0 minutes offset)
    tornado.ioloop.PeriodicCallback(
        refresh_archive_data,
        float(os.getenv("REFRESH_ARCHIVE_DATA_INTERVAL_MINUTES", default=5)) * 60 * 1000,
    ).start()

    # Second callback starts after 1 minute
    loop = tornado.ioloop.IOLoop.instance()
    loop.call_later(
        60,
        lambda: tornado.ioloop.PeriodicCallback(
            refresh_active_broadcasts_data,
            float(os.getenv("REFRESH_ACTIVE_BROADCASTS_DATA_INTERVAL_MINUTES", default=5)) * 60 * 1000,
        ).start(),
    )
    loop.call_later(
        60,
        lambda: tornado.ioloop.PeriodicCallback(
            get_recording_files_share_hashes,
            float(os.getenv("REFRESH_ACTIVE_BROADCASTS_DATA_INTERVAL_MINUTES", default=5)) * 60 * 1000,
        ).start(),
    )
    # Third callback starts after 2 minutes
    loop.call_later(
        120,
        lambda: tornado.ioloop.PeriodicCallback(
            refresh_recording_status_data,
            float(os.getenv("REFRESH_RECORDING_STATUS_DATA_INTERVAL_MINUTES", default=1)) * 60 * 1000,
        ).start(),
    )

    # Fourth callback starts after 3 minutes
    loop.call_later(
        180,
        lambda: tornado.ioloop.PeriodicCallback(
            refresh_scedule_data,
            float(os.getenv("REFRESH_SCHEDULE_DATA_INTERVAL_MINUTES", default=5)) * 60 * 1000,
        ).start(),
    )

    # Fifth callback starts after 4 minutes
    loop.call_later(
        240,
        lambda: tornado.ioloop.PeriodicCallback(
            refresh_love_taps_cache,
            float(os.getenv("REFRESH_LOVE_TAPS_CACHE_INTERVAL_MINUTES", default=5)) * 60 * 1000,
        ).start(),
    )

    # Add this with your other periodic callbacks
    loop.call_later(
        360,
        lambda: tornado.ioloop.PeriodicCallback(
            cleanup_old_analytics,
            24 * 60 * 60 * 1000,  # Run once per day
        ).start(),
    )

    # Add initial refresh of trending archives
    tornado.ioloop.IOLoop.current().run_sync(refresh_trending_archives)

    # Add periodic refresh (after 5 minutes)
    loop.call_later(
        300,
        lambda: tornado.ioloop.PeriodicCallback(
            refresh_trending_archives,
            int(os.getenv("REFRESH_TRENDING_ARCHIVES_INTERVAL_MINUTES", default=5)) * 60 * 1000,
        ).start(),
    )

    tornado.ioloop.IOLoop.instance().start()
