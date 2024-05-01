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
    data = loadJson()
    groupedData = groupDates(data)

    return render_template(
        "index.html",
        downloadableRecordings=groupedData,
        title="HBNI Audio Streaming Archive",
    )


@app.route("/play_recording/<path:file_name>")
def play_recording(file_name):
    data = loadJson()
    groupedData = groupDates(data)
    return render_template(
        "play_recording.html",
        file_name=file_name,
        downloadableRecordings=groupedData,
    )

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

def getColonyList() -> list[str]:
    data = loadJson()
    colonySearchList: list[str] = [fileName.split(" - ")[0] for fileName in data]
    colonySearchList = sorted(set(colonySearchList))
    return colonySearchList


def getMonthsList() -> list[str]:
    data = loadJson()
    monthSearchList: list[str] = []
    for fileName in data:
        monthSearchList.extend(
            month for month in calendar.month_name[1:] if month in fileName
        )
    return set(monthSearchList)


def getDaysList() -> list[str]:
    data = loadJson()
    daySearchList: list[str] = []
    for fileName in data:
        daySearchList.extend(day for day in list(calendar.day_name) if day in fileName)
    return set(daySearchList)


def loadJson() -> dict:
    with open("static/download_links.json", "r") as f:
        data = json.load(f)
    return data

def groupDates(json_data):
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

def getDownloadLink(fileName: str) -> str:
    data = loadJson()
    try:
        return data[fileName]["downloadLink"]
    except KeyError:
        return None


# threading.Thread(target=downloadThread).start()
# app.run(host="10.0.0.217", port=5000, debug=False, threaded=True)
