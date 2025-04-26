from pydub import AudioSegment


def get_audio_length(file_path: str) -> float:
    file_format = file_path.split(".")[-1]
    audio = AudioSegment.from_file(file_path, format=file_format)
    duration_minutes = len(audio) / (1000.0 * 60.0)  # milliseconds to minutes
    return duration_minutes
