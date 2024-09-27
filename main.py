import asyncpg
import json
import os
from datetime import datetime
from collections import defaultdict
import jinja2
from tornado.ioloop import IOLoop
from tornado.web import Application, RequestHandler, url
import traceback

loader = jinja2.FileSystemLoader("templates")
env = jinja2.Environment(loader=loader)

async def get_db_connection():
    return await asyncpg.connect(
        host="localhost",
        database="postgres",
        user="postgres",
        password="postgres"
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
        await conn.execute('''
            UPDATE audioarchives
            SET visit_count = COALESCE(visit_count, 0) + 1, latest_visit = $1
            WHERE filename = $2
        ''', datetime.now(), file_name)
    finally:
        await conn.close()

async def update_click(file_name):
    conn = await get_db_connection()
    try:
        await conn.execute('''
            UPDATE audioarchives
            SET click_count = COALESCE(click_count, 0) + 1, latest_click = $1
            WHERE filename = $2
        ''', datetime.now(), file_name)
    finally:
        await conn.close()


def format_length(length_in_minutes):
    hours, minutes = divmod(int(length_in_minutes), 60)
    hours_string = f"{hours} hour{'s' if hours > 1 else ''}" if hours > 0 else ""
    minutes_string = f"{minutes} minute{'s' if minutes != 1 else ''}" if minutes > 0 else ""

    if hours_string and minutes_string:
        return f"{hours_string}, {minutes_string}"
    return hours_string or minutes_string


def get_grouped_data(audio_data):
    today = datetime.today()
    current_year, current_month, current_week = today.year, today.month, today.isocalendar()[1]

    # Predefined group names
    groups = {"Today": {}, "Yesterday": {}, "Two Days Ago": {}, "Three Days Ago": {}, "Sometime This Week": {}, "Last Week": {}, "Sometime This Month": {}, "Last Month": {}, "Two Months Ago": {}, "Three Months Ago": {}, "Sometime This Year": {}, "Last Year": {}, "Two Years Ago": {}, "Three Years Ago": {}, "Everything Else": {}}


    for row in audio_data:
        itemData = dict(row)
        itemData['formatted_length'] = format_length(itemData['length'])

        item_date = datetime.strptime(row['date'], "%B %d %A %Y %I_%M %p")
        item_week = item_date.isocalendar()[1]
        diff_days = (today - item_date).days
        item_name = row['filename'].replace("_", ":").replace(".mp3", "")

        # Group the items by date range
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

    # Return only non-empty groups
    return {key: value for key, value in groups.items() if value}


class MainHandler(RequestHandler):
    async def get(self):
        try:
            audio_data = await fetch_audio_archives()  # Await the async database call
            grouped_data = get_grouped_data(audio_data)

            template = env.get_template("index.html")
            rendered_template = template.render(
                downloadableRecordings=grouped_data,
                title="HBNI Audio Streaming Archive",
                recording_status={}
            )
            self.write(rendered_template)
        except Exception as e:
            traceback.print_exc()
            self.set_status(500)
            self.write({"error": f"{str(e)} {traceback.print_exc()}"})

def url_for_static(filename):
    return f"/static/{filename}"


class PlayRecordingHandler(RequestHandler):
    async def get(self, file_name):
        await update_visit(file_name)  # Await the async database update

        conn = await get_db_connection()
        try:
            result = await conn.fetchrow('''
                SELECT visit_count, click_count, latest_visit, latest_click
                FROM audioarchives
                WHERE filename = $1
            ''', file_name)
        finally:
            await conn.close()

        if result:
            visit_count = result['visit_count'] or 0
            click_count = result['click_count'] or 0
            latest_visit = result['latest_visit'] or 'N/A'
            latest_click = result['latest_click'] or 'N/A'
        else:
            visit_count = 0
            click_count = 0
            latest_visit = 'N/A'
            latest_click = 'N/A'

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
            url_for=url_for_static
        )
        self.write(rendered_template)

class ButtonPressedHandler(RequestHandler):
    async def post(self):
        try:
            data = json.loads(self.request.body.decode("utf-8"))
            item_name = data.get("itemName").replace(":", "_") + ".mp3"
            await update_click(item_name)  # Await the async database update
            self.write(json.dumps({"status": "success"}))
        except Exception as e:
            traceback.print_exc()
            self.write({"error": f"{str(e)}"})
            self.set_status(500)

# Tornado application setup
def make_app():
    return Application([
        url(r"/", MainHandler),
        url(r"/play_recording/(.*)", PlayRecordingHandler),
        url(r"/button_pressed", ButtonPressedHandler),
    ],
    static_path=os.path.join(os.path.dirname(__file__), "static"),
    )

if __name__ == "__main__":
    app = make_app()
    app.listen(5000)
    IOLoop.current().start()
