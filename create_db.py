import psycopg2
import json
import os

from dotenv import load_dotenv

load_dotenv()

def create_table_if_not_exists():
    conn = psycopg2.connect(
        host=os.environ.get('POSTGRES_HOST'),
        port=os.environ.get('POSTGRES_PORT'),
        database=os.environ.get('POSTGRES_DB'),
        user=os.environ.get('POSTGRES_USER'),
        password=os.environ.get('POSTGRES_PASSWORD')
    )
    cursor = conn.cursor()

    create_table_query = '''
    CREATE TABLE IF NOT EXISTS audioarchives (
        id SERIAL PRIMARY KEY,
        filename TEXT NOT NULL,
        date TEXT,
        description TEXT,
        download_link TEXT,
        length FLOAT,
        host TEXT,
        visit_count INTEGER,
        latest_visit TIMESTAMP,
    );
    '''
    cursor.execute(create_table_query)
    conn.commit()

    cursor.close()
    conn.close()

# Function to insert data into the database
def insert_data(filename, data):
    conn = psycopg2.connect(
        host=os.environ.get('POSTGRES_HOST'),
        port=os.environ.get('POSTGRES_PORT'),
        database=os.environ.get('POSTGRES_DB'),
        user=os.environ.get('POSTGRES_USER'),
        password=os.environ.get('POSTGRES_PASSWORD')
    )
    cursor = conn.cursor()

    insert_query = '''
    INSERT INTO audioarchives (filename, date, description, download_link, length, host, visit_count, latest_visit)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
    '''

    cursor.execute(insert_query, (
        filename,
        data.get('date'),
        data.get('description'),
        data['downloadLink'],
        float(data['length']),
        data.get('host'),
        data.get('visit_count', 0),
        data.get('latest_visit'),
    ))

    conn.commit()
    cursor.close()
    conn.close()


def migrate_json_to_db(json_file_path):
    if not os.path.exists(json_file_path):
        print(f"File {json_file_path} does not exist.")
        return

    with open(json_file_path, 'r') as json_file:
        data = json.load(json_file)
        for filename, file_data in data.items():
            insert_data(filename, file_data)


if __name__ == "__main__":
    create_table_if_not_exists()
    migrate_json_to_db('static/download_links.json')
