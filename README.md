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

   - `POSTGRES_HOST`: The hostname or IP address of the PostgreSQL server.
   - `POSTGRES_PORT`: The port number of the PostgreSQL server.
   - `POSTGRES_DB`: The name of the PostgreSQL database.
   - `POSTGRES_USER`: The username to use when connecting to the PostgreSQL server.
   - `POSTGRES_PASSWORD`: The password to use when connecting to the PostgreSQL server.
   - `STATIC_RECORDINGS_PATH`: The path to the directory where the archived broadcasts are stored.
   - `RECORDINGS_STATUS_PATH`: The path to the file where the recording status is stored.
   - `SECRET_KEY`: A secret key used for session management.
   - `HBNI_STREAMING_PASSWORD`: The password used to access the HBNI Audio Streaming Service.

4. Run the application by executing the following command:

    ```bash
    python main.py
    ```

## Usage

To access the application, open your web browser and navigate to the URL where the application is running.

## Docker & Synology NAS

- Make sure you set port to 5053.
- Under Volume Settings you need to add a **folder**, you need to set it to this path: `/web/HBNI Audio Stream Recorder/static/Recordings` and call the mount point `/app/static/Recordings` (It should be the same as the `STATIC_RECORDINGS_PATH` environment variable).
- Under Volume Settings you need to add a **file**, you need to set it to this path: `/web/HBNI Audio Stream Recorder/static/recording_status.json` and call the mount point `/app/static/recording_status.json` (It should be the same as the `RECORDINGS_STATUS_PATH` environment variable).

## Contributing

Contributions are welcome! If you have any suggestions or improvements, please send an email.

## License

This project is licensed under the MIT License.
