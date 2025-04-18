# HBNI Audio Archive

This is a web application that allows users to browse and listen to archived broadcasts from the HBNI Audio Streaming Service.

## Features

- Browse and listen to archived broadcasts from the HBNI Audio Streaming Service.
- Search for specific broadcasts by date, description, or host.
- View detailed information about each broadcast, including the date, description, host, length, and download links.
- Download individual broadcasts directly from the application.
- View the number of times each broadcast has been visited and downloaded.

## Installation

1. Clone the repository to your local machine.
2. Install the required Python packages by running the following command in the project directory:

    ```bash
    pip install -r requirements.txt
    ```

3. Set the following environment variables in your system's environment variables (or create a `.env` file in the project directory):

   - `PORT`: The port number to use for the application.
     - (Default: 5053)
   - `TZ`: The timezone to use for the application.
     - (Default: America/Guatemala)
   - `MAX_POSTGRES_WORKERS`: The maximum number of concurrent database connections.
     - (Default: 200)
   - `POSTGRES_USER`: The username to use when connecting to the PostgreSQL server.
     - (Default: admin)
   - `POSTGRES_PASSWORD`: The password to use when connecting to the PostgreSQL server.
   - `POSTGRES_DB`: The name of the PostgreSQL database.
     - (Default: hbni)
   - `POSTGRES_HOST`: The hostname or IP address of the PostgreSQL server.
     - (Default: 172.17.0.1)
   - `POSTGRES_PORT`: The port number of the PostgreSQL server.
     - (Default: 5434)
   - `STATIC_RECORDINGS_PATH`: The path to the directory where the archived broadcasts are stored.
     - (Default: /app/static/Recordings)
   - `RECORDINGS_STATUS_PATH`: The path to the file where the recording status is stored.
     - (Default: /app/static/recording_statis.json)
   - `ICECAST_BROADCASTING_IP`: The username used to access the HBNI Audio Streaming Service.
     - (Default: 172.17.0.1)
   - `ICECAST_BROADCASTING_PORT`: The port number used to access the HBNI Audio Streaming Service.
     - (Default: 8000)
   - `ICECAST_BROADCASTING_PASSWORD`: The password used to access the HBNI Audio Streaming Service.
   - `ICECAST_BROADCASTING_SOURCE`: The source name used for the broadcast.
     - (Default: broadcast.hbni.net)

4. Run the application by executing the following command:

    ```bash
    python main.py
    ```

## Usage

To access the application, open your web browser and navigate to the URL where the application is running.

## Docker & Synology NAS

- Make sure you set port to 5053.

## Contributing

Contributions are welcome! If you have any suggestions or improvements, please send an email.

## License

This project is licensed under the MIT License.
