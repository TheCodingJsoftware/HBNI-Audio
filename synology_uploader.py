import psycopg2
from urllib.parse import quote

website_url = "https://audioarchives.hbni.net"

db_settings = {
    'host': "10.0.0.10",
    'port': "5434",
    'database': "hbni",
    'user': "admin",
    'password': "Pine2admin"
}

def insert_data_to_db(file_name, download_url, date, description, length, host):
    conn = psycopg2.connect(**db_settings)
    cursor = conn.cursor()

    insert_query = '''
    INSERT INTO audioarchives (filename, date, description, download_link, length, host, visit_count, latest_visit)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
    '''

    cursor.execute(insert_query, (
        file_name,
        date,
        description,
        download_url,
        length,
        host,
        0,
        None,
    ))

    conn.commit()
    cursor.close()
    conn.close()

def upload(file_name: str, file_path: str, host: str, description: str, date: str, length: float):
    download_url = f"{website_url}/play_recording/{quote(file_name)}"

    insert_data_to_db(file_name, download_url, date, description, length, host)
