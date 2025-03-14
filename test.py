import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

db_settings = {
    "host": f"{os.getenv('POSTGRES_HOST')}",
    "port": f"{os.getenv('POSTGRES_PORT')}",
    "database": f"{os.getenv('POSTGRES_DB')}",
    "user": f"{os.getenv('POSTGRES_USER')}",
    "password": f"{os.getenv('POSTGRES_PASSWORD')}",
}


try:
    # Connect to PostgreSQL database
    conn = psycopg2.connect(**db_settings)
    # Create a cursor object
    cursor = conn.cursor()

    # SQL query to update download_link column
    update_query = """
    UPDATE audioarchives
    SET download_link = REPLACE(download_link, 'audioarchives', 'broadcasting')
    WHERE download_link LIKE '%audioarchives%';
    """

    # Execute the update query
    cursor.execute(update_query)

    # Commit the changes
    conn.commit()

    print("Download links updated successfully.")

except Exception as e:
    print(f"Error: {e}")

finally:
    # Close cursor and connection
    if cursor:
        cursor.close()
    if conn:
        conn.close()
