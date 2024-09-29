import json
import os
import time
import subprocess
import traceback
from datetime import datetime

import asyncpg
import jinja2
import tornado.gen
import tornado.httpserver
import tornado.ioloop
import tornado.web
import tornado.websocket
from dotenv import load_dotenv
from tornado.web import Application, RequestHandler, url

load_dotenv()

loader = jinja2.FileSystemLoader("templates")
env = jinja2.Environment(loader=loader)

live_broadcasts = {}
listeners = {}

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
        diff_days = (today - item_date).days
        item_name = row["filename"].replace("_", ":").replace(".mp3", "")

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


class MainHandler(RequestHandler):
    async def get(self):
        try:
            audio_data = await fetch_audio_archives()
            grouped_data = get_grouped_data(audio_data)

            try:
                path = os.getenv("STATIC_PATH", "/app/static")
                with open(f"{path}/recording_status.json", "r", encoding="utf-8") as f:
                    recording_status = json.load(f)
            except Exception:
                recording_status = {"ERROR": "Could not load recording status JSON file."}

            template = env.get_template("index.html")
            rendered_template = template.render(
                downloadableRecordings=grouped_data,
                recording_status=recording_status,
            )
            self.write(rendered_template)
        except Exception as e:
            traceback.print_exc()
            self.set_status(500)
            self.write({"error": f"{str(e)} {traceback.print_exc()}"})


def url_for_static(filename):
    static_recordings_path = os.getenv("STATIC_RECORDINGS_PATH", "/app/static/Recordings")
    return f"{static_recordings_path}/{filename}"


class PlayRecordingHandler(RequestHandler):
    async def get(self, file_name):
        await update_visit(file_name)  # Await the async database update

        conn = await get_db_connection()
        try:
            result = await conn.fetchrow(
                """
                SELECT visit_count, click_count, latest_visit, latest_click
                FROM audioarchives
                WHERE filename = $1
            """,
                file_name,
            )
        finally:
            await conn.close()

        if result:
            visit_count = result["visit_count"] or 0
            click_count = result["click_count"] or 0
            latest_visit = result["latest_visit"] or "N/A"
            latest_click = result["latest_click"] or "N/A"
        else:
            visit_count = 0
            click_count = 0
            latest_visit = "N/A"
            latest_click = "N/A"

        audio_data = await fetch_audio_archives()
        grouped_data = get_grouped_data(audio_data)

        template = env.get_template("play_recording.html")
        rendered_template = template.render(
            title=file_name.split(" - ")[0],
            file_name=file_name,
            visit_count=visit_count,
            click_count=click_count,
            latest_visit=latest_visit,
            latest_click=latest_click,
            downloadableRecordings=grouped_data,
            url_for=url_for_static,
        )
        self.write(rendered_template)


class BroadcastHandler(RequestHandler):
    def get(self):
        template = env.get_template("broadcast.html")
        rendered_template = template.render(
            broadcast_name="",
        )
        self.write(rendered_template)


class ListenHandler(RequestHandler):
    def get(self, broadcast_name):
        template = env.get_template("listen.html")
        rendered_template = template.render()
        self.write(rendered_template)


class BroadcastWSHandler(tornado.websocket.WebSocketHandler):
    def open(self):
        self.mount_name = 'default'  # default mount if none is provided
        self.description = ''
        self.file = None  # File to save the broadcast audio

        # Create the file path for saving the broadcast (e.g., "/app/static/Recordings/live_broadcast.mp3")
        self.file_path = os.path.join(os.getenv("STATIC_RECORDINGS_PATH", ""), f"{self.mount_name}.mp3")

        if not os.path.exists(os.path.dirname(self.file_path)):
            with open(self.file_path, 'wb') as f:
                f.write(b'')

        self.file = open(self.file_path, 'wb')

        listeners[self.mount_name] = listeners.get(self.mount_name, [])
        print(f"Broadcast started on mount: {self.mount_name}, saving to {self.file_path}")

    def on_message(self, message):
        if isinstance(message, str):  # First message should be metadata
            metadata = json.loads(message)
            self.mount_name = metadata.get('mountName', 'default')
            self.description = metadata.get('description', '')
            listeners[self.mount_name] = listeners.get(self.mount_name, [])
            print(f"Mount Name: {self.mount_name}, Description: {self.description}")
        else:  # Audio data
            # Broadcast the audio data to all listeners of this mount
            for listener in listeners.get(self.mount_name, []):
                if listener.ws_connection and listener.ws_connection.is_open():
                    listener.write_message(message, binary=True)

            # Write the audio data to the file
            if self.file:
                self.file.write(message)

    def on_close(self):
        print(f"Broadcast ended on mount: {self.mount_name}")

        # Close the file when the broadcast ends
        if self.file:
            self.file.close()

        if self.mount_name in listeners:
            del listeners[self.mount_name]


class ListenWSHandler(tornado.websocket.WebSocketHandler):
    def open(self, mount_name):
        print(f"New listener joined mount: {mount_name}")
        self.mount_name = mount_name
        listeners[mount_name] = listeners.get(mount_name, [])
        listeners[mount_name].append(self)

    def on_close(self):
        listeners[self.mount_name].remove(self)
        if not listeners[self.mount_name]:
            del listeners[self.mount_name]
        print(f"Listener left mount: {self.mount_name}")


class DownloadLinksJSONHandler(RequestHandler):
    async def get(self):
        audio_data = await fetch_audio_archives()

        json_response = {}
        for row in audio_data:
            file_name = row['filename']
            file_description = row['description']
            file_date = row['date']
            file_length = row['length']
            host = row['host']
            file_id = row['id']
            download_link = row['download_link']

            json_response[file_name] = {
                "date": file_date,
                "description": file_description,
                "downloadLink": download_link,
                "length": file_length,
                "host": host,
                "id": file_id
            }

        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(json_response, indent=4))


class RecordingStatusJSONHandler(RequestHandler):
    def get(self):
        try:
            path = os.getenv("STATIC_PATH", "/app/static")
            with open(f"{path}/recording_status.json", "r", encoding="utf-8") as f:
                recording_status = json.load(f)
        except Exception:
            recording_status = {"ERROR": "Could not load recording status JSON file."}

        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(recording_status, indent=4))


def make_app():
    return Application(
        [
            url(r"/", MainHandler),
            url(r"/play_recording/(.*)", PlayRecordingHandler),
            url(r"/broadcast", BroadcastHandler),
            url(r"/broadcast_ws", BroadcastWSHandler),
            url(r"/listen/(.*)", ListenWSHandler),
            url(r"/listen_ws/(.*)", ListenWSHandler),
            url(r"/download_links.json", DownloadLinksJSONHandler),
            url(r"/app/static/Recordings/(.*)", tornado.web.StaticFileHandler, {
                'path': os.getenv("STATIC_RECORDINGS_PATH", "/app/static/Recordings")
            }),
            url(r"/recording_status.json", RecordingStatusJSONHandler),
        ],
        static_path=os.path.join(os.path.dirname(__file__), "static"),  # Path inside container
    )


if __name__ == "__main__":
    app = tornado.httpserver.HTTPServer(make_app())
    app.listen(int(os.getenv("PORT", default=5053)))
    tornado.ioloop.IOLoop.instance().start()
