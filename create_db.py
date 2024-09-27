import psycopg2
import json
import os

from dotenv import load_dotenv

load_dotenv()

# Function to connect to the PostgreSQL database and create a table if it doesn't exist
def create_table_if_not_exists():
    # Connect to the PostgreSQL server
    conn = psycopg2.connect(
        host=os.environ.get('POSTGRES_HOST'),
        database=os.environ.get('POSTGRES_DB'),
        user=os.environ.get('POSTGRES_USER'),
        password=os.environ.get('POSTGRES_PASSWORD')
    )
    cursor = conn.cursor()

    # Create table if it does not exist
    create_table_query = '''
    CREATE TABLE IF NOT EXISTS audioarchives (
        id SERIAL PRIMARY KEY,
        filename TEXT NOT NULL,
        date TEXT,
        description TEXT,
        download_link TEXT,
        length FLOAT,
        host TEXT,
        click_count INTEGER,
        visit_count INTEGER,
        latest_visit TIMESTAMP,
        latest_click TIMESTAMP
    );
    '''
    cursor.execute(create_table_query)
    conn.commit()

    cursor.close()
    conn.close()

# Function to insert data into the database
def insert_data(filename, data):
    conn = psycopg2.connect(
        host="localhost",
        database="postgres",
        user="postgres",
        password="postgres"
    )
    cursor = conn.cursor()

    insert_query = '''
    INSERT INTO audioarchives (filename, date, description, download_link, length, host, click_count, visit_count, latest_visit, latest_click)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
    '''

    cursor.execute(insert_query, (
        filename,
        data.get('date'),
        data.get('description'),
        data['downloadLink'],
        float(data['length']),
        data.get('host'),
        data.get('click_count', 0),
        data.get('visit_count', 0),
        data.get('latest_visit'),
        data.get('latest_click')
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
    # Step 1: Ensure the table exists
    create_table_if_not_exists()

    # Step 2: Migrate data from JSON to PostgreSQL
    migrate_json_to_db('static/download_links.json')
