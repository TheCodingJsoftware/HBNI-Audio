import calendar
import datetime
import json
import os
import sched
import threading
import time
from os import listdir
from os.path import isfile, join
from urllib.parse import unquote

import requests
from flask import (
    Flask,
    request,
    jsonify,
    current_app,
    render_template,
    send_file,
    send_from_directory,
    url_for,
)

app = Flask(__name__)
s = sched.scheduler(time.time, time.sleep)



@app.route("/")
def index() -> None:
    with open("static/download_links.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    with open("static/recording_status.json", 'r', encoding="utf-8") as f:
        recording_status = json.load(f)

    return render_template(
        "index.html",
        downloadableRecordings=get_grouped_data(data),
        title="HBNI Audio Streaming Archive",
        recording_status=recording_status
    )


@app.route("/play_recording/<path:file_name>")
def play_recording(file_name: str):
    with open("static/download_links.json", "r", encoding="utf-8") as f:
        download_links_data = json.load(f)
    item_name = unquote(file_name.split("/play_recording/")[-1])
    download_links_data[item_name]["visit_count"] += 1
    with open("static/download_links.json", "w", encoding="utf-8") as f:
        json.dump(download_links_data, f, indent=4)

    return render_template(
        "play_recording.html",
        file_name=file_name,
        downloadableRecordings=get_grouped_data(download_links_data),
    )

@app.route('/button_pressed', methods=['POST'])
def process_button_click():
    data = request.get_json()
    item_name = data.get('itemName').replace(":", "_") + ".mp3"
    with open("static/download_links.json", "r", encoding="utf-8") as f:
        download_links_data = json.load(f)
    download_links_data[item_name]["click_count"] += 1
    with open("static/download_links.json", "w", encoding="utf-8") as f:
        json.dump(download_links_data, f, indent=4)
    response_data = {
        'downloadLink': download_links_data[item_name]["downloadLink"]
    }
    return jsonify(response_data)

@app.route("/frequently-asked-questions.html")
def frequently_asked_questions():
    return render_template(
        "frequently-asked-questions.html",
    )

@app.route("/download_links.json")
def download_links():
    with open("static/download_links.json", "r", encoding="utf-8") as f:
        contents = f.read()
    return contents

def get_grouped_data(json_data):
    today = datetime.date.today()
    current_month = today.month
    current_week = today.isocalendar()[1]
    current_year = today.year

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
        "Everything Else": {}
    }

    for item, itemData in json_data.items():
        itemData['display_name'] = itemData['host'].replace("/","").title()
        itemData['file_name'] = unquote(itemData['downloadLink'].split('/play_recording/')[-1])
        item_date = datetime.datetime.strptime(json_data[item]["date"], "%B %d %A %Y %I_%M %p").date()
        item_week = item_date.isocalendar()[1]
        diff = today - item_date

        item: str = item.replace("_", ":").replace(".mp3", "")
        if item_date.year == current_year:
            if item_date.month == current_month:
                if item_week == current_week:
                    if diff.days == 0:
                        groups["Today"].update({item: itemData})
                    elif diff.days == 1:
                        groups["Yesterday"].update({item: itemData})
                    elif diff.days == 2:
                        groups["Two Days Ago"].update({item: itemData})
                    elif diff.days == 3:
                        groups["Three Days Ago"].update({item: itemData})
                    else:
                        groups["Sometime This Week"].update({item: itemData})
                elif item_week == current_week - 1:
                    groups["Last Week"].update({item: itemData})
                else:
                    groups["Sometime This Month"].update({item: itemData})
            elif item_date.month == current_month - 1:
                groups["Last Month"].update({item: itemData})
            elif item_date.month == current_month - 2:
                groups["Two Months Ago"].update({item: itemData})
            elif item_date.month == current_month - 3:
                groups["Three Months Ago"].update({item: itemData})
            else:
                groups["Sometime This Year"].update({item: itemData})
        elif item_date.year == current_year -1:
            groups["Last Year"].update({item: itemData})
        elif item_date.year == current_year -2:
            groups["Two Years Ago"].update({item: itemData})
        elif item_date.year == current_year -3:
            groups["Three Years Ago"].update({item: itemData})
        else:
            groups["Everything Else"].update({item: itemData})

    # Remove empty groups
    groups = {key: value for key, value in groups.items() if value}
    # Reverse order
    for groupName, groupData in groups.items():
        groupData = dict(reversed(groupData.items()))
        groups[groupName] = groupData

    return groups


# threading.Thread(target=downloadThread).start()
# app.run(host="10.0.0.217", port=5000, debug=False, threaded=True)
