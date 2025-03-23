import asyncio
import os
from urllib.parse import quote

import aiohttp
import asyncpg
from dotenv import load_dotenv

load_dotenv()

# Database settings
db_settings = {
    "host": os.getenv("POSTGRES_HOST"),
    "port": int(os.getenv("POSTGRES_PORT", 5434)),
    "database": os.getenv("POSTGRES_DB"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}

FILEBROWSER_URL = os.getenv("FILEBROWSER_URL")
FILEBROWSER_USERNAME = os.getenv("FILEBROWSER_USERNAME")
FILEBROWSER_PASSWORD = os.getenv("FILEBROWSER_PASSWORD")
FILEBROWSER_UPLOAD_PATH = os.getenv("FILEBROWSER_UPLOAD_PATH")


async def insert_data_to_db(
    pool, file_name, download_url, date, description, length, host, share_hash
):
    async with pool.acquire() as conn:
        query = """
        INSERT INTO audioarchives (filename, date, description, download_link, length, host, share_hash, visit_count, latest_visit)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9);
        """
        await conn.execute(
            query,
            file_name,
            date,
            description,
            download_url,
            length,
            host,
            share_hash,
            0,
            None,
        )


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
                raise Exception(
                    f"Failed to create share link: {response.status} - {body}"
                )
            data = await response.json()
            return data["hash"]


async def get_filebrowser_token():
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{FILEBROWSER_URL}/api/login",
            json={"username": FILEBROWSER_USERNAME, "password": FILEBROWSER_PASSWORD},
        ) as response:
            token = await response.text()
            return token.strip()


async def delete_existing_file(file_relative_path: str, token: str):
    async with aiohttp.ClientSession() as session:
        async with session.delete(
            f"{FILEBROWSER_URL}/api/resources/{file_relative_path}",
            headers={"X-Auth": token},
        ) as response:
            if response.status not in [200, 204, 404]:
                body = await response.text()
                raise Exception(
                    f"Failed to delete existing file: {response.status} - {body}"
                )


async def upload_to_filebrowser(file_path, file_name) -> str:
    token = await get_filebrowser_token()
    headers = {"X-Auth": token.strip(), "accept": "*/*"}
    file_relative_path = f"{FILEBROWSER_UPLOAD_PATH}/{file_name}"

    await delete_existing_file(file_relative_path, token)

    async with aiohttp.ClientSession() as session:
        with open(file_path, "rb") as f:
            form = aiohttp.FormData()
            form.add_field("files", f, filename=file_name, content_type="audio/mpeg")

            async with session.post(
                f"{FILEBROWSER_URL}/api/resources/{FILEBROWSER_UPLOAD_PATH}/{file_name}",
                headers=headers,
                data=form,
            ) as response:
                if response.status != 200:
                    body = await response.text()
                    raise Exception(f"Upload failed: {response.status} - {body}")

    share_url = await get_public_share_url(file_relative_path, token)
    return share_url


async def upload(
    file_name: str,
    file_path: str,
    host: str,
    description: str,
    date: str,
    length: float,
):
    sanitized_file_name = (
        file_name.replace("&amp;", "&")
        .replace("&Amp;", "&")
        .replace("&", "and")
        .replace("/", " or ")
    )

    try:
        share_hash = await upload_to_filebrowser(file_path, sanitized_file_name)
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {file_path}")
    except PermissionError:
        raise PermissionError(f"Permission denied for reading file: {file_path}")
    except Exception as e:
        raise RuntimeError(f"Unexpected error while uploading file: {str(e)}")

    pool = await asyncpg.create_pool(**db_settings)
    download_url = f"https://broadcasting.hbni.net/play_recording/{quote(file_name)}"
    await insert_data_to_db(
        pool, file_name, download_url, date, description, length, host, share_hash
    )
    await pool.close()


if __name__ == "__main__":
    asyncio.run(
        upload(
            "Glenwayprivate - Unspecified description - February 20 Thursday 2025 08_50 PM - 1h 36m 34s.mp3",
            "CURRENTLY_RECORDING/Glenwayprivate - Unspecified description - February 20 Thursday 2025 08_50 PM - 1h 36m 34s.mp3",
            "glenway",
            "Unspecified description",
            "February 20 Thursday 2025 08_50 PM",
            96.53333333333334,
        ),
        debug=True,
    )
